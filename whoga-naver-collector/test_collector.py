"""Synthetic edge-case tests. These are NOT live Naver collection evidence."""
import json
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from collector import Accumulator, DEFAULT_URL, ValidationError, digest, target_url
from build_snapshot import build
from publish import prepare
from monitor import atomic_json


def row(n):
    return {'text':f'수성범어더블유 101동\n매매 6억\n오피스텔168OB㎡ (전용78.36OB){n}/58층남서향\n집주인확인매물 2026.10.19',
        'grouped':True,'representativeArticleId':None}


def state(rows,total=3,bottom=False):
    return {'rows':rows,'cardCount':len(rows),'declaredCount':total,'sourceReady':True,
        'scope':{'sale':True,'allAreas':True,'allBuildings':True},'atBottom':bottom,'loading':False}


class CollectorTests(unittest.TestCase):
    def test_exact_url_and_allowlist(self):
        self.assertEqual(target_url(),DEFAULT_URL)
        for url in ('https://evil.test/map','https://fin.land.naver.com@evil.test/map',
                    DEFAULT_URL.replace('A1','B1'),DEFAULT_URL+'\n',DEFAULT_URL+'&tradeTypes=A1'):
            with self.assertRaises(ValidationError):target_url(url)

    def test_virtualized_batches_accumulate_and_need_terminal_stability(self):
        a=Accumulator()
        self.assertFalse(a.feed(state([row(1),row(2)])))
        self.assertFalse(a.feed(state([row(2),row(3)],bottom=True)))
        self.assertTrue(a.feed(state([row(2),row(3)],bottom=True)))
        self.assertEqual(len(a.rows),3);self.assertEqual(a.repeats,3)
        self.assertTrue(all(r['item']['articleId'] is None for r in a.rows.values()))

    def test_count_match_without_end_is_insufficient(self):
        a=Accumulator()
        for _ in range(3):self.assertFalse(a.feed(state([row(1),row(2),row(3)])))

    def test_ambiguous_same_text_cards_fail(self):
        with self.assertRaises(ValidationError):Accumulator().feed(state([row(1),row(1)]))

    def test_total_change_scope_and_access_fail(self):
        a=Accumulator();a.feed(state([row(1)]))
        with self.assertRaises(ValidationError):a.feed(state([row(2)],total=4))
        for update in ({'blocked':True},{'notFound':True},{'scope':{'sale':True}}):
            with self.assertRaises(ValidationError):Accumulator().feed({**state([row(1)]),**update})

    def test_empty_or_partial_never_complete(self):
        a=Accumulator()
        for _ in range(6):self.assertFalse(a.feed(state([row(1)],bottom=True)))
        self.assertFalse(Accumulator().feed(state([],total=0,bottom=True)))

    def bundle(self,path):
        a=Accumulator();a.feed(state([row(1)],total=1,bottom=True))
        raw={'run_id':'test-run','source_url':DEFAULT_URL,'source_url_sha256':digest(DEFAULT_URL),
            'collected_at':'2026-10-20T00:01:00+09:00','cards':list(a.rows.values())}
        report={k:v for k,v in raw.items() if k!='cards'}
        report.update(status='pass',completeness='verified',raw_sha256=digest(raw),terminal_confirmed=True,
            identical_complete_passes=2,duplicate_count=0,missing_count=0,visible_total_count=1,unique_collected_count=1,
            view={'width':1440,'height':900},transport='synthetic-test')
        atomic_json(path/'raw-cards.json',raw);atomic_json(path/'validation.json',report)
        return raw,report

    def test_build_kst_date_and_legacy_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);self.bundle(path);s=build(path)
            self.assertEqual(s['date'],'2026-10-20')
            self.assertEqual(s['count'],len(s['items']));self.assertEqual(s['schemaVersion'],2)

    def test_unknown_tampered_and_cross_run_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for key,value in (('status','unknown'),('run_id','old-run'),('raw_sha256','bad'),('identical_complete_passes',1)):
                _,report=self.bundle(p);report[key]=value;atomic_json(p/'validation.json',report)
                with self.assertRaises(ValidationError):build(p)

    def test_manual_run_cannot_publish_even_default_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.bundle(p)
            before={f.name:f.read_bytes() for f in p.iterdir()}
            with self.assertRaises(ValidationError):prepare(p,root=p,event='workflow_dispatch',ref='refs/heads/main',manual_url='')
            self.assertEqual(before,{f.name:f.read_bytes() for f in p.iterdir()})

    def test_invalid_bundle_preserves_existing_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.bundle(p)
            folder=p/'whoga-naver-collector';folder.mkdir();(folder/'latest.json').write_text('old')
            report=json.loads((p/'validation.json').read_text());report['status']='fail';atomic_json(p/'validation.json',report)
            with self.assertRaises(ValidationError):prepare(p,root=p,event='schedule',ref='refs/heads/main',manual_url='')
            self.assertEqual((folder/'latest.json').read_text(),'old')

if __name__=='__main__':unittest.main()
