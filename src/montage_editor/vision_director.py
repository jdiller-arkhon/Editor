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

import numpy as np

LOG = logging.getLogger(__name__)

MODEL = 'claude-opus-5-5'
FALLBACK_BETA = 'server-side-fallback-2026-07-01'
EVENTS = ('elimination', 'multi_elimination', 'clutch', 'objective', 'outplay', 'movement',
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
    jpeg = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height}',
                           '-i', 'pipe:0', '-frames:v', '1', '-q:v', '5', '-f', 'image2pipe', '-c:v', 'mjpeg',
                           'pipe:1'], input=raw, check=True, capture_output=True).stdout
    if not jpeg.startswith(b'\xff\xd8'):
        raise ValueError('Could not encode a review image')
    return jpeg


def labelled_frame(source, at, text):
    """One RGB tile at ``at`` seconds with a burned-in label (letterboxed to TILE)."""
    w, h = TILE
    vf = (f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,'
          f"drawtext=text='{text}':x=6:y=6:fontsize=18:fontcolor=yellow:box=1:boxcolor=black@0.65")
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{max(0.0, at):.3f}', '-i', source, '-frames:v', '1',
                          '-vf', vf, '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1'],
                         check=True, capture_output=True).stdout
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
        raise ValueError('Claude review has no moments')
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
            raise ValueError('Claude review contains an invalid or unknown moment')
        seen.add(ident)
        moments[ident] = dict(moment, note=moment['note'][:200])
    if not moments:
        raise ValueError('Claude review judged no moments')
    sequence = []
    for ident in review.get('sequence', []):
        if isinstance(ident, int) and ident in moments and moments[ident]['usable'] and ident not in sequence:
            sequence.append(ident)
    rationale = str(review.get('rationale', ''))[:1000]
    return moments, sequence, rationale


def apply_review(candidates, pool, moments, sequence):
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
        entry = dict(candidate, time=time, score=moment['highlight']/10, event=moment['event'],
                     ai_note=moment['note'], judged_by='claude vision review',
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

    def __init__(self, model=MODEL, client=None, effort='high', limit=24):
        self.model, self.effort, self.limit = model, effort, limit
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
