"""
Statistical analysis and chart generation.
Replicates the paper's Tables 5-9 and Figures 1-5.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.config import RESULTS_DIR, AHP_WEIGHTS

# Output directories
CHARTS_DIR = RESULTS_DIR / "charts"
TABLES_DIR = RESULTS_DIR / "tables"


def load_aggregate() -> dict:
    """Load Monte Carlo aggregate results."""
    path = RESULTS_DIR / "aggregate" / "monte_carlo_aggregate.json"
    with open(path, "r") as f:
        return json.load(f)


def load_phase_data(phase: str, n_runs: int = 30) -> pd.DataFrame:
    """Load all per-transaction CSVs for a phase across runs."""
    frames = []
    for run_id in range(n_runs):
        csv_path = RESULTS_DIR / f"run_{run_id}" / f"{phase}.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            df["run_id"] = run_id
            frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame()


# =========================================================
# Statistical Tests (Table 5-6 equivalents)
# =========================================================

def paired_t_test(baseline_means: list, decm_means: list) -> dict:
    """Paired t-test for matched Monte Carlo runs."""
    t_stat, p_value = stats.ttest_rel(baseline_means, decm_means)
    return {"t_stat": t_stat, "p_value": p_value, "significant": p_value < 0.05}


def wilcoxon_test(baseline_means: list, decm_means: list) -> dict:
    """Wilcoxon signed-rank (non-parametric alternative)."""
    try:
        stat, p_value = stats.wilcoxon(baseline_means, decm_means)
        return {"stat": stat, "p_value": p_value, "significant": p_value < 0.05}
    except ValueError:
        return {"stat": 0, "p_value": 1.0, "significant": False}


def cohens_d(baseline: list, decm: list) -> float:
    """Cohen's d effect size."""
    diff = np.array(baseline) - np.array(decm)
    return float(np.mean(diff) / (np.std(diff, ddof=1) + 1e-12))


def one_way_anova(*groups) -> dict:
    """One-way ANOVA across all phases."""
    f_stat, p_value = stats.f_oneway(*groups)
    return {"F_stat": f_stat, "p_value": p_value, "significant": p_value < 0.05}


def compute_efficiency_index(metrics: dict, weights: dict = None) -> float:
    """
    AHP-weighted composite Efficiency Index (EI).
    Paper Section 3.3, Table 4.
    EI = sum(w_i × normalized_score_i)
    """
    if weights is None:
        weights = AHP_WEIGHTS

    # Map metric names to weight keys
    metric_to_weight = {
        "latency_s": "transactional",
        "cost_usd": "transactional",
        "cpu_cycles": "computational",
        "memory_mb": "computational",
        "verification_s": "governance",
        "price_deviation": "cognitive",
        "negotiation_rounds": "cognitive",
        "energy_wh": "environmental",
        "carbon_gco2": "environmental",
    }

    total = 0.0
    weight_sum = 0.0

    for metric, weight_key in metric_to_weight.items():
        if metric in metrics:
            w = weights.get(weight_key, 0.2)
            # Normalize: lower is better, so invert
            val = metrics[metric].get("grand_mean", metrics[metric].get("mean", 0))
            score = 1.0 / (1.0 + val) if val >= 0 else 0
            total += w * score
            weight_sum += w

    return total / weight_sum if weight_sum > 0 else 0


# =========================================================
# Generate Tables (matching paper format)
# =========================================================

def generate_comparison_table(aggregate: dict) -> pd.DataFrame:
    """
    Generate Table 7 equivalent: Baseline vs DECM comparison.
    """
    rows = []
    metrics = {
        "latency_s": ("Transaction Latency", "s"),
        "cost_usd": ("Cost per Transaction", "USD"),
        "cpu_cycles": ("CPU Cycles", "M"),
        "memory_mb": ("Memory Usage", "MB"),
        "verification_s": ("Verification Time", "s"),
        "price_deviation": ("Price Deviation", "fraction"),
        "negotiation_rounds": ("Negotiation Rounds", "#"),
        "energy_wh": ("Energy per Tx", "Wh"),
        "carbon_gco2": ("Carbon per Tx", "gCO2"),
    }

    baseline = aggregate.get("baseline", {})
    decm = aggregate.get("decm_full", {})

    for metric_key, (label, unit) in metrics.items():
        b = baseline.get(metric_key, {})
        d = decm.get(metric_key, {})

        b_mean = b.get("grand_mean", 0)
        b_std = b.get("grand_std", 0)
        d_mean = d.get("grand_mean", 0)
        d_std = d.get("grand_std", 0)

        improvement = ((b_mean - d_mean) / b_mean * 100) if b_mean > 0 else 0

        rows.append({
            "Metric": label,
            "Unit": unit,
            "Baseline (mean)": f"{b_mean:.4f}",
            "Baseline (std)": f"{b_std:.4f}",
            "DECM (mean)": f"{d_mean:.4f}",
            "DECM (std)": f"{d_std:.4f}",
            "Improvement (%)": f"{improvement:+.1f}%",
        })

    return pd.DataFrame(rows)


def generate_ablation_table(aggregate: dict) -> pd.DataFrame:
    """Generate Table 9 equivalent: Ablation study results."""
    rows = []
    configs = [
        ("decm_full", "DECM Full (AI + Blockchain)"),
        ("ablation_rule", "Blockchain + Rule-based Bot"),
        ("ablation_no_ai", "Blockchain Only (No AI)"),
        ("baseline", "Baseline (Web 2.0)"),
    ]

    key_metrics = ["latency_s", "cost_usd", "carbon_gco2",
                   "verification_s", "price_deviation"]

    for phase, label in configs:
        data = aggregate.get(phase, {})
        if data.get("n_runs", 0) == 0:
            continue
        row = {"Configuration": label}
        for m in key_metrics:
            if m in data:
                row[m] = f"{data[m]['grand_mean']:.4f}"
        rows.append(row)

    return pd.DataFrame(rows)


def generate_statistical_tests(aggregate: dict) -> pd.DataFrame:
    """Generate Table 5 equivalent: Statistical significance tests.
    Loads actual per-run summary JSON files for real paired tests."""
    rows = []
    phases = ["decm_full", "ablation_no_ai", "ablation_rule"]
    metrics = ["latency_s", "cost_usd", "carbon_gco2"]

    baseline_agg = aggregate.get("baseline", {})
    if baseline_agg.get("n_runs", 0) == 0:
        return pd.DataFrame()

    n_runs = baseline_agg["n_runs"]

    # Load actual per-run means from summary JSON files
    def _load_per_run_means(phase_name: str, metric_key: str) -> list:
        means = []
        for run_id in range(n_runs):
            summary_path = RESULTS_DIR / f"run_{run_id}" / f"{phase_name}_summary.json"
            if summary_path.exists():
                with open(summary_path, "r") as f:
                    summary = json.load(f)
                if metric_key in summary:
                    means.append(summary[metric_key].get("mean", 0))
            else:
                # Fallback: try loading from CSV
                csv_path = RESULTS_DIR / f"run_{run_id}" / f"{phase_name}.csv"
                if csv_path.exists():
                    df = pd.read_csv(csv_path)
                    if metric_key in df.columns:
                        means.append(float(df[metric_key].mean()))
        return means

    for phase in phases:
        data = aggregate.get(phase, {})
        if data.get("n_runs", 0) == 0:
            continue

        for metric in metrics:
            b_means = _load_per_run_means("baseline", metric)
            d_means = _load_per_run_means(phase, metric)

            # Ensure equal length (paired test requires it)
            min_len = min(len(b_means), len(d_means))
            if min_len < 2:
                continue
            b_means = b_means[:min_len]
            d_means = d_means[:min_len]

            t_result = paired_t_test(b_means, d_means)
            w_result = wilcoxon_test(b_means, d_means)
            d_effect = cohens_d(b_means, d_means)

            rows.append({
                "Comparison": f"Baseline vs {phase}",
                "Metric": metric,
                "t-stat": f"{t_result['t_stat']:.3f}",
                "p-value (t)": f"{t_result['p_value']:.6f}",
                "Significant (t)": t_result["significant"],
                "Wilcoxon p": f"{w_result['p_value']:.6f}",
                "Cohen's d": f"{d_effect:.3f}",
            })

    return pd.DataFrame(rows)


# =========================================================
# Chart Generation
# =========================================================

def generate_charts(aggregate: dict):
    """Generate all charts matching paper's figures."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns
        sns.set_theme(style="whitegrid", palette="deep")
    except ImportError:
        print("matplotlib/seaborn not installed, skipping charts")
        return

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    _plot_comparison_bar(aggregate, plt, sns)
    _plot_improvement_radar(aggregate, plt)
    _plot_ablation_heatmap(aggregate, plt, sns)
    _plot_efficiency_index(aggregate, plt)

    print(f"Charts saved to {CHARTS_DIR}")


def _plot_comparison_bar(aggregate, plt, sns):
    """Figure 1: Baseline vs DECM bar comparison."""
    metrics = ["latency_s", "cost_usd", "carbon_gco2", "verification_s"]
    labels = ["Latency (s)", "Cost (USD)", "Carbon (gCO2)", "Verification (s)"]

    baseline_vals = []
    decm_vals = []

    for m in metrics:
        b = aggregate.get("baseline", {}).get(m, {})
        d = aggregate.get("decm_full", {}).get(m, {})
        baseline_vals.append(b.get("grand_mean", 0))
        decm_vals.append(d.get("grand_mean", 0))

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))
    bars1 = ax.bar(x - width/2, baseline_vals, width, label="Baseline (Web 2.0)",
                   color="#e74c3c", alpha=0.85)
    bars2 = ax.bar(x + width/2, decm_vals, width, label="DECM (Web 3.0 + AI)",
                   color="#2ecc71", alpha=0.85)

    ax.set_ylabel("Value")
    ax.set_title("Baseline vs DECM: Key Metrics Comparison")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "comparison_bar.png", dpi=150)
    plt.close(fig)


def _plot_improvement_radar(aggregate, plt):
    """Figure 2: Improvement radar chart across 5 dimensions."""
    dimensions = ["Transactional", "Computational", "Governance", "Cognitive", "Environmental"]
    metric_groups = {
        "Transactional": ["latency_s", "cost_usd"],
        "Computational": ["cpu_cycles", "memory_mb"],
        "Governance": ["verification_s"],
        "Cognitive": ["price_deviation", "negotiation_rounds"],
        "Environmental": ["energy_wh", "carbon_gco2"],
    }

    improvements = []
    baseline = aggregate.get("baseline", {})
    decm = aggregate.get("decm_full", {})

    for dim in dimensions:
        dim_improvements = []
        for m in metric_groups[dim]:
            b = baseline.get(m, {}).get("grand_mean", 1)
            d = decm.get(m, {}).get("grand_mean", 1)
            if b > 0:
                dim_improvements.append((b - d) / b * 100)
        improvements.append(np.mean(dim_improvements) if dim_improvements else 0)

    # Radar plot
    angles = np.linspace(0, 2 * np.pi, len(dimensions), endpoint=False).tolist()
    improvements_plot = improvements + [improvements[0]]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    ax.fill(angles, improvements_plot, alpha=0.25, color="#3498db")
    ax.plot(angles, improvements_plot, "o-", color="#3498db", linewidth=2)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dimensions, fontsize=11)
    ax.set_title("DECM Improvement Over Baseline (%)", pad=20, fontsize=14)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "improvement_radar.png", dpi=150)
    plt.close(fig)


def _plot_ablation_heatmap(aggregate, plt, sns):
    """Figure 3: Ablation study heatmap."""
    configs = ["baseline", "ablation_no_ai", "ablation_rule", "decm_full"]
    config_labels = ["Baseline", "No AI", "Rule Bot", "DECM Full"]
    metrics = ["latency_s", "cost_usd", "carbon_gco2", "verification_s", "price_deviation"]
    metric_labels = ["Latency", "Cost", "Carbon", "Verification", "Price Dev."]

    data = np.zeros((len(configs), len(metrics)))
    for i, cfg in enumerate(configs):
        phase = aggregate.get(cfg, {})
        for j, m in enumerate(metrics):
            data[i, j] = phase.get(m, {}).get("grand_mean", 0)

    # Normalize columns to 0-1 for heatmap
    for j in range(data.shape[1]):
        col_max = data[:, j].max()
        if col_max > 0:
            data[:, j] = data[:, j] / col_max

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.heatmap(data, annot=True, fmt=".2f", xticklabels=metric_labels,
                yticklabels=config_labels, cmap="RdYlGn_r", ax=ax)
    ax.set_title("Ablation Study: Normalized Metric Comparison")
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "ablation_heatmap.png", dpi=150)
    plt.close(fig)


def _plot_efficiency_index(aggregate, plt):
    """Figure 4: Composite Efficiency Index by configuration."""
    configs = {
        "Baseline": "baseline",
        "No AI": "ablation_no_ai",
        "Rule Bot": "ablation_rule",
        "DECM Full": "decm_full",
    }

    indices = []
    labels = []
    for label, phase_key in configs.items():
        data = aggregate.get(phase_key, {})
        if data.get("n_runs", 0) > 0:
            ei = compute_efficiency_index(data)
            indices.append(ei)
            labels.append(label)

    fig, ax = plt.subplots(figsize=(8, 5))
    colors = ["#e74c3c", "#e67e22", "#f1c40f", "#2ecc71"][:len(labels)]
    bars = ax.bar(labels, indices, color=colors, alpha=0.85, edgecolor="black")
    ax.set_ylabel("Efficiency Index (higher = better)")
    ax.set_title("Composite Efficiency Index by Configuration")
    ax.set_ylim(0, 1)

    for bar, val in zip(bars, indices):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f"{val:.3f}", ha="center", va="bottom", fontweight="bold")

    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "efficiency_index.png", dpi=150)
    plt.close(fig)


# =========================================================
# Main analysis pipeline
# =========================================================

def run_analysis():
    """Full analysis pipeline."""
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading aggregate results...")
    aggregate = load_aggregate()

    print("Generating comparison table...")
    comparison = generate_comparison_table(aggregate)
    comparison.to_csv(TABLES_DIR / "comparison_table.csv", index=False)
    print(comparison.to_string(index=False))

    print("\nGenerating ablation table...")
    ablation = generate_ablation_table(aggregate)
    ablation.to_csv(TABLES_DIR / "ablation_table.csv", index=False)
    print(ablation.to_string(index=False))

    print("\nGenerating statistical tests...")
    stat_tests = generate_statistical_tests(aggregate)
    stat_tests.to_csv(TABLES_DIR / "statistical_tests.csv", index=False)
    print(stat_tests.to_string(index=False))

    print("\nComputing Efficiency Indices...")
    for phase in ["baseline", "decm_full", "ablation_no_ai", "ablation_rule"]:
        data = aggregate.get(phase, {})
        if data.get("n_runs", 0) > 0:
            ei = compute_efficiency_index(data)
            print(f"  {phase}: EI = {ei:.4f}")

    print("\nGenerating charts...")
    generate_charts(aggregate)

    print("\nAnalysis complete!")


if __name__ == "__main__":
    run_analysis()
