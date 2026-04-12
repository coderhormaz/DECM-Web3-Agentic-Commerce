// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC1155/ERC1155.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "./interfaces/IAgenticAI.sol";
import "./interfaces/IDECMCore.sol";

/**
 * @title DECMCore
 * @notice Decentralized Efficiency Commerce Model - Core Marketplace Contract
 * @dev ERC-1155 multi-token marketplace with Agentic AI evaluation loop.
 *      Replicates the DECM simulation protocol (Naik & Thampi) on Monad Testnet.
 */
contract DECMCore is ERC1155, Ownable, ReentrancyGuard, IDECMCore {
    IAgenticAI public agenticAI;
    bool public aiEnabled;

    uint256 public nextDealId;
    uint256 public nextTokenId;

    mapping(uint256 => Deal) internal _deals;
    mapping(address => bytes32) public userDIDs;
    mapping(address => bool) public registeredAgents;
    mapping(uint256 => uint256) public tokenSupply;

    uint256 public baseFee;
    uint256 public maxGasPerTx;
    uint256 public carbonThreshold;

    uint256 public totalTransactions;
    uint256 public totalLatency;
    uint256 public totalGasUsed;
    uint256 public totalCarbonFootprint;
    uint256 public totalDisputes;
    uint256 public totalDisputesResolved;

    constructor(
        address _agenticAI,
        string memory _uri
    ) ERC1155(_uri) Ownable(msg.sender) {
        if (_agenticAI != address(0)) {
            agenticAI = IAgenticAI(_agenticAI);
            aiEnabled = true;
        }
        baseFee = 30;
        maxGasPerTx = 500000;
        carbonThreshold = 100;
    }

    modifier onlyRegistered() {
        require(registeredAgents[msg.sender], "DECM: not registered");
        _;
    }

    function registerAgent(address agent, bytes32 did) external onlyOwner {
        registeredAgents[agent] = true;
        userDIDs[agent] = did;
    }

    function registerAgentBatch(
        address[] calldata agents,
        bytes32[] calldata dids
    ) external onlyOwner {
        require(agents.length == dids.length, "DECM: length mismatch");
        for (uint256 i = 0; i < agents.length; i++) {
            registeredAgents[agents[i]] = true;
            userDIDs[agents[i]] = dids[i];
        }
    }

    function mintAsset(
        address to,
        uint256 amount,
        bytes calldata data
    ) external onlyOwner returns (uint256 tokenId) {
        tokenId = nextTokenId++;
        _mint(to, tokenId, amount, data);
        tokenSupply[tokenId] = amount;
    }

    function mintExistingAsset(
        address to,
        uint256 tokenId,
        uint256 amount,
        bytes calldata data
    ) external onlyOwner {
        _mint(to, tokenId, amount, data);
        tokenSupply[tokenId] += amount;
    }

    function proposeDeal(
        address seller,
        uint256 tokenId,
        uint256 amount,
        uint256 price,
        bytes calldata metadata
    ) external onlyRegistered nonReentrant returns (uint256 dealId) {
        require(seller != msg.sender, "DECM: self-deal");
        require(balanceOf(seller, tokenId) >= amount, "DECM: insufficient balance");

        dealId = nextDealId++;
        Deal storage d = _deals[dealId];
        d.id = dealId;
        d.buyer = msg.sender;
        d.seller = seller;
        d.tokenId = tokenId;
        d.amount = amount;
        d.proposedPrice = price;
        d.timestamp = block.timestamp;
        d.status = DealStatus.Proposed;
        d.didBuyer = userDIDs[msg.sender];
        d.didSeller = userDIDs[seller];
        d.startGas = gasleft();

        emit DealProposed(dealId, msg.sender, seller, tokenId, price, block.timestamp);

        if (aiEnabled && address(agenticAI) != address(0)) {
            _evaluateWithAI(dealId, metadata);
        } else {
            _executeDeal(dealId, price);
        }
    }

    function _evaluateWithAI(uint256 dealId, bytes calldata metadata) internal {
        Deal storage d = _deals[dealId];
        (bool approved, uint256 adjustedPrice, uint256 confidence) = agenticAI.evaluate(
            dealId, d.buyer, d.seller, d.proposedPrice, d.tokenId, metadata
        );

        d.aiConfidence = confidence;
        d.status = DealStatus.AIEvaluated;
        emit DealEvaluated(dealId, approved, adjustedPrice, confidence);

        if (approved) {
            _executeDeal(dealId, adjustedPrice);
        } else {
            d.status = DealStatus.Rejected;
        }
    }

    function _executeDeal(uint256 dealId, uint256 finalPrice) internal {
        Deal storage d = _deals[dealId];
        d.finalPrice = finalPrice;
        d.status = DealStatus.Accepted;

        _safeTransferFrom(d.seller, d.buyer, d.tokenId, d.amount, "");

        _recordTelemetry(dealId, finalPrice);
    }

    function _recordTelemetry(uint256 dealId, uint256 finalPrice) internal {
        Deal storage d = _deals[dealId];
        uint256 gasUsed = d.startGas - gasleft();
        uint256 latency = block.timestamp - d.timestamp;
        uint256 carbon = (gasUsed * 70) / 100000;

        d.gasUsed = gasUsed;
        d.latency = latency;
        d.carbonFootprint = carbon;

        totalTransactions++;
        totalLatency += latency;
        totalGasUsed += gasUsed;
        totalCarbonFootprint += carbon;

        emit DealCompleted(dealId, finalPrice, gasUsed, latency, carbon);

        uint256 trust;
        if (d.didBuyer != bytes32(0) && d.didSeller != bytes32(0)) trust = 9500;
        else if (d.didBuyer != bytes32(0) || d.didSeller != bytes32(0)) trust = 7000;
        else trust = 5000;

        uint256 deviation;
        if (d.proposedPrice > 0) {
            if (finalPrice > d.proposedPrice) {
                deviation = ((finalPrice - d.proposedPrice) * 10000) / d.proposedPrice;
            } else {
                deviation = ((d.proposedPrice - finalPrice) * 10000) / d.proposedPrice;
            }
        }

        emit TelemetryRecorded(dealId, latency, gasUsed, carbon, trust, deviation);
    }

    function disputeDeal(uint256 dealId) external onlyRegistered {
        Deal storage d = _deals[dealId];
        require(msg.sender == d.buyer || msg.sender == d.seller, "DECM: not party to deal");
        require(d.status == DealStatus.Accepted, "DECM: invalid state");
        d.status = DealStatus.Disputed;
        totalDisputes++;
        emit DealDisputed(dealId, msg.sender);
    }

    function resolveDispute(uint256 dealId, bool favorBuyer) external onlyOwner {
        Deal storage d = _deals[dealId];
        require(d.status == DealStatus.Disputed, "DECM: not disputed");
        if (favorBuyer) {
            _safeTransferFrom(d.buyer, d.seller, d.tokenId, d.amount, "");
        }
        d.status = DealStatus.Resolved;
        totalDisputesResolved++;
        emit DisputeResolved(dealId, DealStatus.Resolved);
    }

    function updateBaseFee(uint256 _newFee) external onlyOwner { baseFee = _newFee; }
    function updateCarbonThreshold(uint256 _t) external onlyOwner { carbonThreshold = _t; }
    function updateMaxGas(uint256 _g) external onlyOwner { maxGasPerTx = _g; }

    function setAgenticAI(address _ai) external onlyOwner {
        agenticAI = IAgenticAI(_ai);
        aiEnabled = _ai != address(0);
    }

    function toggleAI(bool _enabled) external onlyOwner { aiEnabled = _enabled; }

    function getDeal(uint256 dealId) external view returns (Deal memory) {
        return _deals[dealId];
    }

    function getAverageLatency() external view returns (uint256) {
        if (totalTransactions == 0) return 0;
        return totalLatency / totalTransactions;
    }

    function getAverageGas() external view returns (uint256) {
        if (totalTransactions == 0) return 0;
        return totalGasUsed / totalTransactions;
    }

    function getAverageCarbon() external view returns (uint256) {
        if (totalTransactions == 0) return 0;
        return totalCarbonFootprint / totalTransactions;
    }

    function getDisputeRate() external view returns (uint256) {
        if (totalTransactions == 0) return 0;
        return (totalDisputes * 10000) / totalTransactions;
    }
}
