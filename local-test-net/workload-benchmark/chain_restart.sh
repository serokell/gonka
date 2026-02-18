cd ..

./generate-node-keys.sh genesis-keys
./generate-node-keys.sh join1-keys
./generate-node-keys.sh join2-keys

./launch_benchmark_env.sh 3
./propose-large-epoch.sh
cd workload-benchmark
