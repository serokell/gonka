#!/bin/bash
# This script launches 1 genesis node and N join nodes without port forwarding.
# Usage: ./launch_benchmark_nodes.sh [num_join_nodes]
# Defaults to 2 join nodes if not specified.
# Set RESOURCE_LIMITS=true to apply CPU/memory limits.
set -e

NUM_JOIN_NODES="${1:-2}"
NODE_CONFIG_TEMPLATE="node_config.template.json"

RESOURCES_FILE=""
if [ "${RESOURCE_LIMITS}" = "true" ]; then
  RESOURCES_FILE="-f docker-compose.resources.yml"
  echo "Resource limits enabled"
fi

# Generate node keys if they don't exist yet
ensure_node_keys() {
  local keys_dir="$1"
  if [ ! -d "$keys_dir" ]; then
    echo "Keys not found at $keys_dir, generating..."
    ./generate-node-keys.sh "$keys_dir"
  fi
}

# Generate a per-node config by replacing the host field in the template
generate_node_config() {
  local key_name="$1"
  local config_file="node_payload_mock_server_${key_name}.json"
  sed "s/{{KEY_NAME}}/${key_name}/g" "$NODE_CONFIG_TEMPLATE" > "$config_file"
  echo "$config_file"
}

# --- Genesis node ---
export KEY_NAME=genesis
export NODE_CONFIG
NODE_CONFIG="$(generate_node_config "$KEY_NAME")"
docker run --rm -v "$(pwd):/workdir" -w /workdir alpine:3.19 rm -rf prod-local 2>/dev/null || true
export PUBLIC_URL="http://${KEY_NAME}-api:9000"
export POC_CALLBACK_URL="http://${KEY_NAME}-api:9100"
export IS_GENESIS=true
export DASHBOARD_PORT=5173
export IMPORT_KEYS_DIR=./node-keys/genesis-keys
ensure_node_keys "$IMPORT_KEYS_DIR"

mkdir -p "./prod-local/wiremock/$KEY_NAME/mappings/"
mkdir -p "./prod-local/wiremock/$KEY_NAME/__files/"
cp ../testermint/src/main/resources/mappings/*.json "./prod-local/wiremock/$KEY_NAME/mappings/"
sed "s/{{KEY_NAME}}/$KEY_NAME/g" ../testermint/src/main/resources/alternative-mappings/validate_poc_batch.template.json > "./prod-local/wiremock/$KEY_NAME/mappings/validate_poc_batch.json"
if [ -n "$(ls -A ./public-html 2>/dev/null)" ]; then
  cp -r ../public-html/* "./prod-local/wiremock/$KEY_NAME/__files/"
fi

echo "Starting genesis node"
docker compose -p genesis -f docker-compose-base.yml $RESOURCES_FILE \
  -f docker-compose.genesis.yml -f docker-compose.proxy.yml \
  -f docker-compose.explorer.yml  -f docker-compose.benchmark.yml up -d
sleep 40

# --- Join nodes ---
export SEED_API_URL="http://genesis-api:9000"
export SEED_NODE_RPC_URL="http://genesis-node:26657"
export SEED_NODE_P2P_URL="http://genesis-node:26656"
export IS_GENESIS=false

for i in $(seq 1 "$NUM_JOIN_NODES"); do
  export KEY_NAME="join${i}"
  export NODE_CONFIG
  NODE_CONFIG="$(generate_node_config "$KEY_NAME")"
  export PUBLIC_URL="http://${KEY_NAME}-api:9000"
  export POC_CALLBACK_URL="http://${KEY_NAME}-api:9100"
  export P2P_EXTERNAL_ADDRESS="http://${KEY_NAME}-node:26656"
  export IMPORT_KEYS_DIR="./node-keys/join${i}-keys"
  ensure_node_keys "$IMPORT_KEYS_DIR"

  project_name="$KEY_NAME"

  docker compose -p "$project_name" down -v
  docker run --rm -v "$(pwd):/workdir" -w /workdir alpine:3.19 rm -rf "prod-local/$project_name" 2>/dev/null || true

  # Set up wiremock
  mkdir -p "./prod-local/wiremock/$KEY_NAME/mappings/"
  mkdir -p "./prod-local/wiremock/$KEY_NAME/__files/"
  cp ../testermint/src/main/resources/mappings/*.json "./prod-local/wiremock/$KEY_NAME/mappings/"
  sed "s/{{KEY_NAME}}/$KEY_NAME/g" ../testermint/src/main/resources/alternative-mappings/validate_poc_batch.template.json > "./prod-local/wiremock/$KEY_NAME/mappings/validate_poc_batch.json"
  if [ -n "$(ls -A ./public-html 2>/dev/null)" ]; then
    cp -r ../public-html/* "./prod-local/wiremock/$KEY_NAME/__files/"
  fi

  echo "Starting join node '${KEY_NAME}'"
  docker compose -p "$project_name" -f docker-compose-base.yml $RESOURCES_FILE -f docker-compose.join.yml -f docker-compose.benchmark.yml up -d
done
