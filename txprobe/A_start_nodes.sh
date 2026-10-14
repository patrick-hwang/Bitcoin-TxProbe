#!/usr/bin/env bash
set -e

# ==========================================
# Định nghĩa màu hiển thị console
# ==========================================
CYAN='\033[0;36m'
RED='\033[0;31m'
GREEN='\033[0;32m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# ==========================================
# 1. Khởi động các Tor Instances (1 cho 2 Probes + 5 cho 30 Groundtruth)
# ==========================================
echo -e "${CYAN}    Starting Tor daemons (Multi-Instance)...${NC}"

TOR_BIN=$(command -v tor || echo "/usr/bin/tor")
TOR_BASE_DIR="/mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/tor/instances"

if [ ! -x "$TOR_BIN" ]; then
    echo -e "${RED}[!] tor not found at $TOR_BIN. Vui lòng cài đặt: sudo apt install tor${NC}"
    exit 1
fi

TOR_INSTANCES=("tor_probe" "tor_gt1" "tor_gt2" "tor_gt3" "tor_gt4" "tor_gt5")

for inst in "${TOR_INSTANCES[@]}"; do
    INST_DIR="${TOR_BASE_DIR}/${inst}"
    INST_CONF="${INST_DIR}/torrc"
    INST_LOG="/tmp/${inst}_bootstrap.log"

    if [ ! -f "$INST_CONF" ]; then
        echo -e "${RED}[!] Configuration not found: $INST_CONF${NC}"
        exit 1
    fi

    EXISTING_PID=$(pgrep -f "tor.*-f ${INST_CONF}" || true)
    if [ -n "$EXISTING_PID" ]; then
        echo -e "${GREEN}    Tor instance [${inst}] already running (PID: ${EXISTING_PID}). Skipping.${NC}"
        continue
    fi

    rm -f "$INST_LOG"
    "$TOR_BIN" -f "$INST_CONF" --Log "notice file $INST_LOG" >/dev/null 2>&1 &
    INST_PID=$!

    echo -en "${GRAY}    Waiting for [${inst}] (PID ${INST_PID}) to bootstrap...${NC}"
    while true; do
        if [ -f "$INST_LOG" ] && grep -q "Bootstrapped 100%" "$INST_LOG"; then
            echo -e " ${GREEN}Ready!${NC}"
            break
        fi

        echo -en "${GRAY}.${NC}"

        if ! kill -0 "$INST_PID" 2>/dev/null; then
            echo -e "\n${RED}[!] Tor instance [${inst}] terminated unexpectedly! Check ${INST_LOG}${NC}"
            exit 1
        fi
        sleep 1
    done
done

# ==========================================
# 2. Khởi động 32 Bitcoin Nodes (2 probes: 0,1 + 30 groundtruth: 2-31)
# ==========================================
echo -e "${CYAN}[*] Starting Bitcoin Nodes...${NC}"

BITCOIND_CUSTOM="/mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/build/bin/bitcoind"
BITCOIND_OFFICIAL="/mnt/ssd/hdhphat-mindfullab/bitcoin-31.1/bin/bitcoind"

# Kiểm tra sự tồn tại của cả hai phiên bản bitcoind
if [ ! -x "$BITCOIND_CUSTOM" ]; then
    echo -e "${RED}[!] Custom bitcoind not found or not executable at: $BITCOIND_CUSTOM${NC}"
    exit 1
fi

if [ ! -x "$BITCOIND_OFFICIAL" ]; then
    echo -e "${RED}[!] Official bitcoind not found or not executable at: $BITCOIND_OFFICIAL${NC}"
    exit 1
fi

START_NODE_ID=${1:-0}
END_NODE_ID=${2:-31}

for ((i=START_NODE_ID; i<=END_NODE_ID; i++)); do
    # Phân loại binary thực thi theo yêu cầu:
    # Node 0 và 1 dùng TxProbe, từ node 2 đến 31 dùng bản official 31.1
    if [ "$i" -eq 0 ] || [ "$i" -eq 1 ]; then
        BITCOIND_BIN="$BITCOIND_CUSTOM"
        NOTE="[TxProbe]"
    else
        BITCOIND_BIN="$BITCOIND_OFFICIAL"
        NOTE="[Official 31.1]"
    fi

    DATA_DIR="/mnt/ssd/hdhphat-mindfullab/node-data/bitcoin-$i"
    CONF_FILE="${DATA_DIR}/bitcoin.conf"
    NODE_TITLE="Bitcoind-$i"

    # Kiểm tra thư mục dữ liệu
    if [ ! -d "$DATA_DIR" ]; then
        echo -e "${RED}[!] Data directory not found: $DATA_DIR (bỏ qua node $i)${NC}"
        continue
    fi

    EXTRA_ARGS=""
    if [ "$i" -eq 0 ] || [ "$i" -eq 1 ]; then
        EXTRA_ARGS="-txprobelogfile=/mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/txprobe/txprobe_${i}.log"
    fi

    # Khởi động bitcoind ở chế độ daemon (tăng rpcthreads và rpcworkqueue để xử lý kết nối song song)
    if [ -f "$CONF_FILE" ]; then
        "$BITCOIND_BIN" -datadir="$DATA_DIR" -conf="$CONF_FILE" -rpcthreads=64 -rpcworkqueue=256 $EXTRA_ARGS -daemon
    else
        "$BITCOIND_BIN" -datadir="$DATA_DIR" -rpcthreads=64 -rpcworkqueue=256 $EXTRA_ARGS -daemon
    fi
done

echo -e "\n${GREEN}[+] All nodes (${START_NODE_ID}..${END_NODE_ID}) and Tor have been launched!${NC}"
