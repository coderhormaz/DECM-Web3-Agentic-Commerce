// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title DECMGovernance
 * @notice Adaptive-quorum DAO governance for the DECM framework.
 *         Manages parameter-update proposals and voting with dynamic quorum.
 *         Mirrors the Snapshot-style voting described in the DECM paper,
 *         implemented fully on-chain for Monad testnet reproducibility.
 */
contract DECMGovernance is Ownable {
    // --- Types ---
    enum ProposalStatus { Pending, Active, Passed, Rejected, Executed }
    enum ParamType { BaseFee, CarbonThreshold, MaxGas, AIEnabled, Custom }

    struct Proposal {
        uint256 id;
        address proposer;
        ParamType paramType;
        uint256 newValue;
        string description;
        uint256 votesFor;
        uint256 votesAgainst;
        uint256 startTime;
        uint256 endTime;
        ProposalStatus status;
        bool executed;
    }

    // --- State ---
    uint256 public nextProposalId;
    uint256 public votingDuration;    // seconds
    uint256 public quorumPercent;     // 0-100
    uint256 public totalVoters;

    mapping(uint256 => Proposal) public proposals;
    mapping(uint256 => mapping(address => bool)) public hasVoted;
    mapping(address => bool) public isVoter;

    // Adaptive quorum parameters
    uint256 public recentParticipationRate; // 0-10000 bps
    uint256 public minQuorum;   // floor (e.g., 20%)
    uint256 public maxQuorum;   // ceiling (e.g., 60%)

    // Target contract for parameter updates
    address public targetContract;

    // --- Events ---
    event ProposalCreated(uint256 indexed id, address indexed proposer, ParamType paramType, uint256 newValue);
    event Voted(uint256 indexed proposalId, address indexed voter, bool support);
    event ProposalFinalized(uint256 indexed id, ProposalStatus status);
    event ProposalExecuted(uint256 indexed id);
    event VoterAdded(address indexed voter);
    event VoterRemoved(address indexed voter);
    event QuorumUpdated(uint256 newQuorum);

    // --- Constructor ---
    constructor(address _targetContract) Ownable(msg.sender) {
        targetContract = _targetContract;
        votingDuration = 120;   // 2 minutes for simulation speed
        quorumPercent = 30;
        minQuorum = 20;
        maxQuorum = 60;
    }

    // --- Voter Management ---
    function addVoter(address voter) external onlyOwner {
        if (!isVoter[voter]) {
            isVoter[voter] = true;
            totalVoters++;
            emit VoterAdded(voter);
        }
    }

    function addVoterBatch(address[] calldata voters) external onlyOwner {
        for (uint256 i = 0; i < voters.length; i++) {
            if (!isVoter[voters[i]]) {
                isVoter[voters[i]] = true;
                totalVoters++;
                emit VoterAdded(voters[i]);
            }
        }
    }

    function removeVoter(address voter) external onlyOwner {
        if (isVoter[voter]) {
            isVoter[voter] = false;
            totalVoters--;
            emit VoterRemoved(voter);
        }
    }

    // --- Proposal Lifecycle ---
    function createProposal(
        ParamType paramType,
        uint256 newValue,
        string calldata description
    ) external returns (uint256 proposalId) {
        require(isVoter[msg.sender], "GOV: not a voter");

        proposalId = nextProposalId++;
        Proposal storage p = proposals[proposalId];
        p.id = proposalId;
        p.proposer = msg.sender;
        p.paramType = paramType;
        p.newValue = newValue;
        p.description = description;
        p.startTime = block.timestamp;
        p.endTime = block.timestamp + votingDuration;
        p.status = ProposalStatus.Active;

        emit ProposalCreated(proposalId, msg.sender, paramType, newValue);
    }

    function vote(uint256 proposalId, bool support) external {
        require(isVoter[msg.sender], "GOV: not a voter");
        Proposal storage p = proposals[proposalId];
        require(p.status == ProposalStatus.Active, "GOV: not active");
        require(block.timestamp <= p.endTime, "GOV: voting ended");
        require(!hasVoted[proposalId][msg.sender], "GOV: already voted");

        hasVoted[proposalId][msg.sender] = true;

        if (support) {
            p.votesFor++;
        } else {
            p.votesAgainst++;
        }

        emit Voted(proposalId, msg.sender, support);
    }

    function finalizeProposal(uint256 proposalId) external {
        Proposal storage p = proposals[proposalId];
        require(p.status == ProposalStatus.Active, "GOV: not active");
        require(block.timestamp > p.endTime, "GOV: voting not ended");

        uint256 totalVotes = p.votesFor + p.votesAgainst;
        uint256 currentQuorum = _adaptiveQuorum();

        uint256 quorumNeeded = (totalVoters * currentQuorum) / 100;

        if (totalVotes >= quorumNeeded && p.votesFor > p.votesAgainst) {
            p.status = ProposalStatus.Passed;
        } else {
            p.status = ProposalStatus.Rejected;
        }

        // Update participation rate for adaptive quorum
        if (totalVoters > 0) {
            recentParticipationRate = (totalVotes * 10000) / totalVoters;
        }
        quorumPercent = currentQuorum;
        emit QuorumUpdated(currentQuorum);
        emit ProposalFinalized(proposalId, p.status);
    }

    function executeProposal(uint256 proposalId) external onlyOwner {
        Proposal storage p = proposals[proposalId];
        require(p.status == ProposalStatus.Passed, "GOV: not passed");
        require(!p.executed, "GOV: already executed");

        p.executed = true;
        p.status = ProposalStatus.Executed;

        // Execute parameter update on target contract
        bytes memory callData;
        if (p.paramType == ParamType.BaseFee) {
            callData = abi.encodeWithSignature("updateBaseFee(uint256)", p.newValue);
        } else if (p.paramType == ParamType.CarbonThreshold) {
            callData = abi.encodeWithSignature("updateCarbonThreshold(uint256)", p.newValue);
        } else if (p.paramType == ParamType.MaxGas) {
            callData = abi.encodeWithSignature("updateMaxGas(uint256)", p.newValue);
        } else if (p.paramType == ParamType.AIEnabled) {
            callData = abi.encodeWithSignature("toggleAI(bool)", p.newValue != 0);
        }

        if (callData.length > 0) {
            (bool success,) = targetContract.call(callData);
            require(success, "GOV: execution failed");
        }

        emit ProposalExecuted(proposalId);
    }

    // --- Adaptive Quorum ---
    /// @dev Adjusts quorum based on recent participation.
    ///      High participation → lower quorum (efficient governance).
    ///      Low participation → higher quorum (ensure legitimacy).
    function _adaptiveQuorum() internal view returns (uint256) {
        if (recentParticipationRate == 0) return quorumPercent;

        // If participation > 70%, reduce quorum toward minQuorum
        // If participation < 30%, raise quorum toward maxQuorum
        if (recentParticipationRate > 7000) {
            return minQuorum;
        } else if (recentParticipationRate < 3000) {
            return maxQuorum;
        } else {
            // Linear interpolation between max and min
            uint256 range = maxQuorum - minQuorum;
            uint256 participationRange = 7000 - 3000;
            uint256 offset = recentParticipationRate - 3000;
            return maxQuorum - (range * offset) / participationRange;
        }
    }

    // --- View ---
    function getProposal(uint256 id) external view returns (Proposal memory) {
        return proposals[id];
    }

    function getAdaptiveQuorum() external view returns (uint256) {
        return _adaptiveQuorum();
    }

    function setVotingDuration(uint256 _duration) external onlyOwner {
        votingDuration = _duration;
    }

    function setTargetContract(address _target) external onlyOwner {
        targetContract = _target;
    }
}
