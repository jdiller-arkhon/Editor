"""Draft preview -> final render of the same edit, presets, and manual shot editing."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from montage_editor.config import PRESETS, Settings, draft_of, preset
from montage_editor.pipeline import Clip, Timeline, create_montage, exchange_shots, render, retarget, swap_shots
from test_rhythm import write_song


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.video = self.root/'game.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30', '-t', '30',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(self.video)], check=True)

    def tearDown(self):
        self.directory.cleanup()

    def test_presets_and_drafts_keep_the_frame_rate(self):
        for name, (w, h, fps, quality) in PRESETS.items():
            final = preset(name, duration=12)
            draft = draft_of(final)
            self.assertEqual((final.width, final.height, final.fps, final.quality), (w, h, fps, quality))
            self.assertEqual(draft.fps, final.fps); self.assertEqual(draft.quality, 'draft')
            self.assertLessEqual(max(draft.width, draft.height), 640)
            self.assertAlmostEqual(draft.width/draft.height, w/h, delta=.02)

    def test_preview_then_final_renders_the_identical_edit(self):
        song, preview = self.root/'song.wav', self.root/'preview.mp4'
        write_song(song, seconds=20)
        final_settings = Settings(width=640, height=360, fps=30, duration=8, quality='high')
        report = create_montage([self.video], song, preview, draft_of(final_settings),
                                story=dict(edit_profile='cinematic', transition='cinematic', interpolation='blend'))
        self.assertEqual((report['width'], report['height']), (draft_of(final_settings).width, draft_of(final_settings).height))
        draft = Timeline.load(preview.with_suffix('.timeline.json'))
        self.assertEqual(draft.settings['quality'], 'draft')
        final = retarget(draft, final_settings, interpolation='motion')
        result = render(final, self.root/'final.mp4')
        self.assertTrue(result['full_decode'])
        self.assertEqual((result['width'], result['height']), (640, 360))
        self.assertEqual([(c.source, c.start, c.duration, c.speed_profile) for c in final.clips],
                         [(c.source, c.start, c.duration, c.speed_profile) for c in draft.clips])
        self.assertEqual(final.boundary_transitions, draft.boundary_transitions)
        with self.assertRaises(ValueError):
            retarget(draft, Settings(width=640, height=360, fps=24, duration=8))

    def test_exchange_and_swap_keep_timing_and_never_reuse_footage(self):
        settings = Settings(width=320, height=180, fps=30)
        timeline = Timeline(1, 'm', settings.__dict__, [Clip(str(self.video), 2, 2, .5), Clip(str(self.video), 10, 3, .7),
                                                       Clip(str(self.video), 20, 2, .6)])
        moved = exchange_shots(timeline, 0, 1)
        self.assertEqual([c.duration for c in moved.clips], [2, 3, 2])
        self.assertTrue(moved.clips[0].start <= 11.5 <= moved.clips[0].start+2)     # shot 2's moment now first
        self.assertTrue(moved.clips[1].start <= 3 <= moved.clips[1].start+3)
        crowded = Timeline(1, 'm', settings.__dict__, [Clip(str(self.video), 0, 4, .5), Clip(str(self.video), 10, 1.5, .7),
                                                      Clip(str(self.video), 12, 2, .6)])
        with self.assertRaisesRegex(ValueError, 'reuse footage'):
            exchange_shots(crowded, 0, 1)   # 4 s around 10.75 s would run into the third shot at 12 s
        edited, applied, rejected = swap_shots(timeline, [(2, dict(source=str(self.video), time=26.0, score=.9,
                                                                    source_duration=30.0))])
        self.assertEqual(rejected, []); self.assertTrue(edited.clips[2].start <= 26 <= edited.clips[2].start+2)
        song = self.root/'song.wav'
        write_song(song, seconds=10)
        from dataclasses import replace
        self.assertTrue(render(replace(edited, music=str(song)), self.root/'edited.mp4')['full_decode'])


if __name__ == '__main__':
    unittest.main()
