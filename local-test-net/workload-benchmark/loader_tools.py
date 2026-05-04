import asyncio
import time
from typing import Callable, Tuple
import threading

_max_workers = 500  # Default
def set_thread_pool_size(size: int):
    """Set the thread pool size (call before running tests)"""
    global _max_workers
    _max_workers = size
    print(f"[POOL] Thread pool size set to: {_max_workers}")

async def async_worker_burst(request_function: Callable, num_requests: int):
    """
    Fire all requests asynchronously in one burst.
    
    Args:
        request_function: Async function to call
        num_requests: Number of requests to fire
    """
    tasks = [asyncio.create_task(request_function()) for _ in range(num_requests)]
    await asyncio.gather(*tasks, return_exceptions=True)


def run_async_worker(request_function: Callable, requests_per_worker: int, worker_id: int):
    """
    Worker thread that runs an async event loop to fire requests.
    
    Args:
        request_function: Async function to call
        requests_per_worker: Number of requests this worker should fire
        worker_id: ID of this worker
    """
    asyncio.run(async_worker_burst(request_function, requests_per_worker))

def generate_load(request_function: Callable,  # Expects SYNC function  
                 requests_per_second: int, 
                 duration_seconds: int, 
                 num_workers: int = 200, 
                 log_file: str = None) -> bool:
    """
    Generate load using pure async - single event loop firing all requests.
    
    Args:
        request_function: Async function to call
        requests_per_second: Number of requests to fire per second
        duration_seconds: How long to generate load (in seconds)
        num_workers: Ignored (kept for API compatibility)
        log_file: Optional log file to write overload warnings
    
    Returns:
        bool: True if completed without overload, False if overloaded
    """
    # Increase default thread pool size
    import concurrent.futures
    import asyncio
    
    # Create event loop with larger thread pool
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Set a large thread pool
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=_max_workers)
    loop.set_default_executor(executor)
    
    try:
        success = loop.run_until_complete(
            _async_load_generation(request_function, requests_per_second, duration_seconds, log_file)
        )
    finally:
        # Don't shut down executor - leave it for reuse
        loop.close()
    
    return success

async def _async_load_generation(request_function: Callable, 
                                 requests_per_second: int,
                                 duration_seconds: int,
                                 log_file: str = None) -> bool:
    """
    Pure async load generation with detailed timing instrumentation.
    """
    start_time = time.time()
    overloaded = False
    progress_interval = max(10, duration_seconds // 10)
    
    # Open log file if provided
    log = open(log_file, 'a') if log_file else None
    
    # Timing statistics
    timing_stats = []
    
    try:
        loop = asyncio.get_running_loop()
        # For each second in the duration
        for second in range(duration_seconds):
            second_start = time.time()
            
            # Time task creation
            task_creation_start = time.time()
            tasks = [
                loop.run_in_executor(None, request_function)  # None = default executor
                for _ in range(requests_per_second)
            ]
            task_creation_time = time.time() - task_creation_start
            
            # Time gather
            gather_start = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            gather_time = time.time() - gather_start
            
            errors = []
            successes = 0
            for r in results:
                if isinstance(r, Exception):
                    errors.append(str(type(r).__name__) + ": " + str(r))
                elif r is None:
                    errors.append("None result")
                else:
                    successes += 1

            error_count = len(errors)
            
            # Total time for this second
            elapsed = time.time() - second_start
            sleep_time = 1.0 - elapsed
            



            # Log detailed timing
            timing_data = {
                'second': second + 1,
                'task_creation_ms': task_creation_time * 1000,
                'gather_ms': gather_time * 1000,
                'total_ms': elapsed * 1000,
                'sleep_ms': max(0, sleep_time * 1000),
                'successes': successes,
                'errors': error_count,
                'overload': sleep_time <= 0
            }
            timing_stats.append(timing_data)
            
            # Log to file
            if log:
                log.write(f"[LOAD][TIMING] Second {second+1}: "
                        f"TaskCreate={task_creation_time*1000:.1f}ms, "
                        f"Gather={gather_time*1000:.1f}ms, "
                        f"Total={elapsed*1000:.1f}ms, "
                        f"Success={successes}/{requests_per_second}, "
                        f"Errors={error_count}\n")
                
                # Log first few unique errors
                if errors:
                    unique_errors = list(set(errors))[:3]  # First 3 unique errors
                    for err in unique_errors:
                        log.write(f"[LOAD][ERROR] {err}\n")
                
                log.flush()
            
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            else:
                warning_msg = f"[LOAD][WARNING] Second {second+1} overloaded, took {elapsed:.3f}s (TaskCreate={task_creation_time*1000:.1f}ms, Gather={gather_time*1000:.1f}ms)"
                print(warning_msg)
                if log:
                    log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {warning_msg}\n")
                    log.flush()
                overloaded = True
            
            # Progress update every N seconds
            if (second + 1) % progress_interval == 0 or (second + 1) == duration_seconds:
                requests_so_far = (second + 1) * requests_per_second
                elapsed_total = time.time() - start_time
                
                # Calculate average timings
                recent_stats = timing_stats[-progress_interval:] if len(timing_stats) >= progress_interval else timing_stats
                avg_task_create = sum(s['task_creation_ms'] for s in recent_stats) / len(recent_stats)
                avg_gather = sum(s['gather_ms'] for s in recent_stats) / len(recent_stats)
                avg_total = sum(s['total_ms'] for s in recent_stats) / len(recent_stats)
                
                print(f"[LOAD] Progress: {second+1}/{duration_seconds}s ({requests_so_far:,} requests fired, {elapsed_total:.1f}s elapsed)")
                print(f"[LOAD]   Avg timing: TaskCreate={avg_task_create:.1f}ms, Gather={avg_gather:.1f}ms, Total={avg_total:.1f}ms")
        
        total_elapsed = time.time() - start_time
        
        # Summary statistics
        total_successes = sum(s['successes'] for s in timing_stats)
        total_errors = sum(s['errors'] for s in timing_stats)
        avg_task_create = sum(s['task_creation_ms'] for s in timing_stats) / len(timing_stats)
        avg_gather = sum(s['gather_ms'] for s in timing_stats) / len(timing_stats)
        max_task_create = max(s['task_creation_ms'] for s in timing_stats)
        max_gather = max(s['gather_ms'] for s in timing_stats)
        
        completion_msg = f"[LOAD] Completed in {total_elapsed:.1f}s"
        print(completion_msg)
        print(f"[LOAD] Total: {total_successes:,} successes, {total_errors:,} errors")
        print(f"[LOAD] Timing breakdown:")
        print(f"[LOAD]   Task creation - Avg: {avg_task_create:.1f}ms, Max: {max_task_create:.1f}ms")
        print(f"[LOAD]   Gather wait   - Avg: {avg_gather:.1f}ms, Max: {max_gather:.1f}ms")
        
        if log:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {completion_msg}\n")
            log.write(f"Total: {total_successes:,} successes, {total_errors:,} errors\n")
            log.write(f"Timing - TaskCreate Avg={avg_task_create:.1f}ms Max={max_task_create:.1f}ms, "
                     f"Gather Avg={avg_gather:.1f}ms Max={max_gather:.1f}ms\n")
        
        if overloaded:
            overload_msg = f"[LOAD] ⚠️  OVERLOAD DETECTED - System could not sustain {requests_per_second:,} req/s"
            print(overload_msg)
            if log:
                log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {overload_msg}\n")
        else:
            success_msg = f"[LOAD] ✓ Successfully sustained {requests_per_second:,} req/s"
            print(success_msg)
            if log:
                log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {success_msg}\n")
        
        print("-" * 80)
        if log:
            log.write("-" * 80 + "\n")
            log.flush()
    
    finally:
        if log:
            log.close()
    
    return not overloaded




def measure_latency(request_function: Callable, start_delay: int, 
                   measurement_interval: int, num_measurements: int, 
                   log_file: str, blockchain_monitor=None, requests_per_second: int = None):
    """
    Measure both server/API latency and blockchain latency.
    
    Args:
        request_function: Function to call and measure (should return response object)
        start_delay: Seconds to wait before starting measurements
        measurement_interval: Seconds between measurements
        num_measurements: Number of measurements to take
        log_file: Path to log file for latency output
        blockchain_monitor: BlockchainMonitor instance (optional)
        requests_per_second: RPS being tested (for display purposes)
    
    Returns:
        list: Response times for each measurement
    """
    def log_and_print(message, log_handle):
        """Helper to write to both console and log file"""
        print(message)
        log_handle.write(message + "\n")
        log_handle.flush()
    
    # Open log file in append mode
    with open(log_file, 'a') as log:
        log_and_print(f"\n{'='*80}", log)
        log_and_print(f"LATENCY MEASUREMENT SESSION - {time.strftime('%Y-%m-%d %H:%M:%S')}", log)
        log_and_print(f"{'='*80}", log)
        log_and_print(f"[LATENCY] Waiting {start_delay}s before starting measurements...", log)
        
        time.sleep(start_delay)
        
        log_and_print(f"[LATENCY] Starting latency measurements: {num_measurements} measurements, {measurement_interval}s apart", log)
        log_and_print("-" * 80, log)
        
        api_latencies = []
        blockchain_data = []
        
        for i in range(1, num_measurements + 1):
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # Time the API request
            api_start_time = time.time()
            try:
                # Call and get full response object
                response_obj = request_function()
                api_end_time = time.time()
                api_latency = api_end_time - api_start_time
                
                # Extract inference ID if available
                inference_id = None
                if response_obj is not None and hasattr(response_obj, 'id'):
                    inference_id = response_obj.id
                
                api_latencies.append(api_latency)
                log_and_print(f"[LATENCY] [{timestamp}] Measurement #{i}/{num_measurements}:", log)
                log_and_print(f"  Server/API Latency: {api_latency:.3f}s ({api_latency * 1000:.1f}ms)", log)
                
                # Track blockchain events if monitor is available and we have inference_id
                if blockchain_monitor and inference_id:
                    # Register this inference_id for tracking/logging
                    blockchain_monitor.track_inference_id(inference_id)
                    
                    log_and_print(f"  Inference ID: {inference_id[:50]}...", log)
                    log_and_print(f"  Waiting for blockchain events...", log)
                    
                    # Wait for blockchain events (with timeout)
                    blockchain_events = blockchain_monitor.get_event_times(inference_id, timeout=30)
                    
                    if blockchain_events.get('start_time') and blockchain_events.get('finish_time'):
                        blockchain_start_latency = blockchain_events['start_time'] - api_start_time
                        blockchain_finish_latency = blockchain_events['finish_time'] - api_start_time
                        
                        # Processing time = maximum of the two (time until both events are confirmed)
                        blockchain_processing_time = max(blockchain_start_latency, blockchain_finish_latency)
                        
                        # Event difference = absolute time between the two events appearing
                        blockchain_event_diff = abs(blockchain_events['finish_time'] - blockchain_events['start_time'])
                        
                        log_and_print(f"  Blockchain StartInference:  {blockchain_start_latency:.3f}s ({blockchain_start_latency * 1000:.1f}ms) [Block #{blockchain_events.get('start_height')}]", log)
                        log_and_print(f"  Blockchain FinishInference: {blockchain_finish_latency:.3f}s ({blockchain_finish_latency * 1000:.1f}ms) [Block #{blockchain_events.get('finish_height')}]", log)
                        log_and_print(f"  Blockchain Processing Time: {blockchain_processing_time:.3f}s ({blockchain_processing_time * 1000:.1f}ms) (until both confirmed)", log)
                        log_and_print(f"  Blockchain Event Difference: {blockchain_event_diff:.3f}s ({blockchain_event_diff * 1000:.1f}ms) (between events)", log)
                        
                        blockchain_data.append({
                            'api_latency': api_latency,
                            'blockchain_start': blockchain_start_latency,
                            'blockchain_finish': blockchain_finish_latency,
                            'blockchain_processing': blockchain_processing_time,
                            'blockchain_diff': blockchain_event_diff,
                            'inference_id': inference_id
                        })
                    elif blockchain_events.get('start_time'):
                        blockchain_start_latency = blockchain_events['start_time'] - api_start_time
                        log_and_print(f"  Blockchain StartInference:  {blockchain_start_latency:.3f}s ({blockchain_start_latency * 1000:.1f}ms) [Block #{blockchain_events.get('start_height')}]", log)
                        log_and_print(f"  Blockchain FinishInference: NOT DETECTED (timeout)", log)
                        
                        blockchain_data.append({
                            'api_latency': api_latency,
                            'blockchain_start': blockchain_start_latency,
                            'blockchain_finish': None,
                            'blockchain_processing': None,
                            'blockchain_diff': None,
                            'inference_id': inference_id
                        })
                    elif blockchain_events.get('finish_time'):
                        blockchain_finish_latency = blockchain_events['finish_time'] - api_start_time
                        log_and_print(f"  Blockchain StartInference:  NOT DETECTED (timeout)", log)
                        log_and_print(f"  Blockchain FinishInference: {blockchain_finish_latency:.3f}s ({blockchain_finish_latency * 1000:.1f}ms) [Block #{blockchain_events.get('finish_height')}]", log)
                        
                        blockchain_data.append({
                            'api_latency': api_latency,
                            'blockchain_start': None,
                            'blockchain_finish': blockchain_finish_latency,
                            'blockchain_processing': None,
                            'blockchain_diff': None,
                            'inference_id': inference_id
                        })
                    else:
                        log_and_print(f"  Blockchain StartInference:  NOT DETECTED (timeout)", log)
                        log_and_print(f"  Blockchain FinishInference: NOT DETECTED (timeout)", log)
                
                log_and_print("-" * 80, log)
                
            except Exception as e:
                log_and_print(f"[LATENCY] [{timestamp}] Measurement #{i}: ERROR - {e}", log)
            
            # Wait before next measurement (except for the last one)
            if i < num_measurements:
                time.sleep(measurement_interval)
        
        # Calculate statistics
        if api_latencies:
            avg_api_latency = sum(api_latencies) / len(api_latencies)
            min_api_latency = min(api_latencies)
            max_api_latency = max(api_latencies)
            
            log_and_print("-" * 80, log)
            log_and_print(f"[LATENCY] Measurement complete:", log)
            if requests_per_second is not None:
                log_and_print(f"  RPS: {requests_per_second:,}", log)
            log_and_print(f"  Successful measurements: {len(api_latencies)}/{num_measurements}", log)
            log_and_print(f"", log)
            log_and_print(f"  SERVER/API LATENCY:", log)
            log_and_print(f"    Average: {avg_api_latency:.3f}s ({avg_api_latency * 1000:.1f}ms)", log)
            log_and_print(f"    Min:     {min_api_latency:.3f}s ({min_api_latency * 1000:.1f}ms)", log)
            log_and_print(f"    Max:     {max_api_latency:.3f}s ({max_api_latency * 1000:.1f}ms)", log)
            
            # Blockchain statistics
            if blockchain_data:
                blockchain_starts = [d['blockchain_start'] for d in blockchain_data if d['blockchain_start'] is not None]
                blockchain_finishes = [d['blockchain_finish'] for d in blockchain_data if d['blockchain_finish'] is not None]
                blockchain_processing = [d['blockchain_processing'] for d in blockchain_data if d['blockchain_processing'] is not None]
                blockchain_diffs = [d['blockchain_diff'] for d in blockchain_data if d['blockchain_diff'] is not None]
                
                if blockchain_starts:
                    log_and_print(f"", log)
                    log_and_print(f"  BLOCKCHAIN START LATENCY:", log)
                    log_and_print(f"    Average: {sum(blockchain_starts)/len(blockchain_starts):.3f}s ({sum(blockchain_starts)/len(blockchain_starts) * 1000:.1f}ms)", log)
                    log_and_print(f"    Min:     {min(blockchain_starts):.3f}s ({min(blockchain_starts) * 1000:.1f}ms)", log)
                    log_and_print(f"    Max:     {max(blockchain_starts):.3f}s ({max(blockchain_starts) * 1000:.1f}ms)", log)
                
                if blockchain_finishes:
                    log_and_print(f"", log)
                    log_and_print(f"  BLOCKCHAIN FINISH LATENCY:", log)
                    log_and_print(f"    Average: {sum(blockchain_finishes)/len(blockchain_finishes):.3f}s ({sum(blockchain_finishes)/len(blockchain_finishes) * 1000:.1f}ms)", log)
                    log_and_print(f"    Min:     {min(blockchain_finishes):.3f}s ({min(blockchain_finishes) * 1000:.1f}ms)", log)
                    log_and_print(f"    Max:     {max(blockchain_finishes):.3f}s ({max(blockchain_finishes) * 1000:.1f}ms)", log)
                
                if blockchain_processing:
                    log_and_print(f"", log)
                    log_and_print(f"  BLOCKCHAIN PROCESSING TIME (until both confirmed):", log)
                    log_and_print(f"    Average: {sum(blockchain_processing)/len(blockchain_processing):.3f}s ({sum(blockchain_processing)/len(blockchain_processing) * 1000:.1f}ms)", log)
                    log_and_print(f"    Min:     {min(blockchain_processing):.3f}s ({min(blockchain_processing) * 1000:.1f}ms)", log)
                    log_and_print(f"    Max:     {max(blockchain_processing):.3f}s ({max(blockchain_processing) * 1000:.1f}ms)", log)
                
                if blockchain_diffs:
                    log_and_print(f"", log)
                    log_and_print(f"  BLOCKCHAIN EVENT DIFFERENCE (between events):", log)
                    log_and_print(f"    Average: {sum(blockchain_diffs)/len(blockchain_diffs):.3f}s ({sum(blockchain_diffs)/len(blockchain_diffs) * 1000:.1f}ms)", log)
                    log_and_print(f"    Min:     {min(blockchain_diffs):.3f}s ({min(blockchain_diffs) * 1000:.1f}ms)", log)
                    log_and_print(f"    Max:     {max(blockchain_diffs):.3f}s ({max(blockchain_diffs) * 1000:.1f}ms)", log)
            
            log_and_print("-" * 80, log)

        return api_latencies
  
def run_load_test(async_request_function: Callable,
                 sync_request_function: Callable,
                 requests_per_second: int = 10,
                 load_duration: int = 120,
                 num_workers: int = 200,
                 latency_start_delay: int = 20,
                 latency_interval: int = 5,
                 latency_measurements: int = 5,
                 log_file: str = None,
                 blockchain_monitor=None) -> Tuple[list, bool]:
    """
    Run parallel hybrid async load generation and sync latency measurement.
    
    Args:
        async_request_function: Async function to call for load testing
        sync_request_function: Sync function to call for latency measurement
        requests_per_second: Number of requests to fire per second
        load_duration: Duration of load generation in seconds
        num_workers: Number of worker threads, each running async event loop
        latency_start_delay: Seconds to wait before starting latency measurements
        latency_interval: Seconds between latency measurements
        latency_measurements: Number of latency measurements to take
        log_file: Path to log file (will be auto-generated with timestamp if None)
    
    Returns:
        Tuple[list, bool]: (latency measurements, success flag - False if overloaded)
    """
    total_requests = requests_per_second * load_duration
    
    # Generate log filename with timestamp if not provided
    create_header = False
    if log_file is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_file = f"/experimental_logs/load_test_{timestamp}.log"
        create_header = True
    
    print("=" * 80)
    print("STARTING HYBRID ASYNC LOAD TEST")
    print("=" * 80)
    print(f"Configuration:")
    print(f"  Load: {requests_per_second:,} req/s for {load_duration}s = {total_requests:,} total requests")
    print(f"  Workers: {num_workers} threads × async event loops")
    print(f"  Latency: {latency_measurements} measurements starting after {latency_start_delay}s, every {latency_interval}s")
    print(f"  Log file: {log_file}")
    print("=" * 80)
    print()
    
    # Write header to log file only if this is a new file
    if create_header:
        with open(log_file, 'w') as log:
            log.write(f"{'='*80}\n")
            log.write(f"LOAD TEST LOG - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            log.write(f"{'='*80}\n")
            log.write(f"Configuration:\n")
            log.write(f"  Load: {requests_per_second:,} req/s for {load_duration}s = {total_requests:,} total requests\n")
            log.write(f"  Workers: {num_workers} threads\n")
            log.write(f"  Latency: {latency_measurements} measurements starting after {latency_start_delay}s, every {latency_interval}s\n")
            log.write(f"{'='*80}\n\n")
    
    # Shared state for overload detection
    overload_detected = [False]
    
    latency_results = []
    def latency_wrapper():
        latency_results.extend(
            measure_latency(sync_request_function, latency_start_delay, 
                          latency_interval, latency_measurements, log_file,
                          blockchain_monitor, requests_per_second)  # Pass blockchain_monitor
        )

    # Start load generation in a separate thread
    def run_load():
        success = generate_load(async_request_function, requests_per_second, load_duration, num_workers, log_file)
        overload_detected[0] = not success
    
    load_thread = threading.Thread(target=run_load, daemon=True)
    
    # Start latency measurement in a separate thread
    latency_results = []
    def latency_wrapper():
        latency_results.extend(
            measure_latency(sync_request_function, latency_start_delay, 
                          latency_interval, latency_measurements, log_file, blockchain_monitor, requests_per_second)
        )
    
    latency_thread = threading.Thread(target=latency_wrapper)
    
    # Start both threads
    test_start = time.time()
    load_thread.start()
    latency_thread.start()
    
    # Wait for both to complete
    load_thread.join()
    latency_thread.join()
    
    test_duration = time.time() - test_start
    
    print()
    print("=" * 80)
    print(f"LOAD TEST COMPLETE (total duration: {test_duration:.1f}s)")
    print(f"Full log saved to: {log_file}")
    print("=" * 80)
    
    return latency_results, not overload_detected[0]
