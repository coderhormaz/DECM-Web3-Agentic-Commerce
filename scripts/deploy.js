const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying with:", deployer.address);
  console.log("Balance:", hre.ethers.formatEther(await hre.ethers.provider.getBalance(deployer.address)));

  // 1. Deploy MockAgenticAI (rule-based bot for Phase 3 ablation)
  const MockAI = await hre.ethers.getContractFactory("MockAgenticAI");
  const mockAI = await MockAI.deploy(
    true,  // alwaysApprove
    200,   // 2% price adjustment
    8500   // 85% confidence
  );
  await mockAI.waitForDeployment();
  const mockAIAddr = await mockAI.getAddress();
  console.log("MockAgenticAI:", mockAIAddr);

  // 2. Deploy DECMCore with AI enabled
  const DECMCore = await hre.ethers.getContractFactory("DECMCore");
  const core = await DECMCore.deploy(
    mockAIAddr,
    "https://decm.example/metadata/{id}.json"
  );
  await core.waitForDeployment();
  const coreAddr = await core.getAddress();
  console.log("DECMCore:", coreAddr);

  // 3. Deploy DECMIdentity
  const DECMIdentity = await hre.ethers.getContractFactory("DECMIdentity");
  const identity = await DECMIdentity.deploy();
  await identity.waitForDeployment();
  const identityAddr = await identity.getAddress();
  console.log("DECMIdentity:", identityAddr);

  // 4. Deploy DECMGovernance pointing at DECMCore
  const DECMGovernance = await hre.ethers.getContractFactory("DECMGovernance");
  const governance = await DECMGovernance.deploy(coreAddr);
  await governance.waitForDeployment();
  const governanceAddr = await governance.getAddress();
  console.log("DECMGovernance:", governanceAddr);

  // Output addresses for scripts
  const addresses = {
    mockAgenticAI: mockAIAddr,
    decmCore: coreAddr,
    decmIdentity: identityAddr,
    decmGovernance: governanceAddr,
    deployer: deployer.address,
    network: hre.network.name,
    chainId: (await hre.ethers.provider.getNetwork()).chainId.toString(),
  };

  console.log("\n--- Deployment Summary ---");
  console.log(JSON.stringify(addresses, null, 2));

  // Write addresses to data/ for Python scripts
  const fs = require("fs");
  fs.writeFileSync(
    "./data/deployed_addresses.json",
    JSON.stringify(addresses, null, 2)
  );
  console.log("Addresses written to data/deployed_addresses.json");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
