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
    create.add_argument('--claude-editor', action='store_true',
                        help='Send sampled frames of candidate moments to Claude for highlight review (needs Anthropic credentials)')
    create.add_argument('--claude-model', default=None, help='Override the Claude model for --claude-editor')
    create.add_argument('--brief', help='Creative brief for the AI director/editor')
    create.add_argument('--story', help='JSON dialogue cues and transition settings')
    create.add_argument('--quality',choices=['draft','high','master'],default='high')
    create.add_argument('--fps', type=int, default=30)
    add = commands.add_parser('add-music', help='Add a soundtrack from a YouTube or Spotify track link')
    add.add_argument('link')
    add.add_argument('--folder', required=True, help='Your music folder')
    add.add_argument('--local-only', action='store_true',
                     help='For Spotify links, only use a matching song already in the folder')
    replay = commands.add_parser('render', help='Render a saved timeline')
    replay.add_argument('timeline')
    replay.add_argument('--output', required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        if args.command == 'doctor':
            result = detect_environment()
        elif args.command == 'add-music':
            from .music_sources import NOTICE, add_music
            logging.info(NOTICE)
            result = add_music(args.link, args.folder, allow_youtube_match=not args.local_only)
        elif args.command == 'render':
            result = render(Timeline.load(args.timeline), args.output)
        else:
            settings = Settings(width=args.width, height=args.height, fps=args.fps, duration=args.duration,quality=args.quality)
            story = None
            if args.story:
                from pathlib import Path
                story = json.loads(Path(args.story).read_text(encoding='utf-8'))
            editor = None
            if args.claude_editor:
                from .vision_director import ClaudeDirector, MODEL
                editor = ClaudeDirector(args.claude_model or MODEL)
            result = create_montage(args.gameplay, args.music, args.output, settings, story, args.ollama_model,
                                    args.brief, ai_editor=editor)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, subprocess.SubprocessError, KeyError) as error:
        detail = error.stderr.decode(errors='replace') if isinstance(error, subprocess.CalledProcessError) else str(error)
        parser.exit(1, f'Error: {detail}\n')
