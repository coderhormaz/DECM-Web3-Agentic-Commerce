// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./interfaces/IAgenticAI.sol";

/**
 * @title MockAgenticAI
 * @notice Mock AI evaluator for testing and ablation (rule-based bot).
 *         Phase 2 (DECM Full):  off-chain relayer provides real AI evals.
 *         Phase 3a (Ablation):  this contract acts as rule-based bot.
 *         Phase 3b (No-AI):     DECMCore.aiEnabled = false.
 */
contract MockAgenticAI is IAgenticAI {
    bool public alwaysApprove;
    uint256 public priceAdjustmentBps; // basis points to adjust price
    uint256 public fixedConfidence;

    constructor(bool _alwaysApprove, uint256 _adjustBps, uint256 _confidence) {
        alwaysApprove = _alwaysApprove;
        priceAdjustmentBps = _adjustBps;
        fixedConfidence = _confidence;
    }

    function evaluate(
        uint256 /* dealId */,
        address /* buyer */,
        address /* seller */,
        uint256 price,
        uint256 /* tokenId */,
        bytes calldata /* metadata */
    ) external view override returns (bool approved, uint256 adjustedPrice, uint256 confidence) {
        // Rule-based: adjust price by configured bps
        if (priceAdjustmentBps > 0) {
            adjustedPrice = price - (price * priceAdjustmentBps) / 10000;
        } else {
            adjustedPrice = price;
        }
        approved = alwaysApprove;
        confidence = fixedConfidence;
    }
}
