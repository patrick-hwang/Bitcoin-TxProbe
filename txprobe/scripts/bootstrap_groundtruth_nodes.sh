#!/usr/bin/env bash
# ==============================================================================
# Script: bootstrap_groundtruth_nodes.sh
# Mục đích: Tự động khởi tạo dữ liệu và cấu hình cho các groundtruth nodes (7..31)
# từ node mẫu bitcoin-2 đã được prune sạch (1.1 GB).
# ==============================================================================

set -euo pipefail

BASE_DIR="/mnt/ssd/hdhphat-mindfullab"
NODE_DATA_DIR="${BASE_DIR}/node-data"
SOURCE_NODE="${NODE_DATA_DIR}/bitcoin-2"

if [ ! -d "$SOURCE_NODE" ]; then
    echo "[!] Source node $SOURCE_NODE does not exist."
    exit 1
fi

echo "[*] Verifying source node template..."
if [ ! -d "${SOURCE_NODE}/testnet4/chainstate" ] || [ ! -d "${SOURCE_NODE}/testnet4/blocks" ]; then
    echo "[!] chainstate or blocks missing in ${SOURCE_NODE}/testnet4."
    exit 1
fi

echo "[*] Source node size:"
du -sh "$SOURCE_NODE"

# Cập nhật prune=550 cho các node cũ 0..6
echo "[*] Updating prune=550 for existing nodes 0..6..."
for i in {0..6}; do
    CONF="${NODE_DATA_DIR}/bitcoin-${i}/bitcoin.conf"
    if [ -f "$CONF" ]; then
        sed -i 's/^prune=.*/prune=550/' "$CONF"
    fi
done

echo "[*] Bootstrapping groundtruth nodes 7 to 31..."

for i in {7..31}; do
    TARGET_DIR="${NODE_DATA_DIR}/bitcoin-${i}"
    TARGET_TESTNET="${TARGET_DIR}/testnet4"
    CONF_FILE="${TARGET_DIR}/bitcoin.conf"

    RPCPORT=$((48332 + 3 * i))
    PORT=$((48333 + 3 * i))
    ONION_PORT=$((19000 + 10 * i))
    TORCONTROL_PORT=$((19001 + 10 * i))

    echo "--- Bootstrapping Node ${i} (RPC: ${RPCPORT}, P2P: ${PORT}, Onion: ${ONION_PORT}) ---"

    mkdir -p "$TARGET_TESTNET"

    # Tạo bitcoin.conf
    cat <<EOF > "$CONF_FILE"
datadir=${TARGET_DIR}

# Global settings
chain=testnet4
server=1
listen=1

# Testnet4 specific settings
[testnet4]
rpcport=${RPCPORT}
port=${PORT}
rpcuser=expuser${i}
rpcpassword=strongpassword${i}
rpcallowip=127.0.0.1

# Proxy
onion=127.0.0.1:${ONION_PORT}
torcontrol=127.0.0.1:${TORCONTROL_PORT}

# Prune mode & performance
prune=550
dbcache=150
maxmempool=100

# Debug
# debug=net
# maxlogsize=0
EOF

    # Copy blocks và chainstate từ source node (bỏ qua nếu đã tồn tại)
    if [ ! -d "${TARGET_TESTNET}/chainstate" ]; then
        echo "  Copying chainstate..."
        cp -a "${SOURCE_NODE}/testnet4/chainstate" "${TARGET_TESTNET}/"
    fi

    if [ ! -d "${TARGET_TESTNET}/blocks" ]; then
        echo "  Copying blocks..."
        cp -a "${SOURCE_NODE}/testnet4/blocks" "${TARGET_TESTNET}/"
    fi

    # Đảm bảo không tồn tại các file identity / state của node cũ
    rm -f "${TARGET_TESTNET}/onion_v3_private_key" \
          "${TARGET_TESTNET}/peers.dat" \
          "${TARGET_TESTNET}/banlist.json" \
          "${TARGET_TESTNET}/bitcoind.pid" \
          "${TARGET_TESTNET}/debug.log" \
          "${TARGET_TESTNET}/settings.json" \
          "${TARGET_TESTNET}/fee_estimates.dat" \
          "${TARGET_TESTNET}/.lock"
done

echo ""
echo "[+] All groundtruth nodes 7 to 31 successfully bootstrapped!"
echo "[*] Total disk usage for node-data:"
du -sh "$NODE_DATA_DIR"
df -h "$BASE_DIR"
