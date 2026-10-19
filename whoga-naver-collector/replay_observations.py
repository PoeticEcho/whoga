"""Validate recorded UI observations; this is not an unattended browser transport.

The caller must capture panel.js's read-only output, with real timestamps, during
two top-to-bottom passes. Replayed evidence can never be promoted by publish.py.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from collector import CONFIG, Accumulator, ValidationError, atomic_json, digest, target_url
from build_snapshot import build
from monitor import KST, read_json


def timestamp(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValidationError('Observation timestamps require timezone')
    return stamp


def replay(source, output):
    bundle = read_json(Path(source))
    if bundle.get('transport') != 'chatgpt-cloud-browser':
        raise ValidationError('Unsupported observation source')
    url = target_url(bundle['source_url'])
    start, end = timestamp(bundle['started_at']), timestamp(bundle['finished_at'])
    if not 0 < (end-start).total_seconds() <= 600:
        raise ValidationError('Observation session must be within ten minutes')
    passes = {1: Accumulator(), 2: Accumulator()}
    previous, phase, view = start, 1, None
    progress = []
    pass_started = set()
    for event in bundle['observations']:
        stamp, number, state = timestamp(event['observed_at']), event['pass'], event['state']
        if not previous <= stamp <= end or number not in passes or number < phase:
            raise ValidationError('Observation order mismatch')
        if number == 2 and phase == 1 and passes[1].full_stable < 2:
            raise ValidationError('First pass was incomplete')
        if number not in pass_started:
            if number == 2 and state.get('scrollTop') != 0:
                raise ValidationError('Second pass must start at top')
            pass_started.add(number)
        current_view = state.get('viewport')
        if (not isinstance(current_view, dict) or
                any(type(current_view.get(k)) is not int or current_view[k] <= 0 for k in ('width','height'))):
            raise ValidationError('Missing actual viewport')
        if view is not None and view != current_view:
            raise ValidationError('Viewport changed during observation')
        view, previous, phase = current_view, stamp, number
        acc = passes[number]
        complete = acc.feed(state)
        progress.append({'pass': number, 'observed_at': stamp.astimezone(KST).isoformat(),
                         'total': acc.total, 'unique': len(acc.rows), 'dom': state['cardCount'],
                         'at_bottom': state['atBottom'], 'scroll_top': state['scrollTop'], 'complete': complete})
    if (any(a.full_stable < 2 for a in passes.values()) or passes[1].rows != passes[2].rows):
        raise ValidationError('Two identical complete observation passes are required')
    run_id = start.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-cloud-' + digest(bundle)[:10]
    collected = end.astimezone(KST).isoformat()
    rows = list(passes[2].rows.values())
    raw = {'run_id': run_id, 'source_url': url, 'source_url_sha256': digest(url),
           'collected_at': collected, 'cards': rows}
    report = {k:v for k,v in raw.items() if k != 'cards'}
    report.update(started_at=start.astimezone(KST).isoformat(), finished_at=collected,
                  status='pass', completeness='verified', stage='observation-validation',
                  transport='chatgpt-cloud-browser-observations', publication='not-attempted',
                  publication_eligible=False, validation_method='two-complete-dom-observation-passes',
                  visible_total_count=passes[2].total, unique_collected_count=len(rows),
                  duplicate_count=0, missing_count=0, terminal_confirmed=True, identical_complete_passes=2,
                  raw_sha256=digest(raw), observations_sha256=digest(bundle), view=view, progress=progress,
                  identity_method='single-article-id-or-within-run-group-text-sha256',
                  identity_count=sum(bool(r['item']['articleId']) for r in rows),
                  limitation='Assisted UI capture; Playwright navigation, unattended scroll and Pages are not verified.')
    directory = Path(output)/run_id
    directory.mkdir(parents=True, exist_ok=False)
    atomic_json(directory/'raw-cards.json',raw)
    atomic_json(directory/'validation.json',report)
    atomic_json(directory/'dictionaries.json',{'run_id':run_id,'allowed_dongs':CONFIG['allowedDongs'],
                'types':{'168OB':'78OB','180OA':'84OA'},'unit':'displayed-card'})
    build(directory)
    return directory, report


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('observations',type=Path)
    parser.add_argument('--output',type=Path,default=Path('collector-runs'))
    args=parser.parse_args()
    directory,report=replay(args.observations,args.output)
    print(f"Validated UI observations: {report['unique_collected_count']} cards; {directory}; publication blocked")
