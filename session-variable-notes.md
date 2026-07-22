# Session variables 2026-07-22
- Infer topology of a graph of 5 nodes:
  + Node 1
  + Node 2
  + Node 3
  + Node 4
  + Node 5

- Total number of edges: 5 * 4 / 2 = 10

## Steps for a round
- Preparing:
  + (n + 1) conflicting spending transaction: First n transactions = parents, Last one = a flooding transaction.
  + n marker transactions from n parent transactions.
- Phase 1: INV Block --> Use: sendinv_orphan().
  + Sending INV messages of (n + 1) conflicting transaction to all nodes.
- Phase 2: Sending transactions --> Use: sendtxs_orphan().
  + Sending all flooding transactions to set B.
  + Wait 30 seconds.
  + Sending all parent transactions to set A: ptx1 --> peer1, ptx2 --> peer2, ...
  + Wait 30 seconds.
  + Sending all marker transactions to set A: mtx1 --> peer1, mtx2 --> peer2, ...
- Phase 3: Send INVs of marker transactions to the sink set --> Use: sendinv_orphan()
  + Sending all the markers to set B.
- Phase 4: Infer the topology
  + Wait 30 seconds.
  + Check for logs of getdata from peers (node 1, 2, 3, 4, 5).
  + If a peer i does not require data for mtxj then i is connected to j
- Phase 5: Send real transaction --> Use: original sendrawtransaction()
  + Send 1 arbitrary parent transaction into mempool
  + Send the corresponding marker transaction into mempool

## Script:
### Round 1:
  - Set A = {4, 5}
  - Set B = {1, 2, 3}
  - Number of infered edges = 6: 1-4, 1-5, 2-4, 2-5, 3-4, 3-5

### Round 2:
  - Set A = {4, 1}
  - Set B = {2, 3, 5}
  - Number of infered edges = 3: 1-2, 1-3, 4-5

Round 3:
  - Set A = {2}
  - Set B = {3}
  - Number of infered edges = 1: 2-3


# Session variables
- Node 0 address: tb1qg62dlyjz64gvg2uq5ffp3wwlstfqesw3kpr28t
- UTXO's txid: 3d37b03fa8751ff48ff8f09d3d2fdb76ab3001b10b682593b848339aa4e4ea06
  - vout: 0
  - amount: 0.00199000
- $P_TX_RAW: 020000000106eae4a49a3348b89325680bb10130ab76db2f3d9df0f88ff41f75a83fb0373d0000000000fdffffff0170050300000000001600144694df9242d550c42b80a25218b9df82d20cc1d100000000
- $P_TX_SIGNED:
{
  "hex": "0200000000010106eae4a49a3348b89325680bb10130ab76db2f3d9df0f88ff41f75a83fb0373d0000000000fdffffff0170050300000000001600144694df9242d550c42b80a25218b9df82d20cc1d10247304402205886db398bedd8f639d7e79f184f9e6f7bdbb4c9b3e684cffcedcdd86502c16d0220779f3a216ac54880a7046f999846b18bba9a523e583b67816ffc1ef5f3c80b78012103e6d1e10f8fdd7525cb1b3e85e60a4e7cc3546b4764fec33fb7176cc3a51e186900000000", 
  "complete": true
}
- $P_TX_HEX:
0200000000010106eae4a49a3348b89325680bb10130ab76db2f3d9df0f88ff41f75a83fb0373d0000000000fdffffff0170050300000000001600144694df9242d550c42b80a25218b9df82d20cc1d10247304402205886db398bedd8f639d7e79f184f9e6f7bdbb4c9b3e684cffcedcdd86502c16d0220779f3a216ac54880a7046f999846b18bba9a523e583b67816ffc1ef5f3c80b78012103e6d1e10f8fdd7525cb1b3e85e60a4e7cc3546b4764fec33fb7176cc3a51e186900000000
- $P_TX_DECODED:
{ 
    "txid": "1dbbfdd32b761d91c3f18d919454ff00d511cd75cfcd41761a2e38b7a3cf9663", 
    "hash": "12e365dcd0b849e5bee191e8e5debc788f0757dfaa07331132bdf89ba8bc5652", 
    "version": 2, 
    "size": 191, 
    "vsize": 110, 
    "weight": 437, 
    "locktime": 0, 
    "vin": [{ 
      "txid": "3d37b03fa8751ff48ff8f09d3d2fdb76ab3001b10b682593b848339aa4e4ea06", 
      "vout": 0, 
      "scriptSig": { "asm": "", "hex": "" }, 
      "txinwitness": [  
        "304402205886db398bedd8f639d7e79f184f9e6f7bdbb4c9b3e684cffcedcdd86502c16d0220779f3a216ac54880a7046f999846b18bba9a523e583b67816ffc1ef5f3c80b7801",   
        "03e6d1e10f8fdd7525cb1b3e85e60a4e7cc3546b4764fec33fb7176cc3a51e1869" ], 
      "sequence": 4294967293 
      }],
    "vout": [{ 
      "value": 0.00198000, 
      "n": 0, 
      "scriptPubKey": { 
        "asm": "0 4694df9242d550c42b80a25218b9df82d20cc1d1",
        "desc": "addr(tb1qg62dlyjz64gvg2uq5ffp3wwlstfqesw3kpr28t)#cdaq03y5", 
        "hex": "00144694df9242d550c42b80a25218b9df82d20cc1d1",
        "address": "tb1qg62dlyjz64gvg2uq5ffp3wwlstfqesw3kpr28t", 
        "type": "witness_v0_keyhash" 
        } 
      }] 
}
- $P_TXID:
1dbbfdd32b761d91c3f18d919454ff00d511cd75cfcd41761a2e38b7a3cf9663
- $P_TX_SCRIPT_PUBKEY:
00144694df9242d550c42b80a25218b9df82d20cc1d1
- $M_TX_RAW:
02000000016396cfa3b7382e1a7641cdcf75cd11d500ff5494918df1c3911d762bd3fdbb1d0000000000fdffffff0188010300000000001600144694df9242d550c42b80a25218b9df82d20cc1d100000000
- $M_TX_SIGNED:
{ 
  "hex": "020000000001016396cfa3b7382e1a7641cdcf75cd11d500ff5494918df1c3911d762bd3fdbb1d0000000000fdffffff0188010300000000001600144694df9242d550c42b80a25218b9df82d20cc1d10247304402202f0d38fef7195e850e0bd788a8c14d9d46f1f6bd2c74ff21a1277f8a51f617ec02204c69356f3074365df8e8e2f3774482996eb39bf00758e98c8f9177b20c88762a012103e6d1e10f8fdd7525cb1b3e85e60a4e7cc3546b4764fec33fb7176cc3a51e186900000000", 
  "complete": true 
}
- $M_TX_HEX:
020000000001016396cfa3b7382e1a7641cdcf75cd11d500ff5494918df1c3911d762bd3fdbb1d0000000000fdffffff0188010300000000001600144694df9242d550c42b80a25218b9df82d20cc1d10247304402202f0d38fef7195e850e0bd788a8c14d9d46f1f6bd2c74ff21a1277f8a51f617ec02204c69356f3074365df8e8e2f3774482996eb39bf00758e98c8f9177b20c88762a012103e6d1e10f8fdd7525cb1b3e85e60a4e7cc3546b4764fec33fb7176cc3a51e186900000000
- tor --hash-password "pathwa"
Jul 10 11:31:49.926 [warn] Path for GeoIPFile (<default>) is relative and will resolve to C:\Users\Dell\<default>. Is this what you wanted?
Jul 10 11:31:49.926 [warn] Path for GeoIPv6File (<default>) is relative and will resolve to C:\Users\Dell\<default>. Is this what you wanted?
16:334410870313A2C5605275B27E8C111376F43E534FAC0EE96A0EFDDF17
- Node 1's address: 
{
  "address": "xcac3qccz3w4xt5zync645hpbanzmlxzdwlxvbwioms7n62oy6rop6qd.onion",
  "port": 48333
}

# Current progress:
- Đã chuẩn bị xong giao dịch.
- Đã nâng cấp lên phiên bảng version 31.1.
- Xác định đoạn code chặn giao dịch:
  - File ./src/validation.cpp, cụ thể, hàm bool MemPoolAccept::PreChecks(ATMPArgs& args, Workspace& ws).
- Tạo câu lệnh bitcoin-cli mới có luồng đi như sau:
  - sendrawtransaction_orphan $\rightarrow$
  - BroadcastTransaction_orphan $\rightarrow$
  - ProcessTransaction_orphan $\rightarrow$
  - AcceptToMemoryPool_orphan $\rightarrow$
  - AcceptSingleTransactionAndCleanup_orphan $\rightarrow$
  - AcceptSingleTransactionInternal_orphan $\rightarrow$
  - PreChecks_orphan $\rightarrow$
  - CheckTxInputs_orphan
- Tạo hàm lan truyền giao dịch mồ côi:
  - Luồng đi khi gọi gửi giao dịch mồ côi: