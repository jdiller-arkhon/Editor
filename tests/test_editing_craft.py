"""Rendered checks for smooth speed ramps, beat punch-ins and per-cut transitions."""
import json
import subprocess
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

import numpy as np

from montage_editor.config import Settings
from montage_editor.editing import source_offset
from montage_editor.pipeline import Clip, Timeline, render
from montage_editor.rhythm import boundary_styles


def ffmpeg(*args):
    subprocess.run(['ffmpeg', '-v', 'error', *args], check=True)


def frames(path, width, height, fmt='gray', start=None, count=None):
    command = ['ffmpeg', '-v', 'error']
    if start is not None:
        command += ['-ss', str(start)]
    command += ['-i', str(path)]
    if count:
        command += ['-frames:v', str(count)]
    raw = subprocess.run(command+['-pix_fmt', fmt, '-f', 'rawvideo', 'pipe:1'],
                         capture_output=True, check=True).stdout
    channels = 3 if fmt == 'rgb24' else 1
    return np.frombuffer(raw, np.uint8).reshape(-1, height, width, channels).astype(float)


class SmoothRampTests(unittest.TestCase):
    def test_mapping_is_smooth_and_consumes_exact_duration(self):
        speeds = np.diff([source_offset(o, 4, 'ramp') for o in np.linspace(0, 4, 401)])/.01
        self.assertAlmostEqual(source_offset(4, 4, 'ramp'), 4, places=9)
        self.assertAlmostEqual(speeds.max(), 1.5, delta=.03)
        self.assertAlmostEqual(speeds.min(), .5, delta=.03)
        # No jumps: adjacent speeds change gradually (the stepped profile jumps by 0.8x).
        self.assertLess(np.abs(np.diff(speeds)).max(), .2)

    def test_rendered_frames_follow_the_planned_source_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clock, music = root/'clock.mp4', root/'music.wav'
            # Luma encodes source time, so decoded frames reveal which source instant was shown.
            ffmpeg('-f', 'lavfi', '-i', "nullsrc=s=64x36:r=60,geq=lum='clip(20+T*40,0,255)':cb=128:cr=128",
                   '-f', 'lavfi', '-i', 'sine=f=300:sample_rate=8000', '-t', '6', '-c:v', 'libx264',
                   '-qp', '0', '-pix_fmt', 'yuv444p', '-c:a', 'aac', str(clock))
            ffmpeg('-f', 'lavfi', '-i', 'sine=f=220', '-t', '6', str(music))
            settings = Settings(width=64, height=36, fps=30, quality='draft')
            for profile in ('normal', 'ramp'):
                report = render(Timeline(1, str(music), settings.__dict__,
                                         [Clip(str(clock), 1, 4, 0, profile)], gameplay_gain=1),
                                root/f'{profile}.mp4')
                self.assertTrue(report['full_decode'])
                self.assertAlmostEqual(report['duration'], 4, delta=.05)
            normal = frames(root/'normal.mp4', 64, 36).mean(axis=(1, 2, 3))
            ramp = frames(root/'ramp.mp4', 64, 36).mean(axis=(1, 2, 3))
            times = np.arange(len(normal))/30
            shown = np.interp(ramp, normal, times)
            planned = np.array([source_offset(t, 4, 'ramp') for t in times[:len(shown)]])
            self.assertLess(np.abs(shown-planned)[2:-2].max(), .06)
            # An unramped clock would be up to ~0.32 s away from the plan mid-shot.
            self.assertGreater(np.abs(times[:len(shown)]-planned).max(), .25)


class PunchAndTransitionTests(unittest.TestCase):
    def test_beat_punch_changes_frames_only_after_its_accent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, music = root/'game.mp4', root/'music.wav'
            ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30', '-t', '4', '-c:v', 'libx264',
                   '-pix_fmt', 'yuv420p', str(video))
            ffmpeg('-f', 'lavfi', '-i', 'sine=f=220', '-t', '4', str(music))
            settings = Settings(width=160, height=90, fps=30, quality='draft')
            plain = Timeline(1, str(music), settings.__dict__, [Clip(str(video), 0, 3, 0)])
            punched = Timeline(1, str(music), settings.__dict__, [Clip(str(video), 0, 3, 0, accents=[1.0])])
            plain_report = render(plain, root/'plain.mp4')
            report = render(punched, root/'punch.mp4')
            self.assertIn('beat_punch', report['edit_effects'])
            self.assertAlmostEqual(report['duration'], 3, delta=.05)
            a, b = frames(root/'plain.mp4', 160, 90), frames(root/'punch.mp4', 160, 90)
            before = np.abs(a[15]-b[15]).mean()
            on_beat = np.abs(a[31]-b[31]).mean()
            later = np.abs(a[75]-b[75]).mean()
            self.assertGreater(on_beat, 8*max(before, .5))
            self.assertLess(later, on_beat/3)
            self.assertTrue(plain_report['full_decode'])
            with self.assertRaises(ValueError):
                Timeline(1, str(music), settings.__dict__, [Clip(str(video), 0, 3, 0, accents=[3.5])]).validate()

    def test_hard_cut_and_blend_on_chosen_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('red', 'blue', 'lime'):
                ffmpeg('-f', 'lavfi', '-i', f'color=c={name}:s=160x90:r=24', '-t', '2', '-c:v', 'libx264',
                       '-pix_fmt', 'yuv444p', '-qp', '0', str(root/f'{name}.mp4'))
            music = root/'music.wav'
            ffmpeg('-f', 'lavfi', '-i', 'sine=f=220', '-t', '6', str(music))
            settings = Settings(width=160, height=90, fps=24, quality='draft')
            timeline = Timeline(1, str(music), settings.__dict__,
                                [Clip(str(root/f'{n}.mp4'), 0, 2, 1) for n in ('red', 'blue', 'lime')],
                                transition='cinematic', transition_duration=.5,
                                boundary_transitions=['cut', 'smoothleft'])
            report = render(timeline, root/'mixed.mp4')
            self.assertAlmostEqual(report['duration'], 6, delta=.08)
            self.assertEqual([b['effect'] for b in report['transition_boundaries']], ['cut', 'smoothleft'])
            video = frames(root/'mixed.mp4', 160, 90, 'rgb24').reshape(-1, 160*90, 3)
            means = video.mean(axis=1)
            # Frame 47 is the last red frame, 48 the first blue: a clean cut, no blend.
            self.assertGreater(means[47][0], 200)
            self.assertLess(means[47][2], 40)
            self.assertGreater(means[48][2], 200)
            self.assertLess(means[48][0], 40)
            # At the second boundary both blue and lime are visible in one frame.
            mid = video[96]
            blue = np.mean((mid[:, 2] > 150) & (mid[:, 1] < 100))
            lime = np.mean((mid[:, 1] > 150) & (mid[:, 2] < 100))
            self.assertGreater(blue, .1)
            self.assertGreater(lime, .1)
            with self.assertRaises(ValueError):
                Timeline(1, 'm', settings.__dict__, timeline.clips, transition='cut',
                         boundary_transitions=['cut', 'fade']).validate()
            with self.assertRaises(ValueError):
                Timeline(1, 'm', settings.__dict__, timeline.clips, transition='cinematic',
                         boundary_transitions=['cut']).validate()

    def test_styles_follow_phrase_marks_and_old_projects_still_load(self):
        settings = Settings(fps=30)
        clips = [Clip('a', i*4, 2, 1) for i in range(5)]
        timeline = Timeline(1, 'm', settings.__dict__, clips, transition='cinematic')
        music = dict(phrases=[dict(time=4.0, kinds=['grid']), dict(time=6.0, kinds=['grid', 'rise']),
                              dict(time=8.0, kinds=['fall'])])
        self.assertEqual(boundary_styles(timeline, music), ['cut', 'smoothleft', 'zoomin', 'fade'])
        with tempfile.TemporaryDirectory() as directory:
            legacy = asdict(timeline)
            legacy.pop('boundary_transitions')
            for clip in legacy['clips']:
                clip.pop('accents')
            path = Path(directory)/'old.timeline.json'
            path.write_text(json.dumps(legacy))
            loaded = Timeline.load(path)
            self.assertEqual(loaded.boundary_transitions, [])
            self.assertEqual(loaded.clips[0].accents, [])


if __name__ == '__main__':
    unittest.main()
