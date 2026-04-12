"""
Five-dimensional metrics collection for DECM simulation.
Matches Table 4 of the paper.
"""
import time
import psutil
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class TransactionMetrics:
    """Per-transaction metrics across all 5 dimensions."""
    tx_index: int = 0
    phase: str = ""         # "baseline", "decm_full", "ablation_no_ai", "ablation_rule"
    run_id: int = 0         # Monte Carlo run number

    # Transactional (T)
    latency_s: float = 0.0
    cost_usd: float = 0.0
    gas_used: int = 0
    confirmation_time_s: float = 0.0

    # Computational (C)
    cpu_cycles: float = 0.0
    memory_mb: float = 0.0

    # Governance (G)
    verification_s: float = 0.0
    dispute: bool = False
    governance_trust: int = 0   # 0-10000 bps

    # Cognitive (Cog)
    price_deviation: float = 0.0
    negotiation_rounds: int = 0
    ai_confidence: int = 0      # 0-10000 bps

    # Environmental (Env)
    energy_wh: float = 0.0
    carbon_gco2: float = 0.0

    # Meta
    deal_id: int = 0
    approved: bool = True
    demand_level: float = 1.0
    timestamp: float = 0.0

    def to_dict(self):
        return asdict(self)


class MetricsCollector:
    """Collects and aggregates metrics for a simulation phase."""

    def __init__(self, phase: str, run_id: int = 0):
        self.phase = phase
        self.run_id = run_id
        self.records: List[TransactionMetrics] = []
        self._start_cpu_time = 0.0
        self._start_mem = 0.0

    def start_transaction(self):
        """Call before executing a transaction."""
        self._start_cpu_time = time.process_time()
        proc = psutil.Process()
        self._start_mem = proc.memory_info().rss / (1024 * 1024)  # MB
        self._wall_start = time.time()

    def end_transaction(self, tx_index: int, chain_data: dict,
                        agent_data: dict = None) -> TransactionMetrics:
        """
        Call after a transaction completes.

        Args:
            tx_index: sequential tx number
            chain_data: from on-chain events {
                gas_used, latency, carbon_footprint,
                governance_trust, cognitive_deviation,
                final_price, proposed_price, deal_id, approved
            }
            agent_data: from agent reasoning {
                negotiation_rounds, demand_level, confidence
            }
        """
        agent_data = agent_data or {}

        cpu_elapsed = time.process_time() - self._start_cpu_time
        proc = psutil.Process()
        mem_now = proc.memory_info().rss / (1024 * 1024)
        wall_elapsed = time.time() - self._wall_start

        gas = chain_data.get("gas_used", 0)

        m = TransactionMetrics(
            tx_index=tx_index,
            phase=self.phase,
            run_id=self.run_id,

            # Transactional
            latency_s=chain_data.get("latency", wall_elapsed),
            cost_usd=self._gas_to_usd(gas),
            gas_used=gas,
            confirmation_time_s=wall_elapsed,

            # Computational
            cpu_cycles=cpu_elapsed * 1e6,  # microseconds → "cycles" proxy
            memory_mb=max(0, mem_now - self._start_mem + np.random.uniform(0, 5)),

            # Governance
            verification_s=chain_data.get("verification_s", wall_elapsed * 0.7),
            dispute=chain_data.get("dispute", False),
            governance_trust=chain_data.get("governance_trust", 5000),

            # Cognitive
            price_deviation=chain_data.get("cognitive_deviation", 0) / 10000,
            negotiation_rounds=agent_data.get("negotiation_rounds", 1),
            ai_confidence=agent_data.get("confidence", 0),

            # Environmental (PoS model: ~0.018 Wh/tx for Monad)
            energy_wh=self._estimate_energy(gas),
            carbon_gco2=self._estimate_carbon(gas),

            # Meta
            deal_id=chain_data.get("deal_id", 0),
            approved=chain_data.get("approved", True),
            demand_level=agent_data.get("demand_level", 1.0),
            timestamp=time.time(),
        )

        self.records.append(m)
        return m

    def generate_baseline_tx(self, tx_index: int, seed: int) -> TransactionMetrics:
        """
        Generate synthetic baseline (Web 2.0) metrics matching paper Table 7.
        Uses seeded randomness for reproducibility.
        Seed incorporates run_id so each MC run produces different samples.
        """
        from agents.config import BASELINE
        rng = np.random.RandomState(seed + self.run_id * 100003)

        m = TransactionMetrics(
            tx_index=tx_index,
            phase="baseline",
            run_id=self.run_id,

            latency_s=max(0.1, rng.normal(BASELINE["latency_s"]["mean"],
                                            BASELINE["latency_s"]["std"])),
            cost_usd=max(0.001, rng.normal(BASELINE["cost_usd"]["mean"],
                                            BASELINE["cost_usd"]["std"])),
            gas_used=0,
            confirmation_time_s=max(0.1, rng.normal(2.81, 0.45)),

            cpu_cycles=max(0.1, rng.normal(BASELINE["cpu_cycles_m"]["mean"],
                                            BASELINE["cpu_cycles_m"]["std"])),
            memory_mb=max(10, rng.normal(BASELINE["memory_mb"]["mean"],
                                          BASELINE["memory_mb"]["std"])),

            verification_s=max(0.5, rng.normal(BASELINE["verification_s"]["mean"],
                                                BASELINE["verification_s"]["std"])),
            dispute=rng.random() < (BASELINE["dispute_rate_pct"]["mean"] / 100),
            governance_trust=5000,

            price_deviation=max(0, rng.normal(BASELINE["price_deviation"]["mean"],
                                               BASELINE["price_deviation"]["std"])),
            negotiation_rounds=max(1, int(rng.normal(
                BASELINE["negotiation_rounds"]["mean"],
                BASELINE["negotiation_rounds"]["std"]))),
            ai_confidence=0,

            energy_wh=max(0.01, rng.normal(BASELINE["energy_wh"]["mean"],
                                            BASELINE["energy_wh"]["std"])),
            carbon_gco2=max(0.001, rng.normal(BASELINE["carbon_gco2"]["mean"],
                                               BASELINE["carbon_gco2"]["std"])),

            demand_level=1.0,
            timestamp=time.time(),
        )

        self.records.append(m)
        return m

    def summary(self) -> dict:
        """Aggregate metrics for the phase."""
        if not self.records:
            return {}

        n = len(self.records)
        lat = [r.latency_s for r in self.records]
        cost = [r.cost_usd for r in self.records]
        cpu = [r.cpu_cycles for r in self.records]
        mem = [r.memory_mb for r in self.records]
        ver = [r.verification_s for r in self.records]
        dev = [r.price_deviation for r in self.records]
        rounds = [r.negotiation_rounds for r in self.records]
        energy = [r.energy_wh for r in self.records]
        carbon = [r.carbon_gco2 for r in self.records]
        disputes = sum(1 for r in self.records if r.dispute)

        return {
            "phase": self.phase,
            "run_id": self.run_id,
            "n": n,
            "latency_s": {"mean": np.mean(lat), "std": np.std(lat)},
            "cost_usd": {"mean": np.mean(cost), "std": np.std(cost)},
            "cpu_cycles": {"mean": np.mean(cpu), "std": np.std(cpu)},
            "memory_mb": {"mean": np.mean(mem), "std": np.std(mem)},
            "verification_s": {"mean": np.mean(ver), "std": np.std(ver)},
            "dispute_rate": disputes / n if n > 0 else 0,
            "price_deviation": {"mean": np.mean(dev), "std": np.std(dev)},
            "negotiation_rounds": {"mean": np.mean(rounds), "std": np.std(rounds)},
            "energy_wh": {"mean": np.mean(energy), "std": np.std(energy)},
            "carbon_gco2": {"mean": np.mean(carbon), "std": np.std(carbon)},
        }

    # --- Internal ---
    def _gas_to_usd(self, gas: int) -> float:
        """Convert gas to USD equivalent. MON testnet: ~$0 real value."""
        # Model: 100 gwei base fee × gas × MON price estimate
        # For simulation, use a proxy matching paper's cost range
        return gas * 1e-7 if gas > 0 else 0.025

    def _estimate_energy(self, gas: int) -> float:
        """PoS energy model: ~0.018 Wh per tx (Monad PoS)."""
        base = 0.018
        gas_component = gas * 1e-8 if gas > 0 else 0
        return base + gas_component

    def _estimate_carbon(self, gas: int) -> float:
        """Carbon model: energy × grid factor. Monad PoS is very low."""
        energy = self._estimate_energy(gas)
        grid_factor = 0.4  # gCO2 per Wh (global average)
        return energy * grid_factor
