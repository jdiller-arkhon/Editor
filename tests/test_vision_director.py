"""Claude vision editor: real frame extraction and rendering, mocked Anthropic transport.

These tests do not call the live API and are not evidence of Claude's judgement quality;
they verify what is sent, that responses are validated, and how judgements drive the edit.
"""
import base64
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from montage_editor.config import Settings
from montage_editor.pipeline import Timeline, create_montage
from montage_editor.vision_director import (FALLBACK_BETA, MODEL, ClaudeDirector, apply_review,
                                            review_pool, validate_review)
from test_rhythm import write_song


class FakeClient:
    def __init__(self, judge, stop_reason='end_turn'):
        self.judge, self.stop_reason, self.calls = judge, stop_reason, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        ids = [int(b['text'].split()[1].rstrip(':')) for b in kwargs['messages'][0]['content']
               if b['type'] == 'text' and b['text'].startswith('Candidate ')]
        text = json.dumps(self.judge(ids))
        return SimpleNamespace(stop_reason=self.stop_reason, model=kwargs['model'],
                               content=[SimpleNamespace(type='thinking', thinking=''),
                                        SimpleNamespace(type='text', text=text)],
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=200))


def judge(ids):
    moments = []
    for i in ids:
        if i == 0:
            moments.append(dict(id=i, highlight=1, event='menu_or_loading', usable=False, peak='center',
                                note='Scoreboard overlay'))
        elif i == 1:
            moments.append(dict(id=i, highlight=10, event='multi_elimination', usable=True, peak='after',
                                note='Two eliminations in quick succession'))
        else:
            moments.append(dict(id=i, highlight=3, event='movement', usable=True, peak='center', note='Rotation'))
    return dict(moments=moments, sequence=[i for i in ids if i] + [999], rationale='Build to the double.')


class VisionDirectorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.video = self.root/'secret-match-name.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30',
                        '-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=8000', '-t', '30',
                        '-c:v', 'libx264', '-threads', '2', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                        str(self.video)], check=True)

    def tearDown(self):
        self.directory.cleanup()

    def candidates(self):
        return [dict(source=str(self.video), time=float(t), score=s, source_duration=30.0)
                for t, s in ((5, .9), (12, .8), (18, .7), (24, .6))]

    def test_request_sends_real_frames_and_no_paths(self):
        client = FakeClient(judge)
        candidates, report = ClaudeDirector(client=client).review(self.candidates(), 'Hopeful, relentless')
        request = client.calls[0]
        self.assertEqual(request['model'], MODEL)
        self.assertEqual(request['fallbacks'], 'default')
        self.assertIn(FALLBACK_BETA, request['betas'])
        self.assertEqual(request['thinking'], {'type': 'adaptive'})
        self.assertEqual(request['output_config']['format']['type'], 'json_schema')
        blocks = request['messages'][0]['content']
        images = [b for b in blocks if b['type'] == 'image']
        self.assertEqual(len(images), 12)
        for image in images[:3]:
            jpeg = base64.standard_b64decode(image['source']['data'])
            decoded = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height',
                                      '-of', 'csv=p=0', '-'], input=jpeg, capture_output=True, check=True)
            self.assertEqual(decoded.stdout.decode().strip(), '512,288')
        serialized = json.dumps(request)
        self.assertNotIn('secret-match-name', serialized)
        self.assertNotIn(str(self.root), serialized)
        self.assertEqual(report['frames_sent'], 12)
        self.assertEqual(report['usable'], 3)
        by_time = {round(c.get('activity_score', 0), 2): c for c in candidates}
        self.assertTrue(by_time[.9]['exclude'])
        self.assertEqual(by_time[.8]['score'], 1.0)
        self.assertAlmostEqual(by_time[.8]['time'], 12.6)
        self.assertEqual(by_time[.8]['event'], 'multi_elimination')
        self.assertEqual(by_time[.8]['story_rank'], 0)

    def test_invalid_or_refused_reviews_never_reach_the_edit(self):
        pool = self.candidates()
        good = judge(range(4))
        for broken in (dict(good, moments=good['moments']+[dict(good['moments'][1], id=7)]),
                       dict(good, moments=[dict(good['moments'][1], highlight=11)]),
                       dict(good, moments=[dict(good['moments'][1], id=True)]),
                       dict(good, moments=[dict(good['moments'][1], event='headshot_x9')]),
                       dict(good, moments=[good['moments'][1], good['moments'][1]]),
                       dict(good, moments=[])):
            with self.assertRaises(ValueError):
                validate_review(broken, len(pool))
        moments, sequence, _ = validate_review(good, 4)
        self.assertEqual(sequence, [1, 2, 3])  # unknown 999 and unusable 0 are dropped
        for stop in ('refusal', 'max_tokens'):
            with self.assertRaises(ValueError):
                ClaudeDirector(client=FakeClient(judge, stop)).review(pool)
        output = self.root/'never.mp4'
        with self.assertRaises(ValueError):
            create_montage([self.video], self.video, output, Settings(width=160, height=90, duration=4),
                           ai_editor=ClaudeDirector(client=FakeClient(lambda ids: {'moments': 'x'})))
        self.assertFalse(output.exists())

    def test_missing_credentials_are_explained(self):
        import os
        from unittest.mock import patch
        try:
            import anthropic
        except ImportError:
            self.skipTest('Anthropic SDK extra not installed')
        cleared = {k: v for k, v in os.environ.items() if not k.startswith('ANTHROPIC_')}
        with tempfile.TemporaryDirectory() as empty, patch.dict(os.environ, cleared, clear=True):
            os.environ['ANTHROPIC_CONFIG_DIR'] = empty
            os.environ['HOME'] = empty
            for profile in (None, 'drift-test-missing'):
                if profile:
                    os.environ['ANTHROPIC_PROFILE'] = profile
                with self.assertRaisesRegex(ValueError, 'credentials'):
                    ClaudeDirector().review(self.candidates()[:1])

    def test_pool_interleaves_sources(self):
        other = [dict(c, source='b', score=c['score']-.5) for c in self.candidates()]
        pool = review_pool(self.candidates()+other, 4)
        self.assertEqual([c['source'] for c in pool], [str(self.video), 'b', str(self.video), 'b'])
        rescored = apply_review(self.candidates()+other, pool, validate_review(judge(range(4)), 4)[0], [])
        unreviewed = [c for c in rescored if c['judged_by'] == 'activity heuristic']
        self.assertEqual(len(unreviewed), 4)

    def test_judgements_drive_a_real_render(self):
        song, output = self.root/'song.wav', self.root/'montage.mp4'
        write_song(song, bpm=128, seconds=20, lift_bar=4)
        settings = Settings(width=160, height=90, fps=30, duration=12, quality='draft')
        report = create_montage([self.video], song, output, settings,
                                story=dict(edit_profile='cinematic', transition='cinematic'),
                                ai_editor=ClaudeDirector(client=FakeClient(judge)))
        self.assertTrue(report['full_decode'])
        self.assertEqual(report['ai_director'], 'claude vision')
        self.assertEqual(report['ai_editor']['events']['multi_elimination'], 1)
        analysis = json.loads(output.with_suffix('.analysis.json').read_text())
        self.assertEqual(analysis['ai_editor']['reviewed'], len(analysis['candidates']))
        excluded = [c for c in analysis['candidates'] if c.get('exclude')]
        best = max(analysis['candidates'], key=lambda c: c['score'])
        self.assertEqual(best['event'], 'multi_elimination')
        timeline = Timeline.load(output.with_suffix('.timeline.json'))
        for clip in timeline.clips:
            for bad in excluded:
                self.assertTrue(clip.start+clip.duration <= bad['time']-1+1e-6 or clip.start >= bad['time']+1-1e-6)
        self.assertTrue(any(c.start <= best['time'] <= c.start+c.duration for c in timeline.clips))


if __name__ == '__main__':
    unittest.main()
