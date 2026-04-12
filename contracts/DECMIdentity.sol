// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title DECMIdentity
 * @notice Simplified on-chain DID registry for the DECM framework.
 *         Anchors W3C DID document hashes on-chain, enabling verifiable
 *         credential lookups for buyer/seller agents.
 */
contract DECMIdentity is Ownable {
    struct DIDRecord {
        bytes32 didHash;           // keccak256 of the DID document
        string  didURI;            // e.g. "did:decm:monad:0x..."
        uint256 registeredAt;
        uint256 updatedAt;
        bool    active;
        uint8   trustLevel;        // 0-100
    }

    mapping(address => DIDRecord) public identities;
    mapping(bytes32 => address) public didToAddress;
    uint256 public totalRegistered;

    event DIDRegistered(address indexed account, bytes32 didHash, string didURI);
    event DIDUpdated(address indexed account, bytes32 newDidHash);
    event DIDDeactivated(address indexed account);
    event TrustLevelUpdated(address indexed account, uint8 newLevel);

    constructor() Ownable(msg.sender) {}

    function registerDID(
        address account,
        bytes32 didHash,
        string calldata didURI
    ) external onlyOwner {
        require(!identities[account].active, "DID: already registered");

        identities[account] = DIDRecord({
            didHash: didHash,
            didURI: didURI,
            registeredAt: block.timestamp,
            updatedAt: block.timestamp,
            active: true,
            trustLevel: 50
        });
        didToAddress[didHash] = account;
        totalRegistered++;

        emit DIDRegistered(account, didHash, didURI);
    }

    function registerDIDBatch(
        address[] calldata accounts,
        bytes32[] calldata didHashes,
        string[] calldata didURIs
    ) external onlyOwner {
        require(
            accounts.length == didHashes.length && accounts.length == didURIs.length,
            "DID: length mismatch"
        );
        for (uint256 i = 0; i < accounts.length; i++) {
            if (!identities[accounts[i]].active) {
                identities[accounts[i]] = DIDRecord({
                    didHash: didHashes[i],
                    didURI: didURIs[i],
                    registeredAt: block.timestamp,
                    updatedAt: block.timestamp,
                    active: true,
                    trustLevel: 50
                });
                didToAddress[didHashes[i]] = accounts[i];
                totalRegistered++;
                emit DIDRegistered(accounts[i], didHashes[i], didURIs[i]);
            }
        }
    }

    function updateDID(address account, bytes32 newDidHash) external onlyOwner {
        require(identities[account].active, "DID: not registered");
        bytes32 oldHash = identities[account].didHash;
        delete didToAddress[oldHash];
        identities[account].didHash = newDidHash;
        identities[account].updatedAt = block.timestamp;
        didToAddress[newDidHash] = account;
        emit DIDUpdated(account, newDidHash);
    }

    function deactivateDID(address account) external onlyOwner {
        require(identities[account].active, "DID: not registered");
        identities[account].active = false;
        emit DIDDeactivated(account);
    }

    function updateTrustLevel(address account, uint8 level) external onlyOwner {
        require(identities[account].active, "DID: not registered");
        require(level <= 100, "DID: invalid level");
        identities[account].trustLevel = level;
        emit TrustLevelUpdated(account, level);
    }

    function isActive(address account) external view returns (bool) {
        return identities[account].active;
    }

    function getDID(address account) external view returns (DIDRecord memory) {
        return identities[account];
    }

    function resolveDID(bytes32 didHash) external view returns (address) {
        return didToAddress[didHash];
    }
}
