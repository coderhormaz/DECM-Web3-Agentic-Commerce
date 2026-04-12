"""
Robustness Tests for DECM Simulation.
Implements plan item 29: ±300% latency spikes, agent drops, demand shocks.

Tests how DECM maintains superiority over baseline under stress conditions.
"""
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.config import RESULTS_DIR, TRANSACTIONS_PER_PHASE
from scripts.simulate import SimulationRunner
from scripts.metrics import MetricsCollector


class RobustnessTest:
    """
    Run stress-test scenarios to validate DECM performance under adversity.
    """

    SCENARIOS = {
        "latency_spike_300pct": {
            "description": "±300% latency spikes injected every 200 tx",
            "latency_multiplier_range": (1.0, 4.0),
            "spike_interval": 200,
            "spike_duration": 50,
        },
        "agent_dropout_20pct": {
            "description": "20% of agents randomly drop out mid-simulation",
            "dropout_rate": 0.20,
            "dropout_after_tx": 2000,
        },
        "agent_dropout_50pct": {
            "description": "50% of agents randomly drop out mid-simulation",
            "dropout_rate": 0.50,
            "dropout_after_tx": 2000,
        },
        "demand_extreme": {
            "description": "Extreme demand shocks: ±80% every 250 tx",
            "shock_magnitude": 0.80,
            "shock_interval": 250,
        },
        "combined_stress": {
            "description": "Combined: 300% latency + 20% dropout + extreme demand",
            "latency_multiplier_range": (1.0, 4.0),
            "spike_interval": 200,
            "spike_duration": 50,
            "dropout_rate": 0.20,
            "dropout_after_tx": 2000,
            "shock_magnitude": 0.80,
            "shock_interval": 250,
        },
    }

    def __init__(self, run_id: int = 0, n_tx: int = 2000):
        """
        Args:
            run_id: Run identifier
            n_tx: Transactions per scenario (fewer than full 10K for speed)
        """
        self.run_id = run_id
        self.n_tx = n_tx
        self.results: Dict[str, dict] = {}

    def run_all(self) -> Dict[str, dict]:
        """Run all robustness scenarios."""
        print(f"\n{'='*60}")
        print(f"ROBUSTNESS TESTS — Run {self.run_id}")
        print(f"{'='*60}")

        for scenario_name, config in self.SCENARIOS.items():
            print(f"\n--- Scenario: {scenario_name} ---")
            print(f"  {config['description']}")

            result = self._run_scenario(scenario_name, config)
            self.results[scenario_name] = result

            print(f"  DECM latency: {result['decm']['latency_s']:.3f}s")
            print(f"  Baseline latency: {result['baseline']['latency_s']:.3f}s")
            print(f"  DECM still better: {result['decm_superior']}")

        return self.results

    def _run_scenario(self, name: str, config: dict) -> dict:
        """Run a single robustness scenario."""
        seed_file = str(Path(__file__).parent.parent / "data" / "seeds.csv")

        runner = SimulationRunner(
            run_id=self.run_id + 900,  # offset to avoid overwriting
            seed_file=seed_file,
            use_chain=False,
            use_llm=False,
        )

        # Limit transactions for robustness tests
        runner.seeds = runner.seeds[:self.n_tx]

        # Run baseline (unaffected)
        baseline_collector = runner.run_phase1_baseline()
        baseline_summary = baseline_collector.summary()

        # Run DECM with stress injected
        decm_collector = self._run_stressed_decm(runner, name, config)
        decm_summary = decm_collector.summary()

        # Check if DECM still outperforms
        metrics_to_check = ["latency_s", "cost_usd", "carbon_gco2",
                            "verification_s", "negotiation_rounds"]

        decm_wins = 0
        total_checks = 0
        comparisons = {}

        for m in metrics_to_check:
            if m in baseline_summary and m in decm_summary:
                b_val = baseline_summary[m]["mean"]
                d_val = decm_summary[m]["mean"]
                improvement = ((b_val - d_val) / b_val * 100) if b_val > 0 else 0
                decm_better = d_val < b_val
                comparisons[m] = {
                    "baseline": b_val,
                    "decm_stressed": d_val,
                    "improvement_pct": improvement,
                    "decm_better": decm_better,
                }
                if decm_better:
                    decm_wins += 1
                total_checks += 1

        return {
            "scenario": name,
            "config": config,
            "n_tx": self.n_tx,
            "baseline": {
                "latency_s": baseline_summary["latency_s"]["mean"],
                "cost_usd": baseline_summary["cost_usd"]["mean"],
                "carbon_gco2": baseline_summary["carbon_gco2"]["mean"],
            },
            "decm": {
                "latency_s": decm_summary["latency_s"]["mean"],
                "cost_usd": decm_summary["cost_usd"]["mean"],
                "carbon_gco2": decm_summary["carbon_gco2"]["mean"],
            },
            "comparisons": comparisons,
            "decm_wins": decm_wins,
            "total_checks": total_checks,
            "decm_superior": decm_wins > total_checks / 2,
        }

    def _run_stressed_decm(self, runner: SimulationRunner,
                           scenario_name: str, config: dict) -> MetricsCollector:
        """Run DECM phase with stress conditions injected."""
        runner._init_agents(100, 100)
        collector = MetricsCollector(f"robustness_{scenario_name}", runner.run_id)

        # Apply dropout if configured
        dropout_rate = config.get("dropout_rate", 0)
        dropout_after = config.get("dropout_after_tx", 9999999)

        # Latency spike params
        spike_interval = config.get("spike_interval", 9999999)
        spike_duration = config.get("spike_duration", 0)
        latency_range = config.get("latency_multiplier_range", (1.0, 1.0))

        # Demand shock params
        shock_magnitude = config.get("shock_magnitude", 0.40)
        shock_interval = config.get("shock_interval", 500)

        active_buyers = list(runner.buyers)
        active_sellers = list(runner.sellers)

        for i, seed_data in enumerate(runner.seeds):
            # --- Stress injections ---

            # Agent dropout
            if i == dropout_after and dropout_rate > 0:
                n_drop_b = int(len(active_buyers) * dropout_rate)
                n_drop_s = int(len(active_sellers) * dropout_rate)
                rng = np.random.RandomState(i + runner.run_id)
                rng.shuffle(active_buyers)
                rng.shuffle(active_sellers)
                active_buyers = active_buyers[n_drop_b:]
                active_sellers = active_sellers[n_drop_s:]
                print(f"  Agent dropout at tx {i}: {n_drop_b} buyers, {n_drop_s} sellers removed")

            # Demand shock
            if i > 0 and i % shock_interval == 0:
                shock = 1.0 + np.random.uniform(-shock_magnitude, shock_magnitude)
                runner.demand_level = max(0.2, shock)

            # Select agents from active pool
            buyer = active_buyers[seed_data["buyer_id"] % len(active_buyers)]
            seller = active_sellers[seed_data["seller_id"] % len(active_sellers)]

            market_state = {
                "prices": runner.market_prices[-10:],
                "avg_latency": runner.avg_latency,
                "avg_carbon": runner.avg_carbon,
                "demand_level": runner.demand_level,
            }

            perception = buyer.perceive(market_state)
            decision = buyer.reason(perception)
            buyer.act(decision)

            seller_perception = seller.perceive(market_state)
            seller_decision = seller.reason(seller_perception)
            negotiation_rounds = max(1, abs(
                decision["target_price"] - seller_decision["target_price"]
            ) // 50 + 1)

            collector.start_transaction()
            price = int(seed_data["base_price"] * runner.demand_level)

            eval_data = {
                "deal_id": i, "price": price,
                "market_avg_price": np.mean(runner.market_prices[-10:]),
                "buyer_did": buyer.did_hash, "seller_did": seller.did_hash,
                "carbon_estimate": runner.avg_carbon,
                "demand_level": runner.demand_level,
            }
            approved, adjusted_price, confidence = runner.evaluator.evaluate(eval_data)

            chain_data = runner._execute_on_chain_or_simulate(
                i, buyer, seller, seed_data, adjusted_price, approved, confidence
            )

            # Apply latency spike
            in_spike = (i % spike_interval) < spike_duration
            if in_spike:
                spike_mult = np.random.uniform(*latency_range)
                chain_data["latency"] *= spike_mult
                chain_data["verification_s"] *= spike_mult

            agent_data = {
                "negotiation_rounds": min(negotiation_rounds, 8),
                "demand_level": runner.demand_level,
                "confidence": confidence,
            }

            collector.end_transaction(i, chain_data, agent_data)

            runner.market_prices.append(adjusted_price)
            if len(runner.market_prices) > 100:
                runner.market_prices = runner.market_prices[-100:]

            if collector.records:
                recent = collector.records[-min(100, len(collector.records)):]
                runner.avg_latency = np.mean([r.latency_s for r in recent])
                runner.avg_carbon = np.mean([r.carbon_gco2 for r in recent])

        return collector

    def save_results(self):
        """Save robustness test results."""
        out_dir = RESULTS_DIR / "robustness"
        out_dir.mkdir(parents=True, exist_ok=True)

        with open(out_dir / "robustness_results.json", "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        # Generate summary table
        rows = []
        for name, result in self.results.items():
            rows.append({
                "Scenario": name,
                "Description": result["config"].get("description", ""),
                "DECM Latency (s)": f"{result['decm']['latency_s']:.3f}",
                "Baseline Latency (s)": f"{result['baseline']['latency_s']:.3f}",
                "DECM Cost ($)": f"{result['decm']['cost_usd']:.4f}",
                "Baseline Cost ($)": f"{result['baseline']['cost_usd']:.4f}",
                "Metrics Won": f"{result['decm_wins']}/{result['total_checks']}",
                "DECM Superior": result["decm_superior"],
            })

        df = pd.DataFrame(rows)
        df.to_csv(out_dir / "robustness_table.csv", index=False)
        print(f"\nRobustness results saved to {out_dir}")

        return df


def run_robustness_tests(run_id: int = 0, n_tx: int = 2000):
    """Entry point for robustness testing."""
    tester = RobustnessTest(run_id=run_id, n_tx=n_tx)
    tester.run_all()
    table = tester.save_results()
    print("\n" + table.to_string(index=False))
    return tester.results


if __name__ == "__main__":
    run_robustness_tests()
