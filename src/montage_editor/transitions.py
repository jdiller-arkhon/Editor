"""Bounded two-shot compositing that preserves the original cut clock."""
from pathlib import Path

BLENDS = ('cinematic', 'push', 'zoom_blend', 'blur', 'dissolve')
LOSSLESS = ['-c:v', 'ffv1', '-level', '3', '-pix_fmt', 'yuv444p',
            '-c:a', 'pcm_s24le', '-threads', '2']


def compose(paths, durations, settings, style, seconds, temporary, run):
    """Replace each cut neighbourhood with a two-image blend of identical duration.

    Held edge frames provide transition handles without consuming/repeating source
    intervals elsewhere. At most two shots are decoded in each transition process.
    """
    fps = settings.fps
    frames = [round(d * fps) for d in durations]
    halves = [min(max(1, round(seconds * fps / 2)), frames[i] // 3, frames[i+1] // 3)
              for i in range(len(paths)-1)]
    pieces, boundaries = [], []
    position = 0
    for i, path in enumerate(paths):
        before = halves[i-1] if i else 0
        after = halves[i] if i < len(halves) else 0
        body_frames = frames[i] - before - after
        if body_frames > 0:
            body = Path(temporary) / f'body-{i:05d}.mkv'
            graph = (f'[0:v]trim=start_frame={before}:end_frame={frames[i]-after},'
                     f'setpts=PTS-STARTPTS[v];[0:a]atrim=start={before/fps}:'
                     f'duration={body_frames/fps},asetpts=PTS-STARTPTS[a]')
            run(['ffmpeg','-v','error','-i',str(path),'-filter_complex_threads','1',
                 '-filter_complex',graph,'-map','[v]','-map','[a]'] + LOSSLESS + [str(body)])
            pieces.append((body, body_frames / fps))
        position += durations[i]
        if not after:
            continue
        half, length = after / fps, 2 * after / fps
        effect = {'push':'smoothleft','zoom_blend':'zoomin','blur':'hblur',
                  'dissolve':'fade'}.get(style)
        if style == 'cinematic':
            effect = ('smoothleft','zoomin','hblur','smoothright')[i % 4]
        transition = Path(temporary) / f'blend-{i:05d}.mkv'
        graph = (
            f'[0:v]trim=start_frame={frames[i]-after},setpts=PTS-STARTPTS,'
            f'tpad=stop_mode=clone:stop_duration={half},trim=end_frame={2*after},settb=AVTB[x];'
            f'[1:v]trim=end_frame={after},setpts=PTS-STARTPTS,'
            f'tpad=start_mode=clone:start_duration={half},trim=end_frame={2*after},settb=AVTB[y];'
            f'[x][y]xfade=transition={effect}:duration={length}:offset=0,'
            f'trim=end_frame={2*after},setpts=PTS-STARTPTS[v];'
            f'[0:a]atrim=start={durations[i]-half}:duration={half},asetpts=PTS-STARTPTS,'
            f'afade=t=out:d={half},apad,atrim=duration={length}[a0];'
            f'[1:a]atrim=duration={half},asetpts=PTS-STARTPTS,afade=t=in:d={half},'
            f'adelay={half*1000}:all=1,apad,atrim=duration={length}[a1];'
            f'[a0][a1]amix=inputs=2:duration=first:normalize=0[a]')
        run(['ffmpeg','-v','error','-i',str(path),'-i',str(paths[i+1]),
             '-filter_complex_threads','1','-filter_complex',graph,'-map','[v]','-map','[a]',
             '-t',str(length)] + LOSSLESS + [str(transition)])
        pieces.append((transition,length))
        boundaries.append(dict(at=position,start=position-half,duration=length,effect=effect,
                               handles='held edge frames'))
    return pieces, boundaries
