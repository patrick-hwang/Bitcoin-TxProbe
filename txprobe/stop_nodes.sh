#!/usr/bin/env bash
# ==============================================================================
# Script: stop_nodes.sh
# Mục đích: Dừng an toàn (graceful shutdown) các Bitcoin nodes và Tor daemon.
# Tránh làm hỏng cơ sở dữ liệu LevelDB (chainstate) và block storage.
# ==============================================================================

set -u

# Màu hiển thị console
CYAN='\033[0;36m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# Đường dẫn mặc định
BASE_DIR="/mnt/ssd/hdhphat-mindfullab"
NODE_DATA_DIR="${BASE_DIR}/node-data"
BITCOIN_CLI="${BASE_DIR}/bitcoin-31.1/bin/bitcoin-cli"
BITCOIN_CLI_CUSTOM="${BASE_DIR}/Bitcoin-TxProbe/build/bin/bitcoin-cli"
TORRC_PATH="${BASE_DIR}/Bitcoin-TxProbe/torrc"

# Giới hạn số node (mặc định hỗ trợ từ node 0 đến 31)
START_ID=${1:-0}
END_ID=${2:-31}

echo -e "${CYAN}======================================================${NC}"
echo -e "${CYAN}   Stopping Bitcoin Nodes (ID: ${START_ID} -> ${END_ID})   ${NC}"
echo -e "${CYAN}======================================================${NC}"

stopped_pids=()

# 1. Gửi lệnh stop đến từng Bitcoin Node
for ((i=START_ID; i<=END_ID; i++)); do
    DATA_DIR="${NODE_DATA_DIR}/bitcoin-${i}"
    CONF_FILE="${DATA_DIR}/bitcoin.conf"
    PID_FILE="${DATA_DIR}/testnet4/bitcoind.pid"

    # Kiểm tra xem node data dir có tồn tại không
    if [ ! -d "$DATA_DIR" ]; then
        continue
    fi

    # Lựa chọn binary bitcoin-cli tương ứng
    CLI_BIN="$BITCOIN_CLI"
    if [ "$i" -eq 0 ] || [ "$i" -eq 1 ]; then
        if [ -x "$BITCOIN_CLI_CUSTOM" ]; then
            CLI_BIN="$BITCOIN_CLI_CUSTOM"
        fi
    fi

    PID=""
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE" 2>/dev/null || true)
    fi

    # Kiểm tra nếu tiến trình đang chạy theo PID file
    IS_RUNNING=0
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        IS_RUNNING=1
    fi

    # Nếu không tìm thấy bằng PID file, kiểm tra qua pgrep theo datadir
    if [ "$IS_RUNNING" -eq 0 ]; then
        MATCHING_PID=$(pgrep -f "bitcoind.*-datadir=${DATA_DIR}" || true)
        if [ -n "$MATCHING_PID" ]; then
            PID="$MATCHING_PID"
            IS_RUNNING=1
        fi
    fi

    if [ "$IS_RUNNING" -eq 0 ]; then
        echo -e "${GRAY}[Node ${i}] Already stopped or not running.${NC}"
        continue
    fi

    echo -en "${YELLOW}[*] Stopping Node ${i} (PID: ${PID})...${NC} "

    # Thử gửi lệnh stop qua bitcoin-cli
    STOP_SENT=0
    if [ -x "$CLI_BIN" ] && [ -f "$CONF_FILE" ]; then
        CLI_OUTPUT=$("$CLI_BIN" -datadir="$DATA_DIR" -conf="$CONF_FILE" stop 2>&1 || true)
        if [[ "$CLI_OUTPUT" =~ "Bitcoin Core stopping" ]] || [[ "$CLI_OUTPUT" =~ "stopping" ]]; then
            STOP_SENT=1
        fi
    fi

    # Nếu bitcoin-cli không gửi được (ví dụ RPC bận hoặc cấu hình khác), gửi SIGTERM
    if [ "$STOP_SENT" -eq 0 ]; then
        kill -TERM "$PID" 2>/dev/null || true
    fi

    stopped_pids+=("$PID")
    echo -e "${GREEN}Stop request sent.${NC}"
done

# 2. Đợi tất cả tiến trình bitcoind dừng hoàn toàn (Tránh dừng đột ngột)
if [ ${#stopped_pids[@]} -gt 0 ]; then
    echo -e "\n${CYAN}[*] Waiting for Bitcoin processes to flush LevelDB and exit cleanly...${NC}"
    MAX_WAIT=30
    WAIT_COUNT=0
    while true; do
        STILL_RUNNING=0
        for pid in "${stopped_pids[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                STILL_RUNNING=1
                break
            fi
        done

        if [ "$STILL_RUNNING" -eq 0 ]; then
            echo -e "${GREEN}[+] All bitcoind processes stopped cleanly!${NC}"
            break
        fi

        WAIT_COUNT=$((WAIT_COUNT + 1))
        if [ "$WAIT_COUNT" -ge "$MAX_WAIT" ]; then
            echo -e "\n${RED}[!] Some bitcoind processes took too long. Forcefully terminating remaining ones...${NC}"
            for pid in "${stopped_pids[@]}"; do
                if kill -0 "$pid" 2>/dev/null; then
                    echo -e "${RED}  Killing PID ${pid}...${NC}"
                    kill -9 "$pid" 2>/dev/null || true
                fi
            done
            break
        fi

        echo -en "${GRAY}.${NC}"
        sleep 1
    done
else
    echo -e "\n${GREEN}[+] No active bitcoind processes found in specified range.${NC}"
fi

# 3. Dừng tất cả Tor Daemons liên quan đến dự án (Chỉ dừng khi dừng toàn bộ cụm nodes 0..31)
if [ "$START_ID" -eq 0 ] && [ "$END_ID" -ge 31 ]; then
    echo -e "\n${CYAN}[*] Checking project Tor daemons (Multi-Instance)...${NC}"
    TOR_PIDS=$(pgrep -f "tor.*instances/tor_|tor.*-f ${TORRC_PATH}" || true)

    if [ -n "$TOR_PIDS" ]; then
        echo -en "${YELLOW}[*] Stopping project Tor daemons (PIDs: ${TOR_PIDS//$'\n'/ })...${NC} "
        echo "$TOR_PIDS" | xargs kill -TERM 2>/dev/null || true
        sleep 1
        for pid in $TOR_PIDS; do
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
        done
        echo -e "${GREEN}Done.${NC}"
    else
        echo -e "${GRAY}[*] No project Tor daemons are running.${NC}"
    fi
else
    echo -e "\n${GRAY}[*] Skipping Tor daemon shutdown because only a subset of nodes was stopped.${NC}"
fi

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}   Shutdown complete! All targets are stopped safely. ${NC}"
echo -e "${GREEN}======================================================${NC}"
