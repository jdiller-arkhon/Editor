"""Cancellation and progress through the real pipeline."""
import os
import subprocess
import tempfile
import threading
import time
import unittest
import unittest.mock
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
        # A launcher that starts the real ffmpeg as a child (like Chocolatey/Scoop shims) must
        # not leave that child running after cancel.
        import sys
        marker = Path(tempfile.mkdtemp())/'child.pid'
        launcher = ("import subprocess,sys;p=subprocess.Popen(['ffmpeg','-v','error','-f','lavfi','-i',"
                    "'testsrc2=size=1280x720','-t','600','-f','null','-']);open(sys.argv[1],'w').write(str(p.pid));p.wait()")
        cancel = threading.Event()
        threading.Timer(1.5, cancel.set).start()
        began = time.monotonic()
        with jobs.job(cancel):
            with self.assertRaises(jobs.Cancelled):
                jobs.run([sys.executable, '-c', launcher, str(marker)])
        self.assertLess(time.monotonic()-began, 6)
        time.sleep(.5)
        child = int(marker.read_text())
        if sys.platform == 'win32':
            alive = str(child) in subprocess.run(['tasklist', '/FI', f'PID eq {child}'], capture_output=True,
                                                 text=True).stdout
        else:
            try:
                os.kill(child, 0); alive = Path(f'/proc/{child}').exists() and \
                    'Z' not in Path(f'/proc/{child}/stat').read_text().split()[2]
            except OSError:
                alive = False
        self.assertFalse(alive, 'ffmpeg child of the launcher survived cancel')
        with self.assertRaises(subprocess.CalledProcessError):
            jobs.run(['ffmpeg', '-v', 'error', '-i', '/nonexistent.mp4', '-f', 'null', '-'])
        self.assertEqual(jobs.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'anullsrc', '-t', '0.1',
                                   '-f', 's16le', 'pipe:1']).returncode, 0)

    def test_parallel_keeps_order_runs_concurrently_and_cancels_every_worker(self):
        import sys
        sleep = [sys.executable, '-c', 'import time; time.sleep(1)']
        began = time.monotonic()
        seen = []
        with jobs.job(progress=lambda f, m: seen.append((round(f, 2), m))):
            results = jobs.parallel(lambda n: (jobs.run(sleep), n*n)[1], range(4), 'step {done}/{total}', count=4)
        self.assertEqual(results, [0, 1, 4, 9])
        # ~1 s of real time per job x 4 jobs: concurrent, not sequential.
        self.assertGreater(time.monotonic()-began, .9)          # each job really takes ~1 s
        self.assertLess(time.monotonic()-began, 2.5)
        self.assertEqual(seen[-1], (1.0, 'step 4/4'))
        with self.assertRaises(ZeroDivisionError):
            jobs.parallel(lambda n: 1/n, [2, 1, 0, 3], count=2)
        cancel = threading.Event()
        threading.Timer(.5, cancel.set).start()
        long = ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=640x360', '-t', '600', '-f', 'null', '-']
        began = time.monotonic()
        with jobs.job(cancel), self.assertRaises(jobs.Cancelled):
            jobs.parallel(lambda n: jobs.run(long), range(6), count=3)
        self.assertLess(time.monotonic()-began, 5)    # running workers were stopped, the rest never started
        with unittest.mock.patch.dict(os.environ, {'DRIFT_WORKERS': '1'}):
            self.assertEqual(jobs.workers(), 1)

    def test_parallel_analysis_matches_sequential_analysis(self):
        from montage_editor.pipeline import analyze_gameplay, probe
        with tempfile.TemporaryDirectory() as d:
            video = Path(d)/'long.mp4'
            # 75 s: three 30 s analysis chunks, so chunk order and continuity matter.
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=15', '-f', 'lavfi',
                            '-i', 'sine=f=300:beep_factor=6:sample_rate=8000', '-t', '75', '-c:v', 'libx264', '-preset',
                            'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(video)], check=True)
            media = probe(video)
            with unittest.mock.patch.dict(os.environ, {'DRIFT_WORKERS': '1'}):
                sequential = analyze_gameplay(media, Settings())
            with unittest.mock.patch.dict(os.environ, {'DRIFT_WORKERS': '4'}):
                parallel = analyze_gameplay(media, Settings())
        self.assertEqual(sequential, parallel)
        self.assertGreater(len(parallel), 5)

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
