"""Operator relay for the local-only SenFund CRE + CCIP proof."""
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_tester.exceptions import TransactionFailed
from web3 import EthereumTesterProvider, Web3
from web3.exceptions import Web3Exception
from web3.logs import DISCARD

from . import devchain
from .state import InvalidTransition

SOURCE_SELECTOR = 16015286601757825753  # Ethereum Sepolia, stamped by Chainlink Local
DESTINATION_SELECTOR = 16281711391670634445  # Polygon Amoy, logical destination in local mode
ROUTES = {"USE_MUDREX": 1, "USE_P2P": 2}
RECEIPT_TYPES = ["bytes32", "bytes32", "bytes32", "address", "uint32"]


class LocalPayoutRelay:
    def __init__(self):
        self.w3 = Web3(EthereumTesterProvider())
        deployer = self.w3.eth.accounts[0]
        self.operator = Account.create()
        self.w3.provider.ethereum_tester.add_account(self.operator.key.to_0x_hex())
        self.w3.eth.send_transaction({"from": deployer, "to": self.operator.address, "value": 10**18})
        self.router = devchain.deploy(self.w3, "CCIPLocalRouter", deployer)
        self.sender = devchain.deploy(
            self.w3, "PayoutDecisionSender", deployer, None,
            self.router.address, self.operator.address, DESTINATION_SELECTOR,
        )
        self.receiver = devchain.deploy(
            self.w3, "PayoutDecisionReceiver", deployer, None,
            self.router.address, SOURCE_SELECTOR, self.sender.address, self.operator.address,
        )

    @staticmethod
    def receipt_fields(receipt):
        return (
            bytes.fromhex(receipt["digest"][2:]),
            bytes.fromhex(receipt["txHash"][2:]),
            bytes.fromhex(receipt["blockHash"][2:]),
            Web3.to_checksum_address(receipt["recipient"]),
            receipt["logIndex"],
        )

    def envelope(self, receipt, nonce, route, *, expires_at=None):
        digest, tx, block, recipient, index = self.receipt_fields(receipt)
        expiry = self.w3.eth.get_block("latest").timestamp + 300 if expires_at is None else expires_at
        decision = (digest, tx, block, recipient, bytes.fromhex(nonce), expiry, index, ROUTES[route])
        decision_hash = self.receiver.functions.approvalHash(decision).call()
        signature = self.operator.sign_message(encode_defunct(primitive=decision_hash)).signature
        return decision, signature

    def authorize(self, receipt, nonce, route):
        try:
            return self._authorize(receipt, nonce, route)
        except (TransactionFailed, Web3Exception, ValueError) as error:
            raise InvalidTransition("Local CCIP delivery did not confirm a payout approval") from error

    def _authorize(self, receipt, nonce, route):
        fields = self.receipt_fields(receipt)
        digest = fields[0]
        expected = self.w3.keccak(self.w3.codec.encode(RECEIPT_TYPES, fields))
        approval = self.receiver.functions.approvals(digest)
        before = approval.call()
        tx_hash = None
        if before[3] == 0:
            decision, signature = self.envelope(receipt, nonce, route)
            send = self.sender.functions.sendDecision(self.receiver.address, decision, signature)
            tx = send.transact({"from": self.operator.address, "gas": 1_000_000})
            result = self.w3.eth.wait_for_transaction_receipt(tx)
            approved = self.receiver.events.DecisionApproved().process_receipt(result, errors=DISCARD)
            sent = self.sender.events.DecisionSent().process_receipt(result, errors=DISCARD)
            if (result.status != 1 or len(approved) != 1 or len(sent) != 1
                    or approved[0].args.messageId != sent[0].args.messageId
                    or approved[0].args.invoiceDigest != digest or approved[0].args.creRun != bytes.fromhex(nonce)):
                raise InvalidTransition("CCIP receipt did not contain a matching send and approval")
            tx_hash = Web3.to_hex(result.transactionHash)

        receipt_hash, message_id, approved_run, approved_route = approval.call()
        if receipt_hash != expected or approved_route != ROUTES[route] or not any(message_id):
            raise InvalidTransition("Destination approval does not match this settlement and payout route")
        return {
            "mode": "Chainlink Local 0.3.1, CCIP 2.0.0",
            "evmChainId": self.w3.eth.chain_id,
            "sourceSelector": str(SOURCE_SELECTOR),
            "destinationSelector": str(DESTINATION_SELECTOR),
            "router": self.router.address,
            "sender": self.sender.address,
            "receiver": self.receiver.address,
            "transactionHash": tx_hash,
            "messageId": Web3.to_hex(message_id),
            "invoiceDigest": Web3.to_hex(digest),
            "settlementBinding": Web3.to_hex(receipt_hash),
            "approvedRun": approved_run.hex(),
            "beforeRoute": before[3],
            "afterRoute": approved_route,
            "reused": tx_hash is None,
        }
