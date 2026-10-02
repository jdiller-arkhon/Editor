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
from montage_editor.pipeline import Clip, swap_shots
from montage_editor.vision_director import (DIRECT_SYSTEM, DIRECTOR_MODEL, FALLBACK_BETA, MODEL, REVIEW_SYSTEM,
                                            ClaudeDirector, apply_review, review_pool, validate_direction,
                                            validate_review, validate_swaps)
from test_rhythm import write_song


class FakeClient:
    def __init__(self, judge, stop_reason='end_turn', cut=None, direct=None):
        self.judge, self.stop_reason, self.calls = judge, stop_reason, []
        self.cut = cut or (lambda text: dict(swaps=[], notes='Cut is strong.'))
        self.direct = direct or (lambda text: dict(slots=[], arc='Keep the draft.'))
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        blocks = kwargs['messages'][0]['content']
        if kwargs['system'] == REVIEW_SYSTEM:
            text = json.dumps(self.cut(blocks[0]['text']))
        elif kwargs['system'] == DIRECT_SYSTEM:
            text = json.dumps(self.direct(blocks[0]['text']))
        else:
            ids = [int(b['text'].split()[1].rstrip(':')) for b in blocks
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
            moments.append(dict(id=i, highlight=1, event='menu_or_loading', usable=False, peak_frame=3,
                                note='Scoreboard overlay'))
        elif i == 1:
            moments.append(dict(id=i, highlight=10, event='multi_elimination', usable=True, peak_frame=5,
                                note='Two eliminations in quick succession'))
        else:
            moments.append(dict(id=i, highlight=3, event='movement', usable=True, peak_frame=3, note='Rotation'))
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
        self.assertEqual(len(images), 4)   # one numbered six-frame strip per candidate
        for image in images:
            jpeg = base64.standard_b64decode(image['source']['data'])
            decoded = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height',
                                      '-of', 'csv=p=0', '-'], input=jpeg, capture_output=True, check=True)
            self.assertEqual(decoded.stdout.decode().strip(), '768,288')
        serialized = json.dumps(request)
        self.assertNotIn('secret-match-name', serialized)
        self.assertNotIn(str(self.root), serialized)
        self.assertEqual(report['images_sent'], 4); self.assertEqual(report['frames_per_image'], 6)
        self.assertEqual(report['usable'], 3)
        by_time = {round(c.get('activity_score', 0), 2): c for c in candidates}
        self.assertTrue(by_time[.9]['exclude'])
        self.assertEqual(by_time[.8]['score'], 1.0)
        self.assertAlmostEqual(by_time[.8]['time'], 12.5)   # strip starts 10.5 s; frame 5 = +2.0 s
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
                       dict(good, moments=[dict(good['moments'][1], peak_frame=7)]),
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

    def test_cut_review_swaps_are_validated_and_applied(self):
        song, output = self.root/'song.wav', self.root/'reviewed.mp4'
        write_song(song, bpm=128, seconds=20, lift_bar=4)
        seen = {}

        def cut(text):
            seen['text'] = text
            return dict(swaps=[dict(shot=1, alternate=0, reason='Stronger opener'),
                               dict(shot=2, alternate=1, reason='Overlapping test swap')], notes='Two swaps')
        settings = Settings(width=160, height=90, fps=30, duration=8, quality='draft',
                            minimum_clip=1.5, maximum_clip=2.5)
        report = create_montage([self.video], song, output, settings,
                                story=dict(edit_profile='cinematic', transition='cut'),
                                ai_editor=ClaudeDirector(client=FakeClient(judge, cut=cut)))
        self.assertTrue(report['full_decode'])
        analysis = json.loads(output.with_suffix('.analysis.json').read_text())
        review = analysis['ai_editor']['cut_review']
        self.assertIn('Planned shots', seen['text']); self.assertIn('final shot (closing line)', seen['text'])
        self.assertEqual(review['swaps_applied'][0]['shot'], 1)
        self.assertEqual(review['swaps_applied'][0]['reason'], 'Stronger opener')
        self.assertEqual(len(review['swaps_applied'])+len(review['swaps_rejected']), 2)
        timeline = Timeline.load(output.with_suffix('.timeline.json'))
        for swap in review['swaps_applied']:
            clip = timeline.clips[swap['shot']-1]
            self.assertTrue(clip.start <= swap['source_time'] <= clip.start+clip.duration)
        self.assertAlmostEqual(sum(c.duration for c in timeline.clips), 8, places=6)
        for i, a in enumerate(timeline.clips):
            for b in timeline.clips[i+1:]:
                self.assertTrue(a.start+a.duration <= b.start+1e-6 or b.start+b.duration <= a.start+1e-6)

    def test_swap_rules_and_failed_reviews_keep_the_cut(self):
        with self.assertRaises(ValueError):
            validate_swaps(dict(swaps=[dict(shot=9, alternate=0, reason='x')], notes=''), 3, 2)
        with self.assertRaises(ValueError):
            validate_swaps(dict(swaps=[dict(shot=1, alternate=0, reason='x')]*2, notes=''), 3, 2)
        with self.assertRaises(ValueError):
            validate_swaps(dict(swaps=[dict(shot=i, alternate=i, reason='x') for i in range(1, 6)], notes=''), 9, 9)
        timeline = Timeline(1, 'm', Settings().__dict__, [Clip(str(self.video), 0, 2, .5), Clip(str(self.video), 10, 2, .5)])
        moment = dict(source=str(self.video), time=11.0, score=1.0, source_duration=30.0)
        _, applied, rejected = swap_shots(timeline, [(0, moment)])
        self.assertEqual(applied, []); self.assertEqual(rejected[0]['reason'], 'would reuse footage already in the cut')
        blocked = dict(source=str(self.video), time=20.0, exclude=True, span=[19.0, 21.0])
        _, _, rejected = swap_shots(timeline, [(0, dict(moment, time=20.0))], [blocked])
        self.assertEqual(rejected[0]['reason'], 'covers a non-gameplay span')
        song, output = self.root/'song.wav', self.root/'kept.mp4'
        write_song(song, bpm=128, seconds=20, lift_bar=4)
        report = create_montage([self.video], song, output, Settings(width=160, height=90, duration=6, quality='draft'),
                                ai_editor=ClaudeDirector(client=FakeClient(judge, cut=lambda text: {'swaps': 'nope'})))
        self.assertTrue(report['full_decode'])
        analysis = json.loads(output.with_suffix('.analysis.json').read_text())
        self.assertIn('error', analysis['ai_editor']['cut_review'])

    def test_claude_directs_moments_treatments_and_transitions(self):
        song, output = self.root/'song.wav', self.root/'directed.mp4'
        write_song(song, bpm=128, seconds=20, lift_bar=4)
        seen = {}

        def direct(text):
            seen['text'] = text
            slots = [l for l in text.splitlines() if l[:1] == 'S' and l[1:2].isdigit()]
            moments = [l for l in text.splitlines() if l[:1] == 'M' and l[1:2].isdigit()]
            best = next(int(l.split(':')[0][1:]) for l in moments if 'multi_elimination' in l)
            others = [int(l.split(':')[0][1:]) for l in moments if 'multi_elimination' not in l]
            long_slot = next(i for i, l in enumerate(slots, 1) if float(l.split('(')[1].split('s')[0]) >= 1.0)
            plan = [dict(slot=long_slot, moment=best, treatment='ramp', transition_out='push_left')]
            plan += [dict(slot=i, moment=m, treatment='punch', transition_out='cut')
                     for i, m in zip((i for i in range(1, len(slots)+1) if i != long_slot), others)]
            seen['slot'] = long_slot
            return dict(slots=plan, arc='Open strong, land the double on the long slot.')
        client = FakeClient(judge, direct=direct)
        settings = Settings(width=160, height=90, fps=30, duration=8, quality='draft')
        report = create_montage([self.video], song, output, settings,
                                story=dict(edit_profile='cinematic', transition='cinematic'),
                                ai_editor=ClaudeDirector(client=client))
        self.assertTrue(report['full_decode'])
        request = next(c for c in client.calls if c['system'] == DIRECT_SYSTEM)
        self.assertEqual(request['model'], DIRECTOR_MODEL)
        self.assertEqual(sum(b['type'] == 'image' for b in request['messages'][0]['content']), 1)
        self.assertIn('FINAL (closing line)', seen['text']); self.assertIn('BPM', seen['text'])
        analysis = json.loads(output.with_suffix('.analysis.json').read_text())
        plan = analysis['ai_editor']['edit_plan']
        self.assertIn(seen['slot'], plan['applied'])
        timeline = Timeline.load(output.with_suffix('.timeline.json'))
        hero = timeline.clips[seen['slot']-1]
        best = next(c for c in analysis['candidates'] if c.get('event') == 'multi_elimination')
        self.assertTrue(hero.start <= best['time'] <= hero.start+hero.duration)
        self.assertEqual(hero.speed_profile, 'ramp')
        if seen['slot'] < len(timeline.clips):
            self.assertEqual(timeline.boundary_transitions[seen['slot']-1], 'smoothleft')
        for i, a in enumerate(timeline.clips):
            for b in timeline.clips[i+1:]:
                self.assertTrue(a.source != b.source or a.start+a.duration <= b.start+1e-6 or b.start+b.duration <= a.start+1e-6)

    def test_direction_is_validated_and_conflicts_keep_the_draft(self):
        good = dict(slots=[dict(slot=1, moment=0, treatment='ramp', transition_out='cut'),
                           dict(slot=2, moment=1, treatment='ramp', transition_out='zoom')], arc='x')
        assignments, _ = validate_direction(good, 3, 2)
        self.assertEqual([a[2] for a in assignments], ['ramp', 'straight'])   # no back-to-back slow motion
        for bad in (dict(good, slots=[dict(good['slots'][0], slot=4)]), dict(good, slots=[dict(good['slots'][0], moment=2)]),
                    dict(good, slots=[good['slots'][0], dict(good['slots'][1], moment=0)]),
                    dict(good, slots=[dict(good['slots'][0], treatment='spin')]), {'slots': 'all'}):
            with self.assertRaises(ValueError):
                validate_direction(bad, 3, 2)
        from montage_editor.pipeline import apply_plan
        timeline = Timeline(1, 'm', Settings().__dict__, [Clip(str(self.video), 2, 2, .5), Clip(str(self.video), 10, 2, .5),
                                                          Clip(str(self.video), 20, 2, .5)], transition='cinematic')
        moment = lambda t: dict(source=str(self.video), time=t, score=1.0, source_duration=30.0)
        # Slot 1 takes footage at 25 s; slot 2 asks for 25.5 s too: overlapping, so it keeps its draft.
        result, applied, notes = apply_plan(timeline, [(0, moment(25.0), 'straight', 'push_right'),
                                                       (1, moment(25.5), 'straight', 'cut')], {'beats': []})
        self.assertEqual(applied, [0])
        self.assertTrue(any('reuse' in n['note'] for n in notes))
        self.assertEqual(result.clips[1], timeline.clips[1])
        self.assertEqual(result.boundary_transitions[0], 'smoothright')


if __name__ == '__main__':
    unittest.main()
