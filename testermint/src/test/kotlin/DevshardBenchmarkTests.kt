import com.productscience.*
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Tag
import org.junit.jupiter.api.Test
import java.io.File
import java.time.Duration
import java.util.concurrent.TimeUnit

@Tag("unstable")
class DevshardBenchmarkTests : TestermintTest() {
    private val devshardEscrowModel = defaultModel

    private val noRestrictionsConfig = inferenceConfig.copy(
        genesisSpec = inferenceConfig.genesisSpec?.merge(devshardNoRestrictionsSpec) ?: devshardNoRestrictionsSpec
    )

    @Test
    fun `devshard flow then launch benchmark script`() {
        val (cluster, genesis) = initCluster(config = noRestrictionsConfig, reboot = true)
        genesis.waitForNextEpoch()
        cluster.stubDevshardChatResponse()

        val user = genesis.createFundedDevshardUser("devshard-benchmark-user")
        genesis.waitForNextInferenceWindow()

        val escrowAmount = 7_000_000_000L
        val escrowId = genesis.createDevshardEscrowForUser(escrowAmount, user.keyName, modelId = devshardEscrowModel)

        val handle = genesis.startDevshardProxy(escrowId = escrowId, keyName = user.keyName)
        try {
            genesis.waitForDevshardProxyWarmup()

            logSection("Sending baseline devshard inference")
            val response = genesis.sendChatCompletion(handle.proxyUrl, defaultModel, "benchmark warmup")
            assertThat(response).isNotEmpty()

            val benchmarkDir = File(getRepoRoot(), "local-test-net/workload-benchmark")
            val gonkaEndpoints = cluster.allPairs
                .joinToString(";") { "http://${it.name.trimStart('/')}-api:9000/v1" }

            logSection("Starting workload benchmark container")
            runHostCommand(
                command = listOf("bash", "-lc", "./loadserver_rebuild_and_run.sh"),
                workingDirectory = benchmarkDir,
                environment = mapOf("GONKA_ENDPOINTS" to gonkaEndpoints),
                timeout = Duration.ofMinutes(15),
            )

            logSection("Launching benchmark script inside workload container")
            runHostCommand(
                command = listOf(
                    "docker", "exec", "workload-benchmark-server", "bash", "-lc",
                    "cd /app && nohup ./run_experiment.sh >/tmp/run_experiment.log 2>&1 &"
                ),
                timeout = Duration.ofMinutes(1),
            )

            val benchmarkProcessCheck = runHostCommand(
                command = listOf(
                    "docker", "exec", "workload-benchmark-server", "bash", "-lc",
                    "pgrep -f 'python load_testing.py'"
                ),
                timeout = Duration.ofMinutes(1),
            )
            assertThat(benchmarkProcessCheck).isNotBlank()

            genesis.assertDevshardSettlement(
                handle = handle,
                escrowId = escrowId,
                user = user,
                escrowAmount = escrowAmount,
                requireCompletedValidations = false,
            )
        } finally {
            genesis.stopDevshardProxy(escrowId)
            runHostCommand(
                command = listOf("docker", "stop", "workload-benchmark-server"),
                timeout = Duration.ofMinutes(1),
                checkExitCode = false,
            )
            runHostCommand(
                command = listOf("docker", "rm", "workload-benchmark-server"),
                timeout = Duration.ofMinutes(1),
                checkExitCode = false,
            )
        }
    }

    private fun runHostCommand(
        command: List<String>,
        workingDirectory: File = File(getRepoRoot()),
        environment: Map<String, String> = emptyMap(),
        timeout: Duration,
        checkExitCode: Boolean = true,
    ): String {
        val process = ProcessBuilder(command)
            .directory(workingDirectory)
            .redirectErrorStream(true)
            .also { pb -> pb.environment().putAll(environment) }
            .start()

        val finished = process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS)
        if (!finished) {
            process.destroyForcibly()
            error("Command timed out after ${timeout.seconds}s: ${command.joinToString(" ")}")
        }

        val output = process.inputStream.bufferedReader().readText()
        if (checkExitCode && process.exitValue() != 0) {
            error(
                "Command failed (exit=${process.exitValue()}): ${command.joinToString(" ")}\n$output"
            )
        }
        return output
    }
}
