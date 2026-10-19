"""Prepare whole existing site plus validated data in a staging tree, then commit."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime
from build_snapshot import build
from collector import DEFAULT_URL, ROOT, ValidationError, digest
from monitor import atomic_json, read_json, rebuild_index, now_kst


def prepare(run_dir, root=ROOT, *, event=None, ref=None, manual_url=None):
    event=event or os.environ.get('GITHUB_EVENT_NAME')
    ref=ref or os.environ.get('GITHUB_REF')
    manual_url=os.environ.get('MANUAL_URL','') if manual_url is None else manual_url
    if event!='schedule' or ref!='refs/heads/main' or manual_url:
        raise ValidationError('Only main scheduled default-target runs can publish')
    snapshot=build(run_dir)
    if snapshot['source']['url']!=DEFAULT_URL:
        raise ValidationError('Manual source is not eligible for latest')
    now=datetime.fromisoformat(now_kst()); stamp=datetime.fromisoformat(snapshot['collectedAt'])
    if not 0 <= (now-stamp).total_seconds() <= 1800:
        raise ValidationError('Stale or future collection cannot be published')
    root=Path(root)
    # Every potentially failing validation happens before replacing any tracked data.
    with tempfile.TemporaryDirectory(dir=root,prefix='.map-stage-') as tmp:
        staged=Path(tmp)
        shutil.copytree(root/'data',staged/'data')
        public=staged/'whoga-naver-collector';public.mkdir()
        for pattern in ('snapshot-*.json','latest.json'):
            for p in (root/'whoga-naver-collector').glob(pattern):shutil.copy2(p,public/p.name)
        old=read_json(root/'whoga-naver-collector/latest.json')
        if old and old['collectedAt']>=snapshot['collectedAt']:
            raise ValidationError('Refuse data regression')
        date=snapshot['date']
        prior=read_json(staged/'data'/f'{date}.json')
        if prior:
            # Preserve pre-existing same-day values instead of silently replacing them.
            archive=public/'history';archive.mkdir(exist_ok=True)
            atomic_json(archive/f"{date}-{digest(prior)[:16]}.json",prior)
        atomic_json(staged/'data'/f'{date}.json',snapshot)
        rebuild_index(staged/'data')
        status=read_json(staged/'data/status.json',{})
        status.update(lastAttemptAt=now_kst(),lastAttemptResult='success',lastSuccessAt=snapshot['collectedAt'],
            latestCollectedDate=date,sourceKind='naver-live',message='지도 목록 2회 완전성 검사 통과')
        atomic_json(staged/'data/status.json',status)
        atomic_json(public/'latest.json',snapshot)
        atomic_json(public/f'snapshot-{date}.json',snapshot)
        report=read_json(Path(run_dir)/'validation.json')
        atomic_json(public/'evidence/validation.json',{k:v for k,v in report.items() if k!='progress'})
        # Local staging is private to this job. Git commit and Pages artifact are the atomic public boundaries.
        for source in (staged/'data',public):
            target=root/source.name
            shutil.copytree(source,target,dirs_exist_ok=True)
    return snapshot


def commit():
    subprocess.run(['git','add','data','whoga-naver-collector'],cwd=ROOT,check=True)
    changed=subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode
    if changed:
        subprocess.run(['git','commit','-m','data: publish validated map snapshot [skip ci]'],cwd=ROOT,check=True)
        subprocess.run(['git','push','origin','HEAD:main'],cwd=ROOT,check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run_dir',type=Path);p.add_argument('--commit',action='store_true')
    a=p.parse_args();prepare(a.run_dir)
    if a.commit:commit()
