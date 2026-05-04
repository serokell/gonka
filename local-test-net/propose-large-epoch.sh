#!/bin/bash
# Submit a governance proposal to change epoch params and vote on it from all nodes.
# Discovers join nodes automatically from prod-local/ directories.
# Usage: ./propose-large-epoch.sh [epoch_length]
set -ex

EPOCH_LENGTH="${1:-10000}"
CHAIN_ID="gonka-mainnet"
IMAGE="ghcr.io/product-science/inferenced"
NETWORK="chain-public"
DEPOSIT="25000000ngonka"

GENESIS_HOME="$(pwd)/prod-local/genesis"

# Discover join node directories
JOIN_NODES=()
for dir in prod-local/join*/; do
  [ -d "$dir" ] || continue
  JOIN_NODES+=("$(basename "$dir")")
done

# Helper: run inferenced command with a given node's home directory
run_node() {
  local home_dir="$1"
  shift
  docker run --rm --network "$NETWORK" \
    -v "$home_dir:/root/.inference" \
    "$IMAGE" inferenced "$@"
}

run_genesis() {
  run_node "$GENESIS_HOME" "$@"
}

NODE_URL="http://genesis-node:26657"

# 0. Wait for epoch 0 to finish and validators to be updated (past SetNewValidators stage)
echo "=== Waiting for epoch 1 validators to be set ==="
while true; do
  EPOCH_INFO="$(run_genesis query inference epoch-info -o json --node "$NODE_URL")"
  EPOCH_INDEX="$(echo "$EPOCH_INFO" | jq -r '.latest_epoch.index // "0"')"
  BLOCK_HEIGHT="$(echo "$EPOCH_INFO" | jq -r '.block_height // "0"')"
  POC_START="$(echo "$EPOCH_INFO" | jq -r '.latest_epoch.poc_start_block_height // "0"')"
  POC_DURATION="$(echo "$EPOCH_INFO" | jq -r '.params.epoch_params.poc_stage_duration // "0"')"
  POC_VAL_DELAY="$(echo "$EPOCH_INFO" | jq -r '.params.epoch_params.poc_validation_delay // "0"')"
  POC_VAL_DURATION="$(echo "$EPOCH_INFO" | jq -r '.params.epoch_params.poc_validation_duration // "0"')"
  SET_VALIDATORS_DELAY="$(echo "$EPOCH_INFO" | jq -r '.params.epoch_params.set_new_validators_delay // "0"')"
  SET_VALIDATORS_HEIGHT=$((POC_START + POC_DURATION + POC_VAL_DELAY + POC_VAL_DURATION + SET_VALIDATORS_DELAY))
  if [ "$EPOCH_INDEX" != "0" ] && [ "$BLOCK_HEIGHT" -gt "$SET_VALIDATORS_HEIGHT" ]; then
    echo "Epoch $EPOCH_INDEX, block $BLOCK_HEIGHT (past SetNewValidators at $SET_VALIDATORS_HEIGHT)"
    break
  fi
  echo "Epoch $EPOCH_INDEX, block $BLOCK_HEIGHT (waiting for SetNewValidators at $SET_VALIDATORS_HEIGHT)..."
  sleep 10
done

# 1. Fetch gov module authority address and current params
echo "=== Fetching gov module authority ==="
AUTHORITY="$(run_genesis query auth module-account gov -o json --node "$NODE_URL" \
  | jq -r '.account.value.address')"
echo "Authority: $AUTHORITY"

echo "=== Fetching current params ==="
CURRENT_PARAMS="$(run_genesis query inference params -o json --node "$NODE_URL")"

echo "=== Building proposal JSON ==="
PROPOSAL_JSON="$(echo "$CURRENT_PARAMS" | jq '{
  messages: [{
    "@type": "/inference.inference.MsgUpdateParams",
    authority: "'"$AUTHORITY"'",
    params: (
      .params
      | .epoch_params.epoch_length = "'"$EPOCH_LENGTH"'"
      | .poc_params.models |= (map(. + {model_id: (.model_id // "")}))
      | .poc_params.models[0].model_id = .delegation_params.initial_model_id
    )
  }],
  deposit: "'"$DEPOSIT"'",
  title: "Change epoch length to '"$EPOCH_LENGTH"'",
  summary: "Change epoch_length to '"$EPOCH_LENGTH"' blocks",
  metadata: ""
}')"

# Write proposal locally and docker cp it into the genesis container
PROPOSAL_FILE="./proposal.json"
echo "$PROPOSAL_JSON" > "$PROPOSAL_FILE"

GENESIS_CONTAINER="genesis-node"
CONTAINER_PROPOSAL_PATH="/tmp/proposal.json"
docker cp "$PROPOSAL_FILE" "$GENESIS_CONTAINER:$CONTAINER_PROPOSAL_PATH"
rm -f "$PROPOSAL_FILE"

echo "=== Submitting proposal from genesis ==="
TX_HASH="$(docker exec "$GENESIS_CONTAINER" inferenced tx gov submit-proposal "$CONTAINER_PROPOSAL_PATH" \
  --from genesis \
  --chain-id "$CHAIN_ID" \
  --node "$NODE_URL" \
  --keyring-backend test \
  --gas 1000000 \
  --yes -o json | jq -r '.txhash')"

echo "=== Waiting for tx to be included (txhash: $TX_HASH) ==="
sleep 6

out="$(docker run --rm --network chain-public \
  -v /home/heitor/Work/gonka/gonka/local-test-net/prod-local/genesis:/root/.inference \
  ghcr.io/product-science/inferenced \
  inferenced query tx $TX_HASH \
  -o json --node $NODE_URL 2>&1)"
ec=$?
printf 'exit=%s\n%s\n' "$ec" "$out"

# Get the proposal ID from the tx result
PROPOSAL_ID="$(run_genesis query tx "$TX_HASH" -o json --node "$NODE_URL" \
  | jq -r '.events[] | select(.type=="submit_proposal") | .attributes[] | select(.key=="proposal_id") | .value')"

echo "=== Proposal ID: $PROPOSAL_ID ==="

# 2. Vote from all nodes
echo "=== Voting YES from genesis ==="
run_genesis tx gov vote "$PROPOSAL_ID" yes \
  --from genesis \
  --chain-id "$CHAIN_ID" \
  --node "$NODE_URL" \
  --keyring-backend test \
  --yes

for node_name in "${JOIN_NODES[@]}"; do
  echo "=== Voting YES from $node_name ==="
  run_node "$(pwd)/prod-local/$node_name" tx gov vote "$PROPOSAL_ID" yes \
    --from "${node_name}_warm" \
    --chain-id "$CHAIN_ID" \
    --node "$NODE_URL" \
    --keyring-backend test \
    --yes
done

echo "=== Waiting for votes to be included ==="
sleep 6

# 3. Verify votes
echo "=== Votes on proposal $PROPOSAL_ID ==="
run_genesis query gov votes "$PROPOSAL_ID" --node "$NODE_URL"

echo "=== Proposal status ==="
run_genesis query gov proposal "$PROPOSAL_ID" -o json --node "$NODE_URL" \
  | jq '{id: .proposal.id, status: .proposal.status, voting_end_time: .proposal.voting_end_time}'

# Cleanup
rm -f "$PROPOSAL_FILE"

echo "=== Done! Proposal $PROPOSAL_ID submitted and votes cast. ==="
echo "=== Wait for voting_end_time for the proposal to pass. ==="
