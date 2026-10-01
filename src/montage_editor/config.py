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
