docker stop workload-benchmark-server
docker rm workload-benchmark-server
docker build -t workload-benchmark-server .

cd ..
genesis_addr="$(cat ./genesis-keys/cold_address.txt)"
join1_warm_addr="$(cat ./join1-keys/warm_address.txt)"
join2_warm_addr="$(cat ./join2-keys/warm_address.txt)"

addr="$(docker exec genesis-node inferenced keys show POOL_product_science_inc -a)"
docker exec genesis-node inferenced tx bank send "$addr" "$addr" 100nicoin --yes
moneybag_secret_key="$(docker exec genesis-node inferenced keys export POOL_product_science_inc --unsafe --unarmored-hex --yes)"

cd workload-benchmark

docker run -d \
  --name workload-benchmark-server \
  --network=chain-public \
  -p 5001:5000 \
  -e "GONKA_ENDPOINTS=http://genesis-api:9000/v1;$genesis_addr,http://join1-api:9000/v1;$join1_warm_addr,http://join2-api:9000/v1;$join2_warm_addr" \
  -e "GONKA_PRIVATE_KEY=$moneybag_secret_key" \
  workload-benchmark-server