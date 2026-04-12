"""
Monte Carlo simulation wrapper.
Runs N replications of the 3-phase protocol and aggregates results.
Paper uses 30 runs × 10,000 tx = 300K per phase, 900K total.
"""
import json
import time
import numpy as np
import pandas as pd
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.config import MONTE_CARLO_RUNS as NUM_MONTE_CARLO_RUNS, RESULTS_DIR
from scripts.simulate import run_single


def run_monte_carlo(n_runs: int = None, use_chain: bool = False,
                    use_llm: bool = False, max_workers: int = 1):
    """
    Execute N Monte Carlo replications of the full simulation.

    Args:
        n_runs: Number of runs (default from config)
        use_chain: Use Monad testnet (requires funded wallet)
        use_llm: Use Ollama LLM for agent reasoning
        max_workers: Parallelism (1 for sequential, >1 for parallel)
    """
    if n_runs is None:
        n_runs = NUM_MONTE_CARLO_RUNS

    print(f"Starting Monte Carlo simulation: {n_runs} runs")
    print(f"  Chain: {'Monad testnet' if use_chain else 'simulated'}")
    print(f"  LLM:   {'Ollama' if use_llm else 'heuristic'}")
    print(f"{'='*60}")

    all_results = []
    start_time = time.time()

    if max_workers == 1:
        # Sequential execution
        for run_id in range(n_runs):
            print(f"\n{'#'*60}")
            print(f"# Monte Carlo Run {run_id + 1}/{n_runs}")
            print(f"{'#'*60}")

            result = run_single(run_id, use_chain, use_llm)
            all_results.append(result)

            elapsed = time.time() - start_time
            per_run = elapsed / (run_id + 1)
            remaining = per_run * (n_runs - run_id - 1)
            print(f"\n  Elapsed: {elapsed:.0f}s | "
                  f"Avg: {per_run:.1f}s/run | "
                  f"ETA: {remaining:.0f}s")
    else:
        # Parallel execution (use with caution on chain)
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(run_single, run_id, use_chain, use_llm): run_id
                for run_id in range(n_runs)
            }
            for future in as_completed(futures):
                run_id = futures[future]
                try:
                    result = future.result()
                    all_results.append(result)
                    print(f"  Completed run {run_id + 1}/{n_runs}")
                except Exception as e:
                    print(f"  ERROR in run {run_id}: {e}")
                    all_results.append(None)

    # Aggregate results
    aggregate = _aggregate_results(all_results)

    # Save aggregate
    agg_dir = RESULTS_DIR / "aggregate"
    agg_dir.mkdir(parents=True, exist_ok=True)
    with open(agg_dir / "monte_carlo_aggregate.json", "w") as f:
        json.dump(aggregate, f, indent=2, default=str)

    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"Monte Carlo complete: {n_runs} runs in {total_time:.0f}s")
    print(f"Aggregate results saved to {agg_dir}")

    return aggregate


def _aggregate_results(all_results: list) -> dict:
    """Aggregate summaries across all Monte Carlo runs."""
    phases = ["baseline", "decm_full", "ablation_no_ai", "ablation_rule"]
    metrics = ["latency_s", "cost_usd", "cpu_cycles", "memory_mb",
               "verification_s", "price_deviation", "negotiation_rounds",
               "energy_wh", "carbon_gco2"]

    aggregate = {}

    for phase in phases:
        phase_data = {}
        valid_results = [r[phase] for r in all_results
                         if r and phase in r and r[phase]]

        if not valid_results:
            aggregate[phase] = {"n_runs": 0}
            continue

        for metric in metrics:
            means = [r[metric]["mean"] for r in valid_results if metric in r]
            stds = [r[metric]["std"] for r in valid_results if metric in r]
            if means:
                phase_data[metric] = {
                    "grand_mean": float(np.mean(means)),
                    "grand_std": float(np.std(means)),
                    "avg_within_std": float(np.mean(stds)),
                    "min_mean": float(np.min(means)),
                    "max_mean": float(np.max(means)),
                }

        # Dispute rate (scalar, not dict)
        dispute_rates = [r.get("dispute_rate", 0) for r in valid_results]
        if dispute_rates:
            phase_data["dispute_rate"] = {
                "grand_mean": float(np.mean(dispute_rates)),
                "grand_std": float(np.std(dispute_rates)),
            }

        phase_data["n_runs"] = len(valid_results)
        aggregate[phase] = phase_data

    # Compute efficiency indices (AHP-weighted composite)
    from agents.config import AHP_WEIGHTS
    for phase in phases:
        if phase not in aggregate or aggregate[phase].get("n_runs", 0) == 0:
            continue

        p = aggregate[phase]
        # Efficiency index: lower is better for all metrics
        baseline = aggregate.get("baseline", {})
        if baseline.get("n_runs", 0) > 0:
            improvements = {}
            for metric in metrics:
                if metric in p and metric in baseline:
                    b_mean = baseline[metric]["grand_mean"]
                    p_mean = p[metric]["grand_mean"]
                    if b_mean > 0:
                        improvements[metric] = (b_mean - p_mean) / b_mean * 100
            p["improvements_vs_baseline"] = improvements

    return aggregate


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DECM Monte Carlo Simulation")
    parser.add_argument("--runs", type=int, default=None,
                        help=f"Number of MC runs (default: config value)")
    parser.add_argument("--use-chain", action="store_true")
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--workers", type=int, default=1,
                        help="Parallel workers (1=sequential)")
    args = parser.parse_args()

    aggregate = run_monte_carlo(args.runs, args.use_chain, args.use_llm, args.workers)

    print("\n" + "=" * 60)
    print("AGGREGATE RESULTS")
    print("=" * 60)

    for phase in ["baseline", "decm_full", "ablation_no_ai", "ablation_rule"]:
        data = aggregate.get(phase, {})
        if data.get("n_runs", 0) == 0:
            continue
        print(f"\n{phase} ({data['n_runs']} runs):")
        for metric in ["latency_s", "cost_usd", "carbon_gco2"]:
            if metric in data:
                m = data[metric]
                print(f"  {metric}: {m['grand_mean']:.4f} ± {m['grand_std']:.4f}")
