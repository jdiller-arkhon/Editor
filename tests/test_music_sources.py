"""Music from links: real yt-dlp downloads from a local HTTP server; no YouTube/Spotify traffic.

YouTube itself is not contacted (it bot-checks datacenter IPs), so these tests prove the
download/extract/provenance path and the Spotify safeguards, not YouTube availability.
"""
import functools
import http.server
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from montage_editor.music_sources import add_music, classify, download, spotify_track
from montage_editor.pipeline import music_analysis, probe

PAGE = '''<html><head>
<meta property="og:title" content="Beyonc&eacute; Song &amp; More"/>
<meta property="og:description" content="Test Artist · Album · Song · 2020"/>
<meta name="music:duration" content="{duration}"/>
<meta name="music:musician_description" content="Test Artist"/>
</head></html>'''
TRACK = 'https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b?si=abc'


class LinkTests(unittest.TestCase):
    def test_classification_accepts_tracks_and_videos_only(self):
        for link in ('https://www.youtube.com/watch?v=abc', 'https://youtu.be/abc', 'https://music.youtube.com/watch?v=x',
                     'https://m.youtube.com/watch?v=abc'):
            self.assertEqual(classify(link), 'youtube')
        for link in (TRACK, 'spotify:track:0VjIjW4GlUZAMYd2vXMi3b',
                     'https://open.spotify.com/intl-de/track/0VjIjW4GlUZAMYd2vXMi3b'):
            self.assertEqual(classify(link), 'spotify')
        for link in ('https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M', 'spotify:album:1',
                     'https://youtube.com.evil.example/watch?v=1', 'file:///etc/passwd', 'javascript:alert(1)',
                     'https://example.com/song.mp3'):
            with self.assertRaises(ValueError):
                classify(link)

    def test_spotify_page_metadata_without_audio(self):
        track = spotify_track(TRACK, fetch=lambda url: PAGE.format(duration=200))
        self.assertEqual(track, dict(id='0VjIjW4GlUZAMYd2vXMi3b', url='https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b',
                                     title='Beyoncé Song & More', artist='Test Artist', duration=200.0))
        with self.assertRaises(ValueError):
            spotify_track(TRACK, fetch=lambda url: '<html></html>')


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import yt_dlp  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("yt-dlp extra not installed (pip install -e '.[links]')")
        cls.served = tempfile.TemporaryDirectory()
        root = Path(cls.served.name)
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'aevalsrc=sin(2*PI*220*t)*if(lt(mod(t\\,0.5)\\,0.08)\\,0.8\\,0.1):s=48000',
                        '-t', '6', '-c:a', 'libopus', '-vn', str(root/'song.webm')], check=True)
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        handler = functools.partial(Quiet, directory=str(root))
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/song.webm'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.served.cleanup()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.library = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def redirect(self, queries):
        """Real YoutubeDL, with the query (a YouTube URL or ytsearch) served locally instead."""
        import yt_dlp
        url = self.url

        class Redirect(yt_dlp.YoutubeDL):
            def extract_info(self, query, download=True, **kwargs):
                queries.append(query)
                return super().extract_info(url, download=download, **kwargs)
        return Redirect

    def test_youtube_link_downloads_real_audio_with_provenance(self):
        queries = []
        result = add_music('https://www.youtube.com/watch?v=abc123', self.library, factory=self.redirect(queries))
        self.assertEqual(queries, ['https://www.youtube.com/watch?v=abc123'])
        path = Path(result['path'])
        self.assertEqual(path.parent, self.library)
        self.assertEqual(path.suffix, '.opus')  # audio-only file, original codec kept
        source = json.loads(path.with_name(path.name+'.source.json').read_text())
        self.assertEqual(source['source'], 'youtube')
        self.assertIn('right to use', source['notice'])
        analysis = music_analysis(probe(path), 6)
        self.assertAlmostEqual(analysis['tempo_bpm'], 120, delta=1)
        # Never overwrites an existing download.
        before = path.stat().st_mtime_ns
        again = add_music('https://www.youtube.com/watch?v=abc123', self.library, factory=self.redirect([]))
        self.assertEqual(again['path'], str(path)); self.assertEqual(path.stat().st_mtime_ns, before)

    def test_spotify_uses_youtube_match_only_when_duration_agrees(self):
        queries = []
        result = add_music(TRACK, self.library, factory=self.redirect(queries),
                           fetch=lambda url: PAGE.format(duration=6))
        self.assertEqual(queries, ['ytsearch1:Test Artist - Beyoncé Song & More audio'])
        self.assertEqual(result['source'], 'youtube match for spotify track')
        self.assertTrue(Path(result['path']).name.startswith('Test Artist - Beyoncé Song & More'))
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaisesRegex(ValueError, 'Spotify track is 200s'):
                add_music(TRACK, other, factory=self.redirect([]), fetch=lambda url: PAGE.format(duration=200))
            self.assertEqual(list(Path(other).iterdir()), [])  # rejected download removed

    def test_spotify_prefers_the_local_library_and_never_downloads_then(self):
        song = self.library/'Test Artist - Beyoncé Song & More.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=f=330', '-t', '2', str(song)], check=True)

        def forbidden(options):
            raise AssertionError('must not download')
        result = add_music(TRACK, self.library, factory=forbidden, fetch=lambda url: PAGE.format(duration=200))
        self.assertEqual(result['source'], 'local library')
        self.assertEqual(Path(result['path']), song.resolve())
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaisesRegex(ValueError, 'not in your music folder'):
                add_music(TRACK, empty, allow_youtube_match=False, factory=forbidden,
                          fetch=lambda url: PAGE.format(duration=200))

    def test_errors_are_explained(self):
        class Bot:
            def __init__(self, options): pass
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def extract_info(self, query, download=True):
                raise RuntimeError('ERROR: [youtube] x: Sign in to confirm you’re not a bot. Use --cookies')
        with self.assertRaisesRegex(ValueError, 'not a bot; try again later'):
            download('https://youtu.be/x', self.library, factory=Bot)
        with patch.dict(sys.modules, {'yt_dlp': None}):
            with self.assertRaisesRegex(ValueError, r"\[links\]"):
                download('https://youtu.be/x', self.library)
        with self.assertRaisesRegex(ValueError, 'existing music folder'):
            download('https://youtu.be/x', self.library/'missing', factory=Bot)


if __name__ == '__main__':
    unittest.main()
