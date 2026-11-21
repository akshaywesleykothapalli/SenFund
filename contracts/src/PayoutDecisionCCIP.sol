// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {CCIPReceiver} from "@chainlink/contracts-ccip/contracts/applications/CCIPReceiver.sol";
import {IRouterClient} from "@chainlink/contracts-ccip/contracts/interfaces/IRouterClient.sol";
import {Client} from "@chainlink/contracts-ccip/contracts/libraries/Client.sol";
import {ExtraArgsCodec} from "@chainlink/contracts-ccip/contracts/libraries/ExtraArgsCodec.sol";
import {FinalityCodec} from "@chainlink/contracts-ccip/contracts/libraries/FinalityCodec.sol";
import {ECDSA} from "@openzeppelin/contracts@5.3.0/utils/cryptography/ECDSA.sol";
import {MessageHashUtils} from "@openzeppelin/contracts@5.3.0/utils/cryptography/MessageHashUtils.sol";

struct PayoutDecision {
    bytes32 invoiceDigest;
    bytes32 settlementTx;
    bytes32 settlementBlock;
    address recipient;
    bytes16 creRun;
    uint64 expiresAt;
    uint32 logIndex;
    uint8 route;
}

contract PayoutDecisionSender {
    error Unauthorized();
    error IncorrectFee(uint256 required, uint256 supplied);

    IRouterClient public immutable router;
    address public immutable operator;
    uint64 public immutable destinationSelector;

    event DecisionSent(bytes32 indexed messageId, bytes32 indexed invoiceDigest, bytes16 indexed creRun);

    constructor(address router_, address operator_, uint64 destinationSelector_) {
        router = IRouterClient(router_);
        operator = operator_;
        destinationSelector = destinationSelector_;
    }

    function sendDecision(address receiver, PayoutDecision calldata decision, bytes calldata signature)
        external payable returns (bytes32 messageId)
    {
        if (msg.sender != operator) revert Unauthorized();
        Client.EVM2AnyMessage memory message = Client.EVM2AnyMessage({
            receiver: abi.encode(receiver),
            data: abi.encode(decision, signature),
            tokenAmounts: new Client.EVMTokenAmount[](0),
            feeToken: address(0),
            extraArgs: ExtraArgsCodec._getBasicEncodedExtraArgsV3(300_000, FinalityCodec.WAIT_FOR_FINALITY_FLAG)
        });
        uint256 fee = router.getFee(destinationSelector, message);
        if (msg.value != fee) revert IncorrectFee(fee, msg.value);
        messageId = router.ccipSend{value: fee}(destinationSelector, message);
        emit DecisionSent(messageId, decision.invoiceDigest, decision.creRun);
    }
}

contract PayoutDecisionReceiver is CCIPReceiver {
    error UntrustedSource();
    error InvalidDecision();
    error InvalidSignature();
    error AlreadyApproved(bytes32 invoiceDigest);

    struct Approval {
        bytes32 receiptHash;
        bytes32 messageId;
        bytes16 creRun;
        uint8 route;
    }

    uint64 public immutable sourceSelector;
    address public immutable sourceSender;
    address public immutable operator;
    mapping(bytes32 => Approval) public approvals;

    event DecisionApproved(
        bytes32 indexed invoiceDigest, bytes32 indexed messageId, bytes16 indexed creRun, uint8 route
    );

    constructor(address router, uint64 sourceSelector_, address sourceSender_, address operator_) CCIPReceiver(router) {
        sourceSelector = sourceSelector_;
        sourceSender = sourceSender_;
        operator = operator_;
    }

    function approvalHash(PayoutDecision memory decision) public view returns (bytes32) {
        return keccak256(abi.encode("SenFund Payout Decision v1", block.chainid, address(this), decision));
    }

    function _ccipReceive(Client.Any2EVMMessage memory message) internal override {
        if (message.sourceChainSelector != sourceSelector || abi.decode(message.sender, (address)) != sourceSender) {
            revert UntrustedSource();
        }
        (PayoutDecision memory decision, bytes memory signature) = abi.decode(message.data, (PayoutDecision, bytes));
        if (decision.invoiceDigest == bytes32(0) || decision.settlementTx == bytes32(0)
            || decision.settlementBlock == bytes32(0) || decision.recipient == address(0)
            || decision.creRun == bytes16(0) || decision.expiresAt < block.timestamp
            || (decision.route != 1 && decision.route != 2) || message.destTokenAmounts.length != 0) {
            revert InvalidDecision();
        }
        if (approvals[decision.invoiceDigest].route != 0) revert AlreadyApproved(decision.invoiceDigest);
        bytes32 signedHash = MessageHashUtils.toEthSignedMessageHash(approvalHash(decision));
        if (ECDSA.recover(signedHash, signature) != operator) revert InvalidSignature();

        bytes32 receiptHash = keccak256(abi.encode(
            decision.invoiceDigest, decision.settlementTx, decision.settlementBlock, decision.recipient, decision.logIndex
        ));
        approvals[decision.invoiceDigest] = Approval(receiptHash, message.messageId, decision.creRun, decision.route);
        emit DecisionApproved(decision.invoiceDigest, message.messageId, decision.creRun, decision.route);
    }
}
