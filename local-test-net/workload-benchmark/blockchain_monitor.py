import urllib.request
from websockets.sync.client import connect
import time
import json
import threading

class BlockchainMonitor:
    """
    Monitors blockchain for inference events in the background.
    Tracks StartInference and FinishInference events by inference_id.
    """

    def __init__(self, websocket_url="ws://genesis-node:26657/websocket",
                 grpc_url="http://genesis-node:1317/cosmos/tx/v1beta1/txs",
                 log_file=None):
        self.websocket_url = websocket_url
        self.grpc_url = grpc_url
        self.log_file = log_file
        self.inference_events = {}
        self.tracked_ids = set()  # NEW: Only log events for these IDs
        self.lock = threading.Lock()
        self.running = False
        self.thread = None

    def track_inference_id(self, inference_id):
        """
        Register an inference_id to track and log.
        Only events for tracked IDs will be written to the log file.
        """
        with self.lock:
            self.tracked_ids.add(inference_id)

    def _log(self, message):
        """Write message to log file and console"""
        print(message)
        if self.log_file:
            try:
                with open(self.log_file, 'a') as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
                    f.flush()
            except Exception as e:
                print(f"[BLOCKCHAIN] Failed to write to log: {e}")

    def start(self):
        """Start the blockchain monitoring thread"""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._watch_blockchain, daemon=True)
        self.thread.start()
        self._log("[BLOCKCHAIN] Monitor started")

    def stop(self):
        """Stop the blockchain monitoring thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self._log("[BLOCKCHAIN] Monitor stopped")

    def get_event_times(self, inference_id, timeout=60):
        """
        Get blockchain event times for an inference_id.
        Waits up to timeout seconds for BOTH events to appear.
        """
        # Check if this ID is tracked
        is_tracked = False
        with self.lock:
            is_tracked = inference_id in self.tracked_ids

        if is_tracked:
            self._log(f"[BLOCKCHAIN] Waiting for events for inference ID: {inference_id[:50]}...")

        start_wait = time.time()

        while time.time() - start_wait < timeout:
            with self.lock:
                if inference_id in self.inference_events:
                    events = self.inference_events[inference_id]
                    # Check if we have both events
                    if events.get('start_time') and events.get('finish_time'):
                        if is_tracked:
                            self._log(f"[BLOCKCHAIN] Both events found for {inference_id[:50]}...")
                        return events
            time.sleep(0.1)

        # Timeout - return whatever we have
        timeout_time = start_wait + timeout

        with self.lock:
            events = self.inference_events.get(inference_id, {})

            if is_tracked:
                if events.get('start_time') or events.get('finish_time'):
                    self._log(f"[BLOCKCHAIN] Timeout - partial events for {inference_id[:50]}: Start={events.get('start_time') is not None}, Finish={events.get('finish_time') is not None}")
                else:
                    self._log(f"[BLOCKCHAIN] Timeout - no events found for {inference_id[:50]}")

            return {
                'start_time': events.get('start_time', timeout_time),
                'finish_time': events.get('finish_time', timeout_time),
                'start_height': events.get('start_height', 0),
                'finish_height': events.get('finish_height', 0),
                'timed_out': True,
                'partial': bool(events.get('start_time') or events.get('finish_time'))
            }

    def _fetch_json(self, url: str, timeout: int = 30):
        while True:
            try:
                with urllib.request.urlopen(url, timeout=timeout) as response:
                    return json.loads(response.read().decode())
            except Exception as e:
                self._log(f"Error fetching {url}: {e}, retrying...")
                pass

    def _fetch_json_bak(self, url, timeout=10):
        """Fetch JSON from URL with retries"""
        checks = 0
        while checks < 3:
            try:
                with urllib.request.urlopen(url, timeout=timeout) as response:
                    return json.loads(response.read().decode())
            except Exception as e:
                checks += 1
                time.sleep(0.5)
        return None

    def _process_msg(self, msg, height):
        """Process blockchain message and extract inference events"""
        msg_type = msg.get('@type')

        if msg_type == '/cosmos.authz.v1beta1.MsgExec':
            for inner in msg.get("msgs", []):
                self._process_msg(inner, height)

        elif msg_type == '/inference.inference.MsgStartInference':
            inference_id = msg.get('inference_id')
            if inference_id:
                # Store the event (for ALL requests)
                with self.lock:
                    if inference_id not in self.inference_events:
                        self.inference_events[inference_id] = {}
                    self.inference_events[inference_id]['start_time'] = time.time()
                    self.inference_events[inference_id]['start_height'] = height

                    # Only LOG if this ID is being tracked
                    is_tracked = inference_id in self.tracked_ids

                if is_tracked:
                    self._log(f"[BLOCKCHAIN] ✓ StartInference detected: {inference_id[:50]}... at height {height}")

        elif msg_type == '/inference.inference.MsgFinishInference':
            inference_id = msg.get('inference_id')
            if inference_id:
                # Store the event (for ALL requests)
                with self.lock:
                    if inference_id not in self.inference_events:
                        self.inference_events[inference_id] = {}
                    self.inference_events[inference_id]['finish_time'] = time.time()
                    self.inference_events[inference_id]['finish_height'] = height

                    # Only LOG if this ID is being tracked
                    is_tracked = inference_id in self.tracked_ids

                if is_tracked:
                    self._log(f"[BLOCKCHAIN] ✓ FinishInference detected: {inference_id[:50]}... at height {height}")

    def _watch_blockchain(self):
        """Main blockchain watching loop"""
        retry_delay = 5

        while self.running:
            try:
                websocket = connect(self.websocket_url)
                websocket.send(json.dumps({
                    "jsonrpc": "2.0",
                    "method": "subscribe",
                    "id": "0",
                    "params": {
                        "query": "tm.event='Tx'"
                    }
                }))

                self._log("[BLOCKCHAIN] Connected to websocket")

                while self.running:
                    try:
                        message = websocket.recv(timeout=1.0)
                        tx_notification = json.loads(message)

                        txs = tx_notification.get('result', {}).get('events', {}).get("tx.hash", [])
                        heights = tx_notification.get('result', {}).get('events', {}).get("tx.height", [])

                        for (tx, height) in zip(txs, heights):
                            decoded_tx = self._fetch_json(f"{self.grpc_url}/{tx}")
                            if decoded_tx:
                                for msg in decoded_tx.get('tx', {}).get('body', {}).get('messages', []):
                                    self._process_msg(msg, height)

                    except TimeoutError:
                        continue
                    except Exception as e:
                        if self.running:
                            # Don't log websocket timeout errors
                            if "timed out" not in str(e).lower():
                                self._log(f"[BLOCKCHAIN] Error processing message: {e}")
                        break

            except Exception as e:
                if self.running:
                    self._log(f"[BLOCKCHAIN] Connection error: {e}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)

            if not self.running:
                break
