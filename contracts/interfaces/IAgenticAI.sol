// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title IAgenticAI
 * @notice Interface for the off-chain Agentic AI evaluation oracle.
 *         The off-chain relayer listens to DealProposed events, runs
 *         multi-objective optimization (speed, cost, trust, sustainability),
 *         and calls back through a contract that implements this interface.
 */
interface IAgenticAI {
    /**
     * @notice Evaluate a proposed deal using AI reasoning.
     * @param dealId   Unique deal identifier
     * @param buyer    Buyer address
     * @param seller   Seller address
     * @param price    Proposed price (in token-native units)
     * @param tokenId  ERC-1155 token being traded
     * @param metadata Arbitrary bytes (JSON-LD product ontology, DID docs, etc.)
     * @return approved      Whether the AI approves the deal
     * @return adjustedPrice AI-suggested price (may equal proposed price)
     * @return confidence    Confidence score 0-10000 (basis points)
     */
    function evaluate(
        uint256 dealId,
        address buyer,
        address seller,
        uint256 price,
        uint256 tokenId,
        bytes calldata metadata
    ) external returns (bool approved, uint256 adjustedPrice, uint256 confidence);
}
