"""Rendered checks for motion-matched pushes and impact frames."""
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from montage_editor import craft
from montage_editor.config import Settings
from montage_editor.editing import source_offset
from montage_editor.pipeline import Clip, Timeline, match_push_directions, render
from test_finishing import ffmpeg, frames


class TechniqueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        root = cls.root = Path(cls.directory.name)
        cls.music = root/'music.wav'
        ffmpeg('-f', 'lavfi', '-i', 'sine=f=220:sample_rate=48000', '-t', '8', str(cls.music))
        # A wide test card viewed through a moving window: the camera pans right or left.
        for name, x in (('right', 't*120'), ('left', '600-t*120')):
            ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=960x180:rate=30', '-t', '5', '-vf', f"crop=320:180:x='{x}':y=0",
                   '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(root/f'pan-{name}.mp4'))
        ffmpeg('-f', 'lavfi', '-i', 'color=c=0x404040:size=320x180:rate=30', '-t', '5', '-c:v', 'libx264',
               '-pix_fmt', 'yuv420p', str(root/'still.mp4'))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_pan_is_measured_from_real_frames(self):
        self.assertLess(craft.pan_velocity(str(self.root/'pan-right.mp4'), 2.0), -1.5)   # image moves left
        self.assertGreater(craft.pan_velocity(str(self.root/'pan-left.mp4'), 2.0), 1.5)
        self.assertEqual(craft.push_for_pan(craft.pan_velocity(str(self.root/'still.mp4'), 2.0)), None)

    def test_pushes_follow_the_camera_into_the_next_shot(self):
        settings = Settings(width=320, height=180, fps=30, quality='draft')
        clips = [Clip(str(self.root/'pan-right.mp4'), 0, 1.5, 1), Clip(str(self.root/'pan-left.mp4'), 0, 1.5, 1),
                 Clip(str(self.root/'still.mp4'), 0, 1.5, 1), Clip(str(self.root/'pan-right.mp4'), 2, 1.5, 1)]
        timeline = Timeline(1, str(self.music), settings.__dict__, clips, transition='cinematic',
                            boundary_transitions=['smoothright', 'smoothleft', 'smoothright'])
        matched, changes = match_push_directions(timeline)
        # Camera turning right (image moving left) -> push left; left -> right; still camera -> unchanged.
        self.assertEqual(matched.boundary_transitions, ['smoothleft', 'smoothright', 'smoothright'])
        self.assertEqual([c['boundary'] for c in changes], [1, 2])
        report = render(matched, self.root/'matched.mp4')
        self.assertTrue(report['full_decode'])
        self.assertEqual([b['effect'] for b in report['transition_boundaries']], matched.boundary_transitions)

    def test_impact_frames_flash_and_shake_on_the_hit_only_when_enabled(self):
        settings = Settings(width=320, height=180, fps=30, quality='draft')
        clip = Clip(str(self.root/'still.mp4'), 0, 2.0, 1, 'ramp', source_offset(1.0, 2.0, 'ramp'), 1.0)
        base = Timeline(1, str(self.music), settings.__dict__, [clip])
        brightness = {}
        for name, timeline in (('plain', base), ('impact', replace(base, impacts=True))):
            report = render(timeline, self.root/f'{name}.mp4')
            self.assertTrue(report['full_decode'])
            brightness[name] = frames(self.root/f'{name}.mp4', 320, 180).mean(axis=(1, 2, 3))
        self.assertEqual(report['finishing']['impacts'], 1)
        lift = brightness['impact']-brightness['plain']
        hit = int(round(1.0*30))
        self.assertGreater(lift[hit:hit+2].min(), 25)                   # the two hit frames flash
        self.assertLess(np.abs(np.delete(lift, range(hit-1, hit+3))).max(), 3)   # nothing else changes
        self.assertFalse(replace(base, impacts=False).impacts)          # off by default
        self.assertFalse(Timeline(1, str(self.music), settings.__dict__, [clip]).impacts)

    def test_beat_pulses_pick_drops_and_loud_downbeats(self):
        from montage_editor.rhythm import beat_pulses
        hop = .05
        energy = np.r_[np.full(200, .1), np.full(200, 1.0)]          # quiet 10 s, loud 10 s
        music = dict(downbeats=list(np.arange(0, 20, 2.0)), energy=list(energy), hop_seconds=hop,
                     phrases=[dict(time=10.0, kinds=['drop']), dict(time=4.0, kinds=['phrase'])])
        pulses = beat_pulses(music, 20)
        self.assertIn(10.0, pulses)                                     # the drop
        self.assertTrue(all(t >= 10 for t in pulses), pulses)           # only the loud section
        self.assertEqual(len(pulses), len(set(pulses)))
        self.assertLessEqual(len(beat_pulses(music, 20, limit=2)), 2)
        self.assertEqual(beat_pulses(dict(downbeats=[], energy=[1.0]), 20), [])

    def test_beat_fx_flash_and_split_only_on_the_pulse(self):
        settings = Settings(width=960, height=540, fps=30, quality='draft')   # 4 px split survives 4:2:0
        source = self.root/'bars.mp4'
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30,eq=saturation=0.5:brightness=-0.1', '-t', '5',
               '-c:v', 'libx264', '-pix_fmt', 'yuv444p', '-qp', '0', str(source))
        base = Timeline(1, str(self.music), settings.__dict__, [Clip(str(source), 0, 1.5, 1), Clip(str(source), 2, 1.5, 1)])
        fx = replace(base, pulses=[2.0])                                 # 0.5 s into shot 2
        render(base, self.root/'nofx.mp4'); render(fx, self.root/'fx.mp4')
        a, b = frames(self.root/'nofx.mp4', 960, 540, 'rgb24'), frames(self.root/'fx.mp4', 960, 540, 'rgb24')
        lift = b.mean(axis=(1, 2, 3))-a.mean(axis=(1, 2, 3))
        hit = 60
        self.assertGreater(lift[hit], 12)                                  # exposure pulse on the beat
        self.assertLess(lift[hit+12], lift[hit]/3)                         # and it decays
        self.assertLess(np.abs(lift[:hit-1]).max(), 1.5)                   # nothing before it
        def offset(frame, channel):
            # Horizontal displacement of a colour channel against green, from edge (gradient) alignment.
            edges = np.diff(frame[..., :], axis=1)
            errors = [np.abs(edges[:, 6+d:-6+d, channel]-edges[:, 6:-6, 1]).mean() for d in range(-4, 5)]
            return int(np.argmin(errors))-4
        self.assertEqual((offset(a[hit], 0), offset(a[hit], 2)), (0, 0))   # aligned without FX
        self.assertNotEqual(offset(b[hit], 0), 0)                          # red split on the hit frame ...
        self.assertNotEqual(offset(b[hit], 0), offset(b[hit], 2))         # ... so red and blue no longer align
        self.assertEqual(offset(b[hit+6], 0), 0)                           # and gone a few frames later
        with self.assertRaises(ValueError):
            replace(base, pulses=[99.0]).validate()

    def test_loudness_target_is_met(self):
        from montage_editor.benchmark import loudness
        settings = Settings(width=160, height=90, fps=30, quality='draft')
        music = self.root/'loud.wav'
        ffmpeg('-f', 'lavfi', '-i', 'anoisesrc=c=pink:a=0.05:d=8', str(music))
        base = Timeline(1, str(music), settings.__dict__, [Clip(str(self.root/'still.mp4'), 0, 3, 1)], normalize_audio=True)
        measured = {}
        for target in (-16.0, -14.0):
            render(replace(base, target_lufs=target), self.root/f'lufs{-target:g}.mp4')
            measured[target] = loudness(self.root/f'lufs{-target:g}.mp4')[0]
        self.assertAlmostEqual(measured[-16.0], -16, delta=1)
        self.assertAlmostEqual(measured[-14.0], -14, delta=1)
        with self.assertRaises(ValueError):
            replace(base, target_lufs=-3.0).validate()

    def test_one_edit_is_delivered_in_every_format(self):
        from montage_editor.pipeline import render_formats
        settings = Settings(width=640, height=360, fps=30, duration=2, quality='draft')
        clips = [Clip(str(self.root/'pan-right.mp4'), 0, 1.0, 1), Clip(str(self.root/'pan-left.mp4'), 1, 1.0, 1)]
        timeline = Timeline(1, str(self.music), settings.__dict__, clips, transition='cinematic',
                            boundary_transitions=['smoothleft'], faith_message='Keep the faith.', bookends=True)
        out = self.root/'delivery'/'edit.mp4'
        reports = render_formats(timeline, out, ['youtube-1080p60', 'shorts-1080x1920', 'instagram-1080x1350'])
        self.assertEqual([(r['width'], r['height']) for r in reports], [(1920, 1080), (1080, 1920), (1080, 1350)])
        self.assertTrue(all(r['full_decode'] and abs(r['duration']-2) < .05 for r in reports))
        for r in reports:
            saved = Timeline.load(Path(r['path']).with_suffix('.timeline.json'))
            self.assertEqual([(c.start, c.duration) for c in saved.clips], [(c.start, c.duration) for c in clips])
            self.assertEqual(saved.settings['fps'], 30)                  # timing kept, never re-cut at 60
        self.assertEqual(Timeline.load(out.with_name('edit-shorts-1080x1920.timeline.json')).reframe, 'follow')
        # Portrait output is cropped to the action, not letterboxed: no black bars top or bottom.
        portrait = frames(Path(reports[1]['path']), 1080, 1920)
        self.assertGreater(portrait[15][:80].mean(), 20)
        with self.assertRaises(FileExistsError):
            render_formats(timeline, out, ['shorts-1080x1920'])
        with self.assertRaises(ValueError):
            render_formats(timeline, out, ['8k-imax'])


if __name__ == '__main__':
    unittest.main()
