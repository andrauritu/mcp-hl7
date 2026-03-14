// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

contract MedicalAudit {

    event AdmissionRecorded(
        uint256 indexed patientId,
        string messageType,
        uint256 timestamp
    );

    event DiagnosisRecorded(
        uint256 indexed patientId,
        string icdCode,
        uint256 timestamp
    );

    function recordAdmission(uint256 patientId, string calldata messageType) external {
        emit AdmissionRecorded (patientId, messageType, block.timestamp);
    }

    function recordDiagnosis (uint256 patientId, string calldata icdCode) external {
        emit DiagnosisRecorded(patientId, icdCode, block.timestamp);
    }
}