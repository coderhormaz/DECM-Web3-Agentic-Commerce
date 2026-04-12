"""
Semantic Product Catalog for DECM.
Implements plan items 12-13: RDF/OWL product ontology as JSON-LD.

Architecture (paper Section 4.3):
  - JSON-LD based product ontology (lightweight alternative to Apache Jena)
  - Product categories, attributes, and provenance metadata
  - Linked Data compatible with Schema.org and GS1 vocabularies
  - IPFS-pinnable metadata structure
"""
import json
import hashlib
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path


# JSON-LD Context for DECM product ontology
DECM_CONTEXT = {
    "@context": {
        "@vocab": "https://decm.example/ontology/",
        "schema": "https://schema.org/",
        "gs1": "https://www.gs1.org/voc/",
        "decm": "https://decm.example/ns/v1/",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "name": "schema:name",
        "description": "schema:description",
        "price": {"@id": "schema:price", "@type": "xsd:decimal"},
        "currency": "schema:priceCurrency",
        "category": "schema:category",
        "seller": "schema:seller",
        "carbonFootprint": "decm:carbonFootprint",
        "sustainabilityScore": "decm:sustainabilityScore",
        "provenanceHash": "decm:provenanceHash",
        "tokenId": "decm:tokenId",
    }
}


@dataclass
class ProductMetadata:
    """JSON-LD compatible product metadata for DECM marketplace."""
    token_id: int
    name: str
    description: str = ""
    category: str = "digital_asset"
    base_price: float = 100.0
    currency: str = "USD"
    seller_did: str = ""
    carbon_footprint_gco2: float = 0.01
    sustainability_score: float = 0.85
    attributes: dict = field(default_factory=dict)
    created_at: str = ""
    provenance_hash: str = ""

    def to_jsonld(self) -> dict:
        """Convert to JSON-LD document."""
        return {
            **DECM_CONTEXT,
            "@type": "decm:DigitalAsset",
            "@id": f"decm:asset:{self.token_id}",
            "tokenId": self.token_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "price": self.base_price,
            "currency": self.currency,
            "seller": self.seller_did,
            "carbonFootprint": self.carbon_footprint_gco2,
            "sustainabilityScore": self.sustainability_score,
            "decm:attributes": self.attributes,
            "schema:dateCreated": self.created_at,
            "provenanceHash": self.provenance_hash,
        }

    def compute_ipfs_hash(self) -> str:
        """Compute content hash (simulates IPFS CID)."""
        content = json.dumps(self.to_jsonld(), sort_keys=True)
        return f"Qm{hashlib.sha256(content.encode()).hexdigest()[:44]}"


class SemanticCatalog:
    """
    Semantic product catalog using JSON-LD ontology.
    Provides product discovery, categorization, and provenance tracking.
    """

    # Product categories matching paper's digital commerce taxonomy
    CATEGORIES = [
        "digital_asset", "software_license", "nft_artwork",
        "data_service", "cloud_compute", "api_access",
        "digital_media", "smart_contract_template", "defi_instrument",
        "iot_data_feed",
    ]

    def __init__(self):
        self.products: Dict[int, ProductMetadata] = {}
        self.category_index: Dict[str, List[int]] = {c: [] for c in self.CATEGORIES}

    def register_product(self, token_id: int, name: str = None,
                         category: str = None, base_price: float = 100.0,
                         seller_did: str = "") -> ProductMetadata:
        """Register a new product in the semantic catalog."""
        if name is None:
            name = f"DECM Asset #{token_id}"
        if category is None:
            category = self.CATEGORIES[token_id % len(self.CATEGORIES)]

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        product = ProductMetadata(
            token_id=token_id,
            name=name,
            description=f"Tokenized digital asset registered on DECM marketplace",
            category=category,
            base_price=base_price,
            currency="USD",
            seller_did=seller_did,
            carbon_footprint_gco2=0.008 + (token_id % 10) * 0.001,
            sustainability_score=0.80 + (token_id % 20) * 0.01,
            attributes={
                "version": "1.0",
                "standard": "ERC-1155",
                "chain": "monad-testnet",
            },
            created_at=now,
        )

        product.provenance_hash = product.compute_ipfs_hash()
        self.products[token_id] = product
        self.category_index[category].append(token_id)

        return product

    def register_batch(self, count: int, base_price_range=(50, 200)) -> List[ProductMetadata]:
        """Batch-register products for simulation."""
        import numpy as np
        products = []
        for i in range(count):
            price = np.random.uniform(*base_price_range)
            product = self.register_product(
                token_id=i,
                base_price=round(price, 2),
                seller_did=f"did:decm:seller:{i % 100}",
            )
            products.append(product)
        return products

    def query_by_category(self, category: str) -> List[ProductMetadata]:
        """SPARQL-like query by category."""
        token_ids = self.category_index.get(category, [])
        return [self.products[tid] for tid in token_ids if tid in self.products]

    def query_by_price_range(self, min_price: float, max_price: float) -> List[ProductMetadata]:
        """Query products within price range."""
        return [p for p in self.products.values()
                if min_price <= p.base_price <= max_price]

    def get_product(self, token_id: int) -> Optional[ProductMetadata]:
        """Get product by token ID."""
        return self.products.get(token_id)

    def export_catalog(self, path: str):
        """Export full catalog as JSON-LD document."""
        catalog = {
            **DECM_CONTEXT,
            "@type": "decm:ProductCatalog",
            "schema:dateModified": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "decm:totalProducts": len(self.products),
            "decm:categories": list(self.category_index.keys()),
            "decm:products": [p.to_jsonld() for p in self.products.values()],
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(catalog, f, indent=2)

    def summary(self) -> dict:
        """Catalog summary statistics."""
        import numpy as np
        prices = [p.base_price for p in self.products.values()]
        return {
            "total_products": len(self.products),
            "categories_used": sum(1 for ids in self.category_index.values() if ids),
            "avg_price": float(np.mean(prices)) if prices else 0,
            "price_range": (float(min(prices)), float(max(prices))) if prices else (0, 0),
            "avg_sustainability": float(np.mean([p.sustainability_score for p in self.products.values()])) if self.products else 0,
        }
