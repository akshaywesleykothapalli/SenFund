# SenFund ENSv2 Setup

Use the [official Ethereum Sepolia deployment](https://docs.ens.domains/learn/deployments/). The SenFund integration reads public records. The ENS owner signs registration, role and record changes in their wallet.

1. Set up a parent and issue a merchant subname using the ENSv2 Permissioned Registry. Attach a dedicated Permissioned Resolver to the subname. Follow the [ENSv2 subname guide](https://docs.ens.domains/ensv2/subnames/).
2. Call `setAddress(bytes,uint256,bytes)` on that resolver with the DNS-encoded merchant subname, Whitechain Sepolia coin type `0x80000752`, and the exact 20-byte payment wallet. Keep the parent resolver's default record unset for this demo. Retain ownership and upgrade rights in the owner wallet. When delegating, use `grantSetterRoles` for this coin-type setter on this dedicated resolver. The delegate must lack the default-address and root roles. [Permissioned Resolver guide](https://docs.ens.domains/ensv2/permissioned-resolver/)
3. Set `SENFUND_ENS_NAME`, `SENFUND_ENS_RESOLVER`, and `SENFUND_ENS_RPC` in `.env`. Use the explicit lowercase ASCII subname and a public HTTPS Ethereum Sepolia RPC that supports browser requests. Checkout publishes this URL.
4. Run `.venv/bin/python scripts/checkout_config.py` after configuring the deployment. Host the generated trust file with checkout. The file pins the merchant signer, token, spender and ENS resolver, independently of the invoice URL.
5. Issue an invoice and open its link. Rotate the explicit record to a second controlled wallet. Verify the original link cannot ask for approval. Cancel or expire the old invoice before issuing a replacement and record both wallet outcomes. In a separate transaction, show that the delegate cannot change another coin type.

## Prepare owner wallet transactions

Generate unsigned Ethereum Sepolia calldata for the explicit Whitechain recipient record. Use the dedicated resolver attached to the subname.

```sh
.venv/bin/python scripts/ens_record.py --name merchant.example.eth \
  --resolver <resolver-address> --recipient <whitechain-recipient>
```

Add `--delegate <operator-address>` to prepare the scoped role grant instead. Review the generated chain ID, resolver address and operation before signing with your Ethereum Sepolia wallet. The helper creates neither the parent nor the subname and never broadcasts transactions. For the rotation test, generate the record update again with the second controlled wallet address.

Checkout verifies the signed request against the pinned settlement contract and resolves the explicit record both before approval and before settlement. The chain contract pays the address inside the signature. The ENS lookup is a checkout policy and does not revoke an already signed invoice onchain. Use contract cancellation or expiry for revocation. The dashboard, receipt and independent checkout disclose the two different test networks.
