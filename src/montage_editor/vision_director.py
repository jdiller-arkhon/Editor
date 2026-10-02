"""Claude vision editor: watches sampled frames of candidate moments and judges them.

The local engine finds activity candidates and owns all timing (beat grid, retiming,
rendering). Claude sees three JPEG frames around each reviewed candidate and returns a
validated judgement: highlight strength, what kind of moment it is, whether it is
usable footage (not a menu/loading/scoreboard), where the peak is, and a preferred
story order. Nothing it returns is executed; IDs, enums and ranges are validated and
unknown values are rejected before they can reach the renderer.

Privacy: this sends downscaled frames of the user's footage to Anthropic's API. It is
strictly opt-in. Filenames and paths are never sent.
"""
import base64
import json
import logging
import subprocess

LOG = logging.getLogger(__name__)

MODEL = 'claude-opus-5-5'
FALLBACK_BETA = 'server-side-fallback-2026-07-01'
EVENTS = ('elimination', 'multi_elimination', 'clutch', 'objective', 'outplay', 'movement',
          'cinematic', 'setup', 'death', 'menu_or_loading', 'other')
PEAKS = {'before': -.6, 'center': 0.0, 'after': .6}
FRAME_OFFSETS = (-.6, 0.0, .6)

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
                'peak': {'type': 'string', 'enum': list(PEAKS)},
                'note': {'type': 'string'},
            },
            'required': ['id', 'highlight', 'event', 'usable', 'peak', 'note'],
            'additionalProperties': False}},
        'sequence': {'type': 'array', 'items': {'type': 'integer'},
                     'description': 'Usable moment IDs in preferred montage order, opening to climax'},
        'rationale': {'type': 'string'},
    },
    'required': ['moments', 'sequence', 'rationale'],
    'additionalProperties': False,
}

SYSTEM = (
    'You are the senior editor on a high-end gaming montage. For each candidate moment you see '
    'three frames: 0.6 s before, at, and 0.6 s after the measured activity peak. Judge what a top '
    'montage editor would keep: decisive eliminations, multi-kills, clutches, outplays, objective '
    'plays, striking movement or cinematic shots. Score highlight 0-10 honestly; most gameplay is '
    'ordinary, so reserve 8-10 for moments that would make a viewer react. Mark menus, loading '
    'screens, scoreboards, spectator/killcam UI or black frames as usable=false with event '
    'menu_or_loading. Only describe what is visible: if you cannot tell whether an elimination '
    'happened, say so in the note and score accordingly rather than guessing. Pick peak as the frame '
    'where the key action lands. Then give a sequence of usable IDs that builds from a strong opener '
    'toward the biggest moments for the climax. Never invent IDs. Keep notes under 20 words.'
)


def extract_frames(source, time, duration, width=512):
    frames = []
    for offset in FRAME_OFFSETS:
        at = min(max(0.0, time+offset), max(0.0, duration-.05))
        jpeg = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{at:.3f}', '-i', source, '-frames:v', '1',
                               '-vf', f'scale={width}:-2', '-q:v', '5', '-f', 'image2pipe', '-c:v', 'mjpeg',
                               'pipe:1'], check=True, capture_output=True).stdout
        if not jpeg.startswith(b'\xff\xd8'):
            raise ValueError('Could not decode a review frame')
        frames.append(jpeg)
    return frames


def review_pool(candidates, limit):
    """Strongest activity first, interleaved across sources so one clip cannot fill the pool."""
    by_source = {}
    for candidate in sorted(candidates, key=lambda c: (-c['score'], c['source'], c['time'])):
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
                     isinstance(moment['usable'], bool) and moment['peak'] in PEAKS and
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
        time = min(max(0.0, candidate['time']+PEAKS[moment['peak']]), candidate['source_duration'])
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
            for jpeg in extract_frames(candidate['source'], candidate['time'], candidate['source_duration']):
                content.append({'type': 'image', 'source': {
                    'type': 'base64', 'media_type': 'image/jpeg',
                    'data': base64.standard_b64encode(jpeg).decode('ascii')}})
        return dict(model=self.model, max_tokens=16000, betas=[FALLBACK_BETA], fallbacks='default',
                    thinking={'type': 'adaptive'}, output_config={
                        'effort': self.effort, 'format': {'type': 'json_schema', 'schema': SCHEMA}},
                    system=SYSTEM, messages=[{'role': 'user', 'content': content}])

    def review(self, candidates, brief=''):
        try:
            import anthropic
        except ImportError:
            if self._client is None:
                raise ValueError("Claude editor needs the Anthropic SDK: pip install -e '.[ai]'") from None
            anthropic = None
        pool = review_pool(candidates, self.limit)
        if not pool:
            raise ValueError('No candidate moments to review')
        LOG.info('Sending %d candidate moments (%d frames) to %s for review', len(pool), 3*len(pool), self.model)
        request = self.request(pool, brief)
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
            raise ValueError('Claude declined to review this footage')
        if response.stop_reason == 'max_tokens':
            raise ValueError('Claude review was cut off before completing')
        text = next((block.text for block in response.content if block.type == 'text'), None)
        try:
            review = json.loads(text) if text else None
        except json.JSONDecodeError as error:
            raise ValueError('Claude review was not valid JSON') from error
        moments, sequence, rationale = validate_review(review, len(pool))
        report = dict(provider='anthropic', model=getattr(response, 'model', self.model), reviewed=len(pool),
                      frames_sent=3*len(pool), rationale=rationale,
                      usable=sum(m['usable'] for m in moments.values()),
                      events={e: sum(m['event'] == e for m in moments.values()) for e in EVENTS
                              if any(m['event'] == e for m in moments.values())},
                      evidence='three downscaled frames per reviewed candidate; timing remains measured locally')
        usage = getattr(response, 'usage', None)
        if usage is not None:
            report['usage'] = dict(input_tokens=getattr(usage, 'input_tokens', None),
                                   output_tokens=getattr(usage, 'output_tokens', None))
        return apply_review(candidates, pool, moments, sequence), report
