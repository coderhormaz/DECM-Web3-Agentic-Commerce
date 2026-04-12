// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title IDECMCore
 * @notice Events and shared types for the DECM marketplace.
 */
interface IDECMCore {
    enum DealStatus {
        Proposed,
        AIEvaluated,
        Accepted,
        Rejected,
        Disputed,
        Resolved
    }

    struct Deal {
        uint256 id;
        address buyer;
        address seller;
        uint256 tokenId;
        uint256 amount;
        uint256 proposedPrice;
        uint256 finalPrice;
        uint256 timestamp;
        DealStatus status;
        uint256 aiConfidence;
        bytes32 didBuyer;
        bytes32 didSeller;
        uint256 carbonFootprint;
        uint256 gasUsed;
        uint256 latency;
        uint256 startGas;
    }

    // --- Events ---
    event DealProposed(
        uint256 indexed dealId,
        address indexed buyer,
        address indexed seller,
        uint256 tokenId,
        uint256 price,
        uint256 timestamp
    );

    event DealEvaluated(
        uint256 indexed dealId,
        bool approved,
        uint256 adjustedPrice,
        uint256 confidence
    );

    event DealCompleted(
        uint256 indexed dealId,
        uint256 finalPrice,
        uint256 gasUsed,
        uint256 latency,
        uint256 carbonFootprint
    );

    event DealDisputed(uint256 indexed dealId, address indexed disputor);

    event DisputeResolved(uint256 indexed dealId, DealStatus resolution);

    event TelemetryRecorded(
        uint256 indexed dealId,
        uint256 latency,
        uint256 gasUsed,
        uint256 carbonFootprint,
        uint256 governanceTrust,
        uint256 cognitiveDeviation
    );
}
