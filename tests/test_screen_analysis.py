"""HUD-absence exclusion and audio transients on generated footage with known ground truth."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from montage_editor.config import Settings
from montage_editor.pipeline import Timeline, analyze_gameplay, create_montage, probe
from montage_editor.screen_analysis import hud_factor, low_spans
from test_rhythm import write_song

# Moving world + a persistent HUD (bars, boxes, counters). From 12 s to 15 s the HUD is
# hidden and a scoreboard panel is drawn, as in a death screen.
HUD = ("drawbox=x=40:y=300:w=220:h=14:color=0x30d040@1:t=fill:enable='not(between(t,12,15))',"
       "drawbox=x=420:y=286:w=34:h=34:color=0xf0f0f0@1:t=3:enable='not(between(t,12,15))',"
       "drawbox=x=500:y=290:w=90:h=24:color=0xe0c020@1:t=fill:enable='not(between(t,12,15))',"
       "drawbox=x=20:y=20:w=60:h=40:color=0xffffff@1:t=2:enable='not(between(t,12,15))',"
       "drawbox=x=120:y=60:w=400:h=160:color=0x101018@0.85:t=fill:enable='between(t,12,15)',"
       "drawgrid=x=120:y=60:w=40:h=20:t=1:c=0xc0c0ff@0.9:enable='between(t,12,15)'")


def make_game(path, seconds=30, hud=True, burst=None):
    world = 'testsrc2=size=640x360:rate=30,scroll=horizontal=0.004:vertical=0.003'
    video = f'{world},{HUD}' if hud else world
    audio = 'anoisesrc=color=pink:amplitude=0.02:sample_rate=48000'
    if burst is not None:
        audio = (f"aevalsrc='0.02*(random(0)-0.5)+if(between(t,{burst},{burst}+0.12),"
                 f"0.9*(random(1)-0.5)*exp(-(t-{burst})*30),0)':s=48000")
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', video, '-f', 'lavfi', '-i', audio,
                    '-t', str(seconds), '-c:v', 'libx264', '-g', '30', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', str(path)], check=True)


class ScreenTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_hud_absent_span_is_found_and_never_used(self):
        game = self.root/'game.mp4'
        make_game(game)
        report = {}
        candidates = analyze_gameplay(probe(game), Settings(), report)
        spans = report[str(game.resolve())]['excluded_spans']
        self.assertEqual(len(spans), 1, spans)
        a, b = spans[0]
        # Covers the core of the 12-15 s death screen and stays inside it (plus 0.5 s padding).
        self.assertTrue(11.4 <= a <= 13.0 and 14.5 <= b <= 15.6, spans)
        usable = [c for c in candidates if not c.get('exclude')]
        self.assertTrue(usable)
        self.assertFalse(any(a <= c['time'] <= b for c in usable))
        song, output = self.root/'song.wav', self.root/'montage.mp4'
        write_song(song, seconds=24)
        create_montage([game], song, output, Settings(width=320, height=180, duration=12, quality='draft',
                                                      minimum_clip=1.5, maximum_clip=2.5))
        timeline = Timeline.load(output.with_suffix('.timeline.json'))
        for clip in timeline.clips:
            self.assertTrue(clip.start+clip.duration <= a+1e-6 or clip.start >= b-1e-6, (clip, spans))
        analysis = json.loads(output.with_suffix('.analysis.json').read_text())
        self.assertEqual(analysis['screen_analysis'][str(game.resolve())]['excluded_spans'], spans)

    def test_footage_without_a_hud_is_not_excluded(self):
        game = self.root/'plain.mp4'
        make_game(game, seconds=20, hud=False)
        report = {}
        candidates = analyze_gameplay(probe(game), Settings(), report)
        self.assertFalse(any(c.get('exclude') for c in candidates))
        self.assertEqual(report[str(game.resolve())]['excluded_spans'], [])

    def test_gunshot_transient_raises_the_score_there(self):
        quiet, loud = self.root/'quiet.mp4', self.root/'loud.mp4'
        make_game(quiet, seconds=20, hud=False, burst=None)
        make_game(loud, seconds=20, hud=False, burst=13.0)
        settings = Settings()
        near = lambda cs: max((c['score'] for c in cs if abs(c['time']-13) <= .5), default=0)
        best = lambda cs: max(cs, key=lambda c: c['score'])['time']
        self.assertGreater(near(analyze_gameplay(probe(loud), settings)),
                           near(analyze_gameplay(probe(quiet), settings))+.1)
        self.assertLess(abs(best(analyze_gameplay(probe(loud), settings))-13), .5)

    def test_thresholds_and_spans(self):
        self.assertEqual(hud_factor(.2), 0); self.assertEqual(hud_factor(.9), 1)
        self.assertAlmostEqual(hud_factor(.475), .5)
        self.assertEqual(low_spans([0, .25, .5, .75, 1, 3], [1, .1, .2, 1, 1, .1]), [[.25, .5], [3, 3]])


if __name__ == '__main__':
    unittest.main()
