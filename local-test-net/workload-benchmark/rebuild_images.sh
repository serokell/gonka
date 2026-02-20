#! /usr/bin/env bash

tmp=$(jq '."app_state"."inference"."params"."epoch_params"."epoch_length" = "20"' ../../inference-chain/test_genesis_overrides.json) \
    && printf '%s\n' "$tmp" > ../../inference-chain/test_genesis_overrides.json

export GENESIS_OVERRIDES_FILE="inference-chain/test_genesis_overrides.json"
export BLST_PORTABLE=1
export SET_LATEST=1
make -C ../../. build-docker

docker build -t workload-benchmark-server .
