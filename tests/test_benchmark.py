"""Benchmark metrics on real renders; Claude judge via a mocked transport."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from montage_editor.benchmark import compare, judge, score
from montage_editor.config import Settings
from montage_editor.pipeline import create_montage
from montage_editor.vision_director import ClaudeDirector
from test_rhythm import write_song
from test_screen_analysis import make_game


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        root = cls.root = Path(cls.directory.name)
        game, song = root/'game.mp4', root/'song.wav'
        make_game(game, seconds=30)            # has a HUD-hidden "death" span at 12-15 s
        write_song(song, seconds=30, lift_bar=6)
        settings = Settings(width=160, height=90, duration=10, quality='draft')
        cls.cinematic = root/'cinematic.mp4'
        create_montage([game], song, cls.cinematic, settings,
                       story=dict(edit_profile='cinematic', transition='cinematic', normalize_audio=True))
        cls.plain = root/'plain.mp4'
        create_montage([game], song, cls.plain, settings)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_metrics_reflect_the_edit(self):
        cinematic, plain = score(self.cinematic), score(self.plain)
        self.assertEqual(cinematic['sync']['on_beat'], 1.0)
        self.assertEqual(cinematic['integrity']['non_gameplay_share'], 0.0)
        self.assertTrue(cinematic['integrity']['full_decode'])
        self.assertAlmostEqual(cinematic['delivery']['integrated_lufs'], -16, delta=1.5)
        self.assertLess(cinematic['delivery']['peak_dbfs'], 0)
        self.assertGreater(cinematic['highlights']['top_moments_used'], 0)
        self.assertGreater(cinematic['variety']['mean_neighbour_change'], 0)
        self.assertGreater(cinematic['craft']['hard_cuts'], 0)
        self.assertEqual(plain['craft']['blends'], 0)
        rows = compare([cinematic, plain])
        self.assertEqual([r['output'] for r in rows], ['cinematic.mp4', 'plain.mp4'])

    def test_judge_is_validated(self):
        metrics = score(self.cinematic)

        def client(grade):
            def create(**kwargs):
                self.assertEqual(sum(b['type'] == 'image' for b in kwargs['messages'][0]['content']), 1)
                return SimpleNamespace(stop_reason='end_turn', model=kwargs['model'],
                                       content=[SimpleNamespace(type='text', text=json.dumps(grade))], usage=None)
            return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        good = dict(moments=6, variety=7, pacing=8, story=5, overall=6, strengths='On the beat.', weaknesses='Repetitive.')
        result = judge(self.cinematic, metrics, ClaudeDirector(client=client(good)))
        self.assertEqual(result['overall'], 6)
        with self.assertRaises(ValueError):
            judge(self.cinematic, metrics, ClaudeDirector(client=client(dict(good, overall=11))))

    def test_cli_writes_a_report(self):
        report = self.root/'bench.json'
        out = subprocess.run(['python', '-m', 'montage_editor.cli', 'benchmark', str(self.cinematic), str(self.plain),
                              '--report', str(report)], capture_output=True, text=True, check=True)
        self.assertEqual(len(json.loads(out.stdout)), 2)
        self.assertEqual(len(json.loads(report.read_text())), 2)


if __name__ == '__main__':
    unittest.main()
