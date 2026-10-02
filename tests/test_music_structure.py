"""Drops, builds, timbre downbeats, manual beat override and drop-aware choices (decoded audio)."""
import json
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from montage_editor.config import Settings
from montage_editor.music_sections import choose_section
from montage_editor.pipeline import Timeline, create_montage, direct, music_analysis, probe
from montage_editor.rhythm import boundary_styles

RATE, BPM, OFFSET = 22050, 128, .3
PERIOD = 60/BPM


def save(path, y):
    y = np.clip(y/np.abs(y).max()*.8, -1, 1)
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(RATE)
        handle.writeframes((y*32767).astype('<i2').tobytes())


def drop_song(path, seconds=40, hats_lift=4, build=(5, 8), drop=8, seed=1):
    """Clicks on every beat; hats get louder at bar ``hats_lift`` (no bass); bars build..drop-1
    ramp up; a sustained bass line and kick enter at bar ``drop``."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds*RATE))/RATE
    y = .02*np.sin(2*np.pi*330*t)
    n = 0
    while OFFSET+n*PERIOD < seconds-.3:
        at, bar = OFFSET+n*PERIOD, n//4
        i = int(at*RATE); hit = np.arange(int(.08*RATE))/RATE
        ramp = 1+(bar-build[0]+1)*.5 if build[0] <= bar < build[1] else 1
        level = (.5 if bar >= hats_lift else .25)*ramp
        y[i:i+len(hit)] += level*rng.normal(0, 1, len(hit))*np.exp(-hit*70)
        if bar >= drop and n % 2 == 0:
            kick = np.arange(int(.2*RATE))/RATE
            y[i:i+len(kick)] += .9*np.sin(2*np.pi*55*kick)*np.exp(-kick*12)
        n += 1
    start = OFFSET+drop*4*PERIOD
    bass = t >= start
    y[bass] += .45*np.sin(2*np.pi*50*t[bass])
    save(path, y)
    return start


def chord_song(path, seconds=30, change_phase=2):
    """Equal kicks on alternate beats (phases 0 and 2); sustained chords change only at
    ``change_phase`` of each bar, so accents alone cannot tell beat 1 from beat 3."""
    t = np.arange(int(seconds*RATE))/RATE
    y = np.zeros_like(t)
    chords = ((330, 415, 494), (294, 370, 440), (349, 440, 523), (392, 494, 587))
    bar = 4*PERIOD
    first = OFFSET+change_phase*PERIOD-bar
    k = 0
    while first+k*bar < seconds:
        a, b = int(max(0, first+k*bar)*RATE), int(min(seconds, first+(k+1)*bar)*RATE)
        span = t[a:b]
        for f in chords[k % 4]:
            y[a:b] += .1*np.sin(2*np.pi*f*span)
        k += 1
    n = 0
    while OFFSET+n*PERIOD < seconds-.3:
        i = int((OFFSET+n*PERIOD)*RATE)
        if n % 2 == 0:
            kick = np.arange(int(.15*RATE))/RATE
            y[i:i+len(kick)] += .8*np.sin(2*np.pi*60*kick)*np.exp(-kick*25)
        hat = np.arange(int(.03*RATE))/RATE
        y[i:i+len(hat)] += .3*np.sin(2*np.pi*3000*hat)*np.exp(-hat*120)
        n += 1
    save(path, y)


class StructureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_bass_entrance_is_a_drop_and_a_hat_lift_is_not(self):
        song = self.root/'drop.wav'
        start = drop_song(song)
        music = music_analysis(probe(song), 30)
        drops = [p for p in music['phrases'] if 'drop' in p['kinds']]
        self.assertEqual(len(drops), 1, music['phrases'])
        self.assertLess(abs(drops[0]['time']-start), .05)
        hats = OFFSET+4*4*PERIOD
        self.assertFalse(any('drop' in p['kinds'] and abs(p['time']-hats) < .1 for p in music['phrases']))
        builds = [p for p in music['phrases'] if 'build' in p['kinds']]
        self.assertTrue(builds and builds[0]['time'] < drops[0]['time'])
        self.assertGreater(drops[0]['time']-builds[0]['time'], 2*4*PERIOD-.05)

    def test_downbeats_found_from_chord_changes_alone(self):
        song = self.root/'chords.wav'
        chord_song(song)
        music = music_analysis(probe(song), 30)
        self.assertGreater(music['beat_confidence'], .5)
        phases = {round((t-OFFSET)/PERIOD) % 4 for t in music['downbeats']}
        self.assertEqual(phases, {2})   # where the chords change, not merely the first kick

    def test_manual_override_replaces_the_grid(self):
        song = self.root/'drop.wav'
        drop_song(song)
        music = music_analysis(probe(song), 20, start=2.0, override={'bpm': 100, 'first_downbeat': 3.5})
        self.assertEqual(music['cut_mode'], 'beats (manual grid)')
        self.assertEqual(music['tempo_bpm'], 100)
        self.assertTrue(np.allclose(np.diff(music['beats']), .6, atol=1e-3))
        self.assertIn(1.5, [round(t, 4) for t in music['downbeats']])   # 3.5 s song time = 1.5 s excerpt time
        for bad in (10, 400, 'fast'):
            with self.assertRaises(ValueError):
                music_analysis(probe(song), 10, override={'bpm': bad, 'first_downbeat': 0})
        video, output = self.root/'game.mp4', self.root/'manual.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30', '-t', '30',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True)
        report = create_montage([video], song, output, Settings(width=160, height=90, duration=8, quality='draft'),
                                story=dict(beat_override={'bpm': 100, 'first_downbeat': .2},
                                           edit_profile='cinematic', transition='cinematic'))
        self.assertEqual(report['music_alignment']['mode'], 'beats (manual grid)')
        self.assertEqual(report['music_alignment']['on_beat'], 1.0)
        timeline = Timeline.load(output.with_suffix('.timeline.json'))
        position = 0
        for clip in timeline.clips[:-1]:
            position += clip.duration
            self.assertLess(abs(((position-.2)/.6) - round((position-.2)/.6))*.6, .5/30+1e-6)
        self.assertIsInstance(timeline.boundary_transitions, list)

    def test_excerpt_prefers_a_build_and_drop(self):
        energy = np.ones(int(120/.05))
        self.assertEqual(choose_section(energy, 120, 30, starts=[0, 20, 40, 60, 80], drops=None), 0)
        start = choose_section(energy, 120, 30, starts=[0, 20, 40, 60, 80], drops=[70.0])
        self.assertTrue(start+.15*30 <= 70 <= start+.75*30, start)

    def test_strongest_moment_lands_on_the_drop_and_the_build_punches(self):
        beats = [round(OFFSET+i*PERIOD, 4) for i in range(70)]
        downbeats = beats[::4]
        music = dict(beats=beats, downbeats=downbeats, energy=[.5]*int(32/.05), hop_seconds=.05,
                     onsets=beats, beat_confidence=1.0, tempo_bpm=BPM,
                     phrases=[dict(time=downbeats[4], bar=4, kinds=['grid', 'build']),
                              dict(time=downbeats[8], bar=8, kinds=['grid', 'drop'])])
        candidates = [{'source': 's', 'time': float(t), 'score': .6, 'source_duration': 200} for t in range(4, 190, 6)]
        for c in candidates[8:30]:
            c['score'] = .65
        candidates[3]['score'] = 1.0
        timeline = direct(candidates, music, 'song', Settings(), 30, cinematic=True)
        starts = np.cumsum([0]+[c.duration for c in timeline.clips[:-1]])
        at_drop = [c for s, c in zip(starts, timeline.clips) if abs(s-downbeats[8]) <= 1/60]
        self.assertEqual(len(at_drop), 1)
        self.assertEqual(at_drop[0].score, 1.0)
        build = [c for s, c in zip(starts, timeline.clips) if downbeats[4]-1e-6 <= s < downbeats[8]-1e-6]
        self.assertTrue(build and all(len(c.accents) >= 2 for c in build if c.speed_profile == 'normal'))
        self.assertEqual(boundary_styles(timeline, music)[[round(s, 3) for s in starts[1:]].index(
            min((round(s, 3) for s in starts[1:]), key=lambda s: abs(s-downbeats[8])))], 'zoomin')


if __name__ == '__main__':
    unittest.main()
