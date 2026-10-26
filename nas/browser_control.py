"""Hand the visible display to one comparison worker, then restore the desktop."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import socket
import time

REQUEST = Path('/tmp/whoga-comparison-owner')
READY = Path('/tmp/whoga-browser-ready')


def comparison_active():
    try:
        pid = int(REQUEST.read_text())
        if pid <= 1:
            return False
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def desktop_connected():
    try:
        with socket.create_connection(('127.0.0.1', 9222), timeout=.2):
            return True
    except OSError:
        return False


def wait_for_desktop(timeout=30):
    deadline = time.monotonic() + timeout
    while not (READY.exists() and desktop_connected()):
        if time.monotonic() >= deadline:
            raise RuntimeError('수집 브라우저가 준비되지 않았습니다.')
        time.sleep(.2)


@contextmanager
def reserve_display():
    with Path('/tmp/whoga-comparison.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        REQUEST.write_text(str(os.getpid()))
        try:
            deadline = time.monotonic() + 30
            while desktop_connected():
                if time.monotonic() >= deadline:
                    raise RuntimeError('기존 브라우저가 비교 시험에 화면을 넘기지 못했습니다.')
                time.sleep(.2)
            yield
        finally:
            REQUEST.unlink(missing_ok=True)
