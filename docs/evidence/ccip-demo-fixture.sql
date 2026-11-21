-- Run only against an empty SenFund demo database after backend.db.DB creates its schema.
-- Reuses a public testnet payment with synthetic pre-payout app state.
BEGIN;
INSERT INTO invoices(id, invoice_id, created_at, usd, amount_units, data, request, payment, conversion, tx_hash)
VALUES ('inv_4fe69ac0f479', '0x01e8abc89bfb2cf890997d7cec8d6bae279851f8c8390e08d976fb7c17a08378',
        unixepoch(), '3', '3000000', '{}',
        '{"invoiceId":"0x01e8abc89bfb2cf890997d7cec8d6bae279851f8c8390e08d976fb7c17a08378","digest":"0x61cd04d65d85cf34b98689ae4234a207cf2e8bd48794ca06f48711848d5a19ed","merchant":"0x09e5f80F0f9C90976116c4f7AEC7F484e8181E19","recipient":"0x09e5f80F0f9C90976116c4f7AEC7F484e8181E19","token":"0xcedfB56113143d55b2358b8CFbB0dEB5Ad2f55a7","amount":"3000000"}',
        'PAID', 'COMPLETED', '0xca8d066095a407552697f77dc866ae939390712a87e38eabb12dc52efc342c62');
INSERT INTO receipts(invoice, chain_id, tx_hash, log_index, block_number, block_hash, payer, amount)
VALUES ('inv_4fe69ac0f479', 1874, '0xca8d066095a407552697f77dc866ae939390712a87e38eabb12dc52efc342c62',
        2, 12352312, '0xdd0d9e3733b2f85ff1af09a4f9bdce910161935a0bbcf7bc58b6803869e051b8',
        '0xaB13Ac7c45E0972d4f84fCFfae9A1f55aC77b883', '3000000');
INSERT INTO operations(key, invoice, stage, status, detail, at)
VALUES ('inv_4fe69ac0f479:conversion:testnet', 'inv_4fe69ac0f479', 'conversion', 'COMPLETED',
        '{"net_usd":"2.50"}', unixepoch());
COMMIT;
