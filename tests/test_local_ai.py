"""Local (Ollama) AI director: real frames and renders, a fake Ollama HTTP server on loopback.

The fake server stands in for Ollama's HTTP API so these tests are deterministic and run in
CI. They verify what is sent, that replies are validated and how judgements drive the edit;
they are not evidence of any local model's judgement quality.
"""
import base64
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from montage_editor import jobs, local_ai
from montage_editor.config import Settings
from montage_editor.pipeline import create_montage
from montage_editor.vision_director import DIRECT_SYSTEM, REVIEW_SYSTEM, LocalDirector
from test_rhythm import write_song
from test_vision_director import judge


class FakeOllama:
    """Minimal /api/version, /api/tags, /api/show, /api/pull and /api/chat."""

    def __init__(self, models=('qwen2.5vl:7b',), vision=('qwen2.5vl:7b',), delay=0.0, reply=None):
        self.models, self.vision, self.delay, self.reply = list(models), set(vision), delay, reply
        self.received = threading.Event()
        self.queued = []        # one-off replies served before the normal answers
        self.chats, self.pulls = [], []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, body, lines=False):
                data = b''.join(json.dumps(b).encode()+b'\n' for b in body) if lines else json.dumps(body).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == '/api/version':
                    self.send({'version': '0.test'})
                elif self.path == '/api/tags':
                    self.send({'models': [{'name': m} for m in owner.models]})
                else:
                    self.send_error(404)

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path == '/api/show':
                    self.send({'capabilities': ['completion']+(['vision'] if payload['model'] in owner.vision else [])})
                elif self.path == '/api/pull':
                    owner.pulls.append(payload)
                    owner.models.append(payload['model']); owner.vision.add(payload['model'])
                    self.send([{'status': 'pulling manifest'}, {'status': 'downloading', 'total': 100, 'completed': 40},
                               {'status': 'downloading', 'total': 100, 'completed': 100}, {'status': 'success'}], lines=True)
                elif self.path == '/api/chat':
                    owner.chats.append(payload)
                    owner.received_at = time.monotonic(); owner.received.set()
                    time.sleep(owner.delay)
                    self.send(owner.answer(payload))
                else:
                    self.send_error(404)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.host = f'http://127.0.0.1:{self.server.server_address[1]}'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def answer(self, payload):
        if self.queued:
            return self.queued.pop(0)
        if self.reply is not None:
            return self.reply
        system, user = payload['messages'][0]['content'], payload['messages'][1]['content']
        if system == REVIEW_SYSTEM:
            content = dict(swaps=[], notes='Cut is strong.')
        elif system == DIRECT_SYSTEM:
            content = dict(slots=[], arc='Keep the draft.')
        else:
            ids = [int(line.split()[1].rstrip(':')) for line in user.splitlines() if line.startswith('Candidate ')]
            content = judge(ids)
            for moment in content['moments']:
                moment['observations'] = 'HUD visible; two opponents drop.'
        return {'model': payload['model'], 'message': {'role': 'assistant', 'content': json.dumps(content)},
                'done': True, 'done_reason': 'stop', 'total_duration': 2_500_000_000,
                'prompt_eval_count': 900, 'eval_count': 120}

    def close(self):
        self.server.shutdown(); self.server.server_close()


class LocalDirectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        cls.video = cls.root/'secret-match-name.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30',
                        '-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=8000', '-t', '30',
                        '-c:v', 'libx264', '-threads', '2', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                        str(cls.video)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        self.ollama = FakeOllama()
        self.addCleanup(self.ollama.close)

    def candidates(self):
        return [dict(source=str(self.video), time=float(t), score=s, source_duration=30.0)
                for t, s in ((5, .9), (12, .8), (18, .7), (24, .6), (27, .5))]

    def test_review_runs_locally_in_batches_with_real_frames(self):
        # A configured proxy must be ignored: requests go straight to loopback.
        proxy = {'HTTP_PROXY': 'http://192.0.2.1:9', 'http_proxy': 'http://192.0.2.1:9', 'NO_PROXY': '', 'no_proxy': ''}
        with patch.dict(os.environ, proxy):
            candidates, report = LocalDirector(host=self.ollama.host, batch=2).review(self.candidates(), 'Hopeful')
        self.assertEqual(len(self.ollama.chats), 3)                      # 5 moments in batches of 2
        first = self.ollama.chats[0]
        self.assertEqual(first['model'], 'qwen2.5vl:7b')
        self.assertFalse(first['stream'])
        item = first['format']['properties']['moments']['items']
        self.assertEqual(item['required'][0], 'observations')            # describe before judging
        # One judgement per strip is enforced by the schema itself.
        self.assertEqual((first['format']['properties']['moments']['minItems'], item['properties']['id']['enum']),
                         (2, [0, 1]))
        images = first['messages'][1]['images']
        self.assertEqual(len(images), 2)
        self.assertEqual(base64.b64decode(images[0])[:2], b'\xff\xd8')   # real JPEG strips
        self.assertNotIn('secret-match-name', json.dumps(self.ollama.chats))
        self.assertEqual(report['provider'], 'ollama (local)')
        self.assertEqual(report['reviewed'], 5)
        self.assertEqual(report['seconds'], 7.5)
        by_time = {round(c['activity_score'], 1): c for c in candidates}
        # Batch-local ids map back to the right moments: id 0 of each batch is the menu screen.
        self.assertTrue(by_time[.9]['exclude'] and by_time[.7]['exclude'] and by_time[.5]['exclude'])
        # Local judgements are blended with the measured activity score (60/40).
        self.assertEqual(by_time[.8]['event'], 'multi_elimination')
        self.assertAlmostEqual(by_time[.8]['score'], .6*1.0+.4*.8)
        self.assertAlmostEqual(by_time[.6]['score'], .6*1.0+.4*.6)
        self.assertEqual(by_time[.8]['judged_by'], 'local vision review (qwen2.5vl:7b)')

    def test_local_director_directs_and_renders_a_real_montage(self):
        song, output = self.root/'song.wav', self.root/'local.mp4'
        write_song(song, bpm=128, seconds=20, lift_bar=4)
        settings = Settings(width=160, height=90, fps=30, duration=12, quality='draft')
        report = create_montage([self.video], song, output, settings,
                                story=dict(edit_profile='cinematic', transition='cinematic'),
                                ai_editor=LocalDirector(host=self.ollama.host))
        self.assertTrue(report['full_decode'])
        self.assertEqual(report['ai_director'], 'local vision')
        self.assertEqual(report['ai_editor']['provider'], 'ollama (local)')
        systems = [c['messages'][0]['content'] for c in self.ollama.chats]
        self.assertIn(DIRECT_SYSTEM, systems)          # the local model also directs the edit
        analysis = json.loads(output.with_suffix('.analysis.json').read_text())
        # The cut review ran: either the local model saw it, or no unused alternates were left.
        review = analysis['ai_editor']['cut_review']
        self.assertNotIn('error', review)
        self.assertTrue(REVIEW_SYSTEM in systems or review['notes'] == 'no unused alternates')
        self.assertEqual(analysis['ai_editor']['edit_plan']['model'], 'qwen2.5vl:7b')

    def test_failures_are_explained_and_hosts_are_local_only(self):
        with self.assertRaisesRegex(ValueError, 'only talks to Ollama on this computer'):
            LocalDirector(host='http://example.com:11434')
        with self.assertRaisesRegex(ValueError, 'needs Ollama running'):
            LocalDirector(host='http://127.0.0.1:9').review(self.candidates())
        self.ollama.reply = {'error': 'model requires more system memory'}
        with self.assertRaisesRegex(ValueError, 'more system memory'):
            LocalDirector(host=self.ollama.host).review(self.candidates())
        self.ollama.reply = {'message': {'content': '{"moments": [{"id": 99}]}'}, 'done_reason': 'stop'}
        with self.assertRaisesRegex(ValueError, 'invalid or unknown moment'):
            LocalDirector(host=self.ollama.host).review(self.candidates())
        self.ollama.reply = {'message': {'content': '{"moments": ['}, 'done_reason': 'length'}
        with self.assertRaisesRegex(ValueError, 'cut off'):
            LocalDirector(host=self.ollama.host).review(self.candidates())

    def test_an_incomplete_local_answer_is_retried_once(self):
        empty = {'message': {'content': json.dumps(dict(moments=[], sequence=[], rationale=''))}, 'done_reason': 'stop'}
        self.ollama.queued = [dict(empty)]
        candidates, report = LocalDirector(host=self.ollama.host, batch=5).review(self.candidates())
        self.assertEqual((len(self.ollama.chats), report['reviewed']), (2, 5))
        self.ollama.chats.clear()
        self.ollama.queued = [dict(empty), dict(empty)]
        with self.assertRaisesRegex(ValueError, 'judged no moments'):
            LocalDirector(host=self.ollama.host, batch=5).review(self.candidates())
        self.assertEqual(len(self.ollama.chats), 2)

    def test_cancel_stops_a_slow_local_model(self):
        self.ollama.delay = 5
        cancel = threading.Event()
        # Cancel while the model is thinking, not between requests.
        threading.Thread(target=lambda: self.ollama.received.wait(30) and cancel.set(), daemon=True).start()
        with self.assertRaises(jobs.Cancelled), jobs.job(cancel=cancel):
            LocalDirector(host=self.ollama.host).review(self.candidates())
        self.assertTrue(self.ollama.received.is_set())
        self.assertEqual(len(self.ollama.chats), 1)
        self.assertLess(time.monotonic()-self.received_at(), 2.5)

    def received_at(self):
        return self.ollama.received_at

    def test_status_readiness_and_download(self):
        host = self.ollama.host
        self.ollama.models.append('llama3.2:3b')
        state = local_ai.status(host)
        self.assertEqual((state['running'], state['version']), (True, '0.test'))
        self.assertEqual(state['vision_models'], ['qwen2.5vl:7b'])
        self.assertTrue(local_ai.readiness('qwen2.5vl:7b', host)[0])
        ready, message = local_ai.readiness('llama3.2:3b', host)
        self.assertFalse(ready); self.assertIn('cannot see images', message)
        ready, message = local_ai.readiness('qwen2.5vl:3b', host)
        self.assertFalse(ready); self.assertIn('not downloaded', message)
        seen = []
        self.assertTrue(local_ai.pull('qwen2.5vl:3b', lambda f, m: seen.append(f), host=host))
        self.assertEqual(seen, [.4, 1.0])
        self.assertTrue(local_ai.readiness('qwen2.5vl:3b', host)[0])
        for bad in ('', 'a b', '../x', 'x;rm', 'q'*201, None):
            with self.assertRaises(ValueError):
                local_ai.pull(bad, host=host)
        self.assertEqual(len(self.ollama.pulls), 1)
        stopped = local_ai.status('http://127.0.0.1:9')
        self.assertFalse(stopped['running'])
        self.assertIn('not running', local_ai.readiness('qwen2.5vl:7b', 'http://127.0.0.1:9')[1])


@unittest.skipUnless(os.environ.get('DRIFT_LIVE_OLLAMA'), 'live local-model check: set DRIFT_LIVE_OLLAMA=<model>')
class LiveLocalModelCheck(unittest.TestCase):
    """Opt-in: real inference by a real local model on real frames (slow on CPU)."""

    def test_real_model_returns_a_valid_review(self):
        model = os.environ['DRIFT_LIVE_OLLAMA']
        ready, message = local_ai.readiness(model)
        self.assertTrue(ready, message)
        with tempfile.TemporaryDirectory() as d:
            video = Path(d)/'clip.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30',
                            '-t', '8', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True)
            candidates, report = LocalDirector(model, batch=1, limit=1).review(
                [dict(source=str(video), time=4.0, score=.5, source_duration=8.0)])
        self.assertEqual(report['reviewed'], 1)
        self.assertGreater(report['seconds'], 0)
        print(f'\nlive {model}: {report["seconds"]} s, event {candidates[0].get("event")}')


if __name__ == '__main__':
    unittest.main()
