"""Bounded waits for observable asynchronous behavior."""
import time


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError('condition was not met before deadline')
        time.sleep(0.01)
