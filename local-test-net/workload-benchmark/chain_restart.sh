cd ..

./generate-node-keys.sh genesis-keys
./generate-node-keys.sh join1-keys
./generate-node-keys.sh join2-keys

./launch.sh
./propose-large-epoch.sh
cd workload_benchmark
