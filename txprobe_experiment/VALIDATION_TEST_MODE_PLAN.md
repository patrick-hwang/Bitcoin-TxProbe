# Validation Test Mode plan

Phase 1 is implemented as a read-only snapshot command:

```powershell
python -m txprobe_experiment.main --validation-groundtruth
```

It obtains `getnetworkinfo` from nodes 0--6 and `getpeerinfo` from nodes
1--5, excludes nodes 0 and 6, and discovers external peers through their
normalized `addr` endpoint. It excludes external localhost and IPv6 endpoints,
then prints `gt_edges` with both directed pairs `(u, v)` and `(v, u)`. This
command does not add, remove, or disconnect peers.

The remaining phases should be implemented in this order:

1. **Phase 2 -- INVBLOCK filter setup:** connect nodes 0 and 6 to the Phase 1
   participant set and wait until RPC confirms the links.
2. **Phases 3--5 -- transaction delivery:** create the conflicting and marker
   transaction families, verify delivery, and run the TxProbe send sequence.
3. **Phases 6--7 -- validation and observation:** query transaction knowledge,
   track `S_wrong`, then collect `getdata` requests for marker inventories to
   construct `nE`.
4. **Phase 8 -- transitory filter:** take a second peer snapshot, derive the
   after-set, after-edges, and ignored edges `iE`.
5. **Phase 9 -- inference and reporting:** emit aligned ground-truth and
   inference matrices with `*`, `0`, and `1`, followed by metrics.

The current random-topology experiment remains unchanged and is intentionally
separate from this validation command.
