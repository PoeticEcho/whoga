import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('nas_run', Path(__file__).with_name('run.py'))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

class GateTests(unittest.TestCase):
    def test_probe_does_not_collect_full(self):
        stages = []
        run.sequence('probe', stages.append)
        self.assertEqual(stages, ['probe'])

    def test_full_always_probes_first(self):
        stages = []
        run.sequence('full', stages.append)
        self.assertEqual(stages, ['probe', 'full'])

    def test_probe_failure_blocks_full(self):
        stages = []
        def fail(stage):
            stages.append(stage)
            raise RuntimeError('connection reset')
        with self.assertRaises(RuntimeError):
            run.sequence('full', fail)
        self.assertEqual(stages, ['probe'])

if __name__ == '__main__':
    unittest.main()
