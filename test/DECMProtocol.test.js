const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("DECM Protocol", function () {
  let owner, buyer, seller, other;
  let core, mockAI, identity, governance;

  beforeEach(async function () {
    [owner, buyer, seller, other] = await ethers.getSigners();

    // Deploy MockAgenticAI
    const MockAI = await ethers.getContractFactory("MockAgenticAI");
    mockAI = await MockAI.deploy(true, 200, 8500);
    await mockAI.waitForDeployment();

    // Deploy DECMCore with AI
    const DECMCore = await ethers.getContractFactory("DECMCore");
    core = await DECMCore.deploy(
      await mockAI.getAddress(),
      "https://decm.example/{id}.json"
    );
    await core.waitForDeployment();

    // Deploy Identity
    const DECMIdentity = await ethers.getContractFactory("DECMIdentity");
    identity = await DECMIdentity.deploy();
    await identity.waitForDeployment();

    // Deploy Governance
    const DECMGovernance = await ethers.getContractFactory("DECMGovernance");
    governance = await DECMGovernance.deploy(await core.getAddress());
    await governance.waitForDeployment();

    // Register agents
    const buyerDid = ethers.keccak256(ethers.toUtf8Bytes("did:decm:buyer1"));
    const sellerDid = ethers.keccak256(ethers.toUtf8Bytes("did:decm:seller1"));
    await core.registerAgent(buyer.address, buyerDid);
    await core.registerAgent(seller.address, sellerDid);

    // Mint tokens to seller
    await core.mintAsset(seller.address, 1000, "0x");

    // Seller must approve DECMCore to transfer tokens
    await core.connect(seller).setApprovalForAll(await core.getAddress(), true);
  });

  describe("DECMCore", function () {
    it("should register agents with DIDs", async function () {
      expect(await core.registeredAgents(buyer.address)).to.be.true;
      expect(await core.registeredAgents(seller.address)).to.be.true;
      expect(await core.userDIDs(buyer.address)).to.not.equal(ethers.ZeroHash);
    });

    it("should mint ERC-1155 tokens", async function () {
      const balance = await core.balanceOf(seller.address, 0);
      expect(balance).to.equal(1000);
    });

    it("should propose and execute a deal with AI evaluation", async function () {
      const tx = await core.connect(buyer).proposeDeal(
        seller.address,
        0,     // tokenId
        10,    // amount
        1000,  // price
        "0x"   // metadata
      );
      const receipt = await tx.wait();

      // Check events
      const dealProposedEvent = receipt.logs.find(
        (log) => {
          try {
            return core.interface.parseLog(log)?.name === "DealProposed";
          } catch { return false; }
        }
      );
      expect(dealProposedEvent).to.not.be.undefined;

      // Check deal state
      const deal = await core.getDeal(0);
      expect(deal.status).to.equal(2); // Accepted
      expect(deal.buyer).to.equal(buyer.address);
      expect(deal.seller).to.equal(seller.address);

      // Check token transfer
      expect(await core.balanceOf(buyer.address, 0)).to.equal(10);
      expect(await core.balanceOf(seller.address, 0)).to.equal(990);
    });

    it("should execute deal without AI when disabled", async function () {
      await core.toggleAI(false);

      await core.connect(buyer).proposeDeal(
        seller.address, 0, 5, 500, "0x"
      );

      const deal = await core.getDeal(0);
      expect(deal.status).to.equal(2); // Accepted
      expect(deal.finalPrice).to.equal(500); // No AI adjustment
    });

    it("should record telemetry", async function () {
      await core.connect(buyer).proposeDeal(
        seller.address, 0, 10, 1000, "0x"
      );

      expect(await core.totalTransactions()).to.equal(1);
      expect(await core.totalGasUsed()).to.be.gt(0);
    });

    it("should handle disputes", async function () {
      await core.connect(buyer).proposeDeal(
        seller.address, 0, 10, 1000, "0x"
      );

      // Buyer approves core for reverse transfer
      await core.connect(buyer).setApprovalForAll(await core.getAddress(), true);

      await core.connect(buyer).disputeDeal(0);
      const deal = await core.getDeal(0);
      expect(deal.status).to.equal(4); // Disputed

      await core.resolveDispute(0, true);
      const resolved = await core.getDeal(0);
      expect(resolved.status).to.equal(5); // Resolved
    });

    it("should reject self-deals", async function () {
      await expect(
        core.connect(buyer).proposeDeal(buyer.address, 0, 10, 1000, "0x")
      ).to.be.revertedWith("DECM: self-deal");
    });

    it("should reject unregistered agents", async function () {
      await expect(
        core.connect(other).proposeDeal(seller.address, 0, 10, 1000, "0x")
      ).to.be.revertedWith("DECM: not registered");
    });

    it("should batch register agents", async function () {
      const agents = [other.address];
      const dids = [ethers.keccak256(ethers.toUtf8Bytes("did:decm:other"))];
      await core.registerAgentBatch(agents, dids);
      expect(await core.registeredAgents(other.address)).to.be.true;
    });

    it("should update governance parameters", async function () {
      await core.updateBaseFee(50);
      expect(await core.baseFee()).to.equal(50);

      await core.updateCarbonThreshold(200);
      expect(await core.carbonThreshold()).to.equal(200);
    });
  });

  describe("DECMIdentity", function () {
    it("should register and resolve DIDs", async function () {
      const didHash = ethers.keccak256(ethers.toUtf8Bytes("did:decm:monad:buyer1"));
      await identity.registerDID(buyer.address, didHash, "did:decm:monad:buyer1");

      const record = await identity.getDID(buyer.address);
      expect(record.active).to.be.true;
      expect(record.didHash).to.equal(didHash);

      const resolved = await identity.resolveDID(didHash);
      expect(resolved).to.equal(buyer.address);
    });

    it("should update trust levels", async function () {
      const didHash = ethers.keccak256(ethers.toUtf8Bytes("did:decm:monad:s1"));
      await identity.registerDID(seller.address, didHash, "did:decm:monad:s1");

      await identity.updateTrustLevel(seller.address, 85);
      const record = await identity.getDID(seller.address);
      expect(record.trustLevel).to.equal(85);
    });

    it("should batch register DIDs", async function () {
      const accounts = [buyer.address, seller.address];
      const hashes = [
        ethers.keccak256(ethers.toUtf8Bytes("did:1")),
        ethers.keccak256(ethers.toUtf8Bytes("did:2")),
      ];
      const uris = ["did:decm:1", "did:decm:2"];
      await identity.registerDIDBatch(accounts, hashes, uris);
      expect(await identity.totalRegistered()).to.equal(2);
    });
  });

  describe("DECMGovernance", function () {
    beforeEach(async function () {
      await governance.addVoterBatch([
        buyer.address,
        seller.address,
        owner.address,
      ]);
    });

    it("should create and vote on proposals", async function () {
      await governance.connect(buyer).createProposal(
        0,    // BaseFee
        50,   // newValue
        "Increase base fee to 50 bps"
      );

      const proposal = await governance.getProposal(0);
      expect(proposal.status).to.equal(1); // Active

      await governance.connect(buyer).vote(0, true);
      await governance.connect(seller).vote(0, true);
      await governance.connect(owner).vote(0, false);

      const updated = await governance.getProposal(0);
      expect(updated.votesFor).to.equal(2);
      expect(updated.votesAgainst).to.equal(1);
    });

    it("should implement adaptive quorum", async function () {
      const quorum = await governance.getAdaptiveQuorum();
      expect(quorum).to.be.gte(20);
      expect(quorum).to.be.lte(60);
    });

    it("should prevent double voting", async function () {
      await governance.connect(buyer).createProposal(0, 50, "test");
      await governance.connect(buyer).vote(0, true);
      await expect(
        governance.connect(buyer).vote(0, true)
      ).to.be.revertedWith("GOV: already voted");
    });
  });

  describe("MockAgenticAI", function () {
    it("should return adjusted price with configured bps", async function () {
      const [approved, adjustedPrice, confidence] = await mockAI.evaluate.staticCall(
        1, buyer.address, seller.address, 10000, 0, "0x"
      );
      expect(approved).to.be.true;
      expect(adjustedPrice).to.equal(9800); // 10000 - 2%
      expect(confidence).to.equal(8500);
    });
  });
});
