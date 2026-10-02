import json
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from montage_editor.config import Settings
from montage_editor.pipeline import Timeline, create_montage, direct, music_analysis, probe
from montage_editor.rhythm import alignment_report, plan_cuts


def write_song(path, bpm=128, offset=.3, seconds=40, lift_bar=8, rate=22050, noise=False, seed=0):
    """Kick on each downbeat, snare-like noise on other beats, off-beat hats, a pad.

    Everything doubles in level (plus a tonal layer) from ``lift_bar`` onwards, so the
    ground-truth tempo, beat times, downbeat phase and energy lift are all known.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds*rate))/rate
    if noise:
        y = rng.normal(0, .2, len(t))
    else:
        y = .05*np.sin(2*np.pi*220*t)
        beat, n = 60/bpm, 0
        while offset+n*beat < seconds-.3:
            at = offset+n*beat
            i = int(at*rate)
            hit = np.arange(int(.15*rate))/rate
            loud = n//4 >= lift_bar
            gain = 1 if loud else .45
            if n % 4 == 0:
                y[i:i+len(hit)] += gain*np.sin(2*np.pi*60*hit)*np.exp(-hit*25)
            else:
                y[i:i+len(hit)] += gain*.5*rng.normal(0, 1, len(hit))*np.exp(-hit*60)
            if loud:
                y[i:i+len(hit)] += .2*np.sin(2*np.pi*440*hit)
            j = int((at+beat/2)*rate)
            y[j:j+int(.03*rate)] += gain*.15*rng.normal(0, 1, int(.03*rate))
            n += 1
    y = np.clip(y/np.abs(y).max()*.8, -1, 1)
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((y*32767).astype('<i2').tobytes())


def grid_error(times, bpm, offset):
    period = 60/bpm
    times = np.asarray(times)
    return np.abs(times-(offset+np.round((times-offset)/period)*period))


class MeasuredGridTests(unittest.TestCase):
    def test_decoded_track_tempo_beats_downbeats_and_lift(self):
        with tempfile.TemporaryDirectory() as directory:
            for bpm, offset in ((128, .3), (90, .12), (150, .3)):
                song = Path(directory)/f'{bpm}.wav'
                write_song(song, bpm=bpm, offset=offset)
                music = music_analysis(probe(song), 30)
                self.assertEqual(music['cut_mode'], 'beats')
                self.assertGreater(music['beat_confidence'], .8)
                self.assertAlmostEqual(music['tempo_bpm'], bpm, delta=.5)
                # Under one 30 fps frame; measured from actual FFmpeg-decoded audio.
                self.assertLess(grid_error(music['beats'], bpm, offset).max(), .02)
                period = 60/bpm
                phases = {round((t-offset)/period) % 4 for t in music['downbeats']}
                self.assertEqual(phases, {0})
                lift = offset+8*4*period
                if lift < 30:
                    rises = [p['time'] for p in music['phrases'] if 'rise' in p['kinds']]
                    self.assertTrue(any(abs(t-lift) < .03 for t in rises), (bpm, rises))
                # One mark per lift, not one per following bar.
                bars = [p['bar'] for p in music['phrases'] if 'rise' in p['kinds']]
                self.assertFalse(any(b+1 in bars for b in bars))

    def test_unpulsed_audio_keeps_attack_pacing(self):
        with tempfile.TemporaryDirectory() as directory:
            song = Path(directory)/'noise.wav'
            write_song(song, noise=True)
            music = music_analysis(probe(song), 20)
            self.assertLess(music['beat_confidence'], .5)
            self.assertEqual(music['cut_mode'], 'attacks')
            candidates = [{'source': 'a', 'time': t, 'score': .5, 'source_duration': 60}
                          for t in range(3, 57, 5)]
            timeline = direct(candidates, music, str(song), Settings(), 20)
            # Attack pacing: every interior cut sits on a detected attack or the maximum length.
            position = 0
            for clip in timeline.clips[:-1]:
                position += clip.duration
                self.assertTrue(any(abs(position-t) <= 1/60 for t in music['onsets']) or
                                abs(clip.duration-Settings().maximum_clip) < 1e-6)


class BeatDirectorTests(unittest.TestCase):
    def music(self):
        period, offset = 60/128, .3
        beats = [round(offset+i*period, 4) for i in range(70)]
        energy = [.1 if i*.05 < 15.3 else .6 for i in range(int(32/.05))]
        downbeats = beats[::4]
        return dict(beats=beats, downbeats=downbeats, energy=energy, hop_seconds=.05,
                    onsets=beats, beat_confidence=1.0, tempo_bpm=128,
                    phrases=[dict(time=downbeats[4], bar=4, kinds=['grid']),
                             dict(time=downbeats[8], bar=8, kinds=['grid', 'rise']),
                             dict(time=downbeats[12], bar=12, kinds=['grid'])])

    def test_cuts_on_beats_hit_phrases_and_follow_energy(self):
        music, settings = self.music(), Settings()
        candidates = [{'source': f's{k}', 'time': float(t), 'score': s, 'source_duration': 60}
                      for k in range(3) for t, s in zip(range(3, 57, 6), np.linspace(.2, 1, 9))]
        timeline = direct(candidates, music, 'song', settings, 30, cinematic=True)
        self.assertAlmostEqual(sum(c.duration for c in timeline.clips), 30, places=6)
        cuts, position = [], 0
        for clip in timeline.clips:
            self.assertAlmostEqual(clip.duration*settings.fps, round(clip.duration*settings.fps))
            self.assertGreaterEqual(clip.duration, settings.minimum_clip-1e-6)
            self.assertLessEqual(clip.duration, settings.maximum_clip+1e-6)
            position += clip.duration
            cuts.append(position)
        for cut in cuts[:-1]:
            self.assertLessEqual(min(abs(cut-b) for b in music['beats']), .5/settings.fps+1e-9)
        for phrase in music['phrases']:
            self.assertTrue(any(abs(phrase['time']-c) <= .5/settings.fps for c in cuts))
        report = alignment_report(timeline, music)
        self.assertEqual(report['mode'], 'beats')
        self.assertEqual(report['on_beat'], 1.0)
        self.assertEqual(report['phrase_boundaries_cut'], '3/3')
        starts = np.cumsum([0]+[c.duration for c in timeline.clips[:-1]])
        quiet = [c.duration for s, c in zip(starts, timeline.clips) if s < 15]
        loud = [c.duration for s, c in zip(starts, timeline.clips) if 15.5 < s < 27]
        self.assertGreater(np.mean(quiet), np.mean(loud)+.8)
        # The impact ramp lands on the measured lift, not on a fixed shot count.
        lift = music['phrases'][1]['time']
        impacts = [s for s, c in zip(starts, timeline.clips) if c.speed_profile == 'ramp']
        self.assertTrue(any(abs(s-lift) <= .5/settings.fps for s in impacts))
        for a, b in zip(timeline.clips, timeline.clips[1:]):
            self.assertFalse(a.speed_profile == b.speed_profile == 'ramp')
        anchored = [c for c in timeline.clips if c.anchor_output is not None]
        self.assertTrue(anchored)
        for clip, start in zip(timeline.clips, starts):
            if clip.anchor_output is not None:
                self.assertLess(min(abs(start+clip.anchor_output-b) for b in music['beats']), 1e-6)

    def test_strongest_moments_land_on_the_loudest_music(self):
        music, settings = self.music(), Settings()
        candidates = [{'source': 's', 'time': float(t), 'score': .3, 'source_duration': 200}
                      for t in range(4, 190, 6)]
        for c in candidates[10:24]:
            c['score'] = .95           # plenty of strong clips that match loud music closely
        candidates[5]['score'] = 1.0   # the one great moment
        timeline = direct(candidates, music, 'song', settings, 30, cinematic=True)
        starts = np.cumsum([0]+[c.duration for c in timeline.clips[:-1]])
        hero = [(s, c) for s, c in zip(starts, timeline.clips) if c.start <= 34 <= c.start+c.duration]
        self.assertEqual(len(hero), 1)
        self.assertGreater(hero[0][0], 15.2)   # placed after the measured lift, in the loud half
        self.assertAlmostEqual(hero[0][1].score, 1.0)

    def test_infeasible_bounds_fall_back_without_inventing_beats(self):
        music = self.music()
        music['beats'] = music['beats'][:3]
        self.assertEqual(plan_cuts(music, Settings(), 30), [])
        candidates = [{'source': 'a', 'time': t, 'score': .5, 'source_duration': 60} for t in (5, 20, 40)]
        timeline = direct(candidates, music, 'song', Settings(), 30)
        self.assertTrue(music['cut_mode'].startswith('attacks'))
        self.assertAlmostEqual(sum(c.duration for c in timeline.clips), 30, places=6)


class BeatRenderTests(unittest.TestCase):
    def test_excerpt_starts_on_phrase_and_render_cuts_on_beats(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, song, output = root/'game.mp4', root/'song.wav', root/'montage.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30',
                            '-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=8000', '-t', '40',
                            '-c:v', 'libx264', '-threads', '2', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                            str(video)], check=True)
            write_song(song, bpm=128, offset=.3, seconds=40, lift_bar=12)
            settings = Settings(width=160, height=90, fps=30, duration=10, quality='draft')
            report = create_montage([video], song, output, settings,
                                    story=dict(auto_music_section=True, edit_profile='cinematic',
                                               transition='cinematic', transition_duration=.4))
            self.assertTrue(report['full_decode'])
            self.assertAlmostEqual(report['duration'], 10, delta=.1)
            # The excerpt begins on a measured downbeat of the full song.
            self.assertLess(grid_error([report['music_start']], 128/4, .3)[0], .02)
            alignment = report['music_alignment']
            self.assertEqual(alignment['mode'], 'beats')
            self.assertEqual(alignment['on_beat'], 1.0)
            timeline = Timeline.load(output.with_suffix('.timeline.json'))
            position = timeline.music_start
            for clip in timeline.clips[:-1]:
                position += clip.duration
                self.assertLess(grid_error([position], 128, .3)[0], .5/30+.02)
            # Hard cuts on ordinary beats; blends only on phrase marks of the excerpt.
            effects = [b['effect'] for b in report['transition_boundaries']]
            self.assertEqual(effects, timeline.boundary_transitions)
            self.assertIn('cut', effects)
            analysis = json.loads(output.with_suffix('.analysis.json').read_text())
            marks = [p['time'] for p in analysis['music']['phrases']]
            position = 0
            for clip, effect in zip(timeline.clips, effects):
                position += clip.duration
                if effect != 'cut':
                    self.assertTrue(any(abs(position-t) <= .5/30+1e-6 for t in marks))
            starts = np.cumsum([0]+[c.duration for c in timeline.clips[:-1]])
            accents = [(c, start+a) for c, start in zip(timeline.clips, starts) for a in c.accents]
            self.assertTrue(accents)
            self.assertIn('ramp', report['edit_effects'])
            self.assertIn('beat_punch', report['edit_effects'])
            self.assertTrue(any(e != 'cut' for e in effects))
            for clip, at in accents:
                self.assertEqual(clip.speed_profile, 'normal')
                self.assertLess(min(abs(at-d) for d in analysis['music']['beats']), .5/30+1e-6)
            self.assertEqual(analysis['music']['source_start'], report['music_start'])
            self.assertAlmostEqual(analysis['music']['tempo_bpm'], 128, delta=.5)


if __name__ == '__main__':
    unittest.main()
