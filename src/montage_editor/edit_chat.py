"""Director chat: talk to the AI director about the edit; it answers and proposes app actions.

The model (local Ollama by default, Claude optionally) only returns a reply and a list of
named actions with string values. Nothing it says is executed directly: every action is
checked against the allowed names and values here, then the desktop app applies it through
the same controls a person would use. Unknown or invalid actions are reported, not run.
"""
import json
import re

from .config import PACES, PRESETS
from .craft import LOOKS

SLOW_MOTION = ('motion', 'blend', 'none')
MAKE = ('preview', 'montage', 'final')
SWITCH = ('on', 'off')
MAX_TURNS = 8

ACTIONS = {
    'set_pace': 'one of ' + '/'.join(PACES),
    'set_length': 'target length in seconds, 5-600',
    'set_look': 'colour look: ' + '/'.join(LOOKS),
    'set_tone': 'story tone key (see state.tones)',
    'set_closing_line': 'closing text shown at the end (max 140 characters, may be empty)',
    'set_brief': 'creative brief for the director (max 500 characters)',
    'set_music': 'a YouTube/Spotify link, a file path, or a song title from the music folder',
    'set_format': 'export preset: ' + '/'.join(PRESETS),
    'set_slow_motion': 'slow-motion rendering: ' + '/'.join(SLOW_MOTION),
    'set_swishes': 'transition swish sounds: on/off',
    'set_motion_blur': 'motion blur on speed ramps: on/off',
    'move_shot': 'shot number and direction, e.g. "3 earlier" or "5 later"',
    'swap_shot': 'shot number to replace with the strongest unused moment, e.g. "4"',
    'make': 'preview (fast draft) / montage (full render) / final (render the previewed edit)',
}

CHAT_SCHEMA = {
    'type': 'object',
    'properties': {
        'reply': {'type': 'string'},
        'actions': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {'action': {'type': 'string', 'enum': list(ACTIONS)}, 'value': {'type': 'string'}},
            'required': ['action', 'value'], 'additionalProperties': False}},
    },
    'required': ['reply', 'actions'],
    'additionalProperties': False,
}

CHAT_SYSTEM = (
    'You are the director inside DRIFT, a gaming montage editor, chatting with the person making the '
    'montage. Help them get a great edit: explain editing choices briefly in plain words (beat sync, '
    'pacing, slow motion on decisive hits, hard cuts with motivated transitions on phrase changes and '
    'drops, a strong opening, the biggest moment on the drop, a clean closing shot) and change the app '
    'only through actions. The state JSON shows the current settings and, once a montage exists, its '
    'shots and measured results. Only use action names listed in state.actions with values in the '
    'described form. Make no action unless the person asked for a change or clearly agreed to one; '
    'when they ask for a new version, change settings first and finish with a make action. Never claim '
    'you watched footage, heard music or rendered anything yourself: the engine measures and renders. '
    'Do not change the story tone or closing line unless asked. Keep replies under 80 words.'
)


# An action only runs when the person's message is about it. Small local models otherwise
# "helpfully" change the song, format or tone unasked (measured: qwen2.5vl:3b swapped the
# music for an invented title when asked only to make the edit faster).
TOPICS = {
    'set_pace': r'fast|slow|pace|pacing|intens|calm|chill|energ|hype|hyper|quick|rapid|tempo|cut|speed|relax|aggressive|mellow',
    'set_length': r'\d|second|minute|length|long|short|duration',
    'set_look': r'look|colou?r|grade|grading|mono|black and white|b&w|punchy|vivid|cinematic|clean|warm|cool|saturat|contrast|original',
    'set_tone': r'tone|christian|faith|christ|god|jesus|neutral|subtle|message|story|spiritual|gospel',
    'set_closing_line': r'closing|line|ending|end text|text|quote|caption|words|message|title|says?',
    'set_brief': r'brief|feel|feeling|mood|vibe|style|story|theme|about',
    'set_music': r'song|music|track|soundtrack|audio|beat|tune|http|www\.|spotify|youtu',
    'set_format': r'format|short|tiktok|reel|instagram|youtube|vertical|portrait|landscape|1080|1440|60 ?fps|30 ?fps|export for',
    'set_slow_motion': r'slow|slo-?mo|smooth|interpolat|frame',
    'set_swishes': r'swish|whoosh|sound|sfx|effect',
    'set_motion_blur': r'blur',
    'move_shot': r'shot|clip|move|earlier|later|order|swap|switch',
    'swap_shot': r'shot|clip|swap|replace|change|different|boring|weak|better',
    'make': r'preview|render|make|create|show|export|version|try|again|go|generate|draft|final|see|build|redo',
}


def requested(action, message):
    return message is None or re.search(TOPICS[action], message.lower()) is not None


def validate_actions(actions, state, message=None):
    """(accepted, rejected): accepted = [(action, value)], rejected = [(action, value, reason)].

    With ``message`` (the person's words), actions on topics they did not mention are rejected.
    """
    accepted, rejected = [], []
    tones = set(state.get('tones', []))
    shots = int(state.get('shot_count') or 0)
    if not isinstance(actions, list):
        return [], [('?', '', 'actions were not a list')]
    for entry in actions[:6]:
        if not isinstance(entry, dict) or not isinstance(entry.get('action'), str) or \
                not isinstance(entry.get('value'), str):
            rejected.append(('?', '', 'malformed action')); continue
        action, value = entry['action'], entry['value'].strip()
        word = value.lower()
        reason = None
        if action not in ACTIONS:
            reason = 'unknown action'
        elif action == 'set_pace':
            reason = None if word in PACES else 'unknown pace'; value = word
        elif action == 'set_length':
            number = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds)?', word)
            reason = None if number and 5 <= float(number.group(1)) <= 600 else 'length must be 5-600 seconds'
            value = number.group(1) if number else value
        elif action == 'set_look':
            reason = None if word in LOOKS else 'unknown look'; value = word
        elif action == 'set_tone':
            reason = None if word in tones else 'unknown tone'; value = word
        elif action == 'set_closing_line':
            reason = None if len(value) <= 140 and '\x00' not in value else 'closing line is too long'
        elif action == 'set_brief':
            reason = None if 0 < len(value) <= 500 else 'brief must be 1-500 characters'
        elif action == 'set_music':
            reason = None if 0 < len(value) <= 500 else 'say which song'
        elif action == 'set_format':
            reason = None if word in PRESETS else 'unknown format'; value = word
        elif action == 'set_slow_motion':
            reason = None if word in SLOW_MOTION else 'unknown slow-motion mode'; value = word
        elif action in ('set_swishes', 'set_motion_blur'):
            reason = None if word in SWITCH else 'use on or off'; value = word
        elif action == 'move_shot':
            match = re.fullmatch(r'(?:shot\s*)?(\d+)\s+(earlier|later)', word)
            if not match:
                reason = 'say e.g. "3 earlier"'
            elif not shots or not 1 <= int(match.group(1)) <= shots:
                reason = 'no such shot'
            elif (match.group(2) == 'earlier' and int(match.group(1)) == 1) or \
                    (match.group(2) == 'later' and int(match.group(1)) == shots):
                reason = 'shot is already at that end'
            value = word
        elif action == 'swap_shot':
            match = re.fullmatch(r'(?:shot\s*)?(\d+)', word)
            reason = None if match and shots and 1 <= int(match.group(1)) <= shots else 'no such shot'
            value = match.group(1) if match else value
        elif action == 'make':
            reason = None if word in MAKE else 'unknown render'; value = word
            if word == 'final' and not state.get('has_preview'):
                reason = 'make a preview first'
        if reason is None and not requested(action, message):
            reason = 'not asked for'
        (rejected.append((action, value, reason)) if reason else accepted.append((action, value)))
    # One render at most, and it runs after every settings change.
    makes = [a for a in accepted if a[0] == 'make']
    accepted = [a for a in accepted if a[0] != 'make'] + makes[-1:]
    return accepted, rejected


class EditChat:
    """Conversation with a director (LocalDirector or ClaudeDirector) through its validated JSON call."""

    def __init__(self, director):
        self.director = director
        self.history = []          # [(role, text)]

    def prompt(self, message, state):
        state = dict(state, actions=ACTIONS)
        turns = '\n'.join(f'{"Person" if role == "user" else "Director"}: {text}'
                          for role, text in self.history[-2*MAX_TURNS:])
        return (f'State: {json.dumps(state, ensure_ascii=False)}\n'
                + (f'Conversation so far:\n{turns}\n' if turns else '')
                + f'Person: {message[:2000]}')

    def ask(self, message, state):
        """Returns dict(reply, actions=[(action, value)], rejected=[...], model)."""
        content = [{'type': 'text', 'text': self.prompt(message, state)}]
        answer, response = self.director._call(self.director._request(CHAT_SYSTEM, CHAT_SCHEMA, content), 'chat reply')
        if not isinstance(answer, dict) or not isinstance(answer.get('reply'), str):
            raise ValueError('The director replied without a message')
        reply = answer['reply'].strip()[:1200] or '(no reply)'
        accepted, rejected = validate_actions(answer.get('actions', []), state, message)
        self.history += [('user', message[:2000]), ('assistant', reply)]
        return dict(reply=reply, actions=accepted, rejected=rejected,
                    model=getattr(response, 'model', getattr(self.director, 'model', None)))
