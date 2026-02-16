import loader_tools
import json
import os
import sys
import logging
import asyncio
from contextlib import contextmanager
from gonka_openai import GonkaOpenAI
import os
import sys
import logging
import asyncio
import time
import argparse
import blockchain_monitor

# Configure logging once
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpx").propagate = False
logging.getLogger().setLevel(logging.WARNING)

# Global devnull for suppression
_devnull = open(os.devnull, 'w')

class SuppressPrints:
    """Thread-safe stdout suppression"""
    def __enter__(self):
        self._original = sys.stdout
        sys.stdout = _devnull
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self._original


def make_gonka_request_sync_suppressed():
    """For load generation - fully suppressed"""
    try:
        with SuppressPrints():
            client = GonkaOpenAI()
            response = client.chat.completions.create(
                model="Qwen/Qwen2.5-7B-Instruct",
                messages=[
                    {"role": "user", "content": "Write a one-sentence bedtime story about a unicorn"}
                ]
            )
        return response.choices[0].message.content
    except Exception as e:
        return None


async def make_gonka_request_async():
    """For load generation"""
    try:
        result = await asyncio.to_thread(make_gonka_request_sync_suppressed)
        return result
    except Exception as e:
        return None


def make_gonka_request_sync_verbose():
    """
    For latency measurement - returns full response object for blockchain tracking.
    """
    try:
        with SuppressPrints():
            client = GonkaOpenAI()
            response = client.chat.completions.create(
                model="Qwen/Qwen2.5-7B-Instruct",
                messages=[
                    {"role": "user", "content": "Write a one-sentence bedtime story about a unicorn"}
                ]
            )
        return response  # Return full response object, not just content
    except Exception as e:
        print(f"[ERROR] {e}")
        return None


def load_schedules(filename="schedules.json"):
    """Load experiment schedules from JSON file"""
    with open(filename, 'r') as f:
        return json.load(f)

def run_scheduled_experiment(schedule_name: str,
                             async_request_function,
                             sync_request_function,
                             schedules_file="schedules.json",
                             load_duration=10,
                             num_workers=200,
                             latency_start_delay=2,
                             latency_interval=2,
                             latency_measurements=3,
                             bc_monitor=None):
    """
    Run load test following a schedule from JSON file.
    
    Args:
        schedule_name: Name of the schedule in the JSON file
        async_request_function: Async function for load generation
        sync_request_function: Sync function for latency measurement
        schedules_file: Path to schedules JSON file
        load_duration: Duration for each load test step
        num_workers: Number of worker threads
        latency_start_delay: Delay before latency measurements
        latency_interval: Interval between latency measurements
        latency_measurements: Number of latency measurements
    """
    # Load schedules
    schedules = load_schedules(schedules_file)
    
    if schedule_name not in schedules:
        print(f"ERROR: Schedule '{schedule_name}' not found in {schedules_file}")
        print(f"Available schedules: {list(schedules.keys())}")
        return
    
    schedule = schedules[schedule_name]
    
    # Generate log filename ONCE for the entire experiment
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_file = f"experimental_logs/experiment_{schedule_name}_{timestamp}.log"
    if bc_monitor:
        bc_monitor.log_file = log_file
    
    print("=" * 80)
    print(f"RUNNING SCHEDULED EXPERIMENT: {schedule_name}")
    print("=" * 80)
    print(f"Schedule: {schedule}")
    print(f"Total steps: {len(schedule)}")
    print(f"Duration per step: {load_duration}s")
    print(f"Log file: {log_file}")
    print("=" * 80)
    print()
    
    # Write experiment header to log file
    with open(log_file, 'w') as log:
        log.write(f"{'='*80}\n")
        log.write(f"SCHEDULED EXPERIMENT: {schedule_name}\n")
        log.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"{'='*80}\n")
        log.write(f"Schedule: {schedule}\n")
        log.write(f"Total steps: {len(schedule)}\n")
        log.write(f"Duration per step: {load_duration}s\n")
        log.write(f"{'='*80}\n\n")
    
    # Store results
    results = []
    
    # Run each step in the schedule
    for step_num, rps in enumerate(schedule, 1):
        print()
        print("=" * 80)
        print(f"STEP {step_num}/{len(schedule)}: {rps:,} RPS")
        print("=" * 80)
        print()
        
        # Write step header to log file
        with open(log_file, 'a') as log:
            log.write(f"\n\n{'='*80}\n")
            log.write(f"STEP {step_num}/{len(schedule)}: {rps:,} RPS\n")
            log.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            log.write(f"{'='*80}\n\n")
        
        # Run the load test with the SAME log file
        latency_results, success = loader_tools.run_load_test(
            async_request_function=async_request_function,
            sync_request_function=sync_request_function,
            requests_per_second=rps,
            load_duration=load_duration,
            num_workers=num_workers,
            latency_start_delay=latency_start_delay,
            latency_interval=latency_interval,
            latency_measurements=latency_measurements,
            log_file=log_file,
            blockchain_monitor=bc_monitor  # Pass the same log file to all steps
        )
        
        # Store results
        results.append({
            'step': step_num,
            'rps': rps,
            'latencies': latency_results,
            'success': success
        })
        
        # Check for overload
        if not success:
            print()
            print("=" * 80)
            print(f"⚠️  EXPERIMENT STOPPED AT STEP {step_num}/{len(schedule)}")
            print(f"⚠️  OVERLOAD DETECTED AT {rps:,} RPS")
            if step_num > 1:
                print(f"⚠️  Maximum sustainable load found: {schedule[step_num-2]:,} RPS (step {step_num-1})")
            print("=" * 80)
            
            # Write to log file
            with open(log_file, 'a') as log:
                log.write(f"\n\n{'='*80}\n")
                log.write(f"EXPERIMENT STOPPED AT STEP {step_num}/{len(schedule)}\n")
                log.write(f"OVERLOAD DETECTED AT {rps:,} RPS\n")
                if step_num > 1:
                    log.write(f"Maximum sustainable load found: {schedule[step_num-2]:,} RPS (step {step_num-1})\n")
                log.write(f"{'='*80}\n")
            
            #break
    else:
        # Schedule completed without overload
        print()
        print("=" * 80)
        print(f"✓ EXPERIMENT COMPLETED SUCCESSFULLY")
        print(f"✓ All {len(schedule)} steps completed without overload")
        print(f"✓ Maximum tested load: {schedule[-1]:,} RPS")
        print("=" * 80)
        
        # Write to log file
        with open(log_file, 'a') as log:
            log.write(f"\n\n{'='*80}\n")
            log.write(f"EXPERIMENT COMPLETED SUCCESSFULLY\n")
            log.write(f"All {len(schedule)} steps completed without overload\n")
            log.write(f"Maximum tested load: {schedule[-1]:,} RPS\n")
            log.write(f"{'='*80}\n")
    
    # Print summary
    print()
    print("=" * 80)
    print("EXPERIMENT SUMMARY")
    print("=" * 80)
    for result in results:
        status = "✓ SUCCESS" if result['success'] else "✗ OVERLOAD"
        avg_latency = sum(result['latencies']) / len(result['latencies']) if result['latencies'] else 0
        print(f"Step {result['step']}: {result['rps']:>8,} RPS - {status} - Avg latency: {avg_latency:.3f}s")
    print("=" * 80)
    print(f"Full experiment log: {log_file}")
    print("=" * 80)
    
    # Write summary to log file
    with open(log_file, 'a') as log:
        log.write(f"\n\n{'='*80}\n")
        log.write(f"EXPERIMENT SUMMARY\n")
        log.write(f"{'='*80}\n")
        for result in results:
            status = "SUCCESS" if result['success'] else "OVERLOAD"
            avg_latency = sum(result['latencies']) / len(result['latencies']) if result['latencies'] else 0
            log.write(f"Step {result['step']}: {result['rps']:>8,} RPS - {status} - Avg latency: {avg_latency:.3f}s\n")
        log.write(f"{'='*80}\n")
        log.write(f"Experiment completed: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    return results


if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Run load testing experiment with scheduled RPS')
    
    parser.add_argument('--schedule', type=str, default='fibonacci',
                       help='Schedule name from schedules.json (default: fibonacci)')
    parser.add_argument('--duration', type=int, default=10,
                       help='Duration for each load test step in seconds (default: 10)')
    parser.add_argument('--workers', type=int, default=200,
                       help='Number of worker threads (default: 200)')
    parser.add_argument('--latency-delay', type=int, default=2,
                       help='Delay before starting latency measurements in seconds (default: 2)')
    parser.add_argument('--latency-interval', type=int, default=2,
                       help='Interval between latency measurements in seconds (default: 2)')
    parser.add_argument('--latency-count', type=int, default=3,
                       help='Number of latency measurements to take (default: 3)')
    args = parser.parse_args()

    # Generate log filename
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_file = f"experimental_logs/experiment_{args.schedule}_{timestamp}.log"
    
    # Start blockchain monitor WITH the log file
    bc_monitor = blockchain_monitor.BlockchainMonitor(log_file=log_file)
    bc_monitor.start()
    
    try:
        # Run the scheduled experiment
        print("\n" + "="*80)
        print("Starting load test experiment...")
        print("="*80 + "\n")
        
        results = run_scheduled_experiment(
            schedule_name=args.schedule,
            async_request_function=make_gonka_request_async,
            sync_request_function=make_gonka_request_sync_verbose,
            schedules_file="schedules.json",
            load_duration=args.duration,
            num_workers=args.workers,
            latency_start_delay=args.latency_delay,
            latency_interval=args.latency_interval,
            latency_measurements=args.latency_count,
            bc_monitor=bc_monitor
        )
        time.sleep(20)
    finally:
        bc_monitor.stop()



