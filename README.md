# DECM — Decentralised Digital Commerce

A Web3 digital commerce project: smart contracts for on-chain commerce, with Python agents alongside them. Based on the research paper included in this repository.

## Features

- Smart contracts in `contracts/`, built on Hardhat and OpenZeppelin
- Python agent code for the off-chain side of the system
- Contract compile and test workflow through Hardhat

## Tech Stack

- Solidity, Hardhat, OpenZeppelin
- JavaScript / Node.js (Hardhat tooling)
- Python (agents)

## Getting Started

Prerequisites: Node.js and npm, and Python 3.

```bash
# 1. Install the Node dependencies
npm install

# 2. Compile and test the contracts
npx hardhat compile
npx hardhat test

# 3. Install the Python dependencies
pip install -r requirements.txt
```

### Environment variables

```bash
cp .env.example .env
```

Then fill in your own values in `.env` — never commit real keys or credentials.

## Project Structure

```text
contracts/   # Solidity smart contracts
```

## Notes

- This is one of several DECM variants in my repositories (`decm`, `new-decm`) — this version is the Hardhat + Python agents one, with no web UI.
- Read the included research paper for the design and background behind the contracts.
