const hre = require("hardhat");

async function main() {
    const MedicalAudit = await hre.ethers.getContractFactory("MedicalAudit");
    const contract = await MedicalAudit.deploy();

    const address = contract.target ?? contract.address;
    console.log("MedicalAudit deployed to:", address);
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});