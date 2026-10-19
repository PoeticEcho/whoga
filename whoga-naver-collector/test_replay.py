"""Recorded DOM replay checks; synthetic fixtures never count as live evidence."""
import tempfile
import unittest
from pathlib import Path
from test_collector import row, state
from collector import DEFAULT_URL, ValidationError, atomic_json
from replay_observations import replay
from publish import prepare
from monitor import read_json


def bundle():
    observations=[]
    for i,(number,bottom,top) in enumerate(((1,False,0),(1,True,100),(1,True,100),
                                           (2,False,0),(2,True,100),(2,True,100))):
        s=state([row(1)],total=1,bottom=bottom)
        s.update(scrollTop=top,viewport={'width':1363,'height':936})
        observations.append({'pass':number,'observed_at':f'2026-10-19T10:00:0{i+1}+00:00','state':s})
    return {'transport':'chatgpt-cloud-browser','source_url':DEFAULT_URL,
            'started_at':'2026-10-19T10:00:00+00:00','finished_at':'2026-10-19T10:00:07+00:00',
            'observations':observations}


class ReplayTests(unittest.TestCase):
    def test_valid_replay_builds_legacy_snapshot_with_honest_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);atomic_json(p/'input.json',bundle())
            folder,report=replay(p/'input.json',p/'runs')
            snapshot=read_json(folder/'snapshot.json')
            self.assertEqual(snapshot['count'],1)
            self.assertEqual(snapshot['collectedAt'],'2026-10-19T19:00:07+09:00')
            self.assertEqual(snapshot['validation']['method'],'two-complete-dom-observation-passes')
            self.assertFalse(report['publication_eligible'])

    def test_incomplete_changed_or_out_of_order_observations_fail(self):
        cases=[]
        b=bundle();b['observations'].pop();cases.append(b)
        b=bundle();b['observations'][3]['state']['scrollTop']=100;cases.append(b)
        b=bundle();b['observations'][-1]['state']['viewport']['width']=1440;cases.append(b)
        b=bundle();b['observations'][1]['observed_at']='2026-10-19T09:59:59Z';cases.append(b)
        b=bundle()
        for event in b['observations'][3:]:event['state']['rows']=[row(2)]
        cases.append(b)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for b in cases:
                with self.subTest(bundle=b):
                    atomic_json(p/'input.json',b)
                    with self.assertRaises(ValidationError):replay(p/'input.json',p/'runs')

    def test_assisted_observation_is_rejected_even_under_schedule_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);atomic_json(p/'input.json',bundle())
            folder,_=replay(p/'input.json',p/'runs')
            with self.assertRaisesRegex(ValidationError,'Assisted observation'):
                prepare(folder,root=p,event='schedule',ref='refs/heads/main',manual_url='')


if __name__=='__main__':unittest.main()
