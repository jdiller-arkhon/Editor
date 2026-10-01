import json
from unittest.mock import patch
from dataclasses import replace
import numpy as np
from montage_editor.storytelling import DialogueCue
from pathlib import Path
import subprocess
import tempfile
import unittest

from montage_editor.config import Settings
from montage_editor.pipeline import Clip, Timeline, create_montage, direct, probe, render


class TimelineTests(unittest.TestCase):
    def test_roundtrip_and_invalid_bounds(self):
        timeline = Timeline(1, 'music.wav', Settings().__dict__, [Clip('a.mp4', 0, 2, .5)])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'project.json'
            timeline.save(path)
            self.assertEqual(Timeline.load(path), timeline)
        with self.assertRaises(ValueError):
            Timeline(1, 'music.wav', Settings().__dict__, [Clip('a', -1, 2, 0)]).validate()

    def test_director_no_overlap_or_repeat(self):
        candidates = [{'source':'a', 'time':i, 'score':1, 'source_duration':12} for i in [2,6,10]]
        timeline = direct(candidates, {'onsets':[2,4,6,8,10]}, 'song', Settings(), 30)
        self.assertLessEqual(sum(c.duration for c in timeline.clips), 12)
        for i,a in enumerate(timeline.clips):
            for b in timeline.clips[i+1:]:
                self.assertTrue(a.start+a.duration <= b.start+.00001 or b.start+b.duration <= a.start+.00001)


class RealRenderTests(unittest.TestCase):
    def test_full_pipeline_and_timeline_replay(self):
        # Mandatory integration test: missing FFmpeg must fail CI, never silently skip.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            video, music, output = d/'source.mp4', d/'song.wav', d/'montage.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=24',
                            '-f','lavfi','-i','sine=frequency=440:sample_rate=8000', '-t','12',
                            '-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac',str(video)],check=True)
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                            'aevalsrc=sin(2*PI*220*t)*if(lt(mod(t\\,0.5)\\,0.08)\\,0.8\\,0.08):s=8000',
                            '-t','8',str(music)],check=True)
            report = create_montage([video], music, output, Settings(width=320,height=180,fps=24,duration=6))
            self.assertTrue(report['full_decode'])
            self.assertAlmostEqual(report['duration'],6,delta=.25)
            analysis = json.loads(output.with_suffix('.analysis.json').read_text())
            self.assertGreater(len(analysis['music']['onsets']), 3)
            self.assertGreater(len(analysis['candidates']), 0)
            timeline = Timeline.load(output.with_suffix('.timeline.json'))
            replay = render(timeline, d/'replay.mp4')
            self.assertTrue(replay['valid'])
            def plan(candidates,brief):
                return dict(candidate_order=list(reversed(range(len(candidates)))),minimum_clip=1.5,
                            maximum_clip=4,transition='fade_black',transition_duration=.2,
                            rationale='Measured activity progression'),candidates
            with patch('montage_editor.ai_director.OllamaDirector.plan',side_effect=plan):
                ai_report=create_montage([video],music,d/'ai.mp4',
                    Settings(width=320,height=180,fps=24,duration=6),ai_model='mock-model')
            self.assertEqual(ai_report['ai_director'],'ollama')
            self.assertTrue(ai_report['full_decode'])
            self.assertEqual(Timeline.load(d/'ai.timeline.json').transition,'fade_black')
            story = replace(timeline, dialogue=[DialogueCue(str(music), 1, 0, 2,
                            reference='Original narration inspired by Christian hope')],
                            transition='fade_black')
            story.save(d/'story.json')
            self.assertEqual(Timeline.load(d/'story.json'), story)
            self.assertTrue(render(story, d/'story.mp4')['full_decode'])
            frame = subprocess.run(['ffmpeg','-v','error','-i',str(d/'story.mp4'),
                                    '-frames:v','1','-pix_fmt','gray','-f','rawvideo','pipe:1'],
                                    check=True,capture_output=True).stdout
            self.assertLess(np.frombuffer(frame,dtype=np.uint8).mean(), 3)
            self.assertTrue(render(replace(story,transition='fade_white'),d/'white.mp4')['valid'])
            with self.assertRaises(ValueError):
                replace(story,dialogue=[DialogueCue(str(music),5,0,2)]).validate()
            with self.assertRaises(FileExistsError):
                render(timeline, output)
            with self.assertRaises(ValueError):
                create_montage([music], music, d/'invalid.mp4', Settings())
            with self.assertRaises(ValueError):
                create_montage([video,video], music, d/'duplicate.mp4', Settings())
            self.assertEqual(probe(output)['streams'][0]['width'],320)
