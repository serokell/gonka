#!/bin/bash
set -e

IMAGE="ghcr.io/product-science/inferenced"
OUTPUT_DIR="${1:?Usage: $0 <output-dir> [num-keypairs]}"
NUM_KEYS="${2:-1}"

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

echo "Generating $NUM_KEYS genesis keypair(s) using image $IMAGE"
echo "Output directory: $OUTPUT_DIR"

for i in $(seq 1 "$NUM_KEYS"); do
  echo "--- Generating keypair account${i} ---"
  docker run --rm \
    -v "$OUTPUT_DIR:/keyring-out" \
    "$IMAGE" \
    sh -c "
      set -e

      KEYRING='--keyring-backend test --keyring-dir /tmp/keyring'

      inferenced keys add account${i} \$KEYRING

      inferenced keys show account${i} \$KEYRING \
        -a > /keyring-out/account${i}_address.txt

      inferenced keys export account${i} \
        --unsafe --unarmored-hex --yes \$KEYRING \
        > /keyring-out/account${i}.hex

      echo '=== Account ${i} ==='
      echo \"Address: \$(cat /keyring-out/account${i}_address.txt)\"
      echo 'Private key: account${i}.hex'
    "
done

echo "---"
echo "Exported to: $OUTPUT_DIR"
for i in $(seq 1 "$NUM_KEYS"); do
  echo "  account${i}_address.txt  - account${i} bech32 address"
  echo "  account${i}.hex          - account${i} private key (unarmored hex)"
done
