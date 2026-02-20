#! /usr/bin/env bash

set -e

SCHEDULES_FILE=${SCHEDULES_FILE:-schedules.json}
EXPERIMENTAL_LOGS_DIR=${EXPERIMENTAL_LOGS_DIR:-experimental_logs}

# Schedules to run from SCHEDULES_FILE
schedules=(
    "ping"
)

# Number of runs for each schedule
NUMBER_OF_RUNS="1"
# Number of nodes in the blockchain network
NUMBER_OF_NODES="12"

# Duration of each experiment in seconds
DURATION="300"
# Initial delay before starting latency measurements in seconds
LATENCY_DELAY="10"
# Interval between latency measurements in seconds
LATENCY_INTERVAL="2"
# Number of latency measurements to take
LATENCY_COUNT="7"

restart_blockchain() {
    pushd ..
    echo "Restarting blockchain nodes..."
    ./stop_benchmark_nodes.sh
    sudo rm -rf prod-local || true
    RESOURCE_LIMITS=true ./launch_benchmark_env.sh "$NUMBER_OF_NODES"
    popd
}

run_experiment() {
    local schedule="$1"
    local addr
    addr="$(docker exec genesis-node inferenced keys show POOL_product_science_inc -a)"
    docker exec genesis-node inferenced tx bank send "$addr" "$addr" 100nicoin --yes >/dev/null 2>&1
    sleep 6 # Wait for the transaction to be processed and the chain to stabilize
    GONKA_PRIVATE_KEY="$(docker exec genesis-node inferenced keys export POOL_product_science_inc --unsafe --unarmored-hex --yes)"
    GONKA_ENDPOINTS="$(cat ../benchmark_endpoints.txt)"

    docker run --rm \
        --network=chain-public \
        --ulimit nofile=16384:16384 \
        -v "$(pwd)/$EXPERIMENTAL_LOGS_DIR:/app/experimental_logs" \
        -v "$(pwd)/$SCHEDULES_FILE:/app/schedules.json" \
        -e "GONKA_ENDPOINTS=$GONKA_ENDPOINTS" \
        -e "GONKA_PRIVATE_KEY=$GONKA_PRIVATE_KEY" \
        workload-benchmark-server \
        python load_testing.py \
            --schedule "$schedule" \
            --duration "$DURATION" \
            --workers 300 \
            --latency-delay "$LATENCY_DELAY" \
            --latency-interval "$LATENCY_INTERVAL" \
            --latency-count "$LATENCY_COUNT"
}

mkdir -p "$EXPERIMENTAL_LOGS_DIR"
for schedule in "${schedules[@]}"; do
    for ((run=1; run<=NUMBER_OF_RUNS; run++)); do
        echo "=== Schedule: $schedule | Run: $run/$NUMBER_OF_RUNS ==="
        restart_blockchain
        run_experiment "$schedule"
    done
done

pushd ..
./stop_benchmark_nodes.sh
popd
