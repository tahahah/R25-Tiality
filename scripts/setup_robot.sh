#!/bin/bash

# Orchestrates local/remote setup for the robot:
# 1) Discovers MQTT broker by probing candidate hosts/ports
# 2) Discovers the Raspberry Pi by probing candidate hosts over SSH
# 3) Runs Pi setup scripts remotely and starts services under a tmux session (or nohup fallback)
#
# Usage examples:
#   scripts/setup_robot.sh \
#     --broker-candidates "192.168.0.115,10.1.1.78" \
#     --broker-ports "1883,2883" \
#     --pi-candidates "192.168.0.114,raspberrypi.local" \
#     --pi-user pi \
#     --remote-dir "~/R25-Tiality-worktree" \
#     --video-port 50051
#
# Notes:
# - Assumes SSH key-based auth to the Pi (no interactive password prompts).
# - To avoid host key prompts, StrictHostKeyChecking is disabled for discovery only.
# - This script does not launch the local GUI/video client; it prints a ready-to-run command.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --------------------------- Defaults ---------------------------
DEFAULT_BROKER_CANDIDATES="localhost,10.1.1.110,10.1.1.253,10.1.1.78"
DEFAULT_BROKER_PORTS="1883,2883"
DEFAULT_PI_CANDIDATES="10.1.1.228,10.1.1.253,10.1.1.124,raspberrypi.local"
DEFAULT_PI_USER="pi"
DEFAULT_REMOTE_DIR="~/R25-Tiality-worktree"
DEFAULT_VIDEO_PORT="50051"

BROKER_CANDIDATES="$DEFAULT_BROKER_CANDIDATES"
BROKER_PORTS="$DEFAULT_BROKER_PORTS"
PI_CANDIDATES="$DEFAULT_PI_CANDIDATES"
PI_USER="$DEFAULT_PI_USER"
REMOTE_DIR="$DEFAULT_REMOTE_DIR"
VIDEO_PORT="$DEFAULT_VIDEO_PORT"
NO_VIDEO="0"
IDENTITY_FILE=""
BROKER_HOST_FOR_PI_OVERRIDE=""
DRY_RUN="0"
SSH_PASSWORD="pi"
FALLBACK_IDENTITY="$HOME/.ssh/id_rsa_personal"  # Used if password auth fails

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  --broker-candidates CSV   Comma-separated broker hosts to try (default: $DEFAULT_BROKER_CANDIDATES)
  --broker-ports CSV        Comma-separated ports to try (default: $DEFAULT_BROKER_PORTS)
  --pi-candidates CSV       Comma-separated Pi hosts to try (default: $DEFAULT_PI_CANDIDATES)
  --pi-user USER            SSH username for the Pi (default: $DEFAULT_PI_USER)
  --remote-dir PATH         Path to repo on Pi (default: $DEFAULT_REMOTE_DIR)
  --video-port PORT         gRPC video port on the Pi (default: $DEFAULT_VIDEO_PORT)
  --no-video                Do not pass --video_server to run_tiality.sh
  --identity PATH           SSH private key to use (optional)
  --broker-host-for-pi HOST Override broker host passed to the Pi (useful if discovered host is localhost)
  --ssh-password PASS       Password to use when key auth fails (default: pi; requires sshpass)
  --dry-run                 Show what would be done without executing
  -h|--help                 Show this help
EOF
}

# --------------------------- Arg Parse ---------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --broker-candidates) BROKER_CANDIDATES="$2"; shift 2;;
        --broker-ports) BROKER_PORTS="$2"; shift 2;;
        --pi-candidates) PI_CANDIDATES="$2"; shift 2;;
        --pi-user) PI_USER="$2"; shift 2;;
        --remote-dir) REMOTE_DIR="$2"; shift 2;;
        --video-port) VIDEO_PORT="$2"; shift 2;;
        --no-video) NO_VIDEO="1"; shift 1;;
        --identity) IDENTITY_FILE="$2"; shift 2;;
        --broker-host-for-pi) BROKER_HOST_FOR_PI_OVERRIDE="$2"; shift 2;;
        --ssh-password) SSH_PASSWORD="$2"; shift 2;;
        --dry-run) DRY_RUN="1"; shift 1;;
        -h|--help) usage; exit 0;;
        *) echo "Unknown argument: $1"; usage; exit 1;;
    esac
done

# --------------------------- Helpers ---------------------------
require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "ERROR: Required command '$1' not found in PATH" >&2
        exit 1
    fi
}

ssh_base_args=("-o" "BatchMode=yes" "-o" "ConnectTimeout=4")
# Disable host key checking for initial discovery; later connections will use known_hosts
ssh_probe_args=("-o" "StrictHostKeyChecking=no" "-o" "UserKnownHostsFile=/dev/null")
if [[ -n "$IDENTITY_FILE" ]]; then
    ssh_base_args+=("-i" "$IDENTITY_FILE")
fi

ssh_run() {
    local host="$1"; shift
    local remote_cmd="$1"
    local target="$PI_USER@$host"

    echo "  -> Trying key-based SSH to $target" >&2
    # First try key-based (BatchMode) with relaxed host key checks
    if ssh "${ssh_base_args[@]}" "${ssh_probe_args[@]}" "$target" "$remote_cmd"; then
        return 0
    else
        local rc=$?
        echo "     Key-based SSH failed for $target (exit $rc)" >&2
    fi

    # If sshpass is available, try password-based auth
    if command -v sshpass >/dev/null 2>&1; then
        local pass_args=("-o" "PreferredAuthentications=password" "-o" "PubkeyAuthentication=no" "-o" "ConnectTimeout=4" "-o" "StrictHostKeyChecking=no" "-o" "UserKnownHostsFile=/dev/null")
        echo "  -> Trying password SSH (sshpass) to $target" >&2
        if sshpass -p "$SSH_PASSWORD" ssh "${pass_args[@]}" "$target" "$remote_cmd"; then
            return 0
        else
            local rc=$?
            echo "     sshpass password auth failed for $target (exit $rc)" >&2
        fi
    elif [[ -n "$SSH_PASSWORD" ]]; then
        echo "     sshpass not installed; skipping password auth for $target" >&2
    fi

    # If password auth failed, try hardcoded fallback identity key
    if [[ -f "$FALLBACK_IDENTITY" ]]; then
        local fb_args=("-o" "BatchMode=yes" "-o" "ConnectTimeout=4" "-o" "StrictHostKeyChecking=no" "-o" "UserKnownHostsFile=/dev/null" "-i" "$FALLBACK_IDENTITY")
        echo "  -> Trying fallback key $FALLBACK_IDENTITY for $target" >&2
        if ssh "${fb_args[@]}" "$target" "$remote_cmd"; then
            return 0
        else
            local rc=$?
            echo "     Fallback key auth failed for $target (exit $rc)" >&2
        fi
    else
        echo "     Fallback key not found at $FALLBACK_IDENTITY" >&2
    fi

    return 1
}

nc_probe() {
    # Robustly detect BSD vs GNU flags without tripping 'set -e -o pipefail'
    local host="$1" port="$2"
    local nc_help
    nc_help="$(nc -h 2>&1 || true)"
    if echo "$nc_help" | grep -q "\\-G"; then
        # BSD netcat (macOS) uses -G for timeout (seconds)
        nc -z -G 2 "$host" "$port" >/dev/null 2>&1
    else
        # GNU netcat commonly uses -w for timeout
        nc -z -w 2 "$host" "$port" >/dev/null 2>&1
    fi
}

# Prefer publishing a tiny message with mosquitto_pub when available; fall back to nc
mqtt_probe() {
    local host="$1" port="$2"
    if command -v mosquitto_pub >/dev/null 2>&1; then
        local topic="__probe__/$(date +%s)/$$"
        mosquitto_pub -h "$host" -p "$port" -t "$topic" -m ping -q 0 >/dev/null 2>&1
        return $?
    fi
    nc_probe "$host" "$port"
}

split_csv_to_array() {
    local csv="$1"
    local target_name="$2"
    if [[ -z "$csv" ]]; then
        eval "$target_name=()"
        return
    fi
    local IFS=','
    local -a _tmp=()
    IFS=',' read -r -a _tmp <<< "$csv"
    # Portable assignment for Bash 3.2 (no namerefs)
    eval "$target_name=(\"${_tmp[@]}\")"
}

discover_broker() {
    local hosts_csv="$BROKER_CANDIDATES"
    local ports_csv="$BROKER_PORTS"

    for host in ${hosts_csv//,/ }; do
        for port in ${ports_csv//,/ }; do
            if [[ -z "$host" || -z "$port" ]]; then
                continue
            fi
            if [[ "$host" == "0.0.0.0" ]]; then
                echo "Skipping non-routable candidate 0.0.0.0" >&2
                continue
            fi
            echo "Probing MQTT broker at $host:$port ..." >&2
            if command -v mosquitto_pub >/dev/null 2>&1; then
                local topic="__probe__/$(date +%s)/$$"
                if mosquitto_pub -h "$host" -p "$port" -t "$topic" -m ping -q 0 >/dev/null 2>&1; then
                    echo "Found MQTT broker at $host:$port" >&2
                    printf '%s:%s\n' "$host" "$port"
                    return 0
                else
                    echo "Probe failed via mosquitto_pub to $host:$port" >&2
                fi
            else
                if nc_probe "$host" "$port"; then
                    echo "Found MQTT broker at $host:$port" >&2
                    printf '%s:%s\n' "$host" "$port"
                    return 0
                else
                    echo "Probe failed via nc to $host:$port" >&2
                fi
            fi
        done
    done
    return 1
}

discover_pi() {
    local hosts_csv="$PI_CANDIDATES"
    for host in ${hosts_csv//,/ }; do
        if [[ -z "$host" ]]; then
            continue
        fi
        echo "Probing Pi at $PI_USER@$host (SSH) ..." >&2
        if ssh_run "$host" "echo ok" >/dev/null 2>&1; then
            echo "Found Pi at $host" >&2
            echo "$host"
            return 0
        else
            local rc=$?
            echo "Probe to $host failed (exit $rc)" >&2
        fi
    done
    return 1
}

compute_broker_host_for_pi() {
    local discovered_host="$1"
    local host_for_pi="$discovered_host"
    if [[ -n "$BROKER_HOST_FOR_PI_OVERRIDE" ]]; then
        host_for_pi="$BROKER_HOST_FOR_PI_OVERRIDE"
    elif [[ "$discovered_host" == "127.0.0.1" || "$discovered_host" == "localhost" ]]; then
        # Try to pick a LAN IP visible to the Pi (best-effort on macOS)
        local primary_if
        primary_if=$(route get default 2>/dev/null | awk '/interface:/{print $2}' || true)
        if [[ -n "$primary_if" ]]; then
            local lan_ip
            lan_ip=$(ipconfig getifaddr "$primary_if" 2>/dev/null || true)
            if [[ -n "$lan_ip" ]]; then
                host_for_pi="$lan_ip"
            fi
        fi
    fi
    echo "$host_for_pi"
}

start_remote_services() {
    local pi_host="$1"; shift
    local broker_host="$1"; shift
    local broker_port="$1"; shift
    local video_port="$1"; shift

    # Build run command
    local run_cmd="cd $REMOTE_DIR && chmod +x Pi/init_setup.sh Pi/run_tiality.sh && ./Pi/init_setup.sh && "
    run_cmd+="if command -v tmux >/dev/null 2>&1; then "
    if [[ "$NO_VIDEO" == "1" ]]; then
        run_cmd+="tmux new -ds tiality './Pi/run_tiality.sh --broker $broker_host --broker_port $broker_port'; "
    else
        run_cmd+="tmux new -ds tiality './Pi/run_tiality.sh --broker $broker_host --broker_port $broker_port --video_server $pi_host:$video_port'; "
    fi
    run_cmd+="echo 'run_tiality.sh started in tmux session \"tiality\"'; "
    run_cmd+="else "
    if [[ "$NO_VIDEO" == "1" ]]; then
        run_cmd+="nohup ./Pi/run_tiality.sh --broker $broker_host --broker_port $broker_port > tiality.out 2>&1 & disown; "
    else
        run_cmd+="nohup ./Pi/run_tiality.sh --broker $broker_host --broker_port $broker_port --video_server $pi_host:$video_port > tiality.out 2>&1 & disown; "
    fi
    run_cmd+="echo 'run_tiality.sh started via nohup (logs: tiality.out)'; fi"

    if [[ "$DRY_RUN" == "1" ]]; then
        echo "[DRY-RUN] ssh (key or password) $PI_USER@$pi_host \"$run_cmd\""
        return 0
    fi

    ssh_run "$pi_host" "$run_cmd"
}

# --------------------------- Main ---------------------------

require_cmd ssh
require_cmd nc

echo "--- Discovering MQTT broker ---"
if ! broker_pair=$(discover_broker); then
    echo "ERROR: No reachable MQTT broker found. Provide --broker-candidates/--broker-ports." >&2
    exit 1
fi
BROKER_HOST="${broker_pair%%:*}"
BROKER_PORT="${broker_pair##*:}"
BROKER_HOST_FOR_PI="$(compute_broker_host_for_pi "$BROKER_HOST")"

echo "Selected broker: $BROKER_HOST:$BROKER_PORT (for Pi: $BROKER_HOST_FOR_PI)"

echo "--- Discovering Raspberry Pi ---"
if ! PI_HOST=$(discover_pi); then
    echo "ERROR: Could not reach any Pi candidates over SSH. Check power/network/keys." >&2
    exit 1
fi

echo "--- Running remote setup and starting services ---"
start_remote_services "$PI_HOST" "$BROKER_HOST_FOR_PI" "$BROKER_PORT" "$VIDEO_PORT"

echo
echo "Done. Useful commands:"
echo "- Inspect tmux on Pi: ssh $PI_USER@$PI_HOST 'tmux ls; tmux attach -t tiality'"
echo "- Tail logs (nohup fallback): ssh $PI_USER@$PI_HOST 'cd $REMOTE_DIR && tail -f tiality.out'"
echo "- Suggested local client (if desired):"
echo "  python3 pygame_video_mqtt_client.py --pi_ip $PI_HOST --grpc_port $VIDEO_PORT --broker $BROKER_HOST"


