# Validation Test Mode plan

Phase 1 is implemented as a read-only snapshot command:

```powershell
python -m txprobe_experiment.main --validation-groundtruth
```

It obtains `getnetworkinfo` from nodes 0--6 and `getpeerinfo` from nodes
1--5, excludes nodes 0 and 6, and discovers external peers through their
normalized `addr` endpoint. It excludes external localhost and IPv6 endpoints
and non-full-relay peers (`block-relay-only`, `addr-fetch`, `feeler`), then
prints `gt_edges` with both directed pairs `(u, v)` and `(v, u)`. This
command does not add, remove, or disconnect peers.

Phase 2 is implemented as:

```powershell
python -m txprobe_experiment.main --validation-phase2
```

It cleans up the `addnode` lists and active peers of nodes 0 and 6, adds a
persistent link to every node in `S_groundtruth_before`, waits for qualifying
full-relay links, then announces one probe transaction from node 0 and, 30
seconds later, from node 6. Node 0 writes `txprobe_0.log` and node 6 writes
`txprobe_6.log` (via `-txprobelogfile`); `S_noinvblock` is read from node
6's log. This required rebuilding `bitcoind` with
`MAX_ADDNODE_CONNECTIONS = 125` in `src/net.h`.

The remaining phases should be implemented in this order:

1. **Phases 3--5 -- transaction delivery:** create the conflicting and marker
   transaction families, verify delivery, and run the TxProbe send sequence.
2. **Phases 6--7 -- validation and observation:** query transaction knowledge,
   track `S_wrong`, then collect `getdata` requests for marker inventories to
   construct `nE`.
3. **Phase 8 -- transitory filter:** take a second peer snapshot, derive the
   after-set, after-edges, and ignored edges `iE`.
4. **Phase 9 -- inference and reporting:** emit aligned ground-truth and
   inference matrices with `*`, `0`, and `1`, followed by metrics.

The current random-topology experiment remains unchanged and is intentionally
separate from this validation command.
