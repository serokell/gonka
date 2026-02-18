cd ..

./generate-node-keys.sh genesis-keys
./generate-node-keys.sh join1-keys
./generate-node-keys.sh join2-keys

NUM_JOIN_NODES="${1:-3}"
echo "Using $NUM_JOIN_NODES nodes."
./launch_benchmark_env.sh "$NUM_JOIN_NODES"

cd workload-benchmark
