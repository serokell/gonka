docker stop workload-benchmark-server
docker rm workload-benchmark-server
docker build -t workload-benchmark-server .

addr="$(docker exec genesis-node inferenced keys show POOL_product_science_inc -a)"
docker exec genesis-node inferenced tx bank send "$addr" "$addr" 100nicoin --yes
moneybag_secret_key="$(docker exec genesis-node inferenced keys export POOL_product_science_inc --unsafe --unarmored-hex --yes)"

docker run -d \
  --name workload-benchmark-server \
  --network=chain-public \
  --ulimit nofile=16384:16384 \
  -v ./experimental_logs:/app/experimental_logs \
  -p 5001:5000 \
  -e "GONKA_ENDPOINTS=$GONKA_ENDPOINTS" \
  -e "GONKA_PRIVATE_KEY=$moneybag_secret_key" \
  workload-benchmark-server
