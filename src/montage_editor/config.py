from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    width: int = 1280
    height: int = 720
    fps: int = 30
    duration: float = 30.0
    analysis_fps: int = 4
    minimum_clip: float = 1.5
    maximum_clip: float = 4.0
    quality: str = "high"

    def __post_init__(self):
        if self.quality not in ("draft", "high", "master"):
            raise ValueError("Unknown export quality")
        if self.width <= 0 or self.height <= 0 or self.width % 2 or self.height % 2:
            raise ValueError("Dimensions must be positive even integers")
        if self.fps <= 0 or self.analysis_fps <= 0 or self.duration <= 0:
            raise ValueError("FPS and duration must be positive")
        if not 0 < self.minimum_clip <= self.maximum_clip:
            raise ValueError("Invalid clip duration bounds")


# Delivery presets: (width, height, fps, quality)
PRESETS = {
    'youtube-1080p30': (1920, 1080, 30, 'high'),
    'youtube-1080p60': (1920, 1080, 60, 'high'),
    'youtube-1440p60': (2560, 1440, 60, 'master'),
    'shorts-1080x1920': (1080, 1920, 30, 'high'),
    'instagram-1080x1350': (1080, 1350, 30, 'high'),
}


def preset(name, duration=30.0, **overrides):
    width, height, fps, quality = PRESETS[name]
    return Settings(**dict(dict(width=width, height=height, fps=fps, quality=quality, duration=duration), **overrides))


def draft_of(settings):
    """Fast preview settings with the same frame rate (so the edit can be finalised unchanged)."""
    scale = min(1.0, 640/max(settings.width, settings.height))
    even = lambda v: max(2, int(round(v*scale/2))*2)
    return Settings(**dict(settings.__dict__, width=even(settings.width), height=even(settings.height), quality='draft'))


# Editing pace: (shortest, longest) shot in seconds before beat snapping. "balanced" is the default.
PACES = {
    'calm': (2.0, 5.0),
    'balanced': (1.5, 4.0),
    'fast': (1.0, 3.0),
    'hyper': (.75, 2.25),
}


def with_pace(settings, pace):
    shortest, longest = PACES[pace]
    return Settings(**dict(settings.__dict__, minimum_clip=shortest, maximum_clip=longest))
