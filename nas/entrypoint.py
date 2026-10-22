"""One container: private desktop services and the authenticated dashboard."""
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time


def wait_port(port, process, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Desktop component exited during startup')
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=.5):
                return
        except OSError:
            time.sleep(.2)
    raise RuntimeError(f'Desktop startup timed out on local port {port}')


def main():
    children = []
    stopping = False

    def stop(*args):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # Only the dashboard receives its login secret; never pass it to Chrome.
    desktop_env = {k: v for k, v in os.environ.items() if k != 'DASHBOARD_PASSWORD'}

    def start(args, env=desktop_env):
        child = subprocess.Popen(args, env=env)
        children.append(child)
        return child

    try:
        xvfb = start(['Xvfb', ':99', '-screen', '0', '1440x1000x24', '-nolisten', 'tcp', '-ac'])
        deadline = time.monotonic() + 15
        while not Path('/tmp/.X11-unix/X99').exists():
            if xvfb.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Virtual display did not start')
            time.sleep(.2)
        flux = Path('/tmp/whoga-fluxbox')
        flux.mkdir(exist_ok=True)
        (flux / 'init').write_text('session.screen0.toolbar.visible: false\n')
        start(['fluxbox', '-rc', str(flux / 'init'), '-log', str(flux / 'log')])
        # Loopback-only VNC; the dashboard authenticates every external connection.
        vnc = start(['x11vnc', '-display', ':99', '-localhost', '-rfbport', '5900',
                     '-forever', '-shared', '-nopw', '-quiet', '-noxdamage'])
        wait_port(5900, vnc)
        proxy = start(['websockify', '127.0.0.1:6080', '127.0.0.1:5900'])
        wait_port(6080, proxy)
        browser = start([sys.executable, '/app/nas/desktop.py'])
        wait_port(9222, browser)
        start([sys.executable, '/app/nas/web.py'], env=dict(os.environ))
        while not stopping:
            if any(child.poll() is not None for child in children):
                raise RuntimeError('A desktop component stopped; restarting the container is required')
            time.sleep(.5)
        return 0
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    raise SystemExit(main())
