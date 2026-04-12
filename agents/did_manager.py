"""
W3C DID (Decentralized Identifier) Manager for DECM.
Implements plan items 11-14: DID creation, resolution, and on-chain anchoring.

Architecture (paper Section 4.3, Layer 2):
  - W3C DID Method: did:decm:<role>:<id>
  - DID Documents contain public key, service endpoints, trust metadata
  - DID hashes are anchored on-chain via DECMIdentity.sol
  - Supports batch operations for 200-agent simulations
"""
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from pathlib import Path


@dataclass
class DIDDocument:
    """W3C DID Document (simplified, spec-compliant structure)."""
    id: str                          # did:decm:buyer:42
    controller: str = ""             # DID of controlling entity
    authentication: list = field(default_factory=list)
    verification_method: list = field(default_factory=list)
    service: list = field(default_factory=list)
    created: str = ""
    updated: str = ""
    # DECM-specific
    trust_level: int = 5000          # 0-10000 bps
    role: str = ""                   # buyer / seller
    wallet_address: str = ""
    reputation_score: float = 0.5

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_dict(self) -> dict:
        return {
            "@context": [
                "https://www.w3.org/ns/did/v1",
                "https://decm.example/ns/v1"
            ],
            "id": self.id,
            "controller": self.controller or self.id,
            "authentication": self.authentication,
            "verificationMethod": self.verification_method,
            "service": self.service,
            "created": self.created,
            "updated": self.updated,
            "decm:trustLevel": self.trust_level,
            "decm:role": self.role,
            "decm:wallet": self.wallet_address,
            "decm:reputation": self.reputation_score,
        }

    def hash(self) -> str:
        """Compute keccak256-style hash for on-chain anchoring."""
        content = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()


class DIDManager:
    """
    Manages W3C DIDs for all DECM agents.
    Replaces Veramo SDK with lightweight Python implementation.
    """

    def __init__(self):
        self.registry: Dict[str, DIDDocument] = {}
        self.resolution_cache: Dict[str, dict] = {}

    def create_did(self, role: str, agent_id: int, wallet_address: str,
                   public_key_hex: str = None) -> DIDDocument:
        """
        Create a new DID for an agent.
        Format: did:decm:<role>:<agent_id>
        """
        did_id = f"did:decm:{role}:{agent_id}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        if public_key_hex is None:
            public_key_hex = hashlib.sha256(f"{did_id}:{wallet_address}".encode()).hexdigest()

        doc = DIDDocument(
            id=did_id,
            controller=did_id,
            authentication=[f"{did_id}#keys-1"],
            verification_method=[{
                "id": f"{did_id}#keys-1",
                "type": "EcdsaSecp256k1VerificationKey2019",
                "controller": did_id,
                "publicKeyHex": public_key_hex,
            }],
            service=[
                {
                    "id": f"{did_id}#decm-marketplace",
                    "type": "DECMMarketplace",
                    "serviceEndpoint": "https://decm.example/api/v1",
                },
                {
                    "id": f"{did_id}#semantic-catalog",
                    "type": "LinkedDataCatalog",
                    "serviceEndpoint": "https://decm.example/catalog",
                },
            ],
            created=now,
            updated=now,
            trust_level=5000,
            role=role,
            wallet_address=wallet_address,
            reputation_score=0.5,
        )

        self.registry[did_id] = doc
        return doc

    def create_batch(self, role: str, count: int) -> List[DIDDocument]:
        """Batch-create DIDs for simulation agents."""
        docs = []
        for i in range(count):
            wallet = f"0x{'B' if role == 'buyer' else '5' * 4}{i:036x}"
            doc = self.create_did(role, i, wallet)
            docs.append(doc)
        return docs

    def resolve(self, did_id: str) -> Optional[DIDDocument]:
        """Resolve a DID to its document."""
        return self.registry.get(did_id)

    def update_trust(self, did_id: str, new_trust: int):
        """Update trust level for a DID (0-10000 bps)."""
        doc = self.registry.get(did_id)
        if doc:
            doc.trust_level = max(0, min(10000, new_trust))
            doc.updated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def update_reputation(self, did_id: str, delta: float):
        """Update reputation score based on transaction outcomes."""
        doc = self.registry.get(did_id)
        if doc:
            doc.reputation_score = max(0.0, min(1.0, doc.reputation_score + delta))

    def deactivate(self, did_id: str) -> bool:
        """Deactivate a DID (agent dropout)."""
        if did_id in self.registry:
            del self.registry[did_id]
            return True
        return False

    def get_all_hashes(self) -> Dict[str, str]:
        """Get DID hashes for on-chain anchoring via DECMIdentity.sol."""
        return {did_id: doc.hash() for did_id, doc in self.registry.items()}

    def export_registry(self, path: str):
        """Export full DID registry to JSON file."""
        data = {
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_dids": len(self.registry),
            "dids": {did_id: doc.to_dict() for did_id, doc in self.registry.items()},
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def summary(self) -> dict:
        """Summary statistics of the DID registry."""
        buyers = [d for d in self.registry.values() if d.role == "buyer"]
        sellers = [d for d in self.registry.values() if d.role == "seller"]
        return {
            "total_dids": len(self.registry),
            "buyers": len(buyers),
            "sellers": len(sellers),
            "avg_trust": sum(d.trust_level for d in self.registry.values()) / max(len(self.registry), 1),
            "avg_reputation": sum(d.reputation_score for d in self.registry.values()) / max(len(self.registry), 1),
        }
