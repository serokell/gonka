################################################################################
# Load Testing Experiment Runner
################################################################################
#
# This script runs load testing experiments against the Gonka API.
#
# PARAMETERS:
#   --schedule SCHEDULE_NAME
#       Schedule name from schedules.json (default: fibonacci)
#       Available schedules: fibonacci, linear_1k, exponential, stress_test, quick_test
#
#   --duration SECONDS
#       Duration for each load test step in seconds (default: 10)
#       Example: --duration 30 means each RPS level runs for 30 seconds
#
#   --workers COUNT
#       Number of worker threads (default: 200)
#       Higher values = more parallel execution (useful for high RPS)
#       Recommendation: RPS / 10 to RPS / 100
#
#   --latency-delay SECONDS
#       Delay before starting latency measurements in seconds (default: 2)
#       Gives the load generator time to stabilize before measuring
#
#   --latency-interval SECONDS
#       Interval between latency measurements in seconds (default: 2)
#       How often to measure response time during the test
#
#   --latency-count COUNT
#       Number of latency measurements to take (default: 3)
#       Total measurements = latency-count per step
#
# USAGE EXAMPLES:
#
#   # Run with defaults (fibonacci schedule)
#   ./run_experiment.sh
#
#   # Quick test with ping schedule
#   ./run_experiment.sh --schedule ping --duration 5
#
#   # Stress test with high load
#   ./run_experiment.sh --schedule stress_test --duration 60 --workers 1000
#
#   # Custom configuration
#   ./run_experiment.sh \
#       --schedule fibonacci \
#       --duration 30 \
#       --workers 500 \
#       --latency-delay 5 \
#       --latency-interval 3 \
#       --latency-count 10
#
# OUTPUT:
#   - Console: Real-time progress and summary
#   - Log file: experiment_SCHEDULENAME_TIMESTAMP.log
#       Contains detailed latency measurements and load statistics
#
################################################################################    
#   UI with the logs view is available via :5000/logs
################################################################################

python load_testing.py \
    --schedule fibonacci \
    --duration 15 \
    --workers 300 \
    --latency-delay 3 \
    --latency-interval 2 \
    --latency-count 3