import os
import sys
import logging
import asyncio
from contextlib import contextmanager
from gonka_openai import GonkaOpenAI
import time
import threading

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


# ============================================================================
# CLIENT POOL - Reuse clients instead of creating new ones every time
# ============================================================================

_client_pool = []
_client_pool_lock = threading.Lock()
_client_pool_size = 50  # Adjust based on your needs

def set_pool_size(size: int):
    """Set the client pool size (call before running tests)"""
    global _client_pool_size
    _client_pool_size = size
    print(f"[POOL] Client pool size set to: {_client_pool_size}")

def get_client():
    """Get a GonkaOpenAI client from the pool (or create one)"""
    with _client_pool_lock:
        if _client_pool:
            return _client_pool.pop()
    
    # Create new client if pool is empty
    with SuppressPrints():
        return GonkaOpenAI()

def return_client(client):
    """Return a client to the pool for reuse"""
    with _client_pool_lock:
        if len(_client_pool) < _client_pool_size:
            _client_pool.append(client)


def make_gonka_request_sync_suppressed():
    """For load generation - fully suppressed, with client reuse"""
    MAX_RETRIES = 3
    
    for attempt in range(MAX_RETRIES):
        client = None
        try:
            client = get_client()
            
            with SuppressPrints():
                response = client.chat.completions.create(
                    model="Qwen/Qwen2.5-7B-Instruct",
                    messages=[
                        {"role": "user", "content": "Write a one-sentence bedtime story about a unicorn"}
                    ]
                )
            
            result = response.choices[0].message.content
            return_client(client)
            return result
        
        except Exception as e:
            if 'signature is in the future' in str(e):
                # Discard this client (bad signature), immediately retry with fresh one
                # No sleep - fresh client will have a new timestamp
                continue
            
            # Any other error - raise immediately
            raise
    
    raise RuntimeError("Max retries exceeded for clock skew error")

def make_gonka_request_sync_verbose():
    """
    For latency measurement - returns full response object for blockchain tracking.
    """
    client = None
    try:
        client = get_client()
        
        with SuppressPrints():
            response = client.chat.completions.create(
                model="Qwen/Qwen2.5-7B-Instruct",
                messages=[
                    {"role": "user", "content": "Write a one-sentence bedtime story about a unicorn"}
                ]
            )
        
        return_client(client)  # Return to pool
        return response  # Return full response object, not just content
        
    except Exception as e:
        print(f"[ERROR] {e}")
        raise
