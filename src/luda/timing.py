"""Linux elapsed time includes system suspend; it is not wall-clock time."""
import time


def elapsed_time():
    if hasattr(time, 'CLOCK_BOOTTIME'):
        return time.clock_gettime(time.CLOCK_BOOTTIME)
    return time.monotonic()


def suspend_offset():
    return elapsed_time() - time.monotonic()
