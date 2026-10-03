"""Claude vision editor: watches sampled frames of candidate moments and judges them.

The local engine finds activity candidates and owns all timing (beat grid, retiming,
rendering). Claude sees a numbered six-frame strip (3 s) around each reviewed candidate
and returns a validated judgement: highlight strength, what kind of moment it is, whether
it is usable footage (not a menu/loading/scoreboard), which frame is the peak, and a
preferred story order. A second pass reviews the planned cut as a contact sheet and may
swap weak shots for unused alternates (including the closing shot). Nothing it returns
is executed; IDs, enums and ranges are validated and unknown values are rejected before
they can reach the renderer.

Privacy: this sends downscaled frames of the user's footage to Anthropic's API. It is
strictly opt-in. Filenames and paths are never sent.
"""
import base64
import json
import logging
import subprocess

from . import jobs

import numpy as np

LOG = logging.getLogger(__name__)

MODEL = 'claude-opus-5-5'
DIRECTOR_MODEL = 'claude-fable-5-1'   # Anthropic's most capable model, for full edit direction
MODELS = {'claude-fable-5-1': 'Claude Fable 5.1 • most capable', 'claude-opus-5-5': 'Claude Opus 5.5 • faster, lower cost'}
TREATMENTS = ('straight', 'ramp', 'punch')
TRANSITIONS_OUT = ('cut', 'push_left', 'push_right', 'zoom', 'blur', 'dissolve')
FALLBACK_BETA = 'server-side-fallback-2026-07-01'
EVENTS = ('elimination', 'multi_elimination', 'clutch', 'objective', 'outplay', 'fight', 'movement',
          'cinematic', 'setup', 'death', 'menu_or_loading', 'other')
STRIP_FRAMES, STRIP_STEP = 6, .5
TILE = (256, 144)

SCHEMA = {
    'type': 'object',
    'properties': {
        'moments': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {
                'id': {'type': 'integer'},
                'highlight': {'type': 'integer', 'description': '0 (nothing happens) to 10 (montage-worthy peak)'},
                'event': {'type': 'string', 'enum': list(EVENTS)},
                'usable': {'type': 'boolean'},
                'peak_frame': {'type': 'integer', 'description': 'strip frame 1-6 where the key action lands'},
                'note': {'type': 'string'},
            },
            'required': ['id', 'highlight', 'event', 'usable', 'peak_frame', 'note'],
            'additionalProperties': False}},
        'sequence': {'type': 'array', 'items': {'type': 'integer'},
                     'description': 'Usable moment IDs in preferred montage order, opening to climax'},
        'rationale': {'type': 'string'},
    },
    'required': ['moments', 'sequence', 'rationale'],
    'additionalProperties': False,
}

REVIEW_SCHEMA = {
    'type': 'object',
    'properties': {
        'swaps': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {'shot': {'type': 'integer'}, 'alternate': {'type': 'integer'},
                           'reason': {'type': 'string'}},
            'required': ['shot', 'alternate', 'reason'], 'additionalProperties': False}},
        'notes': {'type': 'string'},
    },
    'required': ['swaps', 'notes'],
    'additionalProperties': False,
}
MAX_SWAPS = 4

DIRECT_SCHEMA = {
    'type': 'object',
    'properties': {
        'slots': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {'slot': {'type': 'integer'}, 'moment': {'type': 'integer'},
                           'treatment': {'type': 'string', 'enum': list(TREATMENTS)},
                           'transition_out': {'type': 'string', 'enum': list(TRANSITIONS_OUT)}},
            'required': ['slot', 'moment', 'treatment', 'transition_out'], 'additionalProperties': False}},
        'arc': {'type': 'string'},
    },
    'required': ['slots', 'arc'],
    'additionalProperties': False,
}

DIRECT_SYSTEM = (
    'You are the director of a top-tier gaming montage. The cut points are fixed to the music: the text '
    'lists every slot S1..Sn with its time, length in beats, intensity 0-1 and musical marks (build, '
    'drop, rise, phrase). The image shows candidate moments M0..Mm at their key frame; the text gives '
    'each one\'s judged highlight score, event and note. Assign one distinct moment to each slot and '
    'choose a treatment and the transition out of the slot. Craft rules of top editors: open with a '
    'strong, readable moment; build intensity; put the biggest moment on the drop or the most intense '
    'slot; treatment "ramp" (slow motion through the hit) only on 1 s+ slots that land a decisive '
    'moment, sparingly, never twice in a row; "punch" (beat punch-ins) for energetic slots and builds; '
    '"straight" otherwise. Mostly hard cuts on beats; reserve push/zoom transitions for phrase changes, '
    'drops and lifts, dissolve for the calm ending; "blur" rarely. Avoid placing near-identical views '
    'next to each other. End on a calm, clean shot that suits a closing line. Never invent slot or '
    'moment numbers. "arc": one sentence describing the story of the edit.'
)
# The editing playbook. Prompts ask for it; ``enforce_playbook`` guarantees it whatever a
# (possibly small, local) model returns. Each rule is standard montage craft:
PLAYBOOK = (
    'hook: the opening shot is one of the stronger moments (viewers decide in seconds)',
    'climax: the strongest moment lands on the drop or the most intense slot',
    'hard cuts on the beat by default; motivated transitions only into a new phrase, build, rise or drop',
    'dissolve only into the final shot; at most one blur blend',
    'slow motion (ramp) is rare: at most one shot in four, never twice in a row, never on the final shot',
    'punch-ins only on energetic music (intensity >= 0.35), never on the final shot',
    'the final shot is played straight so the closing line reads cleanly',
)


DIRECT_SYSTEM_LOCAL = DIRECT_SYSTEM+' Playbook (enforced afterwards): '+'; '.join(PLAYBOOK)+'.'

REVIEW_SYSTEM = (
    'You are the senior editor reviewing a gaming montage cut before render. Image 1 shows each '
    'planned shot S1..Sn at its key moment, in order; the text gives each shot\'s place in the song '
    '(intensity 0-1, and whether it starts a phrase or a lift). Image 2 shows unused alternate moments '
    'A0..Am with their judged highlight score. Propose at most four swaps where an alternate is clearly '
    'better: the biggest moments belong on the most intense music and lifts, weak or repetitive shots '
    'should go, and the final shot should be a calmer, clean image that suits a closing line. Shot '
    'timing and music stay fixed; you only choose footage. Return no swaps if the cut is already '
    'strong. Never invent shot or alternate numbers. Keep reasons under 20 words.'
)

SYSTEM = (
    'You are the senior editor on a high-end gaming montage. For each candidate moment you see '
    'one image: six numbered frames, 0.5 s apart, left-to-right then top-to-bottom, around the '
    'measured activity peak. Judge what a top '
    'montage editor would keep: decisive eliminations, multi-kills, clutches, outplays, objective '
    'plays, striking movement or cinematic shots. Score highlight 0-10 honestly; most gameplay is '
    'ordinary, so reserve 8-10 for moments that would make a viewer react. Mark menus, loading '
    'screens, scoreboards, spectator/killcam UI or black frames as usable=false with event '
    'menu_or_loading. Only describe what is visible: if you cannot tell whether an elimination '
    'happened, say so in the note and score accordingly rather than guessing. Pick peak_frame as the frame '
    'where the key action lands. Then give a sequence of usable IDs that builds from a strong opener '
    'toward the biggest moments for the climax. Never invent IDs. Keep notes under 20 words.'
)


def strip_window(time, duration):
    """Start of the 3 s strip around ``time``, kept inside the source."""
    span = STRIP_STEP*STRIP_FRAMES
    return min(max(0.0, time-1.5), max(0.0, duration-span))


def frame_time(time, duration, frame):
    return strip_window(time, duration)+STRIP_STEP*(frame-1)


def _jpeg(raw, width, height):
    jpeg = jobs.run(['ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height}',
                           '-i', 'pipe:0', '-frames:v', '1', '-q:v', '5', '-f', 'image2pipe', '-c:v', 'mjpeg',
                           'pipe:1'], input=raw).stdout
    if not jpeg.startswith(b'\xff\xd8'):
        raise ValueError('Could not encode a review image')
    return jpeg


def labelled_frame(source, at, text):
    """One RGB tile at ``at`` seconds with a burned-in label (letterboxed to TILE)."""
    w, h = TILE
    vf = (f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,'
          f"drawtext=text='{text}':x=6:y=6:fontsize=18:fontcolor=yellow:box=1:boxcolor=black@0.65")
    raw = jobs.run(['ffmpeg', '-v', 'error', '-ss', f'{max(0.0, at):.3f}', '-i', source, '-frames:v', '1',
                          '-vf', vf, '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1']).stdout
    if len(raw) != w*h*3:
        raise ValueError('Could not decode a review frame')
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3)


def tile(frames, columns):
    w, h = TILE
    rows = (len(frames)+columns-1)//columns
    sheet = np.zeros((rows*h, columns*w, 3), np.uint8)
    for i, frame in enumerate(frames):
        sheet[(i//columns)*h:(i//columns+1)*h, (i % columns)*w:(i % columns+1)*w] = frame
    return _jpeg(sheet.tobytes(), columns*w, rows*h)


def strip(candidate):
    """Six numbered frames, 0.5 s apart, as one 3x2 JPEG."""
    start = strip_window(candidate['time'], candidate['source_duration'])
    limit = max(0.0, candidate['source_duration']-.05)
    return tile([labelled_frame(candidate['source'], min(limit, start+STRIP_STEP*k), str(k+1))
                 for k in range(STRIP_FRAMES)], 3)


def image_block(jpeg):
    return {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg',
                                        'data': base64.standard_b64encode(jpeg).decode('ascii')}}


def review_pool(candidates, limit):
    """Strongest activity first, interleaved across sources so one clip cannot fill the pool."""
    by_source = {}
    for candidate in sorted((c for c in candidates if not c.get('exclude')),
                            key=lambda c: (-c['score'], c['source'], c['time'])):
        by_source.setdefault(candidate['source'], []).append(candidate)
    pool, queues = [], list(by_source.values())
    while len(pool) < limit and any(queues):
        for queue in queues:
            if queue and len(pool) < limit:
                pool.append(queue.pop(0))
    return pool


def validate_review(review, count):
    if not isinstance(review, dict) or not isinstance(review.get('moments'), list):
        raise ValueError('AI review has no moments')
    moments, seen = {}, set()
    for moment in review['moments']:
        try:
            ident = moment['id']
            valid = (isinstance(ident, int) and not isinstance(ident, bool) and 0 <= ident < count and
                     ident not in seen and isinstance(moment['highlight'], int) and
                     0 <= moment['highlight'] <= 10 and moment['event'] in EVENTS and
                     isinstance(moment['usable'], bool) and isinstance(moment['peak_frame'], int) and
                     not isinstance(moment['peak_frame'], bool) and 1 <= moment['peak_frame'] <= STRIP_FRAMES and
                     isinstance(moment['note'], str))
        except (KeyError, TypeError):
            valid = False
        if not valid:
            raise ValueError('AI review contains an invalid or unknown moment')
        seen.add(ident)
        moments[ident] = dict(moment, note=moment['note'][:200])
    if not moments:
        raise ValueError('AI review judged no moments')
    sequence = []
    for ident in review.get('sequence', []):
        if isinstance(ident, int) and ident in moments and moments[ident]['usable'] and ident not in sequence:
            sequence.append(ident)
    rationale = str(review.get('rationale', ''))[:1000]
    return moments, sequence, rationale


def apply_review(candidates, pool, moments, sequence, judge='claude vision review', weight=1.0):
    """Re-score reviewed moments, quarantine unusable footage, de-emphasise unreviewed ones."""
    reviewed = {(c['source'], c['time']): i for i, c in enumerate(pool)}
    order = {ident: rank for rank, ident in enumerate(sequence)}
    result = []
    for candidate in candidates:
        index = reviewed.get((candidate['source'], candidate['time']))
        if index is None or index not in moments:
            result.append(dict(candidate, score=candidate['score']*.3, judged_by='activity heuristic'))
            continue
        moment = moments[index]
        time = min(frame_time(candidate['time'], candidate['source_duration'], moment['peak_frame']),
                   candidate['source_duration'])
        # weight < 1 keeps part of the measured activity score (for less reliable judges).
        entry = dict(candidate, time=time, score=weight*moment['highlight']/10+(1-weight)*candidate['score'],
                     event=moment['event'],
                     ai_note=moment['note'], judged_by=judge,
                     activity_score=candidate['score'])
        if not moment['usable'] or moment['event'] == 'menu_or_loading':
            # Excluded spans are pre-reserved so no clip, not even a fallback fill, covers them.
            entry.update(score=0.0, exclude=True)
        if index in order:
            entry['story_rank'] = order[index]
        result.append(entry)
    return result


class ClaudeDirector:
    """Opt-in: frames of the user's footage are sent to Anthropic's API."""
    label = 'Claude'

    def __init__(self, model=MODEL, client=None, effort='high', limit=24, director_model=DIRECTOR_MODEL,
                 direct_edit=True):
        self.model, self.effort, self.limit = model, effort, limit
        self.director_model, self.direct_edit = director_model, direct_edit
        self.strict = False   # True: the engine enforces PLAYBOOK on the director's plan
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def request(self, pool, brief):
        content = [{'type': 'text', 'text': f'Creative brief: {brief[:2000] or "none"}\n'
                    f'{len(pool)} candidate moments follow. Sources are anonymous IDs.'}]
        sources = {}
        for ident, candidate in enumerate(pool):
            source = sources.setdefault(candidate['source'], len(sources))
            content.append({'type': 'text', 'text': (
                f'Candidate {ident}: source S{source}, t={candidate["time"]:.2f}s, '
                f'measured activity {candidate["score"]:.2f} (motion/loudness, not meaning).')})
            content.append(image_block(strip(candidate)))
        return self._request(SYSTEM, SCHEMA, content)

    def _request(self, system, schema, content):
        return dict(model=self.model, max_tokens=16000, betas=[FALLBACK_BETA], fallbacks='default',
                    thinking={'type': 'adaptive'}, output_config={
                        'effort': self.effort, 'format': {'type': 'json_schema', 'schema': schema}},
                    system=system, messages=[{'role': 'user', 'content': content}])

    def _call(self, request, what):
        """Send one request; return (parsed JSON, response). Errors become clear ValueErrors."""
        try:
            import anthropic
        except ImportError:
            if self._client is None:
                raise ValueError("Claude editor needs the Anthropic SDK: pip install -e '.[ai]'") from None
            anthropic = None
        if anthropic is None:
            response = self.client.beta.messages.create(**request)
        else:
            missing = (anthropic.AuthenticationError,) + ((anthropic.CredentialsError,)
                                                         if hasattr(anthropic, 'CredentialsError') else ())
            try:
                response = self.client.beta.messages.create(**request)
            except missing as error:
                raise ValueError('Claude editor needs Anthropic credentials: set ANTHROPIC_API_KEY '
                                 'or run `ant auth login`') from error
            except anthropic.APIConnectionError as error:
                raise ValueError('Could not reach the Anthropic API for the Claude editor') from error
            except anthropic.APIStatusError as error:
                raise ValueError(f'Claude editor request failed ({error.status_code}): {error.message}') from error
            except TypeError as error:
                # The SDK reports missing credentials this way at request time.
                if 'authentication' not in str(error).lower():
                    raise
                raise ValueError('Claude editor needs Anthropic credentials: set ANTHROPIC_API_KEY '
                                 'or run `ant auth login`') from error
        if response.stop_reason == 'refusal':
            raise ValueError(f'Claude declined the {what}')
        if response.stop_reason == 'max_tokens':
            raise ValueError(f'Claude {what} was cut off before completing')
        text = next((block.text for block in response.content if block.type == 'text'), None)
        try:
            return (json.loads(text) if text else None), response
        except json.JSONDecodeError as error:
            raise ValueError(f'Claude {what} was not valid JSON') from error

    @staticmethod
    def _usage(response):
        usage = getattr(response, 'usage', None)
        return None if usage is None else dict(input_tokens=getattr(usage, 'input_tokens', None),
                                               output_tokens=getattr(usage, 'output_tokens', None))

    def review(self, candidates, brief=''):
        pool = review_pool(candidates, self.limit)
        if not pool:
            raise ValueError('No candidate moments to review')
        LOG.info('Sending %d candidate strips to %s for review', len(pool), self.model)
        review, response = self._call(self.request(pool, brief), 'moment review')
        moments, sequence, rationale = validate_review(review, len(pool))
        report = dict(provider='anthropic', model=getattr(response, 'model', self.model), reviewed=len(pool),
                      images_sent=len(pool), frames_per_image=STRIP_FRAMES, rationale=rationale,
                      usable=sum(m['usable'] for m in moments.values()),
                      events={e: sum(m['event'] == e for m in moments.values()) for e in EVENTS
                              if any(m['event'] == e for m in moments.values())},
                      evidence='six-frame 3 s strip per reviewed candidate; timing remains measured locally',
                      usage=self._usage(response))
        return apply_review(candidates, pool, moments, sequence), report

    def review_cut(self, timeline, candidates, music, brief=''):
        """Second pass: Claude reviews the planned cut and may swap shots for alternates."""
        from .editing import source_offset
        from .pipeline import swap_shots
        clips = timeline.clips[:20]
        covered = lambda c: any(o.source == c['source'] and o.start <= c['time'] <= o.start+o.duration
                                for o in timeline.clips)
        alternates = sorted((c for c in candidates if not c.get('exclude') and not covered(c)),
                            key=lambda c: (-c['score'], c['source'], c['time']))[:8]
        if not alternates:
            return timeline, dict(swaps_applied=[], swaps_rejected=[], notes='no unused alternates')
        energy = np.asarray(music.get('energy', []), dtype=float)
        hop = music.get('hop_seconds', .05)
        scale = (float(np.quantile(energy, .05)), float(np.quantile(energy, .95))) if len(energy) else (0, 1)
        phrases = {round(p['time'], 2): p['kinds'] for p in music.get('phrases', [])}
        lines, frames, position = [], [], 0.0
        for i, clip in enumerate(clips):
            window = energy[int(position/hop):int((position+clip.duration)/hop)+1]
            level = float(np.clip((window.mean()-scale[0])/max(scale[1]-scale[0], 1e-9), 0, 1)) if len(window) else .5
            kinds = next((k for t, k in phrases.items() if abs(t-position) < .05), [])
            lines.append(f'S{i+1}: {position:.1f}-{position+clip.duration:.1f}s, intensity {level:.2f}'
                         + (f', starts {"/".join(kinds)}' if kinds else '')
                         + (', final shot (closing line)' if i == len(timeline.clips)-1 else ''))
            target = clip.anchor_output if clip.anchor_output is not None else clip.duration/2
            frames.append(labelled_frame(clip.source, clip.start+source_offset(target, clip.duration, clip.speed_profile),
                                         f'S{i+1}'))
            position += clip.duration
        alt_frames = [labelled_frame(c['source'], c['time'], f'A{j}') for j, c in enumerate(alternates)]
        alt_lines = [f'A{j}: highlight {c["score"]:.2f}' + (f', {c["event"]}' if c.get('event') else '')
                     + (f' - {c["ai_note"]}' if c.get('ai_note') else '') for j, c in enumerate(alternates)]
        content = [{'type': 'text', 'text': f'Creative brief: {brief[:2000] or "none"}\nPlanned shots:\n'
                    + '\n'.join(lines) + '\nAlternates:\n' + '\n'.join(alt_lines)},
                   image_block(tile(frames, 5)), image_block(tile(alt_frames, 4))]
        review, response = self._call(self._request(REVIEW_SYSTEM, REVIEW_SCHEMA, content), 'cut review')
        swaps = validate_swaps(review, len(clips), len(alternates))
        excluded = [c for c in candidates if c.get('exclude')]
        result, applied, rejected = swap_shots(timeline, [(i-1, alternates[a]) for i, a, _ in swaps], excluded)
        reasons = {i: r for i, _, r in swaps}
        for entry in applied:
            entry['reason'] = reasons[entry['shot']]
        return result, dict(swaps_applied=applied, swaps_rejected=rejected,
                            notes=str(review.get('notes', ''))[:1000], usage=self._usage(response))


    def plan_edit(self, timeline, candidates, music, brief=''):
        """Claude directs the whole edit on the fixed beat slots; the engine executes and checks it."""
        from .pipeline import apply_plan
        pool = sorted((c for c in candidates if not c.get('exclude')), key=lambda c: (-c['score'], c['source'], c['time']))
        pool = pool[:min(40, max(len(timeline.clips)*2, 12))]
        if len(pool) < 2:
            return timeline, dict(applied=[], notes='too few moments to direct')
        frames = [labelled_frame(c['source'], c['time'], f'M{j}') for j, c in enumerate(pool)]
        moment_lines = [f'M{j}: score {c["score"]:.2f}' + (f', {c["event"]}' if c.get('event') else '')
                        + (f' - {c["ai_note"]}' if c.get('ai_note') else '') for j, c in enumerate(pool)]
        content = [{'type': 'text', 'text': f'Creative brief: {brief[:2000] or "none"}\nTempo: '
                    f'{music.get("tempo_bpm") or "unknown"} BPM\nSlots:\n' + '\n'.join(_slot_lines(timeline, music))
                    + '\nMoments:\n' + '\n'.join(moment_lines)},
                   image_block(tile(frames, 6))]
        model = self.director_model
        request = dict(self._request(DIRECT_SYSTEM_LOCAL if self.strict else DIRECT_SYSTEM, DIRECT_SCHEMA, content),
                       model=model)
        plan, response = self._call(request, 'edit direction')
        assignments, arc = validate_direction(plan, len(timeline.clips), len(pool))
        corrections = []
        if self.strict:
            assignments, corrections = enforce_playbook(assignments, slot_facts(timeline, music),
                                                        {j: c['score'] for j, c in enumerate(pool)})
        excluded = [c for c in candidates if c.get('exclude')]
        result, applied, notes = apply_plan(timeline, [(s, pool[m], t, o) for s, m, t, o in assignments], music, excluded)
        return result, dict(model=getattr(response, 'model', model), arc=arc, slots=len(timeline.clips),
                            planned=len(assignments), applied=[a+1 for a in applied], notes=notes,
                            treatments={t: sum(x[2] == t for x in assignments) for t in TREATMENTS},
                            playbook=corrections if self.strict else None,
                            usage=self._usage(response))

def validate_swaps(review, shots, alternates):
    if not isinstance(review, dict) or not isinstance(review.get('swaps'), list):
        raise ValueError('Claude cut review has no swaps list')
    result, seen_shots, seen_alts = [], set(), set()
    for swap in review['swaps']:
        try:
            shot, alt, reason = swap['shot'], swap['alternate'], swap['reason']
            valid = (all(isinstance(v, int) and not isinstance(v, bool) for v in (shot, alt)) and
                     1 <= shot <= shots and 0 <= alt < alternates and isinstance(reason, str) and
                     shot not in seen_shots and alt not in seen_alts)
        except (KeyError, TypeError):
            valid = False
        if not valid:
            raise ValueError('Claude cut review contains an invalid or unknown swap')
        seen_shots.add(shot); seen_alts.add(alt)
        result.append((shot, alt, reason[:200]))
    if len(result) > MAX_SWAPS:
        raise ValueError('Claude cut review proposed too many swaps')
    return result


def validate_direction(plan, slots, moments):
    if not isinstance(plan, dict) or not isinstance(plan.get('slots'), list):
        raise ValueError('Claude edit plan has no slots')
    result, seen_slots, seen_moments = [], set(), set()
    for entry in plan['slots']:
        try:
            slot, moment = entry['slot'], entry['moment']
            valid = (all(isinstance(v, int) and not isinstance(v, bool) for v in (slot, moment)) and
                     1 <= slot <= slots and 0 <= moment < moments and slot not in seen_slots and
                     moment not in seen_moments and entry['treatment'] in TREATMENTS and
                     entry['transition_out'] in TRANSITIONS_OUT)
        except (KeyError, TypeError):
            valid = False
        if not valid:
            raise ValueError('Claude edit plan contains an invalid, duplicate or unknown entry')
        seen_slots.add(slot); seen_moments.add(moment)
        result.append((slot-1, moment, entry['treatment'], entry['transition_out']))
    ramps = sorted(slot for slot, _, treatment, _ in result if treatment == 'ramp')
    if any(b == a+1 for a, b in zip(ramps, ramps[1:])):
        # The prompt forbids back-to-back slow motion; keep the first of each run.
        drop = {b for a, b in zip(ramps, ramps[1:]) if b == a+1}
        result = [(s, m, 'straight' if s in drop else t, o) for s, m, t, o in result]
    return result, str(plan.get('arc', ''))[:400]


def slot_facts(timeline, music):
    """Per slot: intensity 0-1, musical marks and length, for prompts and the playbook."""
    energy = np.asarray(music.get('energy', []), dtype=float)
    hop = music.get('hop_seconds', .05)
    scale = (float(np.quantile(energy, .05)), float(np.quantile(energy, .95))) if len(energy) else (0, 1)
    phrases = [(p['time'], p['kinds']) for p in music.get('phrases', [])]
    facts, position = [], 0.0
    for clip in timeline.clips:
        window = energy[int(position/hop):int((position+clip.duration)/hop)+1]
        level = float(np.clip((window.mean()-scale[0])/max(scale[1]-scale[0], 1e-9), 0, 1)) if len(window) else .5
        marks = sorted({k for t, kinds in phrases if position-.05 <= t < position+clip.duration-.05 for k in kinds})
        facts.append(dict(start=position, duration=clip.duration, level=level, marks=marks))
        position += clip.duration
    return facts


def enforce_playbook(assignments, facts, scores):
    """Apply PLAYBOOK to validated assignments [(slot, moment, treatment, transition_out)].

    ``scores`` maps moment index -> judged score. Returns (assignments, corrections).
    """
    plan = {slot: [moment, treatment, out] for slot, moment, treatment, out in assignments}
    corrections = []
    n = len(facts)
    final = n-1

    def note(rule, slot, change):
        corrections.append(dict(rule=rule, slot=slot+1, change=change))
    # Climax: the best assigned moment goes on the drop (else the most intense slot).
    if len(plan) >= 2:
        drops = [i for i in plan if 'drop' in facts[i]['marks']]
        climax = drops[0] if drops else max(plan, key=lambda i: (facts[i]['level'], -i))
        best = max(plan, key=lambda i: (scores.get(plan[i][0], 0), -i))
        if best != climax and scores.get(plan[best][0], 0) > scores.get(plan[climax][0], 0):
            plan[best][0], plan[climax][0] = plan[climax][0], plan[best][0]
            note('climax', climax, f'moved the strongest moment here from S{best+1}')
    # Hook: the opener should be at least the median assigned moment.
    if 0 in plan and len(plan) >= 3:
        values = sorted(scores.get(m, 0) for m, _, _ in plan.values())
        median = values[len(values)//2]
        if scores.get(plan[0][0], 0) < median:
            options = [i for i in plan if i not in (0, final) and 'drop' not in facts[i]['marks']
                       and scores.get(plan[i][0], 0) >= median and i != max(plan, key=lambda j: scores.get(plan[j][0], 0))]
            if options:
                swap = min(options, key=lambda i: scores.get(plan[i][0], 0))
                plan[0][0], plan[swap][0] = plan[swap][0], plan[0][0]
                note('hook', 0, f'opened with a stronger moment from S{swap+1}')
    # Treatments.
    ramps = 0
    budget = max(1, n//4)
    for i in sorted(plan):
        treatment = plan[i][1]
        if treatment == 'ramp' and (i == final or ramps >= budget or plan.get(i-1, [None, None])[1] == 'ramp'):
            plan[i][1] = 'straight'; note('slow motion', i, 'played straight')
        elif treatment == 'punch' and (i == final or facts[i]['level'] < .35):
            plan[i][1] = 'straight'; note('punch-ins', i, 'played straight')
        ramps += plan[i][1] == 'ramp'
    # Transitions out of slot i lead into slot i+1.
    blurs = 0
    for i in sorted(plan):
        out = plan[i][2]
        if i == final or out == 'cut':
            continue
        into_final = i+1 == final
        motivated = bool(set(facts[i+1]['marks']) & {'phrase', 'grid', 'build', 'rise', 'drop'})
        allowed = (out == 'dissolve' and into_final) or (out != 'dissolve' and motivated and
                                                         (out != 'blur' or blurs == 0))
        if not allowed:
            plan[i][2] = 'cut'; note('transitions', i, f'{out} became a hard cut')
        blurs += plan[i][2] == 'blur'
    return [(i, m, t, o) for i, (m, t, o) in sorted(plan.items())], corrections


def _slot_lines(timeline, music):
    energy = np.asarray(music.get('energy', []), dtype=float)
    hop = music.get('hop_seconds', .05)
    scale = (float(np.quantile(energy, .05)), float(np.quantile(energy, .95))) if len(energy) else (0, 1)
    phrases = [(p['time'], p['kinds']) for p in music.get('phrases', [])]
    period = 60/music['tempo_bpm'] if music.get('tempo_bpm') else None
    lines, position = [], 0.0
    for i, clip in enumerate(timeline.clips):
        window = energy[int(position/hop):int((position+clip.duration)/hop)+1]
        level = float(np.clip((window.mean()-scale[0])/max(scale[1]-scale[0], 1e-9), 0, 1)) if len(window) else .5
        marks = sorted({k for t, kinds in phrases if position-.05 <= t < position+clip.duration-.05 for k in kinds})
        beats = f', {clip.duration/period:.0f} beats' if period else ''
        lines.append(f'S{i+1}: {position:.2f}-{position+clip.duration:.2f}s ({clip.duration:.2f}s{beats}), '
                     f'intensity {level:.2f}' + (f', marks {"/".join(marks)}' if marks else '')
                     + (', FINAL (closing line)' if i == len(timeline.clips)-1 else ''))
        position += clip.duration
    return lines


# ---------------------------------------------------------------------------------------
# Local director: the same prompts, schemas, validation and edit execution, served by a
# vision model running in Ollama on this machine. Footage never leaves the computer.

LOCAL_MODEL = 'qwen2.5vl:7b'
LOCAL_HOST = 'http://127.0.0.1:11434'
# Share of a reviewed moment's score taken from the local model; the rest stays the measured
# activity score. Measured on Xonotic strips (CPU, Q4): qwen2.5vl:7b labelled a death screen
# correctly but called a real fight "movement" with highlight 0, so it does not get the last word.
LOCAL_WEIGHT = .6


def _local_schema(schema):
    """Small local models answer better when asked to describe before they judge."""
    local = json.loads(json.dumps(schema))
    items = local['properties'].get('moments', {}).get('items')
    if items:
        items['properties'] = dict(observations={'type': 'string'}, **items['properties'])
        items['required'] = ['observations']+items['required']
    return local


CHECK_SYSTEM = (
    'You check gameplay clips for a montage editor. Each image is one clip: six numbered frames, 0.5 s '
    'apart (left to right, top to bottom). Look at every frame. For each clip answer the checklist '
    'from what is visible only: observations (one short sentence), overlay_frames (numbers of the '
    'frames where a scoreboard, stats table, menu, death or respawn screen, loading screen or a large '
    'text panel covers the game; [] if none), enemy_visible (another player or opponent appears), '
    'firing (muzzle flashes, projectiles, beams, explosions or impacts), kill (an opponent clearly '
    'dies: gibs, ragdoll, burst, or a kill message), peak_frame (the frame with the most action), '
    'highlight (0-10: how much a viewer would want to see this; ordinary walking is 1-3). If unsure, '
    'answer false. Never invent clip numbers.'
)
CHECK_ITEM = {
    'type': 'object',
    'properties': {
        'id': {'type': 'integer'}, 'observations': {'type': 'string'},
        'overlay_frames': {'type': 'array', 'items': {'type': 'integer', 'minimum': 1, 'maximum': STRIP_FRAMES}},
        'enemy_visible': {'type': 'boolean'}, 'firing': {'type': 'boolean'}, 'kill': {'type': 'boolean'},
        'peak_frame': {'type': 'integer', 'minimum': 1, 'maximum': STRIP_FRAMES},
        'highlight': {'type': 'integer', 'minimum': 0, 'maximum': 10},
    },
    'required': ['id', 'observations', 'overlay_frames', 'enemy_visible', 'firing', 'kill', 'peak_frame', 'highlight'],
    'additionalProperties': False,
}


def checklist_moment(answer):
    """Turn one checklist answer into a standard review judgement (validated by validate_review).

    Unusable when two or more frames are covered by an overlay; the highlight is half the model's
    own score and half a fixed evidence score (2 base, +2 enemy, +2 firing, +4 kill), because small
    models judge single facts more reliably than overall quality.
    """
    if not isinstance(answer, dict):
        return answer
    try:
        overlay = {f for f in answer['overlay_frames'] if isinstance(f, int) and 1 <= f <= STRIP_FRAMES}
        enemy, firing, kill = (answer[k] is True for k in ('enemy_visible', 'firing', 'kill'))
        own, peak = answer['highlight'], answer['peak_frame']
        if not (isinstance(own, int) and isinstance(peak, int)) or isinstance(own, bool) or isinstance(peak, bool):
            raise TypeError
    except (KeyError, TypeError):
        return dict(id=answer.get('id'))           # rejected by validate_review
    usable = len(overlay) < 2
    evidence = 2+2*enemy+2*firing+4*kill
    if usable and peak in overlay:
        peak = min((f for f in range(1, STRIP_FRAMES+1) if f not in overlay), key=lambda f: abs(f-peak))
    event = ('menu_or_loading' if not usable else 'elimination' if kill else
             'fight' if enemy and firing else 'movement')
    highlight = 0 if not usable else int(round(.5*max(0, min(10, own))+.5*evidence))
    return dict(id=answer['id'], highlight=highlight, event=event, usable=usable, peak_frame=peak,
                note=str(answer.get('observations', ''))[:200],
                checklist=dict(overlay_frames=sorted(overlay), enemy_visible=enemy, firing=firing, kill=kill))


class LocalDirector(ClaudeDirector):
    """Vision director backed by a local Ollama model (loopback only, no proxy, no redirects)."""
    label = 'Local AI'

    def __init__(self, model=LOCAL_MODEL, host=LOCAL_HOST, timeout=900, batch=4, num_ctx=8192, weight=LOCAL_WEIGHT,
                 limit=16, think=False, **options):
        from urllib.parse import urlparse
        parsed = urlparse(host)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('The local AI director only talks to Ollama on this computer')
        super().__init__(model=model, client=None, director_model=model, limit=limit, **options)
        self.host, self.timeout, self.batch, self.num_ctx = host.rstrip('/'), timeout, batch, num_ctx
        self.weight, self.think = weight, think
        self.strict = True    # small local models get the playbook enforced, not just requested

    def request(self, pool, brief):
        """Checklist review: one answer per strip is pinned by the schema (small models otherwise skip some)."""
        content = [{'type': 'text', 'text': f'Creative brief: {brief[:500] or "none"}\n'
                    f'{len(pool)} clips follow, in order, ids 0-{len(pool)-1}.'}]
        for ident, candidate in enumerate(pool):
            content.append({'type': 'text', 'text': f'Clip {ident}:'})
            content.append(image_block(strip(candidate)))
        item = json.loads(json.dumps(CHECK_ITEM))
        item['properties']['id'] = {'type': 'integer', 'enum': list(range(len(pool)))}
        schema = {'type': 'object', 'properties': {'moments': {'type': 'array', 'items': item,
                  'minItems': len(pool), 'maxItems': len(pool)}}, 'required': ['moments'], 'additionalProperties': False}
        texts = [b['text'] for b in content if b['type'] == 'text']
        images = [b['source']['data'] for b in content if b['type'] == 'image']
        return dict(model=self.model, system=CHECK_SYSTEM, schema=schema, text='\n'.join(texts), images=images)

    def _request(self, system, schema, content):
        texts = [b['text'] for b in content if b['type'] == 'text']
        images = [b['source']['data'] for b in content if b['type'] == 'image']
        return dict(model=self.model, system=system, schema=_local_schema(schema), text='\n'.join(texts), images=images)

    def _call(self, request, what):
        from urllib.error import URLError
        from urllib.request import ProxyHandler, Request, build_opener
        from .ai_director import NoRedirect
        payload = {'model': request['model'], 'stream': False, 'format': request['schema'], 'think': self.think,
                   'options': {'temperature': .1, 'num_ctx': self.num_ctx},
                   'messages': [{'role': 'system', 'content': request['system']},
                                {'role': 'user', 'content': request['text'], 'images': request['images']}]}
        call = Request(self.host+'/api/chat', data=json.dumps(payload).encode(),
                       headers={'Content-Type': 'application/json'})

        def send():
            with build_opener(ProxyHandler({}), NoRedirect()).open(call, timeout=self.timeout) as reply:
                return json.load(reply)
        try:
            body = _cancellable(send)
        except URLError as error:
            raise ValueError('The local AI director needs Ollama running on this computer '
                             f'({self.host}); start Ollama or choose another director') from error
        except (TimeoutError, OSError) as error:
            raise ValueError(f'The local model did not answer the {what} in time') from error
        except json.JSONDecodeError as error:
            raise ValueError(f'Ollama returned an unreadable reply to the {what}') from error
        if body.get('error'):
            raise ValueError(f'Ollama could not run the {what}: {str(body["error"])[:200]}')
        if body.get('done_reason') == 'length':
            raise ValueError(f'The local {what} was cut off before completing')
        try:
            return json.loads(body['message']['content']), _LocalResponse(body, request['model'])
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError(f'The local {what} was not valid JSON') from error

    @staticmethod
    def _usage(response):
        return getattr(response, 'usage', None)

    def review(self, candidates, brief=''):
        """Judge moments in small batches (local models handle few images per prompt best)."""
        pool = review_pool(candidates, self.limit)
        if not pool:
            raise ValueError('No candidate moments to review')
        moments, seconds = {}, 0.0
        for offset in range(0, len(pool), self.batch):
            chunk = pool[offset:offset+self.batch]
            LOG.info('Local review of moments %d-%d with %s', offset+1, offset+len(chunk), self.model)
            jobs.report(offset/len(pool), f'Local AI is watching moments {offset+1}-{offset+len(chunk)} of {len(pool)}')
            for attempt in (1, 2):   # small local models occasionally return an incomplete answer
                review, response = self._call(self.request(chunk, brief), 'moment review')
                seconds += response.seconds
                if isinstance(review, dict) and isinstance(review.get('moments'), list):
                    review = dict(review, moments=[checklist_moment(m) for m in review['moments']])
                try:
                    local, _, _ = validate_review(review, len(chunk))
                    break
                except ValueError:
                    if attempt == 2:
                        raise
            moments.update({offset+i: m for i, m in local.items()})
        report = dict(provider='ollama (local)', model=self.model, reviewed=len(pool), images_sent=len(pool),
                      frames_per_image=STRIP_FRAMES, seconds=round(seconds, 1),
                      usable=sum(m['usable'] for m in moments.values()),
                      events={e: sum(m['event'] == e for m in moments.values()) for e in EVENTS
                              if any(m['event'] == e for m in moments.values())},
                      weight=self.weight,
                      evidence='six-frame strips judged by a local vision model, blended with measured activity; '
                               'timing remains measured locally')
        return apply_review(candidates, pool, moments, [], judge=f'local vision review ({self.model})',
                            weight=self.weight), report


def _cancellable(work, poll=.2):
    """Run a blocking local-model request while honouring the job's cancel button."""
    import threading
    outcome = {}

    def target():
        try:
            outcome['value'] = work()
        except BaseException as error:   # re-raised in the caller's thread
            outcome['error'] = error
    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    while worker.is_alive():
        jobs.check()
        worker.join(poll)
    if 'error' in outcome:
        raise outcome['error']
    return outcome['value']


class _LocalResponse:
    def __init__(self, body, model):
        self.model = body.get('model', model)
        self.seconds = (body.get('total_duration') or 0)/1e9
        self.usage = dict(prompt_tokens=body.get('prompt_eval_count'), output_tokens=body.get('eval_count'),
                          seconds=round(self.seconds, 1))
