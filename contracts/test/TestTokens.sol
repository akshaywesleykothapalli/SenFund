// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

// Test-only contracts. Never deployed to a public network.
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockUSDT is ERC20 {
    constructor() ERC20("Mock Tether USD", "USDT") {}
    function decimals() public pure override returns (uint8) { return 6; }
    function mint(address to, uint256 amount) external { _mint(to, amount); }
}

/// Takes a 1% fee on transfer, so the recipient receives less than `amount`.
contract FeeOnTransferToken is ERC20 {
    constructor() ERC20("Fee Token", "FEE") {}
    function decimals() public pure override returns (uint8) { return 6; }
    function mint(address to, uint256 amount) external { _mint(to, amount); }
    function _update(address from, address to, uint256 value) internal override {
        if (from != address(0) && to != address(0)) {
            uint256 fee = value / 100;
            super._update(from, address(0xdead), fee);
            value -= fee;
        }
        super._update(from, to, value);
    }
}

/// Emits an event with the same signature as SenFundSettlement.InvoiceSettled from an untrusted address.
contract ForgedEmitter {
    event InvoiceSettled(
        bytes32 indexed invoiceId, bytes32 indexed digest, address indexed payer,
        address merchant, address recipient, address token, uint256 amount
    );
    function forge(bytes32 invoiceId, bytes32 d, address merchant, address recipient, address token, uint256 amount) external {
        emit InvoiceSettled(invoiceId, d, msg.sender, merchant, recipient, token, amount);
    }
}
