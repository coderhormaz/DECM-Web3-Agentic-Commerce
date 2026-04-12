"""
Off-chain AI Evaluator Relayer for DECM.
Replaces Chainlink Functions (unavailable on Monad).

Architecture:
  1. Listens to DealProposed events from DECMCore contract
  2. Runs AI evaluation via Ollama/Llama 3
  3. Calls DECMCore.evaluate() callback on-chain

For simulation purposes, this module provides evaluation logic
that the simulation runner calls directly (no persistent listener).
"""
import json
import time
import numpy as np
import requests
from typing import Tuple


class AIEvaluator:
    """
    Agentic AI evaluation engine.
    Runs multi-objective optimization for deal approval.
    """

    def __init__(self, ollama_url="http://localhost:11434", model="llama3",
                 use_llm=True):
        self.ollama_url = ollama_url
        self.model = model
        self.use_llm = use_llm

        # Learning state
        self.eval_count = 0
        self.approval_rate = 0.0
        self.avg_adjustment = 0.0
        self.price_history = []

        # Thresholds (adaptive, updated by telemetry feedback)
        self.max_price_deviation = 0.15  # 15% max deviation
        self.min_trust_score = 0.5
        self.carbon_penalty_threshold = 0.3  # gCO2/tx

    def evaluate(self, deal_data: dict) -> Tuple[bool, int, int]:
        """
        Evaluate a proposed deal.

        Args:
            deal_data: {
                deal_id, buyer, seller, price, token_id,
                buyer_did, seller_did, market_avg_price,
                carbon_estimate, demand_level
            }

        Returns:
            (approved, adjusted_price, confidence_bps)
        """
        self.eval_count += 1

        if self.use_llm:
            try:
                return self._llm_evaluate(deal_data)
            except Exception:
                pass

        return self._rule_evaluate(deal_data)

    def _rule_evaluate(self, data: dict) -> Tuple[bool, int, int]:
        """Rule-based evaluation (used for ablation phase)."""
        price = data.get("price", 100)
        market_avg = data.get("market_avg_price", 100)
        demand = data.get("demand_level", 1.0)

        # Price fairness check
        if market_avg > 0:
            deviation = abs(price - market_avg) / market_avg
        else:
            deviation = 0

        # Trust check (DID presence)
        has_buyer_did = data.get("buyer_did", "") != ""
        has_seller_did = data.get("seller_did", "") != ""
        trust = 0.95 if (has_buyer_did and has_seller_did) else 0.70

        # Carbon check
        carbon = data.get("carbon_estimate", 0.1)
        carbon_ok = carbon < self.carbon_penalty_threshold

        # Approval logic
        approved = deviation < self.max_price_deviation and trust >= self.min_trust_score

        # Price adjustment: nudge toward market average
        if deviation > 0.05:
            adjusted = int(market_avg * demand * (1 + np.random.uniform(-0.02, 0.02)))
        else:
            adjusted = price

        # Confidence based on how many checks pass
        checks_passed = sum([
            deviation < self.max_price_deviation,
            trust >= self.min_trust_score,
            carbon_ok,
        ])
        confidence = int((checks_passed / 3) * 10000)

        # Update learning state
        self.price_history.append(price)
        self.approval_rate = (
            (self.approval_rate * (self.eval_count - 1) + (1 if approved else 0))
            / self.eval_count
        )

        return (approved, max(1, adjusted), confidence)

    def _llm_evaluate(self, data: dict) -> Tuple[bool, int, int]:
        """LLM-based evaluation using Ollama."""
        prompt = f"""You are an AI evaluator for a decentralized marketplace.
Evaluate this deal for approval:
- Proposed price: {data.get('price', 0)}
- Market average: {data.get('market_avg_price', 0)}
- Demand level: {data.get('demand_level', 1.0):.2f}
- Buyer has DID: {bool(data.get('buyer_did'))}
- Seller has DID: {bool(data.get('seller_did'))}
- Est. carbon: {data.get('carbon_estimate', 0):.4f} gCO2

Optimize for: fair pricing, trust, low carbon.
Reply ONLY with JSON: {{"approved": true/false, "adjusted_price": <int>, "confidence": 0-100}}"""

        resp = requests.post(
            f"{self.ollama_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.2, "num_predict": 128}},
            timeout=30,
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Ollama error: {resp.status_code}")

        text = resp.json().get("response", "")
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(text[start:end])
            approved = bool(result.get("approved", True))
            adjusted = max(1, int(result.get("adjusted_price", data["price"])))
            confidence = min(10000, max(0, int(result.get("confidence", 75)) * 100))
            return (approved, adjusted, confidence)

        return self._rule_evaluate(data)

    def update_thresholds(self, telemetry: dict):
        """
        Adaptive threshold update from telemetry feedback loop.
        Called after batches of transactions (Section 4.6).
        """
        avg_carbon = telemetry.get("avg_carbon", 0)
        dispute_rate = telemetry.get("dispute_rate", 0)

        # If carbon is too high, tighten threshold
        if avg_carbon > self.carbon_penalty_threshold:
            self.carbon_penalty_threshold *= 0.95

        # If dispute rate is high, tighten price deviation allowed
        if dispute_rate > 0.03:
            self.max_price_deviation = max(0.05, self.max_price_deviation * 0.95)
        elif dispute_rate < 0.01:
            self.max_price_deviation = min(0.25, self.max_price_deviation * 1.02)
