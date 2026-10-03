import argparse
import json
import logging
import subprocess
from .config import Settings
from .environment import detect_environment
from .pipeline import Timeline, create_montage, render


def choose_director(mode, local_model=None, claude_model=None):
    """The AI editor object for create_montage, or None for the activity engine."""
    from .vision_director import LOCAL_MODEL, MODEL, ClaudeDirector, LocalDirector
    if mode == 'claude':
        return ClaudeDirector(claude_model or MODEL)
    if mode == 'activity':
        return None
    from .local_ai import readiness
    model = local_model or LOCAL_MODEL
    ready, message = readiness(model)
    if ready:
        logging.info('Local AI director: %s', message)
        return LocalDirector(model)
    if mode == 'local':
        raise ValueError(message)
    logging.warning('Local AI director unavailable (%s) - using the activity engine', message)
    return None


def main():
    parser = argparse.ArgumentParser(description='Local gaming montage editor')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor')
    create = commands.add_parser('create', help='Analyze gameplay and music, then render')
    create.add_argument('--gameplay', nargs='+', required=True)
    create.add_argument('--music', required=True,
                        help='Song file (audio or video), or a YouTube/Spotify track link (downloaded to ~/Music/DRIFT)')
    create.add_argument('--pace', choices=['calm', 'balanced', 'fast', 'hyper'], default='balanced')
    create.add_argument('--output', required=True)
    create.add_argument('--duration', type=float, default=30)
    create.add_argument('--width', type=int, default=1280)
    create.add_argument('--height', type=int, default=720)
    create.add_argument('--director', choices=['auto', 'local', 'claude', 'activity'], default='auto',
                        help='auto (default): the local vision AI when Ollama has the model, otherwise the activity '
                             'engine; local: require the local AI; claude: send frames to Claude; activity: no AI')
    create.add_argument('--local-model', default=None, help='Ollama vision model for the local director (default qwen3.5:9b)')
    create.add_argument('--ollama-model', help='Legacy text-only Ollama planner (motion/audio numbers, no vision)')
    create.add_argument('--claude-editor', action='store_true', help='Same as --director claude')
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
    bench = commands.add_parser('benchmark', help='Score rendered montages (reads their sidecars)')
    bench.add_argument('outputs', nargs='+')
    bench.add_argument('--judge', action='store_true', help='Add a Claude rubric grade (sends a contact sheet)')
    bench.add_argument('--report', help='Write the full JSON results here')
    replay = commands.add_parser('render', help='Render a saved timeline')
    replay.add_argument('timeline')
    replay.add_argument('--output', required=True)
    replay.add_argument('--formats', help='Comma-separated export presets to deliver the same edit for, e.g. '
                        'youtube-1080p30,shorts-1080x1920,instagram-1080x1350 (files get -<preset> suffixes)')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        if args.command == 'doctor':
            from .local_ai import RECOMMENDED, status
            result = detect_environment()
            result['local_ai'] = dict(status(), recommended=RECOMMENDED[0]['name'])
        elif args.command == 'add-music':
            from .music_sources import NOTICE, add_music
            logging.info(NOTICE)
            result = add_music(args.link, args.folder, allow_youtube_match=not args.local_only)
        elif args.command == 'benchmark':
            from .benchmark import compare, judge, score
            results = []
            director = None
            if args.judge:
                from .vision_director import ClaudeDirector
                director = ClaudeDirector()
            for output in args.outputs:
                metrics = score(output)
                if director:
                    metrics['judge'] = judge(output, metrics, director)
                results.append(metrics)
            if args.report:
                from pathlib import Path
                Path(args.report).write_text(json.dumps(results, indent=2), encoding='utf-8')
            result = compare(results)
        elif args.command == 'render':
            if args.formats:
                from .pipeline import render_formats
                result = render_formats(Timeline.load(args.timeline), args.output,
                                        [f.strip() for f in args.formats.split(',') if f.strip()])
            else:
                result = render(Timeline.load(args.timeline), args.output)
        else:
            from .config import with_pace
            from .music_library import default_library, interpret_song
            settings = with_pace(Settings(width=args.width, height=args.height, fps=args.fps, duration=args.duration,
                                          quality=args.quality), args.pace)
            kind, value = interpret_song(args.music)
            if kind == 'link':
                from .music_sources import NOTICE, add_music
                logging.info(NOTICE)
                default_library().mkdir(parents=True, exist_ok=True)
                args.music = add_music(value, str(default_library()))['path']
            story = None
            if args.story:
                from pathlib import Path
                story = json.loads(Path(args.story).read_text(encoding='utf-8'))
            editor = choose_director('claude' if args.claude_editor else args.director, args.local_model,
                                     args.claude_model)
            result = create_montage(args.gameplay, args.music, args.output, settings, story, args.ollama_model,
                                    args.brief, ai_editor=editor)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, subprocess.SubprocessError, KeyError) as error:
        detail = error.stderr.decode(errors='replace') if isinstance(error, subprocess.CalledProcessError) else str(error)
        parser.exit(1, f'Error: {detail}\n')


if __name__ == '__main__':
    main()
