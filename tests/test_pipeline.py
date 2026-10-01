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

    def test_retimed_activity_anchor(self):
        from montage_editor.editing import source_offset
        candidates = [{'source':'a','time':i,'score':.8,'source_duration':30} for i in (3,9,15,21)]
        timeline = direct(candidates,{'onsets':[1,2,3,4,5,6]},'music',Settings(),6,cinematic=True)
        self.assertTrue(any(c.speed_profile=='impact' for c in timeline.clips))
        for c in timeline.clips:
            self.assertAlmostEqual(c.duration*Settings().fps,round(c.duration*Settings().fps))
        for clip in timeline.clips:
            self.assertAlmostEqual(source_offset(clip.duration,clip.duration,clip.speed_profile),clip.duration)
            if clip.anchor_source is not None:
                self.assertAlmostEqual(clip.start+source_offset(clip.anchor_output,clip.duration,
                                       clip.speed_profile),clip.anchor_source)
        with self.assertRaises(ValueError):
            replace(timeline,gameplay_gain=float('nan')).validate()

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
            # Many fractional-second shots exposed cumulative AAC/container concat drift.
            fractional=replace(timeline,clips=[Clip(str(video),i*.5,11/24,0) for i in range(16)])
            fractional_report=render(fractional,d/'fractional.mp4')
            self.assertTrue(fractional_report['full_decode'])
            self.assertAlmostEqual(fractional_report['duration'],16*11/24,delta=.08)

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
                            transition='fade_black',faith_message='Walk with Christ.')
            story.save(d/'story.json')
            self.assertEqual(Timeline.load(d/'story.json'), story)
            self.assertTrue(render(story, d/'story.mp4')['full_decode'])
            frame = subprocess.run(['ffmpeg','-v','error','-i',str(d/'story.mp4'),
                                    '-frames:v','1','-pix_fmt','gray','-f','rawvideo','pipe:1'],
                                    check=True,capture_output=True).stdout
            self.assertLess(np.frombuffer(frame,dtype=np.uint8).mean(), 3)
            self.assertTrue(render(replace(story,transition='fade_white'),d/'white.mp4')['valid'])
            cinematic=replace(timeline,clips=[replace(c,speed_profile='impact',anchor_source=None,
                anchor_output=None) for c in timeline.clips],transition='zoom',gameplay_gain=.25,
                music_gain=.8,normalize_audio=True)
            cinematic_report=render(cinematic,d/'cinematic.mp4')
            self.assertEqual(cinematic_report['audio_mastering'],'measured two-pass loudnorm')
            self.assertTrue(cinematic_report['full_decode'])
            def decoded_frame(path):
                return subprocess.run(['ffmpeg','-v','error','-ss','0.2','-i',str(path),
                    '-frames:v','1','-pix_fmt','gray','-f','rawvideo','pipe:1'],
                    check=True,capture_output=True).stdout
            difference=abs(np.frombuffer(decoded_frame(d/'cinematic.mp4'),dtype=np.uint8).astype(float)-
                           np.frombuffer(decoded_frame(d/'replay.mp4'),dtype=np.uint8)).mean()
            self.assertGreater(difference,1)
            samples=subprocess.run(['ffmpeg','-v','error','-i',str(d/'cinematic.mp4'),
                '-vn','-ac','1','-ar','8000','-f','f32le','pipe:1'],check=True,capture_output=True).stdout
            audio=np.frombuffer(samples,dtype='<f4')
            self.assertGreater(np.sqrt(np.mean(audio*audio)),.01)
            self.assertLess(abs(audio).max(),1)
            # The soundtrack frequency survives the mix, rather than an empty audio stream.
            spectrum=abs(np.fft.rfft(audio[16000:32000]))
            self.assertGreater(spectrum[440],spectrum[600]*10)
            # Silent video inputs must still concatenate with normal audio inputs.
            silent_video=d/'silent-video.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x180:r=24',
                            '-t','2','-c:v','libx264','-threads','2',str(silent_video)],check=True)
            mixed_sources=replace(cinematic,clips=[Clip(str(silent_video),0,2,0,'impact'),
                                   Clip(str(video),4,2,1)],dialogue=[],faith_message='')
            self.assertTrue(render(mixed_sources,d/'mixed-sources.mp4')['full_decode'])
            silent=d/'silent.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','anullsrc=r=8000:cl=mono',
                            '-t','2',str(silent)],check=True)
            from montage_editor.pipeline import music_analysis
            with self.assertRaisesRegex(ValueError,'silent'):
                music_analysis(probe(silent),2)

            with self.assertRaises(ValueError):
                replace(story,dialogue=[DialogueCue(str(music),5,0,2)]).validate()
            with self.assertRaises(FileExistsError):
                render(timeline, output)
            with self.assertRaises(ValueError):
                create_montage([music], music, d/'invalid.mp4', Settings())
            with self.assertRaises(ValueError):
                create_montage([video,video], music, d/'duplicate.mp4', Settings())
            self.assertEqual(probe(output)['streams'][0]['width'],320)
