#!/bin/bash
set -e

IMAGE="ghcr.io/product-science/inferenced"
OUTPUT_DIR="${1:?Usage: $0 <output-dir>}"
CHAIN_ID="${CHAIN_ID:-gonka-mainnet}"
COIN_DENOM="${COIN_DENOM:-ngonka}"

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

echo "Generating keys using image $IMAGE"
echo "Output directory: $OUTPUT_DIR"

docker run --rm \
  -v "$OUTPUT_DIR:/keyring-out" \
  "$IMAGE" \
  sh -c "
    set -e

    KEYRING='--keyring-backend test --keyring-dir /tmp/keyring'

    # --- Cold key (main account) ---
    inferenced keys add cold \$KEYRING

    inferenced keys show cold \$KEYRING \
      -a > /keyring-out/cold_address.txt

    inferenced keys export cold \
      --unsafe --unarmored-hex --yes \$KEYRING \
      > /keyring-out/cold.hex

    # --- Warm key (ML operations) ---
    inferenced keys add warm \$KEYRING

    inferenced keys show warm \$KEYRING \
      -a > /keyring-out/warm_address.txt

    inferenced keys export warm \
      --unsafe --unarmored-hex --yes \$KEYRING \
      > /keyring-out/warm.hex

    # --- Validator and P2P keys via init ---
    inferenced init node \
      --chain-id '$CHAIN_ID' \
      --default-denom '$COIN_DENOM' \
      --home /tmp/node-home > /dev/null 2>&1

    cp /tmp/node-home/config/priv_validator_key.json /keyring-out/priv_validator_key.json
    cp /tmp/node-home/config/node_key.json /keyring-out/node_key.json

    echo '=== Cold key (account) ==='
    echo \"Address: \$(cat /keyring-out/cold_address.txt)\"
    echo 'Private key: cold.hex'
    echo '=== Warm key (ML operations) ==='
    echo \"Address: \$(cat /keyring-out/warm_address.txt)\"
    echo 'Private key: warm.hex'
    echo '=== Validator ==='
    echo \"Consensus pubkey: \$(jq -r '.pub_key.value' /keyring-out/priv_validator_key.json)\"
  "

echo "---"
echo "Exported to: $OUTPUT_DIR"
echo "  cold_address.txt         - cold key bech32 address"
echo "  cold.hex                 - cold key private key (unarmored hex)"
echo "  warm_address.txt         - warm key bech32 address"
echo "  warm.hex                 - warm key private key (unarmored hex)"
echo "  priv_validator_key.json  - validator consensus key"
echo "  node_key.json            - p2p node identity key"
