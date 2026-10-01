import argparse
import json
import logging
import subprocess
from .config import Settings
from .environment import detect_environment
from .pipeline import Timeline, create_montage, render


def main():
    parser = argparse.ArgumentParser(description='Local gaming montage editor')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor')
    create = commands.add_parser('create', help='Analyze gameplay and music, then render')
    create.add_argument('--gameplay', nargs='+', required=True)
    create.add_argument('--music', required=True)
    create.add_argument('--output', required=True)
    create.add_argument('--duration', type=float, default=30)
    create.add_argument('--width', type=int, default=1280)
    create.add_argument('--height', type=int, default=720)
    create.add_argument('--ollama-model', help='Installed local Ollama model for experimental automatic direction')
    create.add_argument('--brief', help='Creative brief for the local director')
    create.add_argument('--story', help='JSON dialogue cues and transition settings')
    create.add_argument('--fps', type=int, default=30)
    replay = commands.add_parser('render', help='Render a saved timeline')
    replay.add_argument('timeline')
    replay.add_argument('--output', required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        if args.command == 'doctor':
            result = detect_environment()
        elif args.command == 'render':
            result = render(Timeline.load(args.timeline), args.output)
        else:
            settings = Settings(width=args.width, height=args.height, fps=args.fps, duration=args.duration)
            story = None
            if args.story:
                from pathlib import Path
                story = json.loads(Path(args.story).read_text(encoding='utf-8'))
            result = create_montage(args.gameplay, args.music, args.output, settings, story, args.ollama_model, args.brief)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, subprocess.SubprocessError, KeyError) as error:
        detail = error.stderr.decode(errors='replace') if isinstance(error, subprocess.CalledProcessError) else str(error)
        parser.exit(1, f'Error: {detail}\n')
