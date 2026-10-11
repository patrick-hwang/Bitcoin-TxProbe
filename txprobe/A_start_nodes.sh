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
# 1. Khởi động Tor
# ==========================================
echo -e "${CYAN}    Starting Tor daemon...${NC}"

# Đường dẫn tor trên Linux (mặc định tìm theo PATH hoặc /usr/bin/tor)
TOR_BIN=$(command -v tor || echo "/usr/bin/tor")

# Đường dẫn file cấu hình torrc (thay đổi nếu bạn đặt ở đường dẫn khác)
TORRC_PATH="/mnt/ssd/hdhphat-mindfullab/Bitcoin-TxProbe/torrc"
TOR_LOG="/tmp/tor_bootstrap.log"

if [ ! -x "$TOR_BIN" ]; then
    echo -e "${RED}[!] tor not found at $TOR_BIN. Vui lòng cài đặt: sudo apt install tor${NC}"
    exit 1
fi

if [ ! -f "$TORRC_PATH" ]; then
    echo -e "${RED}[!] torrc not found at $TORRC_PATH${NC}"
    exit 1
fi

EXISTING_TOR_PID=$(pgrep -f "tor.*-f ${TORRC_PATH}" || true)
if [ -n "$EXISTING_TOR_PID" ]; then
    echo -e "${GREEN}    Tor daemon is already running (PID: ${EXISTING_TOR_PID}). Skipping startup.${NC}"
else
    if [ -f "$TOR_LOG" ]; then
        echo "Remove existed tor log $TOR_LOG"
        rm -f "$TOR_LOG"
    fi

    # Chạy Tor ngầm và ghi log để theo dõi tiến trình bootstrap
    "$TOR_BIN" -f "$TORRC_PATH" --Log "notice file $TOR_LOG" >/dev/null 2>&1 &
    TOR_PID=$!

    # Đợi Tor bootstrap đạt 100%
    echo -en "${GRAY}    Waiting for Tor to bootstrap...${NC}"

    while true; do
        if [ -f "$TOR_LOG" ] && grep -q "Bootstrapped 100%" "$TOR_LOG"; then
            break
        fi

        echo -en "${GRAY}.${NC}"

        # Kiểm tra xem tiến trình Tor có còn hoạt động không
        if ! kill -0 "$TOR_PID" 2>/dev/null; then
            echo -e "\n${RED}[!] Tor is terminated.${NC}"
            exit 1
        fi

        sleep 2
    done
    echo ""
    echo -e " ${GREEN}Ready!${NC}"
fi

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
