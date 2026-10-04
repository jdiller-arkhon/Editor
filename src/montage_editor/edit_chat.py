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
MAKE = ('preview', 'montage', 'final', 'render', 'formats')
SWITCH = ('on', 'off')
TREATMENTS = ('slow motion', 'punch', 'straight')
CUTS = ('cut', 'push_left', 'push_right', 'zoom', 'blur', 'dissolve')
MAX_TURNS = 8
# Named directing styles: each is a bundle of the settings below, applied through the same controls.
STYLES = {
    'hype': dict(set_pace='fast', set_look='punchy', set_slow_motion='motion', set_swishes='on', set_beat_fx='on',
                 set_motion_blur='on'),
    'cinematic': dict(set_pace='balanced', set_look='film', set_slow_motion='motion', set_swishes='on',
                      set_beat_fx='off', set_motion_blur='on'),
    'chill': dict(set_pace='calm', set_look='clean', set_slow_motion='motion', set_swishes='off', set_beat_fx='off'),
    'raw': dict(set_pace='fast', set_look='none', set_swishes='off', set_beat_fx='off', set_motion_blur='off'),
}

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
    'set_beat_fx': 'flash, colour split and shake on drops and loud downbeats: on/off',
    'apply_style': 'a whole directing style: ' + '/'.join(STYLES) + ' (hype = fast, punchy, beat FX; '
                   'cinematic = film grade, smooth slow motion; chill = calm and clean; raw = fast, no effects)',
    'set_shot': 'shot number and treatment, e.g. "4 slow motion", "2 punch" (beat punch-ins) or "6 straight"',
    'set_cut': 'shot number and the transition out of it, e.g. "5 dissolve"; one of ' + '/'.join(CUTS),
    'make': 'preview (fast draft) / montage (full new render) / final (render the previewed edit) / '
            'render (render the current edited timeline) / formats (deliver the edit for every platform)',
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
    'Do not change the story tone or closing line unless asked. Keep replies under 80 words.\n'
    'Examples (person -> actions):\n'
    '"make it faster" -> set_pace fast\n'
    '"black and white, then show me" -> set_look mono; make preview\n'
    '"make it hype" -> apply_style hype\n'
    '"shot 3 is boring" -> swap_shot 3\n'
    '"slow-mo on shot 4" -> set_shot "4 slow motion"\n'
    '"dissolve out of shot 5" -> set_cut "5 dissolve"\n'
    '"I made changes, render it" -> make render\n'
    '"export for every platform" -> make formats\n'
    '"why open with that shot?" -> no actions; explain using state.shots'
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
    'make': r'preview|render|make|create|show|export|version|try|again|go|generate|draft|final|see|build|redo|platform|format|everywhere',
    'set_beat_fx': r'beat|flash|fx|effect|split|shake|glitch|hype|intens|energ',
    'apply_style': r'style|hype|cinematic|chill|calm|raw|energ|vibe|feel|mood|like a|kaiser|montage',
    'set_shot': r'slow|slo-?mo|punch|zoom|straight|normal|speed|ramp|shot',
    'set_cut': r'transition|dissolve|cut|push|zoom|blur|fade|blend|between|out of|into|after',
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
        elif action == 'apply_style':
            reason = None if word in STYLES else 'unknown style'; value = word
        elif action == 'set_shot':
            match = re.fullmatch(r'(?:shot\s*)?(\d+)\s+(slow[- ]?mo(?:tion)?|punch(?:-ins?)?|straight|normal)', word)
            if not match:
                reason = 'say e.g. "4 slow motion"'
            elif not shots or not 1 <= int(match.group(1)) <= shots:
                reason = 'no such shot'
            else:
                kind = match.group(2)
                value = f"{match.group(1)} {'slow motion' if kind.startswith('slow') else 'punch' if kind.startswith('punch') else 'straight'}"
        elif action == 'set_cut':
            match = re.fullmatch(r'(?:shot\s*)?(\d+)\s+([a-z_ ]+)', word)
            kind = match.group(2).strip().replace(' ', '_') if match else ''
            if not match or kind not in CUTS:
                reason = 'say e.g. "5 dissolve"'
            elif not shots or not 1 <= int(match.group(1)) < shots:
                reason = 'no transition out of that shot'
            else:
                value = f'{match.group(1)} {kind}'
        elif action in ('set_swishes', 'set_motion_blur', 'set_beat_fx'):
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
            if word in ('render', 'formats') and not shots:
                reason = 'create a montage first'
        if reason is None and not requested(action, message):
            reason = 'not asked for'
        (rejected.append((action, value, reason)) if reason else accepted.append((action, value)))
    # One render at most, and it runs after every settings change.
    makes = [a for a in accepted if a[0] == 'make']
    accepted = [a for a in accepted if a[0] != 'make'] + makes[-1:]
    return accepted, rejected


URL = re.compile(r'(?:https?://|www\.|youtu\.be/|open\.spotify\.com/|spotify:)\S+', re.I)


def ground(accepted, rejected, message, state):
    """The person's literal words win over a small model's paraphrase.

    Measured with qwen3.5:9b: "make it 45 seconds" came back as set_length "]}", a pasted song
    link was dropped, and "film look" became "cinematic". When the message itself names a value
    for an action the model chose (or, for links, plainly asks for one), that value is used.
    Returns (accepted, rejected, notes).
    """
    text = (message or '').lower()
    accepted, notes = list(accepted), []
    chosen = {a for a, _ in accepted}

    def named(options):
        hits = [o for o in options if re.search(rf'\b{re.escape(o)}\b', text)]
        return hits[0] if len(hits) == 1 else None

    def put(action, value, why):
        nonlocal accepted
        if any(a == action and v == value for a, v in accepted):
            return
        accepted = [(a, v) for a, v in accepted if a != action]
        accepted.insert(len([a for a in accepted if a[0] != 'make']), (action, value))
        notes.append(f'{action} "{value}" taken from your words ({why})')
    # Values the model got wrong for an action it did pick.
    for action, value, reason in list(rejected):
        if action == 'set_length':
            number = re.search(r'\b(\d{1,3}(?:\.\d+)?)\s*(?:s\b|sec|second)', text)
            if number and 5 <= float(number.group(1)) <= 600:
                put('set_length', number.group(1), 'seconds'); rejected.remove((action, value, reason))
    look, pace, style = named(LOOKS), named(PACES), named(STYLES)
    if 'set_look' in chosen and look and look != 'none':
        put('set_look', look, 'look named')
    if 'set_pace' in chosen and pace:
        put('set_pace', pace, 'pace named')
    if 'apply_style' in chosen and style:
        put('apply_style', style, 'style named')
    link = URL.search(message or '')
    if link and 'set_music' not in chosen and re.search(r'\b(song|music|track|soundtrack|audio|tune)\b', text):
        put('set_music', link.group(0).rstrip('.,)'), 'link pasted')
    elif link and 'set_music' in chosen:
        put('set_music', link.group(0).rstrip('.,)'), 'link pasted')
    return accepted, rejected, notes


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

    def ask(self, message, state, sheet=None):
        """Returns dict(reply, actions=[(action, value)], rejected=[...], model).

        ``sheet``: optional JPEG contact sheet of the current edit (shots labelled S1..Sn), so the
        director can judge the actual footage when asked for feedback.
        """
        text = self.prompt(message, state)
        if sheet:
            text += ('\nThe image is a contact sheet of the current edit: one key frame per shot, labelled '
                     'S1..Sn in order. Base any judgement of shots on it.')
        content = [{'type': 'text', 'text': text}]
        if sheet:
            from .vision_director import image_block
            content.append(image_block(sheet))
        answer, response = self.director._call(self.director._request(CHAT_SYSTEM, CHAT_SCHEMA, content), 'chat reply')
        if not isinstance(answer, dict) or not isinstance(answer.get('reply'), str):
            raise ValueError('The director replied without a message')
        reply = answer['reply'].strip()[:1200] or '(no reply)'
        accepted, rejected = validate_actions(answer.get('actions', []), state, message)
        accepted, rejected, grounded = ground(accepted, rejected, message, state)
        self.history += [('user', message[:2000]), ('assistant', reply)]
        return dict(reply=reply, actions=accepted, rejected=rejected, grounded=grounded,
                    model=getattr(response, 'model', getattr(self.director, 'model', None)))


LOOK = re.compile(r'look at|take a look|have a look|watch|see |review|feedback|critique|opinion|rate|rating|how (is|does|good)|improve|better|'
                  r'weak|boring|strong|best|worst|shot \d|which shot|what do you think', re.I)


def wants_a_look(message):
    """Whether the person is asking the director to judge the current edit."""
    return LOOK.search(message or '') is not None


def contact_sheet(timeline, limit=24):
    """JPEG with one labelled key frame per shot (S1..Sn) of ``timeline``."""
    from .editing import source_offset
    from .vision_director import labelled_frame, tile
    frames = []
    for i, clip in enumerate(timeline.clips[:limit]):
        at = clip.anchor_output if clip.anchor_output is not None else clip.duration/2
        frames.append(labelled_frame(clip.source, clip.start+source_offset(at, clip.duration, clip.speed_profile), f'S{i+1}'))
    return tile(frames, 6)
