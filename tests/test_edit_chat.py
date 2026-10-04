"""Director chat: validation of proposed actions and a round trip through the local director."""
import json
import unittest

from montage_editor.edit_chat import ACTIONS, CHAT_SYSTEM, EditChat, validate_actions
from montage_editor.vision_director import LocalDirector
from test_local_ai import FakeOllama

STATE = dict(tones=['subtle', 'christian', 'neutral'], shot_count=5, has_preview=False)


class EditChatTests(unittest.TestCase):
    def test_only_known_actions_with_valid_values_are_accepted(self):
        accepted, rejected = validate_actions([
            dict(action='set_pace', value='Fast'), dict(action='set_length', value='45 s'),
            dict(action='make', value='preview'), dict(action='set_look', value='punchy'),
            dict(action='move_shot', value='shot 3 later'), dict(action='swap_shot', value='4'),
            dict(action='set_tone', value='christian'), dict(action='set_music', value='https://youtu.be/x'),
            dict(action='delete_files', value='/'), dict(action='set_length', value='9000'),
            dict(action='move_shot', value='1 earlier'), dict(action='swap_shot', value='9'),
            dict(action='set_format', value='8k-imax'), dict(action='make', value='final'), 'junk'], STATE)
        self.assertEqual(accepted, [('set_pace', 'fast'), ('set_length', '45'), ('set_look', 'punchy'),
                                    ('move_shot', 'shot 3 later'), ('swap_shot', '4'), ('make', 'preview')])
        # Only the first six entries are considered at all; 'make' runs last.
        self.assertEqual(len(rejected), 0)
        accepted, rejected = validate_actions([
            dict(action='set_music', value='https://youtu.be/x'), dict(action='make', value='preview'),
            dict(action='delete_files', value='/'), dict(action='set_length', value='9000'),
            dict(action='move_shot', value='1 earlier'), dict(action='make', value='final'), 'junk'], STATE)
        self.assertEqual(accepted, [('set_music', 'https://youtu.be/x'), ('make', 'preview')])
        self.assertEqual([r[2] for r in rejected], ['unknown action', 'length must be 5-600 seconds',
                                                     'shot is already at that end', 'make a preview first'])
        self.assertEqual(validate_actions('nope', STATE)[0], [])

    def test_actions_the_person_did_not_ask_for_are_not_run(self):
        # Real qwen2.5vl:3b output for "Make it faster and more intense, then show me a quick preview".
        proposed = [dict(action='set_pace', value='fast'), dict(action='set_look', value='punchy'),
                    dict(action='set_music', value='The Game by The Weeknd'),
                    dict(action='set_format', value='youtube-1080p60'), dict(action='set_slow_motion', value='motion'),
                    dict(action='make', value='preview')]
        accepted, rejected = validate_actions(proposed, STATE, 'Make it faster and more intense, then show me a quick preview')
        self.assertEqual(accepted, [('set_pace', 'fast'), ('make', 'preview')])
        self.assertEqual({r[0] for r in rejected if r[2] == 'not asked for'},
                         {'set_look', 'set_music', 'set_format', 'set_slow_motion'})
        accepted, _ = validate_actions([dict(action='set_music', value='https://youtu.be/x'),
                                        dict(action='set_format', value='shorts-1080x1920')], STATE,
                                       'use https://youtu.be/x and make a tiktok version')
        self.assertEqual([a[0] for a in accepted], ['set_music', 'set_format'])

    def test_chat_round_trip_with_the_local_director(self):
        ollama = FakeOllama()
        self.addCleanup(ollama.close)
        ollama.reply = {'model': 'qwen3.5:9b', 'done_reason': 'stop', 'message': {'content': json.dumps(dict(
            reply='Faster cuts suit this song; I set the pace to fast and will make a preview.',
            actions=[dict(action='set_pace', value='fast'), dict(action='make', value='preview'),
                     dict(action='run_shell', value='rm -rf')]))}}
        chat = EditChat(LocalDirector(host=ollama.host))
        result = chat.ask('Make it more intense and show me', dict(STATE, pace='balanced'))
        self.assertEqual(result['actions'], [('set_pace', 'fast'), ('make', 'preview')])
        self.assertEqual(result['rejected'][0][:2], ('run_shell', 'rm -rf'))
        request = ollama.chats[0]
        self.assertEqual(request['messages'][0]['content'], CHAT_SYSTEM)
        self.assertEqual(request['messages'][1]['images'], [])
        self.assertEqual(request['format']['properties']['actions']['items']['properties']['action']['enum'], list(ACTIONS))
        self.assertIn('"pace": "balanced"', request['messages'][1]['content'])
        chat.ask('Thanks. Now shorter?', STATE)
        follow_up = ollama.chats[1]['messages'][1]['content']
        self.assertIn('Person: Make it more intense and show me', follow_up)          # the conversation carries over
        self.assertIn('Director: Faster cuts suit this song', follow_up)
        ollama.reply = {'done_reason': 'stop', 'message': {'content': json.dumps(dict(actions=[]))}}
        with self.assertRaisesRegex(ValueError, 'without a message'):
            chat.ask('hello', STATE)

    def test_the_director_can_look_at_the_edit_when_asked(self):
        import base64, subprocess, tempfile
        from pathlib import Path
        from montage_editor.config import Settings
        from montage_editor.edit_chat import contact_sheet, wants_a_look
        from montage_editor.pipeline import Clip, Timeline
        self.assertTrue(wants_a_look('How is it? Which shot is weakest?'))
        self.assertTrue(wants_a_look('take a look and tell me what to improve'))
        self.assertFalse(wants_a_look('Use a punchy colour look and make it 45 seconds'))
        with tempfile.TemporaryDirectory() as d:
            video = Path(d)/'v.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30', '-t', '6',
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True)
            timeline = Timeline(1, 'song.wav', Settings().__dict__, [Clip(str(video), 0, 2, .5), Clip(str(video), 3, 2, .5)])
            sheet = contact_sheet(timeline)
        self.assertEqual(sheet[:2], b'\xff\xd8')
        ollama = FakeOllama()
        self.addCleanup(ollama.close)
        ollama.reply = {'done_reason': 'stop', 'message': {'content': json.dumps(dict(
            reply='S2 is the weaker shot; swapping it.', actions=[dict(action='swap_shot', value='2')]))}}
        result = EditChat(LocalDirector(host=ollama.host)).ask('Which shot is weakest? Swap it.', dict(STATE, shot_count=2), sheet)
        self.assertEqual(result['actions'], [('swap_shot', '2')])
        sent = ollama.chats[0]['messages'][1]
        self.assertEqual(base64.b64decode(sent['images'][0]), sheet)
        self.assertIn('contact sheet of the current edit', sent['content'])

    def test_new_talents_styles_shot_treatments_cuts_and_renders(self):
        accepted, rejected = validate_actions([
            dict(action='apply_style', value='Hype'), dict(action='set_shot', value='shot 4 slow-mo'),
            dict(action='set_cut', value='3 push left'), dict(action='set_beat_fx', value='off'),
            dict(action='make', value='formats'), dict(action='set_cut', value='8 dissolve')],
            STATE, 'make it hype, slow-mo on shot 4, push out of shot 3, no beat flashes, export every platform')
        self.assertEqual(accepted, [('apply_style', 'hype'), ('set_shot', '4 slow motion'), ('set_cut', '3 push_left'),
                                    ('set_beat_fx', 'off'), ('make', 'formats')])
        self.assertEqual(validate_actions([dict(action='set_cut', value='5 dissolve')], STATE, 'dissolve after 5')[1][0][2],
                         'no transition out of that shot')          # STATE has 5 shots: the last has no "out"
        self.assertEqual(validate_actions([dict(action='apply_style', value='vaporwave')], STATE, 'style')[1][0][2],
                         'unknown style')
        self.assertEqual(validate_actions([dict(action='make', value='render')], dict(STATE, shot_count=0), 'render')[1][0][2],
                         'create a montage first')
        from montage_editor.edit_chat import CHAT_SYSTEM, STYLES
        self.assertIn('apply_style hype', CHAT_SYSTEM)                  # worked examples for small models
        self.assertTrue(all(set(v) <= set(ACTIONS) for v in STYLES.values()))

    def test_one_shot_can_be_retreated_or_given_a_new_transition(self):
        import subprocess, tempfile
        from pathlib import Path
        from montage_editor.config import Settings
        from montage_editor.pipeline import Clip, Timeline, edit_shot
        with tempfile.TemporaryDirectory() as d:
            video = Path(d)/'v.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30', '-t', '20',
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True)
            clips = [Clip(str(video), 1, 2, .5), Clip(str(video), 6, 2, .9), Clip(str(video), 11, .6, .4)]
            timeline = Timeline(1, 'song.wav', Settings().__dict__, clips, transition='cinematic',
                                boundary_transitions=['cut', 'cut'])
            moment = clips[1].start+1
            slow = edit_shot(timeline, 1, treatment='slow motion')
            self.assertEqual(slow.clips[1].speed_profile, 'ramp')
            self.assertEqual((slow.clips[1].duration, slow.clips[0], slow.clips[2]), (2, clips[0], clips[2]))   # timing kept
            self.assertAlmostEqual(slow.clips[1].anchor_source, moment, places=2)                  # same moment, now slowed
            punched = edit_shot(slow, 1, treatment='punch', beats=[2.5, 3.0, 3.5, 9.0])
            self.assertEqual((punched.clips[1].speed_profile, punched.clips[1].accents), ('normal', [0.5, 1.0, 1.5]))
            self.assertEqual(edit_shot(punched, 1, treatment='straight').clips[1].accents, [])
            faded = edit_shot(timeline, 0, transition='dissolve')
            self.assertEqual(faded.boundary_transitions, ['fade', 'cut'])
            for bad in (dict(index=2, treatment='slow motion'),            # 0.6 s is too short to slow down
                        dict(index=2, transition='dissolve'),              # last shot has no transition out
                        dict(index=1, treatment='punch', beats=[]),        # no beats to punch on
                        dict(index=9, treatment='straight')):
                with self.assertRaises(ValueError):
                    edit_shot(timeline, **bad)
            with self.assertRaisesRegex(ValueError, 'plain cuts'):
                edit_shot(Timeline(1, 'song.wav', Settings().__dict__, clips), 0, transition='dissolve')

    def test_the_persons_literal_words_win_over_a_paraphrase(self):
        from montage_editor.edit_chat import ground
        # Real qwen3.5:9b mistakes from the scripted evaluation.
        accepted, rejected, notes = ground([], [('set_length', ']}', 'length must be 5-600 seconds')],
                                           'can you make it 45 seconds long', STATE)
        self.assertEqual((accepted, rejected), ([('set_length', '45')], []))
        self.assertEqual(ground([], [], 'use this song https://youtu.be/abc123', STATE)[0],
                         [('set_music', 'https://youtu.be/abc123')])
        self.assertEqual(ground([('set_pace', 'calm'), ('set_look', 'cinematic'), ('make', 'preview')], [],
                                'make it calmer and give it a film look, then preview it', STATE)[0],
                         [('set_pace', 'calm'), ('set_look', 'film'), ('make', 'preview')])
        # No overreach: a link that is not about music, or a look the model did not touch, is left alone.
        self.assertEqual(ground([('set_look', 'punchy')], [], 'saw the youtu.be/x clip? make it punchy', STATE)[0],
                         [('set_look', 'punchy')])
        self.assertEqual(ground([('set_pace', 'fast')], [], 'faster, but keep the film look', STATE)[0],
                         [('set_pace', 'fast')])
        self.assertEqual(ground([('make', 'preview')], [], 'show me', STATE), ([('make', 'preview')], [], []))


if __name__ == '__main__':
    unittest.main()
