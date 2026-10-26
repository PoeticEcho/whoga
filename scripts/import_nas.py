"""Validate NAS full JSON and import card-level snapshots; never execute source-branch code."""
import argparse
from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nas.plan import validate_plan
from monitor import atomic_json, read_json, rebuild_index, validate_snapshot, floor_category

KST = ZoneInfo('Asia/Seoul')

def require(ok, message):
    if not ok: raise ValueError(message)

def timestamp(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(stamp.tzinfo is not None, 'Timezone is required')
    return stamp

def price_range(text):
    require(isinstance(text, str) and text.startswith('매매 '), 'Expected sale price text')
    values=[]
    for part in text[3:].split('~'):
        part=re.sub(r'변동.*$', '', part).replace(',', '').strip()
        match=re.fullmatch(r'(?:(\d+)억)?\s*(\d+)?(?:만(?:원)?)?', part)
        require(match is not None and any(match.groups()), 'Unrecognized price text')
        values.append(int(match[1] or 0)*100_000_000+int(match[2] or 0)*10_000)
    require(1<=len(values)<=2 and values==sorted(values) and min(values)>0, 'Invalid price range')
    return min(values),max(values)

def validate_price(row):
    lo,hi=row.get('priceMinWon'),row.get('priceMaxWon')
    require(type(lo) is int and type(hi) is int and 0<lo<=hi, 'Invalid price numbers')
    require((lo,hi)==price_range(row.get('priceText')), 'Text/number price mismatch')

def convert(payload, config, source_path, source_commit):
    p=payload; target=p.get('target',{})
    require(p.get('schemaVersion')=='nas-experiment-1' and p.get('mode')=='full', 'Only NAS full snapshots are eligible')
    require(target.get('complexNo')==config['complexId'] and target.get('tradeType')=='A1', 'Wrong complex or trade type')
    require(target.get('sourceUrl')=='https://fin.land.naver.com/complexes/'+config['complexId'], 'Wrong source URL')
    legacy = config['complexId'] == '140635'
    name = target.get('complexName')
    require(isinstance(name,str) and 0<len(name)<=100 and target.get('estateTypeText') in ('아파트','오피스텔'), 'Wrong complex/type')
    if legacy: require(name in ('수성범어더블유','수성범어W') and target['estateTypeText']=='오피스텔', 'Wrong complex/type')
    run=p.get('runId','');require(re.fullmatch('[a-f0-9]{32}',run) is not None, 'Invalid run ID')
    require(source_path==f'nas-imports/{config["complexId"]}/{run}.json', 'Filename/run mismatch')
    stamp=timestamp(p['collectedAt']);require(stamp<=datetime.now(KST)+timedelta(minutes=5), 'Future collection time')
    cards,articles=p.get('cards'),p.get('articles')
    require(isinstance(cards,list) and cards and isinstance(articles,list) and articles, 'Empty/invalid data')
    require(type(p.get('displayedCardCount')) is int and type(p.get('collectedCardCount')) is int and p['displayedCardCount']==p['collectedCardCount']==len(cards), 'Partial cards')
    require(type(p.get('articleCount')) is int and p['articleCount']==len(articles), 'Partial articles')
    by_id={}
    for a in articles:
        aid=a.get('articleNo');require(isinstance(aid,str) and re.fullmatch(r'\d+',aid) is not None and aid not in by_id,'Duplicate/invalid article ID')
        validate_price(a);by_id[aid]=a
    refs=[];items=[]
    for i,c in enumerate(cards):
        require(type(c.get('cardIndex')) is int and c['cardIndex']==i,'Wrong card order')
        validate_price(c)
        summary=c.get('summary');require(isinstance(summary,list) and len(summary)==4 and all(isinstance(x,str) for x in summary),'Invalid summary')
        kind,area,floor,direction=summary
        require(kind==target['estateTypeText'],'Unsupported property kind')
        dong=re.fullmatch(re.escape(name)+r'\s+([^\s]{1,30}동)',c.get('name',''))
        require(dong is not None,'Card complex/building mismatch')
        if legacy: require(dong[1] in config['allowedDongs'],'Unsupported building')
        floor_match=re.fullmatch(r'(\d+|저|중|고)/(\d+)층',floor);require(floor_match is not None,'Invalid floor')
        require(direction in ('남서향','남동향','북서향','북동향','남향','북향','동향','서향'),'Invalid direction')
        ob=bool(re.search(r'78\.36',area));oa=bool(re.search(r'84\.02',area))
        if legacy:
            require(ob != oa,'Unsupported or ambiguous area')
            require(not (ob and re.search('180|OA',area)) and not (oa and re.search('168|OB',area)),'Conflicting area type')
        else:
            require(0<len(area)<=100 and re.search(r'\d',area) and ('㎡' in area or 'm²' in area),'Invalid area')
        area_type = ('78OB' if ob else '84OA') if legacy else area
        ids=c.get('articleNos');require(isinstance(ids,list) and ids,'Empty group')
        count=c.get('uiAgentCount')
        if count is not None:
            require(type(count) is int and count==len(ids) and c.get('groupedArticleCount')==len(ids),'Partial group')
        else:require(len(ids)==1,'Ungrouped card with multiple members')
        for aid in ids:
            require(aid in by_id and aid not in refs,'Missing or repeated member')
            a=by_id[aid];refs.append(aid)
            require(type(a.get('cardIndex')) is int and a['cardIndex']==i,'Member/card mismatch')
            require(a.get('name')==c['name'] and a.get('areaText')==area and a.get('floorInfo')==floor and a.get('direction')==direction,'Member fields mismatch')
            require(c['priceMinWon']<=a['priceMinWon']<=a['priceMaxWon']<=c['priceMaxWon'],'Member price outside group')
        dates=[by_id[aid].get('displayDate') for aid in ids if by_id[aid].get('displayDate')]
        require(all(isinstance(d,str) and re.fullmatch(r'\d{4}\.\d{2}\.\d{2}',d) for d in dates),'Invalid display date')
        items.append(dict(id='nas_'+run+'_'+str(i),articleId=ids[0] if len(ids)==1 else None,
                          articleNos=ids,dong=dong[1],type=area_type,floor=floor,direction=direction,
                          floorCat=(floor_category(floor_match[1]) if legacy or not floor_match[1].isdigit() else ('저층' if int(floor_match[1])<=int(floor_match[2])/3 else '중층' if int(floor_match[1])<=int(floor_match[2])*2/3 else '고층')),priceRaw=c['priceText'][3:].strip(),
                          minPrice=float(Decimal(c['priceMinWon'])/100_000_000),maxPrice=float(Decimal(c['priceMaxWon'])/100_000_000),
                          confirmDate=max(dates) if dates else '',agencyCount=count if count is not None else 1,
                          agencyInfo=f'중개사 {count}곳 공동등록' if count is not None else '',desc='',baseTag=''))
    require(len(refs)==len(by_id),'Unreferenced articles')
    snapshot=dict(schemaVersion=2,date=stamp.astimezone(KST).date().isoformat(),collectedAt=p['collectedAt'],
                  count=len(items),declaredCount=len(cards),items=items, complexNo=config['complexId'], complexName=name,
                  source=dict(kind='naver-live',url=config['sourceUrl'],collectionPath='nas-docker',runId=run,
                              importPath=source_path,importCommit=source_commit,articleCount=len(articles)),
                  validation=dict(complete=True,declaredCount=len(cards),parsedCount=len(cards),
                                  method='nas-full-card-member-price-validation',identityCount=sum(bool(x['articleId']) for x in items)))
    validate_snapshot(snapshot,require_complete=True,allowed_dongs=config.get('allowedDongs') if legacy else None)
    return snapshot

def import_snapshots(candidates, data_dir, config, source_commit):
    # Validate the entire incoming batch before changing any tracked data.
    snapshots=[convert(p,config,path,source_commit) for path,p in candidates]
    data_dir=Path(data_dir);changes=[]
    for snap in sorted(snapshots,key=lambda s:timestamp(s['collectedAt'])):
        path=data_dir/(snap['date']+'.json');old=read_json(path,{})
        if old.get('source',{}).get('runId')==snap['source']['runId']:continue
        if old.get('collectedAt') and timestamp(old['collectedAt'])>=timestamp(snap['collectedAt']):continue
        if old.get('source',{}).get('runId') and old.get('collectedAt'):
            archive=data_dir/(old['date']+'_nas_'+old['source']['runId']+'.json')
            old['label']=old['date']+' '+timestamp(old['collectedAt']).astimezone(KST).strftime('%H:%M')
            atomic_json(archive,old)
        snap['label']=snap['date']+' '+timestamp(snap['collectedAt']).astimezone(KST).strftime('%H:%M')
        atomic_json(path,snap);changes.append(snap)
    if not changes:return False
    index=rebuild_index(data_dir)
    latest=read_json(data_dir/(index['latest']+'.json'))
    if latest.get('source',{}).get('collectionPath')=='nas-docker':
        status=read_json(data_dir/'status.json',{})
        status.update(schemaVersion=2,lastAttemptResult='success',lastAttemptAt=latest['collectedAt'],lastSuccessAt=latest['collectedAt'],
                      latestCollectedDate=latest['date'],sourceKind='naver-live',declaredCount=latest['declaredCount'],verifiedCount=latest['count'],
                      collectionPath='nas-docker',transport='nas-github-import',
                      message='NAS 전체 카드·묶음 매물·가격 검증 후 공개 앱 자료로 변환했습니다.')
        atomic_json(data_dir/'status.json',status)
    return True

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source-ref',required=True);args=parser.parse_args()
    sha=subprocess.check_output(['git','rev-parse',args.source_ref+'^{commit}'],text=True).strip()
    base=read_json('config.json')
    plan=read_json('collection-plan.json',None)
    targets=validate_plan(plan)['targets'] if plan is not None else [dict(complexNo=base['complexId'],label=base['complexName'])]
    changed=False;total=0;catalog=[]
    for target in targets:
        number=target['complexNo'];prefix='nas-imports/'+number+'/'
        config=dict(base,complexId=number,sourceUrl='https://fin.land.naver.com/complexes/'+number)
        names=subprocess.check_output(['git','ls-tree','-r','--name-only',sha,'--',prefix],text=True).splitlines()
        candidates=[]
        for name in names:
            if not name.endswith('.json'):continue
            require(re.fullmatch(re.escape(prefix)+r'[a-f0-9]{32}\.json',name) is not None,'Unexpected import filename')
            raw=subprocess.check_output(['git','show',sha+':'+name]);require(len(raw)<=10_000_000,'Oversized import')
            candidates.append((name,json.loads(raw)))
        data_dir=Path('data') if number==base['complexId'] else Path('data/complexes')/number
        changed=import_snapshots(candidates,data_dir,config,sha) or changed;total+=len(candidates)
        index=read_json(data_dir/'index.json',{})
        latest=read_json(data_dir/(str(index.get('latest'))+'.json'),{})
        catalog.append(dict(complexNo=number,label=target.get('label') or latest.get('complexName') or number,
                            dataPath=str(data_dir),ready=bool(index.get('latest'))))
    # Preserve existing historical complexes as viewable archives when removed from the plan.
    old_catalog=read_json('complexes.json',{'complexes':[]})
    for row in old_catalog['complexes']:
        if row['complexNo'] not in [t['complexNo'] for t in targets]:catalog.append(dict(row,archived=True))
    manifest=dict(schemaVersion=1,complexes=catalog)
    if old_catalog!=manifest:
        atomic_json(Path('complexes.json'),manifest);changed=True
    print(json.dumps(dict(imported=changed,sourceCommit=sha,files=total)))

if __name__=='__main__':main()
