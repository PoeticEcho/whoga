"""Check published bytes, history availability, and existing WhoGa data entrypoint."""
import argparse
import json
import time
from urllib.request import urlopen, Request
from pathlib import Path
from collector import ROOT, ValidationError, digest
from monitor import read_json, validate_snapshot


def verify(base, expected, attempts=6):
    base=base.rstrip('/')+'/'
    paths={f'whoga-naver-collector/latest.json':expected,
        f"whoga-naver-collector/snapshot-{expected['date']}.json":expected,
        f"data/{expected['date']}.json":expected}
    paths['whoga-naver-collector/evidence/validation.json']=read_json(ROOT/'whoga-naver-collector/evidence/validation.json')
    paths['data/index.json']=read_json(ROOT/'data/index.json')
    for entry in paths['data/index.json']['snapshots']:
        paths['data/'+entry['file']]=read_json(ROOT/'data'/entry['file'])
    for old in (ROOT/'whoga-naver-collector').glob('snapshot-*.json'):
        paths['whoga-naver-collector/'+old.name]=read_json(old)
    for relative,local in paths.items():
        for attempt in range(attempts):
            try:
                req=Request(base+relative+'?verify='+expected['run_id'],headers={'Cache-Control':'no-cache'})
                with urlopen(req,timeout=20) as response:
                    if response.status!=200:raise ValidationError('Non-200 public file')
                    remote=json.load(response)
                if remote!=local:raise ValidationError('Published content mismatch: '+relative)
                break
            except Exception:
                if attempt==attempts-1:raise
                time.sleep(10)
        print('HTTP 200 / exact content:',relative)
    for relative in ('index.html','assets/app.mjs'):
        with urlopen(base+relative,timeout=20) as response:
            if response.status!=200:raise ValidationError('Existing app missing')
        print('HTTP 200:',relative)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base_url');p.add_argument('snapshot',type=Path)
    a=p.parse_args();verify(a.base_url,read_json(a.snapshot))
