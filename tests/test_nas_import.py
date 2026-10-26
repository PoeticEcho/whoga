import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('nas_import',ROOT/'scripts/import_nas.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
CONFIG=json.loads((ROOT/'config.json').read_text())
RUN='a'*32
PATH=f'nas-imports/140635/{RUN}.json'

def fixture():
    cards=[];articles=[]
    for i,ids in enumerate([['100','101'],['102']]):
        summary=['오피스텔','168OB㎡ (전용78.36OB)','20/58층','남서향']
        cards.append(dict(cardIndex=i,name='수성범어더블유 103동',priceText='매매 5억 4,000',priceMinWon=540000000,priceMaxWon=540000000,summary=summary,articleNos=ids,uiAgentCount=2 if i==0 else None,groupedArticleCount=2 if i==0 else None))
        for aid in ids:
            articles.append(dict(articleNo=aid,cardIndex=i,name=cards[-1]['name'],priceText='매매 5억 4,000',priceMinWon=540000000,priceMaxWon=540000000,areaText=summary[1],floorInfo=summary[2],direction=summary[3],displayDate='2026.10.25'))
    return dict(schemaVersion='nas-experiment-1',mode='full',runId=RUN,collectedAt='2026-10-25T23:30:00+00:00',publicationEligible=False,
                target=dict(complexNo='140635',complexName='수성범어더블유',tradeType='A1',estateTypeText='오피스텔',sourceUrl='https://fin.land.naver.com/complexes/140635'),
                displayedCardCount=2,collectedCardCount=2,articleCount=3,cards=cards,articles=articles)

class NasImportTests(unittest.TestCase):
    def convert(self,p):return m.convert(p,CONFIG,PATH,'b'*40)
    def seed_history(self, folder):
        # Tests must not inherit live snapshots created earlier in the import job.
        data=Path(folder)/'data';data.mkdir()
        payload=fixture();payload['collectedAt']='2026-10-23T08:00:00+09:00'
        m.atomic_json(data/'2026-10-23.json',self.convert(payload))
        m.rebuild_index(data)
        return data
    def test_card_counts_identity_and_korean_date(self):
        s=self.convert(fixture());self.assertEqual(s['date'],'2026-10-26')
        self.assertEqual(s['count'],2);self.assertEqual(s['source']['articleCount'],3)
        self.assertIsNone(s['items'][0]['articleId']);self.assertEqual(s['items'][0]['articleNos'],['100','101'])
        self.assertEqual(s['items'][1]['articleId'],'102');self.assertEqual(s['items'][0]['minPrice'],5.4)
    def test_partial_probe_duplicate_missing_and_price_mismatch_fail(self):
        mutations=[lambda p:p.update(mode='probe'),lambda p:p.update(displayedCardCount=3),
                   lambda p:p['articles'].pop(),lambda p:p['articles'][1].update(articleNo='100'),
                   lambda p:p['cards'][0].update(articleNos=['100']),
                   lambda p:p['articles'][0].update(priceMinWon=1),
                   lambda p:p['target'].update(tradeType='B1'),
                   lambda p:p['target'].update(complexNo='999'),
                   lambda p:p['cards'][0]['summary'].__setitem__(1,'84.02OA 78.36OB'),
                   lambda p:p.update(collectedAt='2026-10-26T08:00:00')]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                p=fixture();mutate(p)
                with self.assertRaises(ValueError):self.convert(p)
    def test_member_metadata_and_orphans_fail(self):
        p=fixture();p['articles'][0]['floorInfo']='21/58층'
        with self.assertRaises(ValueError):self.convert(p)
        p=fixture();a=copy.deepcopy(p['articles'][0]);a['articleNo']='999';p['articles'].append(a);p['articleCount']=4
        with self.assertRaises(ValueError):self.convert(p)
    def test_preserves_history_idempotent_and_does_not_replace_newer(self):
        with tempfile.TemporaryDirectory() as folder:
            data=self.seed_history(folder)
            original=(data/'2026-10-23.json').read_bytes()
            self.assertTrue(m.import_snapshots([(PATH,fixture())],data,CONFIG,'b'*40))
            self.assertEqual((data/'2026-10-23.json').read_bytes(),original)
            self.assertEqual(m.read_json(data/'index.json')['latest'],'2026-10-26')
            self.assertEqual(m.read_json(data/'status.json')['collectionPath'],'nas-docker')
            before={p.name:p.read_bytes() for p in data.glob('*.json')}
            self.assertFalse(m.import_snapshots([(PATH,fixture())],data,CONFIG,'c'*40))
            older=fixture();older.update(runId='c'*32,collectedAt='2026-10-26T08:00:00+09:00')
            self.assertFalse(m.import_snapshots([('nas-imports/140635/'+'c'*32+'.json',older)],data,CONFIG,'c'*40))
            self.assertEqual(before,{p.name:p.read_bytes() for p in data.glob('*.json')})
    def test_invalid_batch_does_not_modify_any_public_file(self):
        with tempfile.TemporaryDirectory() as folder:
            data=self.seed_history(folder)
            before={p.name:p.read_bytes() for p in data.glob('*.json')}
            bad=fixture();bad['articles'].pop()
            with self.assertRaises(ValueError):m.import_snapshots([(PATH,fixture()),(PATH,bad)],data,CONFIG,'b'*40)
            self.assertEqual(before,{p.name:p.read_bytes() for p in data.glob('*.json')})
    def test_no_uploads_is_noop(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(m.import_snapshots([],folder,CONFIG,'b'*40))
            self.assertEqual(list(Path(folder).iterdir()),[])
