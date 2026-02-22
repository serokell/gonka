docker stop go-workload-benchmark-server
docker rm go-workload-benchmark-server
docker build -t go-workload-benchmark-server .

addr="$(docker exec genesis-node inferenced keys show POOL_product_science_inc -a)"
docker exec genesis-node inferenced tx bank send "$addr" "$addr" 100nicoin --yes
moneybag_secret_key="$(docker exec genesis-node inferenced keys export POOL_product_science_inc --unsafe --unarmored-hex --yes)"

docker run -it \
  --name go-workload-benchmark-server \
  --network=chain-public \
  --ulimit nofile=16384:16384 \
  -v ./experimental_logs:/app/experimental_logs \
  -v ./benchmark:/app/shared \
  -p 5001:5000 \
  -e "GONKA_ENDPOINTS=$GONKA_ENDPOINTS" \
  -e "GONKA_PRIVATE_KEY=$moneybag_secret_key" \
  go-workload-benchmark-server /bin/sh
