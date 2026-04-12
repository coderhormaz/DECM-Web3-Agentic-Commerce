"""
Generate deterministic seed data for DECM simulation.
Creates 10,000 transaction seeds for reproducible Monte Carlo runs.
"""
import csv
import hashlib
import numpy as np
from pathlib import Path


def generate_seeds(n: int = 10000, base_seed: int = 42) -> list:
    """Generate n deterministic transaction seeds."""
    rng = np.random.RandomState(base_seed)
    seeds = []

    for i in range(n):
        seed = {
            "tx_index": i,
            "seed": int(rng.randint(0, 2**31)),
            "buyer_id": int(rng.randint(0, 100)),
            "seller_id": int(rng.randint(0, 100)),
            "token_id": int(rng.randint(0, 50)),
            "base_price": int(rng.uniform(10, 1000)),
            "amount": max(1, int(rng.normal(10, 5))),
            "demand_shock": _demand_shock(i, rng),
        }
        # Ensure buyer != seller
        while seed["buyer_id"] == seed["seller_id"]:
            seed["seller_id"] = int(rng.randint(0, 100))
        seeds.append(seed)

    return seeds


def _demand_shock(tx_index: int, rng) -> float:
    """
    Inject demand shocks every 500 transactions (±40%).
    Paper Section 3.4: "After every 500 transactions, there is a demand shock."
    """
    if tx_index > 0 and tx_index % 500 == 0:
        # Random shock between -40% and +40%
        return 1.0 + rng.uniform(-0.40, 0.40)
    return 1.0


def save_seeds(seeds: list, filepath: str):
    """Save seeds to CSV."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=seeds[0].keys())
        writer.writeheader()
        writer.writerows(seeds)


def load_seeds(filepath: str) -> list:
    """Load seeds from CSV."""
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        seeds = []
        for row in reader:
            seeds.append({
                "tx_index": int(row["tx_index"]),
                "seed": int(row["seed"]),
                "buyer_id": int(row["buyer_id"]),
                "seller_id": int(row["seller_id"]),
                "token_id": int(row["token_id"]),
                "base_price": int(row["base_price"]),
                "amount": int(row["amount"]),
                "demand_shock": float(row["demand_shock"]),
            })
        return seeds


if __name__ == "__main__":
    seeds = generate_seeds(10000, base_seed=42)
    out = Path(__file__).parent.parent / "data" / "seeds.csv"
    save_seeds(seeds, str(out))
    print(f"Generated {len(seeds)} seeds → {out}")

    # Verify
    loaded = load_seeds(str(out))
    assert len(loaded) == 10000
    assert loaded[0]["tx_index"] == 0
    print("Verification passed.")
