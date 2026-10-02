"""Montage-quality refinements measured on rendered output."""
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


def gray_frames(path, w, h):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-pix_fmt', 'gray', '-f', 'rawvideo', 'pipe:1'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(float)


class HandleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.clock = self.root/'clock.mp4'
        # Luma rises 60 levels per second, so a frozen frame and real footage differ visibly.
        ffmpeg('-f', 'lavfi', '-i', "nullsrc=s=160x90:r=30,geq=lum='clip(20+T*60,0,255)':cb=128:cr=128",
               '-t', '4', '-c:v', 'libx264', '-qp', '0', '-pix_fmt', 'yuv444p', str(self.clock))
        self.gray = self.root/'gray.mp4'
        ffmpeg('-f', 'lavfi', '-i', 'color=c=0x808080:s=160x90:r=30', '-t', '4', '-c:v', 'libx264', '-qp', '0',
               '-pix_fmt', 'yuv444p', str(self.gray))
        self.music = self.root/'music.wav'
        ffmpeg('-f', 'lavfi', '-i', 'sine=f=220', '-t', '6', str(self.music))

    def tearDown(self):
        self.directory.cleanup()

    def test_blends_show_real_footage_past_the_cut(self):
        settings = Settings(width=160, height=90, fps=30, quality='draft')
        shots = [Clip(str(self.clock), .5, 1.5, 1), Clip(str(self.gray), 1, 1.5, 1)]
        base = Timeline(1, str(self.music), settings.__dict__, shots+[Clip(str(self.gray), 3, .5, 1)],
                        transition='cinematic', transition_duration=.6, boundary_transitions=['fade', 'cut'])
        # Identical first two shots; here a third shot uses the footage right after shot 1,
        # so the outgoing handle is forbidden and the edge frame must be held instead.
        blocked = replace(base, clips=shots+[Clip(str(self.clock), 2.0, .5, 1)])
        report, held = render(base, self.root/'handles.mp4'), render(blocked, self.root/'held.mp4')
        self.assertEqual(report['transition_boundaries'][0]['handles'], 'source footage')
        self.assertEqual(held['transition_boundaries'][0]['handles'], 'mixed source/held')
        self.assertAlmostEqual(report['duration'], 3.5, delta=.05)
        real, frozen = gray_frames(self.root/'handles.mp4', 160, 90), gray_frames(self.root/'held.mp4', 160, 90)
        cut = 45   # frame index of the cut (1.5 s at 30 fps)
        self.assertLess(np.abs(real[:cut-10]-frozen[:cut-10]).mean(), .5)   # identical before the blend
        # Dissolve weights match, so the difference after the cut is the outgoing shot alone:
        # real footage keeps brightening (+2 levels/frame), a held frame stays put.
        gap = (real[cut+1:cut+8]-frozen[cut+1:cut+8]).mean(axis=(1, 2))
        self.assertTrue(np.all(gap > .3), gap)
        self.assertGreater(gap[-1], gap[0])

    def test_handles_never_show_footage_used_by_another_shot(self):
        settings = Settings(width=160, height=90, fps=30, quality='draft')
        # Shot 2 starts exactly where shot 1 ends in the same source: the post-handle would repeat it.
        timeline = Timeline(1, str(self.music), settings.__dict__, [Clip(str(self.clock), .5, 1.5, 1), Clip(str(self.clock), 2.0, 1.5, 1)],
                            transition='dissolve', transition_duration=.6)
        report = render(timeline, self.root/'adjacent.mp4')
        self.assertEqual(report['transition_boundaries'][0]['handles'], 'held edge frames')


if __name__ == '__main__':
    unittest.main()


def mono(path, rate=48000):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-vn', '-ac', '1', '-ar', str(rate), '-f', 'f32le',
                          'pipe:1'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, '<f4')


def band(samples, freq, rate=48000):
    spectrum = np.abs(np.fft.rfft(samples*np.hanning(len(samples))))
    bin_ = int(round(freq*len(samples)/rate))
    return float(spectrum[bin_-2:bin_+3].max())


class AudioPolishTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.game = self.root/'game.mp4'
        # Loud 1 kHz "gameplay" tone so a mid-cycle splice would click.
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30', '-f', 'lavfi', '-i', 'sine=f=1000:sample_rate=48000',
               '-t', '10', '-af', 'volume=0.8', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'pcm_s16le',
               '-f', 'matroska', str(self.game.with_suffix('.mkv')))
        self.game = self.game.with_suffix('.mkv')
        self.music = self.root/'music.wav'
        ffmpeg('-f', 'lavfi', '-i', 'sine=f=220:sample_rate=48000', '-t', '8', '-af', 'volume=0.3', str(self.music))

    def tearDown(self):
        self.directory.cleanup()

    def test_hard_cuts_do_not_click(self):
        settings = Settings(width=160, height=90, fps=30, quality='draft')
        quiet, peak = self.root/'quiet.mkv', self.root/'peak.mkv'
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30', '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=mono',
               '-t', '4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'pcm_s16le', str(quiet))
        # A 50 Hz tone that starts at its positive peak: cutting into it from silence is a step.
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30', '-f', 'lavfi', '-i',
               "aevalsrc='0.8*cos(2*PI*50*t)':s=48000", '-t', '4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
               '-c:a', 'pcm_s16le', str(peak))
        timeline = Timeline(1, str(self.music), settings.__dict__, [Clip(str(quiet), 0, 2, 1), Clip(str(peak), 0, 2, 1)],
                            gameplay_gain=1, music_gain=0)
        render(timeline, self.root/'cuts.mp4')
        audio = mono(self.root/'cuts.mp4')
        around = np.abs(np.diff(audio[96000-960:96000+960])).max()
        steady = np.abs(np.diff(audio[120000:140000])).max()   # the tone's own slope
        self.assertGreater(np.abs(audio[96000+960:96000+2400]).max(), .5)   # the tone really is there
        self.assertLess(around, max(steady*3, .02))

    def test_highlight_sound_punches_through_the_music(self):
        settings = Settings(width=160, height=90, fps=30, quality='draft')
        clips = [Clip(str(self.game), 0, 2, .2), Clip(str(self.game), 4, 2, 1.0, anchor_source=5.0, anchor_output=1.0),
                 Clip(str(self.game), 7, 2, .2)]
        base = Timeline(1, str(self.music), settings.__dict__, clips, gameplay_gain=.25, music_gain=.8)
        flat, punched = self.root/'flat.mp4', self.root/'punched.mp4'
        render(base, flat)
        render(replace(base, punch_through=True), punched)
        a, b = mono(flat), mono(punched)
        at, calm = slice(int(2.9*48000), int(3.1*48000)), slice(int(.9*48000), int(1.1*48000))
        self.assertGreater(band(b[at], 1000), band(a[at], 1000)*2.5)    # gameplay swells at the moment
        self.assertLess(band(b[at], 220), band(a[at], 220)*.8)          # music dips under it
        self.assertAlmostEqual(band(b[calm], 1000)/band(a[calm], 1000), 1, delta=.1)   # elsewhere unchanged
