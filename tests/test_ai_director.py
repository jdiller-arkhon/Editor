import io
import json
import unittest
from unittest.mock import patch
from montage_editor.ai_director import OllamaDirector,validate_plan,configure_plan
from montage_editor.config import Settings


PLAN=dict(candidate_order=[1,0],minimum_clip=1,maximum_clip=3,transition='fade_white',transition_duration=.15,rationale='Build toward hope.')
CANDIDATES=[dict(source='private-path.mp4',time=1,score=.9,source_duration=10),
            dict(source='private-path.mp4',time=5,score=.5,source_duration=10)]


class DirectorTests(unittest.TestCase):
    def test_structured_local_transport(self):
        response=io.BytesIO(json.dumps({'done':True,'message':{'content':json.dumps(PLAN)}}).encode())
        with patch('montage_editor.ai_director.build_opener') as opener:
            opener.return_value.open.return_value=response
            plan,pool=OllamaDirector('test-model').plan(CANDIDATES)
            request=opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,'http://127.0.0.1:11434/api/chat')
            self.assertNotIn('private-path',request.data.decode())
            self.assertFalse(json.loads(request.data)['stream'])
        ranked,settings=configure_plan(plan,pool,Settings())
        self.assertEqual(ranked[0]['time'],5)
        self.assertEqual(settings.maximum_clip,3)

    def test_invalid_plans_cannot_reach_renderer(self):
        for changes in [dict(candidate_order=[0,0]),dict(candidate_order=[8]),
                        dict(candidate_order=[True]),dict(maximum_clip=float('nan')),
                        dict(minimum_clip=4,maximum_clip=2),dict(transition='execute-shell'),dict(command='rm')]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                validate_plan(dict(PLAN,**changes),2)

    def test_connection_failure_is_explicit(self):
        with patch('montage_editor.ai_director.build_opener') as opener:
            opener.return_value.open.side_effect=OSError('service unavailable')
            with self.assertRaisesRegex(ValueError,'Start local Ollama'):
                OllamaDirector('test-model').plan(CANDIDATES)
