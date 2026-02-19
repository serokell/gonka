## Benchmarks for Gonka local test network

This describes the procedure to run benchmarks on a container network with
the specified number of hosts, each running an API, blockchain node and a mock ML node.

### Creating the environment

You need to have Docker, Java and Gradle to build the docker images. Once you have those, run

```
cd local-test-net
./stop-rebuild.sh
```

### Start the local cluster

* Checkout [serokell/sras/readme-with-patches](https://github.com/serokell/gonka/tree/sras/readme-with-patches).
* Change directory to `local-test-net/workload-benchmark`
* Run `./chain_restart.sh 3`

This will start a local blockchain with 3 hosts.

To limit resources used by the containers you can optionally also set

```
export RESOURCE_LIMITS=true
```

After the script has finished, look for the following line in the output,

```
=========================== GONKA ENDPOINTS ==============================
```

Just below that line, you will see a list of endpoint that looks something like,

```
http://join1-api:9000/v1;gonka1zf6w28urkzd8zvffxv8frknng2jrd....
```

Copy that and use it to define the `GONKA_ENDPOINTS` environment variable.

```
export GONKA_ENDPOINTS="http://join1-api:9000/v1;..."
```

### Start the benchmarking container

Run the following in the same terminal session.
```
./loadserver_rebuild_and_run.sh
```

### Start the benchmark

At this point, you should be able to access the benchmark interface at local port `5001`.
Proceed to log in to the benchmark container,

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
