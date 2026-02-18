## Benchmarks for Gonka local test network

This describes the procedure the run benchmarks on a container network with
the specified number of hosts, each running an API, Blockchain and a mock ML node.

### Creating the environment

Download the required docker images from,

https://github.com/gonka-ai/gonka/actions/runs/21810732149/artifacts/5426499945

After unzipping, load the images one by one

```
docker load -i inference-mock-server.tar.gz
docker load -i decentralized-api.tar.gz
docker load -i inference-chain.tar.gz
docker load -i proxy.tar.gz
```

### Start the local cluster

* Checkout [serokell/sras/readme-with-patches](https://github.com/serokell/gonka/tree/sras/readme-with-patches).
* Change directory to `local-test-net/workload-benchmark`
* Run `./chain_restart.sh`

This will start a local blockchain with 3 hosts. Wait till it finishes.

### Start the benchmarking container

```
./loadserver_rebuild_and_run.sh
```

### Start the benchmark

At this point, you should be able to access the benchmark interface at local port `5001`.
Proceed to ssh to the benchmark container,

```
docker exec -it workload-benchmark-server /bin/bash
```

To start the benchmark, run

```
python load_testing.py --schedule linear_1k
```

To see the various options that can be passed to this script, see source of `run_experiment.sh`.

### Viewing the results

After you start the `load_testing.py` script, the UI should update shortly with the new logs. Click on the new log
entry to start seeing the plots that will be updated realtime.

### Stopping and removing the containers

Change directory to `/local-test-net` and run `./stop.sh`

### Configuring the number of hosts

Edit the `chain_restart.sh` script where it says 3 to the required number of hosts.

```
./launch_benchmark_env.sh 3
```
