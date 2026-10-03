"""One song box: links, file paths and titles; pace presets."""
import tempfile
import unittest
from pathlib import Path

from montage_editor.config import PACES, Settings, with_pace
from montage_editor.music_library import interpret_song, search_libraries


class MusicChoiceTests(unittest.TestCase):
    def test_whatever_is_pasted_is_understood(self):
        with tempfile.TemporaryDirectory() as d:
            song = Path(d)/'Artist - Hope.mp3'; song.touch()
            video = Path(d)/'concert.mp4'; video.touch()
            notes = Path(d)/'notes.txt'; notes.touch()
            self.assertEqual(interpret_song('https://www.youtube.com/watch?v=abc'), ('link', 'https://www.youtube.com/watch?v=abc'))
            self.assertEqual(interpret_song('  youtu.be/abc '), ('link', 'https://youtu.be/abc'))
            self.assertEqual(interpret_song('open.spotify.com/track/1'), ('link', 'https://open.spotify.com/track/1'))
            self.assertEqual(interpret_song('spotify:track:1'), ('link', 'spotify:track:1'))
            self.assertEqual(interpret_song(f'"{song}"'), ('file', str(song.resolve())))   # pasted with quotes
            self.assertEqual(interpret_song(str(video)), ('file', str(video.resolve())))  # songs from videos
            self.assertEqual(interpret_song(str(notes)), ('title', str(notes)))
            self.assertEqual(interpret_song('hope'), ('title', 'hope'))
            self.assertEqual(interpret_song('   '), ('empty', ''))

    def test_titles_search_every_library_once(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            (Path(a)/'Artist - Hope.wav').touch(); (Path(b)/'Hope (live).flac').touch(); (Path(b)/'Other.mp3').touch()
            found = search_libraries([a, b, a, str(Path(a)/'missing'), ''], 'hope')
            self.assertEqual(sorted(p.name for p in found), ['Artist - Hope.wav', 'Hope (live).flac'])

    def test_pace_sets_shot_length_bounds(self):
        base = Settings(duration=20)
        self.assertEqual((base.minimum_clip, base.maximum_clip), PACES['balanced'])
        fast = with_pace(base, 'hyper')
        self.assertEqual((fast.minimum_clip, fast.maximum_clip, fast.duration), (*PACES['hyper'], 20))
        with self.assertRaises(KeyError):
            with_pace(base, 'warp')

    def test_pace_changes_the_real_beat_cut(self):
        from montage_editor.pipeline import music_analysis, probe
        from montage_editor.rhythm import plan_cuts
        from test_rhythm import write_song
        with tempfile.TemporaryDirectory() as d:
            song = Path(d)/'song.wav'
            write_song(song, bpm=120, seconds=24)
            music = music_analysis(probe(song), 20)
            lengths = {}
            for pace in ('calm', 'fast'):
                cuts = plan_cuts(music, with_pace(Settings(duration=20), pace), 20)
                self.assertTrue(cuts)
                lengths[pace] = [length for length, _ in cuts]
                self.assertAlmostEqual(sum(lengths[pace]), 20, delta=.05)
            self.assertLess(max(lengths['fast']), min(PACES['calm'][1], max(lengths['calm']))+1e-6)
            self.assertGreater(len(lengths['fast']), 1.4*len(lengths['calm']))


if __name__ == '__main__':
    unittest.main()
