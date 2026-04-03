const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
    const MedicalAudit = await hre.ethers.getContractFactory("MedicalAudit");
    const contract = await MedicalAudit.deploy();

    const address = contract.target ?? contract.address;
    console.log("MedicalAudit deployed to:", address);

    const out = path.join(__dirname, "..", "deployed.json");
    fs.writeFileSync(out, JSON.stringify({ address }, null, 2));
    console.log("Address saved to contracts/deployed.json");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});