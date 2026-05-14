#!/usr/bin/env bash
set -euo pipefail

FROM_NAME="genesis"
GENESIS_CONTAINER="$FROM_NAME-node"
CHAIN_RPC_PORT="26657"
CHAIN_REST_PORT="1317"
DEVSHARD_ESCROW_AMOUNT=7000000000
MODEL_ID="Qwen/Qwen2.5-7B-Instruct"
NODE_URL="http://$GENESIS_CONTAINER:$CHAIN_RPC_PORT"
STDERR_FILE=""
PROXY_STARTED=0

wait_for_tx() {
  local tx_hash="$1"
  local tx_json=""
  local i

  for i in $(seq 1 60); do
    if tx_json="$({
      docker exec "$GENESIS_CONTAINER" inferenced query tx --type hash "$tx_hash" \
        --node "$NODE_URL" -o json 2>/dev/null
    })"; then
      echo "$tx_json"
      return 0
    fi
    sleep 1
  done

  echo "=== Timed out waiting for tx to be included (txhash: $tx_hash) ==="
  return 1
}

ensure_tx_success() {
  local tx_json="$1"
  local tx_code

  tx_code="$(echo "$tx_json" | jq -r '.code // 0')"
  if [ "$tx_code" != "0" ]; then
    echo "=== Failed with code $tx_code: $(echo "$tx_json" | jq -r '.raw_log // "unknown error"') ==="
    exit "$tx_code"
  fi
}

ensure_curl() {
  docker exec "$GENESIS_CONTAINER" sh -lc 'command -v curl >/dev/null 2>&1'
}

print_proxy_logs() {
  if [ -n "$STDERR_FILE" ]; then
    docker exec "$GENESIS_CONTAINER" sh -lc "test -f '$STDERR_FILE' && cat '$STDERR_FILE' || true"
  fi
}

cleanup() {
  if [ "$PROXY_STARTED" -eq 1 ]; then
    docker exec "$GENESIS_CONTAINER" sh -lc "pkill -f 'DEVSHARD_ESCROW_ID=$ESCROW_ID.*devshardctl' || true" || true
  fi
}

trap print_proxy_logs ERR
trap cleanup EXIT

echo "=== Funding genesis ==="
GENESIS_ADDR="$(docker exec "$GENESIS_CONTAINER" inferenced keys show "$FROM_NAME" -a --keyring-backend test)"
TX_HASH="$({
  docker exec "$GENESIS_CONTAINER" inferenced tx bank send \
    POOL_product_science_inc "$GENESIS_ADDR" "${DEVSHARD_ESCROW_AMOUNT}ngonka" \
    --keyring-backend test --node "$NODE_URL" --yes -o json
} | jq -r '.txhash')"

echo "=== Waiting for bank tx to be included (txhash: $TX_HASH) ==="
TRANSFER_TX="$(wait_for_tx "$TX_HASH")"
ensure_tx_success "$TRANSFER_TX"

echo "=== Copying devshardctl into $GENESIS_CONTAINER ==="
DEVSHARDCTL_LOCAL_BUILD_PATH=../../build/devshardctl
docker cp "$DEVSHARDCTL_LOCAL_BUILD_PATH" "$GENESIS_CONTAINER:/usr/local/bin/devshardctl"
docker exec "$GENESIS_CONTAINER" sh -lc 'chmod +x /usr/local/bin/devshardctl && command -v devshardctl'

ESCROW_ID=""
while [ -z "$ESCROW_ID" ]; do
  echo "=== Creating escrow ID ==="
  TX_HASH="$({
    docker exec "$GENESIS_CONTAINER" inferenced tx inference create-devshard-escrow \
      "$DEVSHARD_ESCROW_AMOUNT" "$MODEL_ID" \
      --from "$FROM_NAME" --keyring-backend test --node "$NODE_URL" --yes -o json
  } | jq -r '.txhash')"

  echo "=== Waiting for escrow tx to be included (txhash: $TX_HASH) ==="
  ESCROW_TX="$(wait_for_tx "$TX_HASH")"
  ensure_tx_success "$ESCROW_TX"

  ESCROW_ID="$(
    echo "$ESCROW_TX" \
    | jq -r '.events[]? | select(.type=="devshard_escrow_created") | .attributes[]? | select(.key=="escrow_id") | .value' \
    | tail -n1
  )"

  if [ -z "$ESCROW_ID" ]; then
    echo "=== Escrow ID is empty even though the tx was included, aborting ==="
    echo "$ESCROW_TX" | jq .
    exit 1
  fi
done

echo "=== Querying escrow ==="
ESCROW_JSON="$({
  docker exec "$GENESIS_CONTAINER" inferenced query inference show-devshard-escrow "$ESCROW_ID" \
    --node "$NODE_URL" -o json
})"
TOTAL_SLOTS="$(echo "$ESCROW_JSON" | jq -r '.escrow.slots | length')"
MAX_SLOTS_PER_HOST="$(echo "$ESCROW_JSON" | jq -r '[.escrow.slots[]] | group_by(.) | map(length) | max // 0')"

if [ "$MAX_SLOTS_PER_HOST" -gt $((TOTAL_SLOTS / 2)) ]; then
  echo "=== Escrow slot distribution is too skewed for timeout voting, aborting ==="
  echo "$ESCROW_JSON" \
    | jq '{escrow_id: .escrow.id, slot_counts: ([.escrow.slots[]] | group_by(.) | map({host: .[0], slots: length}))}'
  exit 1
fi

echo "=== Starting devshardctl ==="
STDERR_FILE="/tmp/devshardctl-proxy-${ESCROW_ID}.log"
DEVSHARD_PORT="8080"
ensure_curl
docker exec \
  -d "$GENESIS_CONTAINER" \
  sh -lc "DEVSHARD_PRIVATE_KEY='$(cat ../genesis-keys/cold.hex)' DEVSHARD_ESCROW_ID='$ESCROW_ID' DEVSHARD_CHAIN_REST='http://localhost:$CHAIN_REST_PORT' DEVSHARD_PORT='$DEVSHARD_PORT' DEVSHARD_STORAGE_PATH='/tmp/devshardctl-proxy-${ESCROW_ID}.db' DEVSHARD_ROUTE_PREFIX='/v1/devshard' devshardctl >'$STDERR_FILE' 2>&1"
PROXY_STARTED=1

echo "=== Waiting for devshardctl to be ready ==="
READY=0
for i in $(seq 1 30); do
  if docker exec "$GENESIS_CONTAINER" sh -lc "curl -sf http://localhost:$DEVSHARD_PORT/v1/status >/dev/null 2>&1"; then
    READY=1
    break
  fi
  sleep 1
done

if [ "$READY" -ne 1 ]; then
  echo "=== devshardctl did not start within 30s ==="
  print_proxy_logs
  exit 1
fi

echo "=== Running load ==="
WORKLOAD_CONTAINER="workload-benchmark-server"
WORKLOAD_SCHEDULE="ping"
# TODO: Use --flow devshards
#docker exec $WORKLOAD_CONTAINER bash -lc "python load_testing.py --schedule $WORKLOAD_SCHEDULE"

RESPONSE_FILE="/tmp/devshard-inference-${ESCROW_ID}.json"
echo "=== Sending a devshard inference ==="
HTTP_STATUS="$(docker exec "$GENESIS_CONTAINER" sh -lc "curl -sS -o '$RESPONSE_FILE' -w '%{http_code}' -X POST 'http://localhost:$DEVSHARD_PORT/v1/chat/completions' -H 'Content-Type: application/json' -d '{\"model\":\"$MODEL_ID\",\"stream\":false,\"max_tokens\":0}'")"
docker exec "$GENESIS_CONTAINER" cat "$RESPONSE_FILE"
if [ "$HTTP_STATUS" != "200" ]; then
  echo "=== Devshard inference failed with HTTP $HTTP_STATUS ==="
  exit 1
fi
if ! docker exec "$GENESIS_CONTAINER" cat "$RESPONSE_FILE" | jq . >/dev/null 2>&1; then
  echo "=== Devshard inference did not return JSON ==="
  exit 1
fi
if docker exec "$GENESIS_CONTAINER" cat "$RESPONSE_FILE" | jq -e '.error' >/dev/null 2>&1; then
  echo "=== Devshard inference returned an error payload ==="
  docker exec "$GENESIS_CONTAINER" cat "$RESPONSE_FILE" | jq .
  exit 1
fi

SETTLEMENT_JSON="settlement-$ESCROW_ID.json"
SETTLEMENT_JSON_CONTAINER="/tmp/$SETTLEMENT_JSON"
echo "=== Waiting before finalization ==="
sleep 2
echo "=== Finalizing devshardctl (settlement JSON: $SETTLEMENT_JSON) ==="
docker exec "$GENESIS_CONTAINER" sh -lc "curl -sS -X POST 'http://localhost:$DEVSHARD_PORT/v1/finalize' -H 'Content-Type: application/json'" \
  > "$SETTLEMENT_JSON"

if ! jq -e '.version and .escrow_id and .state_root and .signatures' "$SETTLEMENT_JSON" >/dev/null 2>&1; then
  echo "=== Finalization did not return settlement JSON ==="
  cat "$SETTLEMENT_JSON"
  exit 1
fi

docker cp "$SETTLEMENT_JSON" "$GENESIS_CONTAINER:$SETTLEMENT_JSON_CONTAINER"

echo "=== Settling escrow ==="
SETTLEMENT_TX_HASH="$({
  docker exec "$GENESIS_CONTAINER" inferenced tx inference settle-devshard-escrow "$SETTLEMENT_JSON_CONTAINER" \
    --from "$FROM_NAME" --keyring-backend test --node "$NODE_URL" --yes -o json
} | jq -r '.txhash')"

echo "=== Waiting for settlement tx to be included (txhash: $SETTLEMENT_TX_HASH) ==="
SETTLEMENT_TX="$(wait_for_tx "$SETTLEMENT_TX_HASH")"
ensure_tx_success "$SETTLEMENT_TX"

echo "=== Stopping devshardctl ==="
docker exec "$GENESIS_CONTAINER" sh -lc "pkill -f 'DEVSHARD_ESCROW_ID=$ESCROW_ID.*devshardctl' || true"
PROXY_STARTED=0
