# Notes for raw transactions

## Validations
- Description: Steps for validating the transaction before sending to a peer.
- Purpose: To avoid penalty from peer.

### 1. Syntax validation
- Check if the syntax is correct:
- Reference: function DecodeHexTx() in ./src/core_id.cpp

### 2. Standardness validation
- Check if the trasaction is in standard form
- Reference: ./src/policy/policy.cpp $\rightarrow$ IsStandardTx()

### 3. Size >= 65 bytes non-witness
- Check if the transaction's serialize size greater then 65
- Purpose: Avoid a specific DoS
- Reference: ./src/validation.cpp $\rightarrow$ PreChecks()

### Not sent validation
- Check if we already sent an INV message about the transaction
- Reference: ./src/net_processing.cpp $\rightarrow$ SendMessages()

### Bloom filter validation
- Check if the transaction go through the bloom filer
- Reference: ./src/net_processing.cpp $\rightarrow$ SendMessages()

### Peer handshake
- Check if the handshake has done: m_next_inv_send_time != 0
- Reference: ./src/net_processing.cpp $\rightarrow$ InitiateTxBroadcastToAll()

## Functions to send transaction
- MakeAndPushMessage, PushMessage in ./src/net_processing.cpp