#!/usr/bin/env bash
set -uo pipefail

RPC_FILE="rpc.txt"
STATUS_FILE="rpc.monad.status.tsv"
BASE_URL="${MONAD_ALCHEMY_BASE_URL:-https://monad-mainnet.g.alchemy.com/v2}"
FORMAT="args"
INCLUDE="usable,usable_fast,usable_slow"
MIN_BLOCKS=0

usage() {
  cat <<'EOF'
Usage:
  scripts/monad_rpc_args.sh [options]

Options:
  --rpc-file PATH       Key/url file to read. Default: rpc.txt
  --status-file PATH    Probe status TSV. Default: rpc.monad.status.tsv
  --base-url URL        Base URL for bare Alchemy keys.
  --format FORMAT       args, urls, or env. Default: args
  --include STATUSES    Comma-separated statuses to include.
  --min-blocks N        Require max_blocks >= N when status file is capacity TSV.
  -h, --help            Show this help.

Examples:
  scripts/monad_rpc_args.sh
  scripts/monad_rpc_args.sh --format urls
  scripts/monad_rpc_args.sh --status-file rpc.monad.capacity.tsv --min-blocks 1000 --format urls
  cargo run --manifest-path crate/Cargo.toml --bin chog_collect -- \
    --mode incremental \
    --data-root data/chog/v1 \
    $(scripts/monad_rpc_args.sh)
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --rpc-file)
      RPC_FILE="${2:-}"
      shift 2
      ;;
    --status-file)
      STATUS_FILE="${2:-}"
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
    --include)
      INCLUDE="${2:-}"
      shift 2
      ;;
    --min-blocks)
      MIN_BLOCKS="${2:-}"
      shift 2
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

case "$FORMAT" in
  args|urls|env) ;;
  *)
    echo "--format must be one of: args, urls, env" >&2
    exit 2
    ;;
esac

if [ ! -f "$RPC_FILE" ]; then
  echo "rpc file not found: $RPC_FILE" >&2
  exit 1
fi

if [ ! -f "$STATUS_FILE" ]; then
  echo "status file not found: $STATUS_FILE" >&2
  echo "refresh it with: scripts/monad_rpc_probe.sh --format status > $STATUS_FILE" >&2
  echo "or use capacity cache: scripts/monad_rpc_args.sh --status-file rpc.monad.capacity.tsv --min-blocks 1000" >&2
  exit 1
fi

if ! [[ "$MIN_BLOCKS" =~ ^[0-9]+$ ]]; then
  echo "--min-blocks must be a non-negative integer" >&2
  exit 2
fi

declare -A STATUS_BY_LINE
declare -A MAX_BLOCKS_BY_LINE
while IFS=$'\t' read -r line col2 col3 _col4 col5 _rest; do
  if [[ "$line" =~ ^[0-9]+$ ]]; then
    if [[ "$col5" =~ ^[0-9]+$ ]] && [ -n "$col3" ]; then
      STATUS_BY_LINE["$line"]="$col3"
      MAX_BLOCKS_BY_LINE["$line"]="$col5"
    else
      STATUS_BY_LINE["$line"]="$col2"
    fi
  fi
done < "$STATUS_FILE"

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

included_status() {
  local status="$1"
  case ",$INCLUDE," in
    *",$status,"*) return 0 ;;
    *) return 1 ;;
  esac
}

urls=()
line_no=0
while IFS= read -r raw_line || [ -n "$raw_line" ]; do
  line_no=$((line_no + 1))
  value=$(trim "$raw_line")
  if [ -z "$value" ]; then
    continue
  fi

  status="${STATUS_BY_LINE[$line_no]:-}"
  max_blocks="${MAX_BLOCKS_BY_LINE[$line_no]:-}"
  if [ "$MIN_BLOCKS" -gt 0 ]; then
    if ! [[ "$max_blocks" =~ ^[0-9]+$ ]] || [ "$max_blocks" -lt "$MIN_BLOCKS" ]; then
      continue
    fi
  fi

  if included_status "$status"; then
    urls+=("$(url_for_value "$value")")
  fi
done < "$RPC_FILE"

case "$FORMAT" in
  urls)
    for url in "${urls[@]}"; do
      printf '%s\n' "$url"
    done
    ;;
  args)
    for url in "${urls[@]}"; do
      printf -- '--rpc-url %s ' "$url"
    done
    printf '\n'
    ;;
  env)
    joined=""
    for url in "${urls[@]}"; do
      if [ -z "$joined" ]; then
        joined="$url"
      else
        joined="$joined,$url"
      fi
    done
    printf 'ALCHEMY_RPC="%s"\n' "$joined"
    printf 'MONAD_RPC_ARGS="'
    for url in "${urls[@]}"; do
      printf -- '--rpc-url %s ' "$url"
    done
    printf '"\n'
    ;;
esac
