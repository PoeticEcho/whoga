"""허용한 공개 파일만 _site/에 복사합니다. Python·상태 이력은 웹에 배포하지 않습니다."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nas.plan import validate_plan
from monitor import ROOT, atomic_json, read_json, rebuild_index, validate_snapshot


def build(destination=None):
    destination = Path(destination or ROOT / "_site")
    if destination.resolve() == ROOT.resolve() or ROOT.resolve().is_relative_to(destination.resolve()):
        raise ValueError("출력 폴더를 확인해 주세요.")
    index = rebuild_index(ROOT / "data")
    for entry in index["snapshots"]:
        validate_snapshot(read_json(ROOT / "data" / entry["file"]))
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for file in ("index.html", ".nojekyll"):
        shutil.copy2(ROOT / file, destination / file)
    config = read_json(ROOT / "config.json")
    public_keys = ("complexId", "complexName", "sourceUrl", "allowedDongs", "dailyTimeLabel", "siteUrl")
    atomic_json(destination / "config.json", {k: config[k] for k in public_keys if k in config})
    shutil.copytree(ROOT / "assets", destination / "assets")
    (destination / "data").mkdir()
    for file in ["index.json", "status.json"] + [e["file"] for e in index["snapshots"]]:
        shutil.copy2(ROOT / "data" / file, destination / "data" / file)
    catalog=read_json(ROOT/'complexes.json', {'schemaVersion':1,'complexes':[{'complexNo':config['complexId'],'label':config.get('complexName',config['complexId']),'dataPath':'data','ready':True}]})
    for entry in catalog['complexes']:
        import re
        number=entry['complexNo']
        if not re.fullmatch(r'[1-9][0-9]{0,11}',number): raise ValueError('Invalid catalog complex')
        expected='data' if number==config['complexId'] else 'data/complexes/'+number
        if entry['dataPath']!=expected: raise ValueError('Invalid catalog path')
        if not entry.get('ready') or expected=='data': continue
        source=ROOT/expected;target=destination/expected;target.mkdir(parents=True)
        subindex=rebuild_index(source)
        for file in ['index.json','status.json']+[row['file'] for row in subindex['snapshots']]:
            if file not in ('index.json','status.json'):
                snap=read_json(source/file);validate_snapshot(snap)
                if snap.get('complexNo')!=number:raise ValueError('Cross-complex snapshot')
            shutil.copy2(source/file,target/file)
    atomic_json(destination/'complexes.json',catalog)
    plan=read_json(ROOT/'collection-plan.json',None)
    if plan is not None:atomic_json(destination/'collection-plan.json',validate_plan(plan))
    print(f"정적 배포 파일 준비 완료 · {len(index['snapshots'])}개 스냅샷")
    return destination


if __name__ == "__main__":
    build()
