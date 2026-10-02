"""Local hardware and executable discovery; no network or model downloads."""
import os
import platform
import shutil
import subprocess


def detect_environment():
    result = {"platform": platform.platform(), "python": platform.python_version(),
              "cpu_count": os.cpu_count(), "ffmpeg": shutil.which("ffmpeg"),
              "ffprobe": shutil.which("ffprobe"), "gpu": None, "encoders": []}
    if result["ffmpeg"]:
        output = subprocess.run([result["ffmpeg"], "-hide_banner", "-encoders"],
                                capture_output=True, text=True, timeout=15, check=True)
        result["encoders"] = [line.split()[1] for line in output.stdout.splitlines()
                              if len(line.split()) > 1 and line.startswith(" V") and line.split()[1] != "="]
    try:
        import yt_dlp
        result["music_links"] = {"yt_dlp": yt_dlp.version.__version__,
                                 "js_runtime": shutil.which("deno") or shutil.which("node")}
    except ImportError:
        result["music_links"] = None
    nvidia = shutil.which("nvidia-smi")
    if nvidia:
        output = subprocess.run([nvidia, "--query-gpu=name", "--format=csv,noheader"],
                                capture_output=True, text=True, timeout=10)
        if output.returncode == 0:
            result["gpu"] = output.stdout.strip()
    return result
