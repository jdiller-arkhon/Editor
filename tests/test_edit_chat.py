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


if __name__ == '__main__':
    unittest.main()
