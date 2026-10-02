"""Cancellation and progress through the real pipeline."""
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

from montage_editor import jobs
from montage_editor.config import Settings
from montage_editor.pipeline import create_montage
from test_rhythm import write_song


class JobTests(unittest.TestCase):
    def test_cancel_stops_a_long_ffmpeg_run_promptly(self):
        cancel = threading.Event()
        threading.Timer(.4, cancel.set).start()
        began = time.monotonic()
        with jobs.job(cancel):
            with self.assertRaises(jobs.Cancelled):
                jobs.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=1280x720', '-t', '600',
                          '-f', 'null', '-'])
        self.assertLess(time.monotonic()-began, 5)
        with self.assertRaises(subprocess.CalledProcessError):
            jobs.run(['ffmpeg', '-v', 'error', '-i', '/nonexistent.mp4', '-f', 'null', '-'])
        self.assertEqual(jobs.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'anullsrc', '-t', '0.1',
                                   '-f', 's16le', 'pipe:1']).returncode, 0)

    def test_spans_nest(self):
        seen = []
        with jobs.job(progress=lambda f, m: seen.append(round(f, 3))):
            jobs.report(.5, 'a')
            with jobs.span(.5, 1):
                jobs.report(0, 'b')
                with jobs.span(.5, 1):
                    jobs.report(1, 'c')
        self.assertEqual(seen, [.5, .5, 1.0])

    def test_montage_reports_progress_and_cancel_leaves_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, song = root/'game.mp4', root/'song.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30', '-t', '20',
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True)
            write_song(song, seconds=20)
            settings = Settings(width=160, height=90, duration=8, quality='draft')
            seen = []
            with jobs.job(progress=lambda f, m: seen.append((f, m))):
                self.assertTrue(create_montage([video], song, root/'done.mp4', settings)['full_decode'])
            fractions = [f for f, _ in seen]
            self.assertEqual(fractions, sorted(fractions))
            self.assertGreaterEqual(fractions[-1], .97)
            self.assertTrue(any('Rendering shot' in m for _, m in seen))
            cancel = threading.Event()

            def progress(fraction, message):
                if fraction > .5:
                    cancel.set()
            output = root/'cancelled.mp4'
            with jobs.job(cancel, progress):
                with self.assertRaises(jobs.Cancelled):
                    create_montage([video], song, output, settings)
            self.assertEqual(sorted(p.name for p in root.iterdir() if p.name.startswith('cancelled')), [])


if __name__ == '__main__':
    unittest.main()
