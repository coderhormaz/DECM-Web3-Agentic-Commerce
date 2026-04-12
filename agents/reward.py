"""
Q-Learning Reward Function for DECM Agents.
Tracks multi-objective performance across transactions
and computes rewards aligned with the 5 efficiency dimensions.
"""
import numpy as np


class DECMReward:
    """
    Multi-objective reward with 5 dimensions matching the paper's
    efficiency framework (Table 4):
        Transactional, Computational, Governance, Cognitive, Environmental
    """

    def __init__(self, weights=None, learning_rate=0.1, discount=0.95):
        self.weights = weights or {
            "transactional": 0.30,
            "computational": 0.15,
            "governance":    0.20,
            "cognitive":     0.15,
            "environmental": 0.20,
        }
        self.lr = learning_rate
        self.gamma = discount

        # Q-table: state → action → value
        self.q_table = {}
        self.history = []

    def compute_reward(self, metrics: dict) -> float:
        """
        Compute composite reward from per-transaction metrics.

        Args:
            metrics: dict with keys:
                latency_s, cost_usd, cpu_cycles, memory_mb,
                verification_s, dispute (bool), price_deviation,
                negotiation_rounds, energy_wh, carbon_gco2
        """
        # Normalize each dimension to 0-1 (higher = better)
        t_score = self._transactional_score(metrics)
        c_score = self._computational_score(metrics)
        g_score = self._governance_score(metrics)
        cog_score = self._cognitive_score(metrics)
        e_score = self._environmental_score(metrics)

        reward = (
            self.weights["transactional"] * t_score +
            self.weights["computational"] * c_score +
            self.weights["governance"] * g_score +
            self.weights["cognitive"] * cog_score +
            self.weights["environmental"] * e_score
        )

        self.history.append({
            "reward": reward,
            "transactional": t_score,
            "computational": c_score,
            "governance": g_score,
            "cognitive": cog_score,
            "environmental": e_score,
        })

        return reward

    def update_q(self, state: str, action: str, reward: float, next_state: str):
        """Standard Q-learning update."""
        if state not in self.q_table:
            self.q_table[state] = {}
        if action not in self.q_table[state]:
            self.q_table[state][action] = 0.0

        # Max Q for next state
        next_max = 0.0
        if next_state in self.q_table:
            next_max = max(self.q_table[next_state].values(), default=0.0)

        old_q = self.q_table[state][action]
        self.q_table[state][action] = old_q + self.lr * (
            reward + self.gamma * next_max - old_q
        )

    def best_action(self, state: str, actions: list, epsilon=0.1) -> str:
        """Epsilon-greedy action selection."""
        if np.random.random() < epsilon or state not in self.q_table:
            return np.random.choice(actions)

        q_values = self.q_table.get(state, {})
        best = max(actions, key=lambda a: q_values.get(a, 0.0))
        return best

    # --- Dimension scorers (0-1, higher = better) ---
    def _transactional_score(self, m):
        # Latency: <0.5s = 1.0, >5s = 0.0; Cost: <$0.01 = 1.0, >$0.1 = 0.0
        lat = max(0, min(1, (5.0 - m.get("latency_s", 2.0)) / 4.5))
        cost = max(0, min(1, (0.1 - m.get("cost_usd", 0.04)) / 0.09))
        return 0.5 * lat + 0.5 * cost

    def _computational_score(self, m):
        cpu = max(0, min(1, (10.0 - m.get("cpu_cycles", 5.0)) / 9.0))
        mem = max(0, min(1, (200 - m.get("memory_mb", 100)) / 180))
        return 0.5 * cpu + 0.5 * mem

    def _governance_score(self, m):
        ver = max(0, min(1, (15.0 - m.get("verification_s", 8.0)) / 14.0))
        disp = 1.0 if not m.get("dispute", False) else 0.0
        return 0.5 * ver + 0.5 * disp

    def _cognitive_score(self, m):
        dev = max(0, min(1, (0.5 - m.get("price_deviation", 0.2)) / 0.5))
        rounds = max(0, min(1, (8.0 - m.get("negotiation_rounds", 3.0)) / 7.0))
        return 0.5 * dev + 0.5 * rounds

    def _environmental_score(self, m):
        energy = max(0, min(1, (1.0 - m.get("energy_wh", 0.2)) / 0.9))
        carbon = max(0, min(1, (0.5 - m.get("carbon_gco2", 0.1)) / 0.45))
        return 0.5 * energy + 0.5 * carbon
