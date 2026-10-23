"""Build only from a passing same-run evidence bundle; never scan for newest files."""
from datetime import datetime, timedelta
import argparse
from pathlib import Path
from collector import CONFIG, DEFAULT_URL, ROOT, ValidationError, atomic_json, digest, identity, target_url
from monitor import KST, read_json, validate_snapshot


def build(directory):
    directory=Path(directory)
    report=read_json(directory/'validation.json')
    raw=read_json(directory/'raw-cards.json')
    if not report or not raw or report.get('status')!='pass' or report.get('completeness')!='verified':
        raise ValidationError('Passing evidence is required')
    for key in ('run_id','source_url','source_url_sha256','collected_at'):
        if not report.get(key) or report[key]!=raw.get(key):
            raise ValidationError('Evidence run mismatch: '+key)
    target_url(raw['source_url'])
    if digest(raw['source_url'])!=raw['source_url_sha256'] or digest(raw)!=report['raw_sha256']:
        raise ValidationError('Evidence hash mismatch')
    observed=datetime.fromisoformat(raw['collected_at'])
    if observed.utcoffset()!=timedelta(hours=9):
        raise ValidationError('Collection timestamp must be KST')
    keys=[r['key'] for r in raw['cards']]
    if len(keys)!=len(set(keys)) or not keys:
        raise ValidationError('Duplicate or empty source cards')
    for row in raw['cards']:
        key, article_id = identity(row)
        if row['key']!=key or row['item']['id']!=row['key']:
            raise ValidationError('Card identity mismatch')
        if row['item'].get('articleId') != article_id:
            raise ValidationError('Source article identity mismatch')
    if not (report.get('terminal_confirmed') and report.get('identical_complete_passes')==2
            and report.get('duplicate_count')==0 and report.get('missing_count')==0
            and report['visible_total_count']==report['unique_collected_count']==len(keys)):
        raise ValidationError('Completeness evidence failed')
    snapshot={'schemaVersion':2,'date':observed.astimezone(KST).date().isoformat(),
        'collectedAt':raw['collected_at'],'run_id':raw['run_id'],
        'source':{'kind':'naver-live','url':raw['source_url']},'source_url_sha256':raw['source_url_sha256'],
        'declaredCount':report['visible_total_count'],'count':len(keys),'items':[r['item'] for r in raw['cards']],
        'view':report['view'],'observation':{'observedAt':raw['collected_at'],'transport':report['transport']},
        'validation':{'complete':True,'declaredCount':len(keys),'parsedCount':len(keys),
            'method':report.get('validation_method','two-complete-map-passes'),
            'identityCount':sum(bool(r['item']['articleId']) for r in raw['cards']),
            'groupIdentity':'within-run-text-sha256'}}
    validate_snapshot(snapshot,require_complete=True,allowed_dongs=CONFIG['allowedDongs'])
    atomic_json(directory/'snapshot.json',snapshot)
    (directory/'compact-snapshot.txt').write_text('\n'.join(
        f"{i['dong']} {i['type']} {i['floor']} {i['direction']} {i['priceRaw']}" for i in snapshot['items'])+'\n')
    return snapshot

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('run_dir',type=Path)
    args=parser.parse_args();snapshot=build(args.run_dir)
    print(f"Validated {snapshot['run_id']}: {snapshot['count']} groups")
