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


if __name__ == '__main__':
    unittest.main()
