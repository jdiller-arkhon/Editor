from pathlib import Path
import tempfile
import unittest
from montage_editor.music_library import find_songs


class MusicTests(unittest.TestCase):
    def test_exact_accent_and_artist_matching(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'Hópe.wav').touch();(root/'Artist - Hope (Live).mp3').touch()
            (root/'hope.txt').touch()
            self.assertEqual([p.name for p in find_songs(root,'hope')],['Hópe.wav'])
            self.assertEqual([p.name for p in find_songs(root,'artist hope')],['Artist - Hope (Live).mp3'])
            self.assertEqual(find_songs(root,'missing'),[])

    def test_ambiguous_tracks_remain_choices(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'Artist One - Light.wav').touch();(root/'Artist Two - Light.mp3').touch()
            self.assertEqual(len(find_songs(root,'light')),2)
            with self.assertRaises(ValueError):find_songs(root,'')
