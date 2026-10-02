"""Rendered checks for interpolation, colour looks, motion blur, follow reframing and swishes."""
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from montage_editor.config import Settings
from montage_editor.pipeline import Clip, Timeline, render


def ffmpeg(*args):
    subprocess.run(['ffmpeg', '-v', 'error', *args], check=True)


def frames(path, w, h, fmt='gray'):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-pix_fmt', fmt, '-f', 'rawvideo', 'pipe:1'],
                         capture_output=True, check=True).stdout
    channels = 3 if fmt == 'rgb24' else 1
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, channels).astype(float)


class FinishingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.music = self.root/'music.wav'
        ffmpeg('-f', 'lavfi', '-i', 'sine=f=220:sample_rate=48000', '-t', '8', str(self.music))

    def tearDown(self):
        self.directory.cleanup()

    def test_motion_interpolation_replaces_held_frames_in_slow_motion(self):
        source = self.root/'fifteen.mp4'
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=15', '-t', '6', '-c:v', 'libx264',
               '-pix_fmt', 'yuv420p', str(source))
        settings = Settings(width=320, height=180, fps=30, quality='draft')
        base = Timeline(1, str(self.music), settings.__dict__, [Clip(str(source), 0, 4, 0, 'ramp')])
        held = {}
        for mode in ('none', 'motion'):
            report = render(replace(base, interpolation=mode), self.root/f'{mode}.mp4')
            self.assertTrue(report['full_decode'])
            self.assertAlmostEqual(report['duration'], 4, delta=.05)
            video = frames(self.root/f'{mode}.mp4', 320, 180)
            middle = video[40:80]   # the slow (0.5x) middle of the cosine ramp
            held[mode] = int((np.abs(np.diff(middle, axis=0)).mean(axis=(1, 2, 3)) < .5).sum())
        self.assertGreater(held['none'], 10)
        self.assertLess(held['motion'], held['none']/3, held)

    def test_looks_change_colour_and_blur_softens_ramps(self):
        source = self.root/'bars.mp4'
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30,eq=saturation=0.4', '-t', '4',
               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(source))   # muted colours leave headroom
        settings = Settings(width=320, height=180, fps=30, quality='draft')
        base = Timeline(1, str(self.music), settings.__dict__, [Clip(str(source), 0, 3, 0, 'ramp')])
        saturation, sharpness = {}, {}
        for name, timeline in (('none', base), ('punchy', replace(base, look='punchy')),
                               ('mono', replace(base, look='mono')), ('blur', replace(base, motion_blur=True))):
            render(timeline, self.root/f'{name}.mp4')
            rgb = frames(self.root/f'{name}.mp4', 320, 180, 'rgb24')[20:70]
            saturation[name] = float((rgb.max(axis=3)-rgb.min(axis=3)).mean())
            gray = rgb.mean(axis=3)
            sharpness[name] = float(np.abs(np.diff(gray, axis=2)).mean())
        self.assertGreater(saturation['punchy'], saturation['none']*1.1)
        self.assertLess(saturation['mono'], 3)
        self.assertLess(sharpness['blur'], sharpness['none']*.97)
        with self.assertRaises(ValueError):
            replace(base, look='neon').validate()

    def test_vertical_follow_crop_keeps_off_centre_action_in_frame(self):
        source = self.root/'mover.mp4'
        # A bright square sweeps from the left edge to the right edge over a mid-grey world.
        ffmpeg('-f', 'lavfi', '-i', 'color=c=0x606060:s=640x360:r=30', '-f', 'lavfi', '-i',
               'color=c=white:s=60x60:r=30', '-t', '4', '-filter_complex',
               "[0][1]overlay=x='40+120*t':y=150:shortest=1", '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
               str(source))
        settings = Settings(width=180, height=320, fps=30, quality='draft')
        base = Timeline(1, str(self.music), settings.__dict__, [Clip(str(source), 0, 4, 0)])
        report = render(replace(base, reframe='follow'), self.root/'follow.mp4')
        self.assertEqual(report['finishing']['reframe'], 'follow')
        follow = frames(self.root/'follow.mp4', 180, 320)
        self.assertGreater(follow[:, 0, :, 0].mean(), 60)            # no letterbox bars: frame filled
        visible = [(f > 200).mean() > .01 for f in follow[8::10]]
        self.assertGreater(np.mean(visible), .8)
        render(base, self.root/'fit.mp4')
        fit = frames(self.root/'fit.mp4', 180, 320)
        self.assertLess(fit[:, 0, :, 0].mean(), 20)                  # fit letterboxes portrait output

    def test_swish_plays_on_directional_blends_only_when_enabled(self):
        clips = []
        for name in ('red', 'blue', 'lime'):
            path = self.root/f'{name}.mp4'
            ffmpeg('-f', 'lavfi', '-i', f'color=c={name}:s=160x90:r=24', '-t', '2', '-c:v', 'libx264',
                   '-pix_fmt', 'yuv420p', str(path))
            clips.append(Clip(str(path), 0, 2, 1))
        quiet = self.root/'quiet.wav'
        ffmpeg('-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=mono', '-t', '6', str(quiet))
        settings = Settings(width=160, height=90, fps=24, quality='draft')
        base = Timeline(1, str(quiet), settings.__dict__, clips, transition='cinematic', transition_duration=.5,
                        boundary_transitions=['smoothleft', 'cut'])
        energy = {}
        for mode in ('none', 'swish'):
            report = render(replace(base, sfx=mode), self.root/f'{mode}.mp4')
            self.assertTrue(report['full_decode'])
            raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(self.root/f'{mode}.mp4'), '-ac', '1', '-ar',
                                  '48000', '-f', 'f32le', 'pipe:1'], capture_output=True, check=True).stdout
            audio = np.frombuffer(raw, '<f4')
            energy[mode] = (float(np.abs(audio[int(1.8*48000):int(2.3*48000)]).mean()),
                            float(np.abs(audio[int(3.8*48000):int(4.3*48000)]).mean()))
        self.assertEqual(report['finishing']['sfx_count'], 1)
        self.assertGreater(energy['swish'][0], energy['none'][0]+.002)   # swish on the push at 2 s
        self.assertLess(energy['swish'][1], .002)                         # nothing on the hard cut at 4 s


if __name__ == '__main__':
    unittest.main()
