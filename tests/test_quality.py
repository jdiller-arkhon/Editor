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


class ShotMatchingTests(unittest.TestCase):
    def test_dark_and_tinted_shots_move_toward_the_rest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = {}
            for name, grade in (('a', 'eq=saturation=0.6'), ('b', 'eq=saturation=0.6'),
                                ('dark', 'eq=saturation=0.6:gamma=0.55'), ('blue', 'eq=saturation=0.6,colorbalance=bm=0.3:rm=-0.2')):
                path = root/f'{name}.mp4'
                ffmpeg('-f', 'lavfi', '-i', f'testsrc2=size=160x90:rate=30,{grade}', '-t', '4', '-c:v', 'libx264',
                       '-pix_fmt', 'yuv444p', '-qp', '0', str(path))
                sources[name] = path
            music = root/'music.wav'
            ffmpeg('-f', 'lavfi', '-i', 'sine=f=220', '-t', '10', str(music))
            settings = Settings(width=160, height=90, fps=30, quality='draft')
            clips = [Clip(str(sources[n]), 1, 2, 1) for n in ('a', 'dark', 'b', 'blue')]
            base = Timeline(1, str(music), settings.__dict__, clips)
            raw, matched = root/'raw.mp4', root/'matched.mp4'
            render(base, raw)
            report = render(replace(base, match_shots=True), matched)
            corrections = report['finishing']['shot_matching']
            self.assertGreater(corrections[1]['gamma'], 1.05)          # dark shot brightened
            self.assertGreater(corrections[3]['tint'][0], 0)            # blue shot: more red ...
            self.assertLess(corrections[3]['tint'][2], 0)               # ... and less blue

            def stats(path):
                raw_rgb = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-pix_fmt', 'rgb24', '-f', 'rawvideo',
                                          'pipe:1'], capture_output=True, check=True).stdout
                video = np.frombuffer(raw_rgb, np.uint8).reshape(-1, 90, 160, 3).astype(float)
                return [video[30+60*i].reshape(-1, 3).mean(axis=0) for i in range(4)]
            before, after = stats(raw), stats(matched)
            luma = lambda rgb: .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]
            reference = np.mean([luma(before[0]), luma(before[2])])
            self.assertLess(abs(luma(after[1])-reference), .6*abs(luma(before[1])-reference))
            cast = lambda rgb: rgb[2]-rgb[0]
            neutral = np.mean([cast(before[0]), cast(before[2])])
            self.assertLess(abs(cast(after[3])-neutral), abs(cast(before[3])-neutral))   # nudged, not flattened
            # Shots that already match are left essentially alone.
            self.assertLess(abs(luma(after[0])-luma(before[0])), 4)


class PacingTests(unittest.TestCase):
    def music(self, phrases):
        period, offset = 60/128, .3
        beats = [round(offset+i*period, 4) for i in range(80)]
        return dict(beats=beats, downbeats=beats[::4], energy=[.5]*int(36/.05), hop_seconds=.05, onsets=beats,
                    beat_confidence=1.0, tempo_bpm=128, phrases=phrases(beats[::4]))

    def plan(self, music, cinematic):
        from montage_editor.pipeline import direct
        candidates = [{'source': f's{k}', 'time': float(t), 'score': .5, 'source_duration': 300}
                      for k in range(3) for t in range(4, 290, 5)]
        timeline = direct(candidates, music, 'song', Settings(), 30, cinematic=cinematic)
        starts = np.cumsum([0]+[c.duration for c in timeline.clips[:-1]])
        return [(round(float(s), 3), round(c.duration, 3)) for s, c in zip(starts, timeline.clips)]

    def test_double_time_burst_follows_the_drop_bar_in_cinematic_mode_only(self):
        music = self.music(lambda d: [dict(time=d[4], bar=4, kinds=['grid', 'drop'])])
        drop, period = music['downbeats'][4], 60/128
        cinematic = self.plan(music, True)
        short = [(s, d) for s, d in cinematic if d < Settings().minimum_clip-1e-6]
        self.assertTrue(2 <= len(short) <= 4, cinematic)
        self.assertTrue(all(drop+4*period-.05 <= s and s+d <= drop+12*period+.05 for s, d in short))
        drop_shot = next(d for s, d in cinematic if abs(s-drop) < .05)
        self.assertGreaterEqual(drop_shot, 1.0)   # long enough for the impact ramp
        self.assertFalse([d for s, d in self.plan(music, False) if d < Settings().minimum_clip-1e-6])

    def test_steady_sections_vary_shot_length(self):
        lengths = [d for s, d in self.plan(self.music(lambda d: []), False)][:-1]
        self.assertGreater(len(set(lengths)), 1, lengths)
        self.assertFalse(any(a == b == c for a, b, c in zip(lengths, lengths[1:], lengths[2:])), lengths)
