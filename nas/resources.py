"""Read-only Linux resource measurements; no process arguments or credentials saved."""
from collections import Counter
from pathlib import Path
import resource
import time


def number(path):
    try:
        value = path.read_text().strip()
        return int(value) if value != 'max' else None
    except (OSError, ValueError):
        return None


def key_values(path):
    try:
        return {key: int(value) for key, value in (line.split()[:2] for line in path.read_text().splitlines())}
    except (OSError, ValueError):
        return {}


def memory_snapshot(root=Path('/')):
    group = root / 'sys/fs/cgroup'
    if (group / 'memory.current').exists():
        memory = dict(version=2, currentBytes=number(group / 'memory.current'),
                      limitBytes=number(group / 'memory.max'), peakBytes=number(group / 'memory.peak'),
                      events=key_values(group / 'memory.events'))
    else:
        candidates = [group / 'memory', group]
        group = next((path for path in candidates if (path / 'memory.usage_in_bytes').exists()), candidates[0])
        memory = dict(version=1 if (group / 'memory.usage_in_bytes').exists() else None,
                      currentBytes=number(group / 'memory.usage_in_bytes'),
                      limitBytes=number(group / 'memory.limit_in_bytes'),
                      peakBytes=number(group / 'memory.max_usage_in_bytes'),
                      failCount=number(group / 'memory.failcnt'))
        if memory['limitBytes'] is not None and memory['limitBytes'] >= 2**60:
            memory['limitBytes'] = None
    try:
        host = {}
        for line in (root / 'proc/meminfo').read_text().splitlines():
            key, value = line.split(':', 1)
            if key in ('MemTotal', 'MemAvailable'):
                host[key + 'Bytes'] = int(value.split()[0]) * 1024
        memory['host'] = host
    except (OSError, ValueError):
        memory['host'] = {}
    return memory


def filesystem_snapshot(path):
    import os
    try:
        stat = os.statvfs(path)
        return dict(totalBytes=stat.f_blocks * stat.f_frsize,
                    availableBytes=stat.f_bavail * stat.f_frsize,
                    usedBytes=(stat.f_blocks - stat.f_bfree) * stat.f_frsize,
                    availableInodes=stat.f_favail)
    except OSError as error:
        return {'unavailable': type(error).__name__}


def browser_snapshot(browser):
    session = browser.new_browser_cdp_session()
    try:
        processes = session.send('SystemInfo.getProcessInfo')['processInfo']
        counts = dict(Counter(item['type'] for item in processes))
        info = dict(processCounts=counts, pageCount=sum(len(context.pages) for context in browser.contexts))
        parent = next((item for item in processes if item['type'] == 'browser'), None)
        if parent:
            process = Path('/proc') / str(parent['id'])
            try:
                # Inspect only known switches, never retain the full command line.
                arguments = process.joinpath('cmdline').read_bytes().split(b'\0')
                info['sharedMemoryDisabled'] = b'--disable-dev-shm-usage' in arguments
                info['headless'] = any(value.startswith(b'--headless') for value in arguments)
                info['openFileDescriptors'] = len(list(process.joinpath('fd').iterdir()))
            except OSError as error:
                info['processInspectionUnavailable'] = type(error).__name__
        return info
    finally:
        session.detach()


def resource_snapshot(browser=None):
    info = dict(at=time.time(), memory=memory_snapshot(),
                filesystems={'tmp': filesystem_snapshot('/tmp'), 'sharedMemory': filesystem_snapshot('/dev/shm')})
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    info['fileDescriptorLimits'] = dict(soft=soft, hard=hard)
    if browser is not None:
        try:
            info['browser'] = browser_snapshot(browser)
        except Exception as error:
            info['browser'] = {'unavailable': type(error).__name__}
    return info
