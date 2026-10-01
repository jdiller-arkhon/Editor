"""Render the licensed gameplay demonstration; media stays outside Git.

Run after installing the project:
python examples/render_gameplay_test.py --assets /path/to/local/assets --output /path/to/test.mp4
Supply the two original downloads documented in docs/TEST_MONTAGE.md.
"""
import argparse
from pathlib import Path
import subprocess

from montage_editor.config import Settings
from montage_editor.pipeline import create_montage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    video = args.assets / 'Xonotic_0-8-2_gameplay.webm'
    song = args.assets / 'Amazing_Grace_US_Marine_Band.ogg'
    for path in (video, song):
        if not path.is_file():
            parser.error(f'Missing original media: {path}; see docs/TEST_MONTAGE.md')
    prepared_video = args.assets / 'gameplay.mp4'
    soundtrack = args.assets / 'soundtrack.wav'
    # Refuse to overwrite preparation outputs. Use a fresh asset directory for a fresh run.
    subprocess.run(['ffmpeg','-v','error','-n','-ss','20','-i',str(video),'-t','110',
                    '-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-threads','2',
                    str(prepared_video)],check=True)
    subprocess.run(['ffmpeg','-v','error','-n','-ss','30','-i',str(song),'-t','28',
                    '-c:a','pcm_s16le',str(soundtrack)],check=True)
    story = dict(edit_profile='cinematic',transition='zoom',transition_duration=.24,
                 gameplay_gain=.10,music_gain=.9,normalize_audio=True,
                 faith_message='Walk with Christ. Let grace lead the way.')
    print(create_montage([prepared_video],soundtrack,args.output,
                        Settings(width=1280,height=720,fps=30,duration=24),story=story))


if __name__ == '__main__':
    main()
