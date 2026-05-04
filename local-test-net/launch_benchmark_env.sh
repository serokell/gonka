#!/bin/bash
# Launch benchmark environment: start nodes, extend epoch, print API endpoints.
# Usage: ./launch_benchmark_env.sh [num_join_nodes] [epoch_length]
set -e

NUM_JOIN_NODES="${1:-2}"
EPOCH_LENGTH="${2:-10000}"
DEBUG=true

./launch_benchmark_nodes.sh "$NUM_JOIN_NODES"
./propose-large-epoch.sh "$EPOCH_LENGTH"

echo ""
echo "=== Node API endpoints ==="
endpoints=""
for i in $(seq 1 "$NUM_JOIN_NODES"); do
  warm_address="$(cat "./node-keys/join${i}-keys/warm_address.txt")"
  entry="http://join${i}-api:9000/v1;${warm_address}"
  if [ -z "$endpoints" ]; then
    endpoints="$entry"
  else
    endpoints="${endpoints},${entry}"
  fi
done
echo "=========================== GONKA ENDPOINTS =============================="
echo "$endpoints"
