#!/usr/bin/env bash
set -uo pipefail

RPC_FILE="rpc.txt"
BASE_URL="${MONAD_ALCHEMY_BASE_URL:-https://monad-mainnet.g.alchemy.com/v2}"
EXPECTED_CHAIN_ID="0x8f"
TIMEOUT=20
SAMPLES=3
FORMAT="table"
USE_PROXY=0
SHOW_FULL=0
PROBE_LOGS=1
CAPACITY_RANGES="100,500,1000,2000,5000,10000,20000"

CHOG_TOKEN="0x350035555e10d9afaf1566aaebfced5ba6c27777"
TRANSFER_TOPIC="0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

usage() {
  cat <<'EOF'
Usage:
  scripts/monad_rpc_probe.sh [options]

Options:
  --rpc-file PATH     Key/url file to read. Default: rpc.txt
  --base-url URL      Base URL for bare Alchemy keys.
  --format FORMAT     table, csv, status, capacity, urls, args, or env. Default: table
  --capacity-ranges N Comma-separated block ranges for capacity format.
  --samples N         eth_blockNumber samples per usable endpoint. Default: 3
  --timeout SECONDS   curl timeout per request. Default: 20
  --no-logs           Skip eth_getLogs capability probe.
  --use-proxy         Respect local proxy environment. Default uses --noproxy '*'.
  --show-full         Show full key/url in table/csv output.
  -h, --help          Show this help.

Examples:
  scripts/monad_rpc_probe.sh
  scripts/monad_rpc_probe.sh --format args
  scripts/monad_rpc_probe.sh --format capacity --samples 0
  cargo run --manifest-path crate/Cargo.toml --bin chog_collect -- \
    --mode incremental \
    --data-root data/chog/v1 \
    $(scripts/monad_rpc_probe.sh --format args)
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --rpc-file)
      RPC_FILE="${2:-}"
      shift 2
      ;;
    --base-url)
      BASE_URL="${2:-}"
      shift 2
      ;;
    --format)
      FORMAT="${2:-}"
      shift 2
      ;;
    --capacity-ranges)
      CAPACITY_RANGES="${2:-}"
      shift 2
      ;;
    --samples)
      SAMPLES="${2:-}"
      shift 2
      ;;
    --timeout)
      TIMEOUT="${2:-}"
      shift 2
      ;;
    --no-logs)
      PROBE_LOGS=0
      shift
      ;;
    --use-proxy)
      USE_PROXY=1
      shift
      ;;
    --show-full)
      SHOW_FULL=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required" >&2
  exit 1
fi

case "$FORMAT" in
  table|csv|status|capacity|urls|args|env) ;;
  *)
    echo "--format must be one of: table, csv, status, capacity, urls, args, env" >&2
    exit 2
    ;;
esac

if [ ! -f "$RPC_FILE" ]; then
  echo "rpc file not found: $RPC_FILE" >&2
  exit 1
fi

if ! [[ "$SAMPLES" =~ ^[0-9]+$ ]]; then
  echo "--samples must be a non-negative integer" >&2
  exit 2
fi

if ! [[ "$TIMEOUT" =~ ^[0-9]+$ ]]; then
  echo "--timeout must be a positive integer" >&2
  exit 2
fi

if [ "$FORMAT" = "table" ]; then
  printf '%-4s %-14s %-17s %-7s %-11s %-9s %-9s %-9s %s\n' \
    "line" "key" "status" "chain" "block" "logs" "samples" "avg_ms" "hint"
fi

if [ "$FORMAT" = "csv" ]; then
  printf 'line,key,status,chain_id,block_hex,block_dec,logs,samples_ok,samples_total,avg_ms,hint,error\n'
fi

if [ "$FORMAT" = "status" ]; then
  printf 'line\tstatus\tchain_id\tblock_dec\tlogs\tsamples\tavg_ms\thint\terror\n'
fi

if [ "$FORMAT" = "capacity" ]; then
  printf 'line\tkey\tstatus\tblock_dec\tmax_blocks\tlast_ok_ms\tlast_ok_logs\tfail_blocks\terror\n'
fi

rpc_request() {
  local url="$1"
  local payload="$2"
  local start_ms end_ms
  local curl_args=()
  local body_file err_file

  if [ "$USE_PROXY" -eq 0 ]; then
    curl_args+=(--noproxy '*')
  fi

  body_file=$(mktemp)
  err_file=$(mktemp)
  start_ms=$(date +%s%3N)
  curl "${curl_args[@]}" -sS --max-time "$TIMEOUT" \
    -H 'content-type: application/json' \
    -d "$payload" \
    -o "$body_file" \
    "$url" 2>"$err_file"
  RPC_CODE=$?
  end_ms=$(date +%s%3N)
  RPC_MS=$((end_ms - start_ms))

  if [ "$RPC_CODE" -eq 0 ]; then
    RPC_BODY=$(<"$body_file")
  else
    RPC_BODY=$(<"$err_file")
    if [ -z "$RPC_BODY" ]; then
      RPC_BODY=$(<"$body_file")
    fi
  fi
  rm -f "$body_file" "$err_file"
}

json_result() {
  printf '%s' "$1" | jq -r '.result // empty' 2>/dev/null
}

json_error() {
  local message
  message=$(printf '%s' "$1" | jq -r '.error.message // empty' 2>/dev/null)
  if [ -n "$message" ]; then
    printf '%s' "$message"
    return
  fi
  printf '%s' "$1" | tr '\n\t' '  ' | sed 's/  */ /g' | cut -c1-160
}

csv_field() {
  local value="${1//\"/\"\"}"
  printf '"%s"' "$value"
}

trim() {
  printf '%s' "$1" | sed 's/#.*$//; s/^[[:space:]]*//; s/[[:space:]]*$//'
}

url_for_value() {
  local value="$1"
  case "$value" in
    http://*|https://*) printf '%s' "$value" ;;
    *) printf '%s/%s' "${BASE_URL%/}" "$value" ;;
  esac
}

redact_value() {
  local value="$1"
  local key="$value"
  case "$value" in
    http://*|https://*) key="${value##*/}" ;;
  esac
  if [ "$SHOW_FULL" -eq 1 ]; then
    printf '%s' "$value"
  elif [ "${#key}" -le 10 ]; then
    printf '%s' "$key"
  else
    printf '%s...%s' "${key:0:6}" "${key: -4}"
  fi
}

hex_to_dec() {
  local value="$1"
  if [[ "$value" =~ ^0x[0-9a-fA-F]+$ ]]; then
    printf '%d' "$((value))"
  else
    printf ''
  fi
}

dec_to_hex() {
  printf '0x%x' "$1"
}

probe_log_capacity() {
  local url="$1" to_block_dec="$2"
  local old_ifs range blocks from_block_dec from_block_hex to_block_hex

  CAP_MAX_BLOCKS=0
  CAP_LAST_OK_MS="-"
  CAP_LAST_OK_LOGS="-"
  CAP_FAIL_BLOCKS="-"
  CAP_ERROR=""

  if ! [[ "$to_block_dec" =~ ^[0-9]+$ ]]; then
    CAP_ERROR="missing block number"
    return
  fi

  old_ifs="$IFS"
  IFS=','
  for range in $CAPACITY_RANGES; do
    IFS="$old_ifs"
    blocks=$(printf '%s' "$range" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
    if ! [[ "$blocks" =~ ^[0-9]+$ ]] || [ "$blocks" -eq 0 ]; then
      CAP_FAIL_BLOCKS="$blocks"
      CAP_ERROR="invalid capacity range"
      return
    fi

    if [ "$to_block_dec" -ge $((blocks - 1)) ]; then
      from_block_dec=$((to_block_dec - blocks + 1))
    else
      from_block_dec=0
    fi
    from_block_hex=$(dec_to_hex "$from_block_dec")
    to_block_hex=$(dec_to_hex "$to_block_dec")
    logs_payload="{\"jsonrpc\":\"2.0\",\"id\":4,\"method\":\"eth_getLogs\",\"params\":[{\"fromBlock\":\"$from_block_hex\",\"toBlock\":\"$to_block_hex\",\"address\":\"$CHOG_TOKEN\",\"topics\":[\"$TRANSFER_TOPIC\"]}]}"

    rpc_request "$url" "$logs_payload"
    if printf '%s' "$RPC_BODY" | jq -e '.result | type == "array"' >/dev/null 2>&1; then
      CAP_MAX_BLOCKS="$blocks"
      CAP_LAST_OK_MS="$RPC_MS"
      CAP_LAST_OK_LOGS=$(printf '%s' "$RPC_BODY" | jq -r '.result | length')
    else
      CAP_FAIL_BLOCKS="$blocks"
      CAP_ERROR=$(json_error "$RPC_BODY")
      return
    fi
    IFS=','
  done
  IFS="$old_ifs"
}

classify_error() {
  local message
  message=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
  case "$message" in
    *"not enabled"*) printf 'network_disabled' ;;
    *"capacity limit exceeded"*) printf 'capacity_exceeded' ;;
    *"app is inactive"*|*"inactive"*) printf 'inactive' ;;
    *"rate limit"*|*"too many requests"*) printf 'rate_limited' ;;
    *"could not resolve host"*) printf 'dns_error' ;;
    *"failed to connect"*) printf 'connect_error' ;;
    *"timed out"*|*"timeout"*) printf 'timeout' ;;
    "") printf 'unknown_error' ;;
    *) printf 'error' ;;
  esac
}

hint_for_status() {
  local status="$1"
  case "$status" in
    usable_fast) printf 'usable; plan unknown; prefer for high volume' ;;
    usable) printf 'usable; plan unknown; rotate with retries' ;;
    usable_slow) printf 'usable but slower; keep as fallback' ;;
    partial) printf 'chain/block ok but logs failed' ;;
    capacity_exceeded) printf 'quota exhausted; likely free/capped app' ;;
    network_disabled) printf 'Monad not enabled for this app' ;;
    inactive) printf 'Alchemy app inactive' ;;
    rate_limited) printf 'throughput limited; lower concurrency' ;;
    dns_error|connect_error|timeout) printf 'local/network path problem' ;;
    *) printf 'not usable for current probe' ;;
  esac
}

print_csv_row() {
  local line="$1" key="$2" status="$3" chain="$4" block_hex="$5" block_dec="$6"
  local logs="$7" ok="$8" total="$9" avg_ms="${10}" hint="${11}" error="${12}"
  printf '%s,' "$line"
  csv_field "$key"; printf ','
  csv_field "$status"; printf ','
  csv_field "$chain"; printf ','
  csv_field "$block_hex"; printf ','
  csv_field "$block_dec"; printf ','
  csv_field "$logs"; printf ','
  printf '%s,%s,' "$ok" "$total"
  csv_field "$avg_ms"; printf ','
  csv_field "$hint"; printf ','
  csv_field "$error"; printf '\n'
}

tsv_field() {
  printf '%s' "$1" | tr '\t\r\n' '   '
}

usable_urls=()
line_no=0

while IFS= read -r raw_line || [ -n "$raw_line" ]; do
  line_no=$((line_no + 1))
  value=$(trim "$raw_line")
  if [ -z "$value" ]; then
    continue
  fi

  url=$(url_for_value "$value")
  label=$(redact_value "$value")

  chain_payload='{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}'
  block_payload='{"jsonrpc":"2.0","id":2,"method":"eth_blockNumber","params":[]}'

  rpc_request "$url" "$chain_payload"
  chain_body="$RPC_BODY"
  chain_id=$(json_result "$chain_body")
  chain_error=$(json_error "$chain_body")

  rpc_request "$url" "$block_payload"
  block_body="$RPC_BODY"
  block_hex=$(json_result "$block_body")
  block_error=$(json_error "$block_body")
  block_dec=$(hex_to_dec "$block_hex")

  logs_status="skip"
  logs_error=""
  if [ "$PROBE_LOGS" -eq 1 ] && [ -n "$block_hex" ]; then
    logs_payload="{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"eth_getLogs\",\"params\":[{\"fromBlock\":\"$block_hex\",\"toBlock\":\"$block_hex\",\"address\":\"$CHOG_TOKEN\",\"topics\":[\"$TRANSFER_TOPIC\"]}]}"
    rpc_request "$url" "$logs_payload"
    if printf '%s' "$RPC_BODY" | jq -e '.result | type == "array"' >/dev/null 2>&1; then
      logs_count=$(printf '%s' "$RPC_BODY" | jq -r '.result | length')
      logs_status="ok:$logs_count"
    else
      logs_error=$(json_error "$RPC_BODY")
      logs_status="err"
    fi
  fi

  sample_ok=0
  sample_total="$SAMPLES"
  avg_ms="-"
  if [ -n "$block_hex" ] && [ "$SAMPLES" -gt 0 ]; then
    total_ms=0
    for ((sample = 1; sample <= SAMPLES; sample++)); do
      rpc_request "$url" "$block_payload"
      sample_block=$(json_result "$RPC_BODY")
      if [ -n "$sample_block" ]; then
        sample_ok=$((sample_ok + 1))
        total_ms=$((total_ms + RPC_MS))
      fi
    done
    if [ "$sample_ok" -gt 0 ]; then
      avg_ms=$((total_ms / sample_ok))
    fi
  fi

  combined_error=""
  if [ "$chain_id" != "$EXPECTED_CHAIN_ID" ] || [ -z "$block_hex" ]; then
    combined_error="${chain_error:-$block_error}"
    if [ -z "$combined_error" ]; then
      combined_error="$block_error"
    fi
    status=$(classify_error "$combined_error")
  elif [ "$PROBE_LOGS" -eq 1 ] && [[ "$logs_status" != ok:* ]]; then
    status="partial"
    combined_error="$logs_error"
  elif [ "$sample_ok" -eq "$sample_total" ] && [ "$sample_total" -gt 0 ] && [ "$avg_ms" != "-" ] && [ "$avg_ms" -le 1000 ]; then
    status="usable_fast"
  elif [ "$sample_ok" -gt 0 ]; then
    status="usable"
  else
    status="usable_slow"
  fi

  hint=$(hint_for_status "$status")
  case "$status" in
    usable_fast|usable|usable_slow)
      usable_urls+=("$url")
      ;;
  esac

  case "$FORMAT" in
    table)
      printf '%-4s %-14s %-17s %-7s %-11s %-9s %-9s %-9s %s\n' \
        "$line_no" "$label" "$status" "${chain_id:-ERR}" "${block_dec:-ERR}" \
        "$logs_status" "$sample_ok/$sample_total" "$avg_ms" "$hint"
      ;;
    csv)
      print_csv_row "$line_no" "$label" "$status" "${chain_id:-}" "$block_hex" \
        "$block_dec" "$logs_status" "$sample_ok" "$sample_total" "$avg_ms" \
        "$hint" "$combined_error"
      ;;
    status)
      printf '%s\t' "$line_no"
      tsv_field "$status"; printf '\t'
      tsv_field "${chain_id:-}"; printf '\t'
      tsv_field "$block_dec"; printf '\t'
      tsv_field "$logs_status"; printf '\t'
      tsv_field "$sample_ok/$sample_total"; printf '\t'
      tsv_field "$avg_ms"; printf '\t'
      tsv_field "$hint"; printf '\t'
      tsv_field "$combined_error"; printf '\n'
      ;;
    capacity)
      if [ "$chain_id" = "$EXPECTED_CHAIN_ID" ] && [ -n "$block_dec" ]; then
        probe_log_capacity "$url" "$block_dec"
      else
        CAP_MAX_BLOCKS=0
        CAP_LAST_OK_MS="-"
        CAP_LAST_OK_LOGS="-"
        CAP_FAIL_BLOCKS="-"
        CAP_ERROR="$combined_error"
      fi
      printf '%s\t' "$line_no"
      tsv_field "$label"; printf '\t'
      tsv_field "$status"; printf '\t'
      tsv_field "$block_dec"; printf '\t'
      tsv_field "$CAP_MAX_BLOCKS"; printf '\t'
      tsv_field "$CAP_LAST_OK_MS"; printf '\t'
      tsv_field "$CAP_LAST_OK_LOGS"; printf '\t'
      tsv_field "$CAP_FAIL_BLOCKS"; printf '\t'
      tsv_field "$CAP_ERROR"; printf '\n'
      ;;
  esac
done < "$RPC_FILE"

case "$FORMAT" in
  urls)
    for url in "${usable_urls[@]}"; do
      printf '%s\n' "$url"
    done
    ;;
  args)
    for url in "${usable_urls[@]}"; do
      printf -- '--rpc-url %s ' "$url"
    done
    printf '\n'
    ;;
  env)
    joined=""
    for url in "${usable_urls[@]}"; do
      if [ -z "$joined" ]; then
        joined="$url"
      else
        joined="$joined,$url"
      fi
    done
    printf 'ALCHEMY_RPC="%s"\n' "$joined"
    printf 'MONAD_RPC_ARGS="'
    for url in "${usable_urls[@]}"; do
      printf -- '--rpc-url %s ' "$url"
    done
    printf '"\n'
    ;;
esac
