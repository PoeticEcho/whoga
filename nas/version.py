"""Identify the source actually inside an image, including ZIP-based NAS builds."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

VERSION = '3.1.0'
ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = [
    'experiments/supplied-v2/collector.py',
    'nas/telegram_setup.py', 'nas/plan.py', 'nas/run.py', 'nas/web.py', 'nas/desktop.py', 'nas/entrypoint.py',
    'nas/diagnostics.py', 'nas/resources.py', 'nas/version.py', 'nas/comparison.py', 'nas/browser_control.py', 'nas/browser_runtime.py',
]


def source_fingerprint(root=ROOT):
    files = sorted(RUNTIME_FILES + [str(p.relative_to(root)) for p in (root / 'nas/static').glob('*') if p.is_file()])
    digest = hashlib.sha256()
    for name in files:
        digest.update(name.encode() + b'\0' + (root / name).read_bytes() + b'\0')
    return digest.hexdigest()


def build_info(root=ROOT):
    baked = root / 'nas/build-info.json'
    if baked.exists():
        return json.loads(baked.read_text())
    source = root / 'nas/source-version.json'
    source_info = json.loads(source.read_text()) if source.exists() else {}
    commit = source_info.get('sourceCommit')
    if not isinstance(commit, str) or not re.fullmatch(r'[a-f0-9]{40}', commit):
        commit = None
    info = dict(version=VERSION, sourceCommit=commit, sourceFingerprint=source_fingerprint(root), builtAt=None)
    base_commit = source_info.get('baseSourceCommit')
    if isinstance(base_commit, str) and re.fullmatch(r'[a-f0-9]{40}', base_commit):
        info['baseSourceCommit'] = base_commit
    return info


if __name__ == '__main__':
    info = build_info()
    if len(sys.argv) == 3 and sys.argv[1] == '--write-build-info':
        if re.fullmatch(r'[a-f0-9]{40}', sys.argv[2]):
            info['sourceCommit'] = sys.argv[2]
        info['builtAt'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        (ROOT / 'nas/build-info.json').write_text(json.dumps(info, ensure_ascii=False, indent=2) + '\n')
    else:
        print(json.dumps(info, ensure_ascii=False))
