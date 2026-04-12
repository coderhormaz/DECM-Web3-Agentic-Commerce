"""
DECM Buyer/Seller Agent Framework.
LangChain-based agents using Ollama (Llama 3) for cognitive reasoning.
Implements the 3-stage perception-reasoning-action loop from Section 4.5.
"""
import json
import time
import random
import hashlib
import numpy as np
import requests
from typing import Optional
from agents.reward import DECMReward


class AgentBase:
    """Base class for DECM agents (buyer or seller)."""

    def __init__(self, agent_id: int, role: str, wallet_address: str,
                 private_key: str, did_hash: str, ollama_url: str,
                 model: str = "llama3", use_llm: bool = True):
        self.agent_id = agent_id
        self.role = role  # "buyer" or "seller"
        self.wallet_address = wallet_address
        self.private_key = private_key
        self.did_hash = did_hash
        self.ollama_url = ollama_url
        self.model = model
        self.use_llm = use_llm

        self.reward_fn = DECMReward()
        self.transaction_count = 0
        self.total_reward = 0.0
        self.price_history = []
        self.epsilon = 0.3  # exploration rate, decays over time

    def perceive(self, market_state: dict) -> dict:
        """
        Stage 1: Perception - Parse contextual metadata.
        Extracts price, DID info, carbon footprint, latency from market state.
        """
        return {
            "current_prices": market_state.get("prices", []),
            "avg_latency": market_state.get("avg_latency", 0),
            "avg_carbon": market_state.get("avg_carbon", 0),
            "demand_level": market_state.get("demand_level", 1.0),
            "agent_role": self.role,
            "tx_count": self.transaction_count,
        }

    def reason(self, perception: dict) -> dict:
        """
        Stage 2: Reasoning - Multi-objective optimization via LLM.
        Uses Ollama/Llama 3 for contextual reasoning about deal parameters.
        Falls back to heuristic if LLM unavailable.
        """
        if self.use_llm:
            try:
                return self._llm_reason(perception)
            except Exception:
                pass
        return self._heuristic_reason(perception)

    def _llm_reason(self, perception: dict) -> dict:
        """Call Ollama for LLM-based reasoning."""
        prompt = self._build_reasoning_prompt(perception)

        response = requests.post(
            f"{self.ollama_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 256},
            },
            timeout=30,
        )

        if response.status_code != 200:
            raise RuntimeError(f"Ollama error: {response.status_code}")

        text = response.json().get("response", "")
        return self._parse_llm_response(text, perception)

    def _heuristic_reason(self, perception: dict) -> dict:
        """Fallback: deterministic heuristic reasoning."""
        prices = perception.get("current_prices", [100])
        avg_price = np.mean(prices) if prices else 100
        demand = perception.get("demand_level", 1.0)

        # Q-learning action selection
        state = self._state_key(perception)
        actions = ["aggressive", "moderate", "conservative"]
        action = self.reward_fn.best_action(state, actions, self.epsilon)

        # Price strategy based on action
        if self.role == "buyer":
            multipliers = {"aggressive": 0.90, "moderate": 0.95, "conservative": 1.0}
        else:
            multipliers = {"aggressive": 1.10, "moderate": 1.05, "conservative": 1.0}

        target_price = int(avg_price * multipliers[action] * demand)
        target_amount = max(1, int(random.gauss(10, 3)))

        return {
            "action": action,
            "target_price": max(1, target_price),
            "target_amount": target_amount,
            "confidence": 0.75 + 0.25 * (1 - self.epsilon),
            "reasoning": f"heuristic_{action}",
        }

    def act(self, decision: dict) -> dict:
        """
        Stage 3: Action - Returns deal parameters for on-chain submission.
        The simulation runner handles actual web3 transaction submission.
        """
        self.transaction_count += 1
        # Decay exploration
        self.epsilon = max(0.05, self.epsilon * 0.998)

        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "wallet": self.wallet_address,
            "price": decision["target_price"],
            "amount": decision["target_amount"],
            "action_type": decision["action"],
            "confidence": decision["confidence"],
        }

    def learn(self, metrics: dict, prev_state: dict, curr_state: dict):
        """Post-transaction learning: update Q-table."""
        reward = self.reward_fn.compute_reward(metrics)
        self.total_reward += reward

        state_key = self._state_key(prev_state)
        next_key = self._state_key(curr_state)
        action = metrics.get("action_type", "moderate")

        self.reward_fn.update_q(state_key, action, reward, next_key)

    def _state_key(self, perception: dict) -> str:
        """Discretize market state for Q-table lookup."""
        demand = perception.get("demand_level", 1.0)
        latency = perception.get("avg_latency", 0)

        d_bucket = "high" if demand > 1.2 else ("low" if demand < 0.8 else "normal")
        l_bucket = "fast" if latency < 1.0 else ("slow" if latency > 3.0 else "medium")

        return f"{self.role}_{d_bucket}_{l_bucket}_{self.transaction_count // 100}"

    def _build_reasoning_prompt(self, perception: dict) -> str:
        return f"""You are a {self.role} agent in a decentralized marketplace.
Current market state:
- Average prices: {perception.get('current_prices', [])}
- Average latency: {perception.get('avg_latency', 0):.2f}s
- Carbon footprint: {perception.get('avg_carbon', 0):.4f} gCO2/tx
- Demand level: {perception.get('demand_level', 1.0):.2f}
- Your transaction count: {self.transaction_count}

Optimize for: speed, cost, trust, and sustainability.
Reply ONLY with JSON: {{"action": "aggressive|moderate|conservative", "price_multiplier": 0.8-1.2, "amount": 1-20, "confidence": 0.0-1.0}}"""

    def _parse_llm_response(self, text: str, perception: dict) -> dict:
        """Parse LLM JSON response, fallback to heuristic on parse error."""
        try:
            # Extract JSON from response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                prices = perception.get("current_prices", [100])
                avg_price = np.mean(prices) if prices else 100
                demand = perception.get("demand_level", 1.0)

                return {
                    "action": data.get("action", "moderate"),
                    "target_price": max(1, int(avg_price * data.get("price_multiplier", 1.0) * demand)),
                    "target_amount": max(1, int(data.get("amount", 10))),
                    "confidence": float(data.get("confidence", 0.75)),
                    "reasoning": "llm",
                }
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
        return self._heuristic_reason(perception)


class BuyerAgent(AgentBase):
    def __init__(self, agent_id, wallet_address, private_key, did_hash,
                 ollama_url="http://localhost:11434", model="llama3",
                 use_llm=True):
        super().__init__(agent_id, "buyer", wallet_address, private_key,
                         did_hash, ollama_url, model, use_llm)


class SellerAgent(AgentBase):
    def __init__(self, agent_id, wallet_address, private_key, did_hash,
                 ollama_url="http://localhost:11434", model="llama3",
                 use_llm=True):
        super().__init__(agent_id, "seller", wallet_address, private_key,
                         did_hash, ollama_url, model, use_llm)
