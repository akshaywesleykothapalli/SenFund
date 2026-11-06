// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

/// @title SenFund invoice settlement
/// @notice Pays a merchant-signed PaymentRequest exactly once. No private invoice data is onchain.
contract SenFundSettlement is EIP712, ReentrancyGuard {
    using SafeERC20 for IERC20;

    bytes32 public constant PAYMENT_REQUEST_TYPEHASH = keccak256(
        "PaymentRequest(bytes32 invoiceId,address merchant,address recipient,address token,uint256 amount,uint256 expiry)"
    );

    uint8 public constant OPEN = 0;
    uint8 public constant SETTLED = 1;
    uint8 public constant CANCELLED = 2;

    /// merchant => invoiceId => OPEN | SETTLED | CANCELLED
    mapping(address => mapping(bytes32 => uint8)) public invoiceState;

    event InvoiceSettled(
        bytes32 indexed invoiceId,
        bytes32 indexed digest,
        address indexed payer,
        address merchant,
        address recipient,
        address token,
        uint256 amount
    );
    event InvoiceCancelled(bytes32 indexed invoiceId, address indexed merchant);

    error RequestExpired();
    error InvoiceNotOpen(uint8 state);
    error BadSignature();
    error ZeroAmount();
    error TransferShortfall(uint256 received, uint256 expected);

    constructor() EIP712("SenFund", "1") {}

    function digest(
        bytes32 invoiceId,
        address merchant,
        address recipient,
        address token,
        uint256 amount,
        uint256 expiry
    ) public view returns (bytes32) {
        return _hashTypedDataV4(
            keccak256(abi.encode(PAYMENT_REQUEST_TYPEHASH, invoiceId, merchant, recipient, token, amount, expiry))
        );
    }

    /// @notice Read-only pre-flight used by the static checkout: returns the digest, whether the
    /// signature is the merchant's, and the invoice's current onchain state.
    function checkRequest(
        bytes32 invoiceId,
        address merchant,
        address recipient,
        address token,
        uint256 amount,
        uint256 expiry,
        bytes calldata signature
    ) external view returns (bytes32 d, bool signatureValid, uint8 state) {
        d = digest(invoiceId, merchant, recipient, token, amount, expiry);
        (address signer, ECDSA.RecoverError err,) = ECDSA.tryRecover(d, signature);
        signatureValid = err == ECDSA.RecoverError.NoError && signer == merchant;
        state = invoiceState[merchant][invoiceId];
    }

    function settle(
        bytes32 invoiceId,
        address merchant,
        address recipient,
        address token,
        uint256 amount,
        uint256 expiry,
        bytes calldata signature
    ) external nonReentrant {
        if (block.timestamp > expiry) revert RequestExpired();
        if (amount == 0) revert ZeroAmount();
        uint8 state = invoiceState[merchant][invoiceId];
        if (state != OPEN) revert InvoiceNotOpen(state);

        bytes32 d = digest(invoiceId, merchant, recipient, token, amount, expiry);
        (address signer, ECDSA.RecoverError err,) = ECDSA.tryRecover(d, signature);
        if (err != ECDSA.RecoverError.NoError || signer != merchant) revert BadSignature();

        // Effects before interaction; a failed transfer reverts this write too, so the invoice stays open.
        invoiceState[merchant][invoiceId] = SETTLED;

        IERC20 t = IERC20(token);
        uint256 before = t.balanceOf(recipient);
        t.safeTransferFrom(msg.sender, recipient, amount);
        uint256 received = t.balanceOf(recipient) - before;
        if (received != amount) revert TransferShortfall(received, amount);

        emit InvoiceSettled(invoiceId, d, msg.sender, merchant, recipient, token, amount);
    }

    /// @notice Merchant voids an unpaid invoice so a leaked request can no longer be paid.
    function cancel(bytes32 invoiceId) external {
        uint8 state = invoiceState[msg.sender][invoiceId];
        if (state != OPEN) revert InvoiceNotOpen(state);
        invoiceState[msg.sender][invoiceId] = CANCELLED;
        emit InvoiceCancelled(invoiceId, msg.sender);
    }
}
