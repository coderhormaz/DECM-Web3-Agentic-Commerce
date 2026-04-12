"""
DECM Simulation Configuration
Monad Testnet parameters and paper-reference values.
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Network ---
MONAD_RPC = os.getenv("MONAD_TESTNET_RPC", "https://testnet-rpc.monad.xyz")
CHAIN_ID = int(os.getenv("CHAIN_ID", "10143"))
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")

# --- LLM ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# --- Simulation Parameters (from paper Section 3.4) ---
TRANSACTIONS_PER_PHASE = 10_000
MONTE_CARLO_RUNS = 30
NUM_BUYERS = 100
NUM_SELLERS = 100
DEMAND_SHOCK_INTERVAL = 500       # every 500 tx
DEMAND_SHOCK_MAGNITUDE = 0.40     # ±40%

# --- Monad-specific ---
MONAD_BLOCK_TIME_MS = 400
MONAD_FINALITY_MS = 800

# --- Paper Baseline Values (Web 2.0 phase, Table 7) ---
BASELINE = {
    "latency_s":         {"mean": 2.81, "std": 0.45},
    "cost_usd":          {"mean": 0.042, "std": 0.007},
    "cpu_cycles_m":      {"mean": 8.4, "std": 1.1},
    "memory_mb":         {"mean": 142, "std": 18},
    "verification_s":    {"mean": 11.2, "std": 1.8},
    "dispute_rate_pct":  {"mean": 3.8, "std": 0.5},
    "price_deviation":   {"mean": 0.27, "std": 0.06},
    "negotiation_rounds":{"mean": 5.8, "std": 1.2},
    "energy_wh":         {"mean": 0.58, "std": 0.07},
    "carbon_gco2":       {"mean": 0.24, "std": 0.03},
}

# --- AHP Weights (Section 3.5, 12 expert raters, α=0.91) ---
AHP_WEIGHTS = {
    "transactional": 0.30,
    "computational": 0.15,
    "governance":    0.20,
    "cognitive":     0.15,
    "environmental": 0.20,
}

# --- Paths ---
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = DATA_DIR / "results"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def load_contract_abi(name: str) -> list:
    """Load compiled ABI from Hardhat artifacts."""
    artifact_path = ARTIFACTS_DIR / "contracts" / f"{name}.sol" / f"{name}.json"
    if not artifact_path.exists():
        raise FileNotFoundError(f"Artifact not found: {artifact_path}")
    with open(artifact_path) as f:
        return json.load(f)["abi"]


def load_deployed_addresses() -> dict:
    """Load deployed contract addresses."""
    addr_path = DATA_DIR / "deployed_addresses.json"
    if not addr_path.exists():
        raise FileNotFoundError(f"Deploy first: {addr_path}")
    with open(addr_path) as f:
        return json.load(f)
