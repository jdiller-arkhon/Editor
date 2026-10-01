"""User-directed Christian narration; no synthesized or attributed speech."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class DialogueCue:
    source: str
    at: float
    start: float
    duration: float
    gain: float = 1.0
    reference: str = ''
    text_kind: str = 'original'

    def validate(self, total):
        if not all(math.isfinite(v) for v in (self.at, self.start, self.duration, self.gain)):
            raise ValueError('Dialogue timing and gain must be finite')
        if self.at < 0 or self.start < 0 or self.duration <= 0 or self.at+self.duration > total+.001:
            raise ValueError('Dialogue cue exceeds timeline or has invalid bounds')
        if not 0 < self.gain <= 4:
            raise ValueError('Dialogue gain must be in (0, 4]')
        if self.text_kind not in ('original', 'paraphrase', 'quotation'):
            raise ValueError('Dialogue text_kind must be original, paraphrase or quotation')
