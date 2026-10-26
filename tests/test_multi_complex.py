import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_nas_import import fixture,m,CONFIG,PATH

ROOT=Path(__file__).resolve().parents[1]
class MultiComplexTests(unittest.TestCase):
    def payload(self,number):
        p=fixture();p['target'].update(complexNo=number,complexName='검증아파트',estateTypeText='아파트',sourceUrl='https://fin.land.naver.com/complexes/'+number)
        for card in p['cards']:
            card['name']='검증아파트 201동';card['summary'][:2]=['아파트','110㎡ (전용84.9)'];card['summary'][2]='10/25층'
        for article in p['articles']:
            article.update(name='검증아파트 201동',areaText='110㎡ (전용84.9)',floorInfo='10/25층')
        return p
    def test_three_complex_import_build_and_isolation(self):
        spec=importlib.util.spec_from_file_location('build_multi',ROOT/'scripts/build_site.py');build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'config.json').write_text(json.dumps(CONFIG))
            (root/'collection-plan.json').write_text(json.dumps(dict(schemaVersion=1,enabled=True,intervalHours=6,targets=[dict(complexNo=n) for n in ['140635','123','456']])))
            for number in ['140635','123','456']:
                p=fixture() if number=='140635' else self.payload(number)
                path=root/'nas-imports'/number/(p['runId']+'.json');path.parent.mkdir(parents=True);path.write_text(json.dumps(p))
            def git(*args):return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.DEVNULL)
            git('init');git('add','.');git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','fixture')
            previous=os.getcwd()
            try:
                os.chdir(root)
                with patch.object(sys,'argv',['import_nas','--source-ref','HEAD']):m.main()
            finally:os.chdir(previous)
            catalog=json.loads((root/'complexes.json').read_text());self.assertEqual(len(catalog['complexes']),3)
            self.assertTrue(all(c['ready'] for c in catalog['complexes']))
            for number in ['123','456']:
                snap=json.loads((root/f'data/complexes/{number}/2026-10-26.json').read_text());self.assertEqual(snap['complexNo'],number);self.assertEqual(snap['items'][0]['type'],'110㎡ (전용84.9)')
                self.assertEqual(snap['items'][0]['floorCat'],'중층')
            (root/'index.html').write_text('test');(root/'.nojekyll').touch();(root/'assets').mkdir()
            with patch.object(build,'ROOT',root):out=build.build(root/'_site')
            self.assertTrue((out/'data/complexes/123/2026-10-26.json').exists())
            self.assertFalse((out/'nas-imports').exists())
    def test_same_day_old_observation_archived_without_reimport_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)
            first=fixture();m.import_snapshots([(PATH,first)],data,CONFIG,'b'*40)
            newer=copy.deepcopy(first);newer.update(runId='c'*32,collectedAt='2026-10-26T09:30:00+09:00')
            newpath='nas-imports/140635/'+'c'*32+'.json'
            self.assertTrue(m.import_snapshots([(newpath,newer)],data,CONFIG,'b'*40))
            self.assertTrue((data/('2026-10-26_nas_'+first['runId']+'.json')).exists())
            before={p.name:p.read_bytes() for p in data.glob('*.json')}
            self.assertFalse(m.import_snapshots([(PATH,first),(newpath,newer)],data,CONFIG,'b'*40))
            self.assertEqual(before,{p.name:p.read_bytes() for p in data.glob('*.json')})
    def test_cross_complex_name_or_price_mismatch_rejected(self):
        p=self.payload('123');p['cards'][0]['name']='다른단지 201동'
        with self.assertRaises(ValueError):m.convert(p,{**CONFIG,'complexId':'123'},PATH.replace('140635','123'),'b'*40)
