"""허용한 공개 파일만 _site/에 복사합니다. Python·상태 이력은 웹에 배포하지 않습니다."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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
    print(f"정적 배포 파일 준비 완료 · {len(index['snapshots'])}개 스냅샷")
    return destination


if __name__ == "__main__":
    build()
