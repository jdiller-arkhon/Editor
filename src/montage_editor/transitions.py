"""Bounded two-shot compositing that preserves the original cut clock."""
from pathlib import Path

BLENDS = ('cinematic', 'push', 'zoom_blend', 'blur', 'dissolve')
EFFECTS = ('smoothleft', 'smoothright', 'zoomin', 'hblur', 'fade')
LOSSLESS = ['-c:v', 'ffv1', '-level', '3', '-pix_fmt', 'yuv444p',
            '-c:a', 'pcm_s24le', '-threads', '2']


def compose(paths, durations, settings, style, seconds, temporary, run, per_cut=None, handles=None):
    """Replace each cut neighbourhood with a two-image blend of identical duration.

    ``handles[i] = (pre, post)``: rendered footage just before/after shot ``i`` (path and
    frame count), used so the blend shows real motion past the cut. Where no unused footage
    exists the edge frame is held instead. The cut clock never moves.
    """
    handles = handles or [(None, None)]*len(paths)
    fps = settings.fps
    frames = [round(d * fps) for d in durations]
    halves = [0 if per_cut and per_cut[i] == 'cut' else
              min(max(1, round(seconds * fps / 2)), frames[i] // 3, frames[i+1] // 3)
              for i in range(len(paths)-1)]
    pieces, boundaries, work = [], [], []
    position = 0
    for i, path in enumerate(paths):
        before = halves[i-1] if i else 0
        after = halves[i] if i < len(halves) else 0
        body_frames = frames[i] - before - after
        if body_frames > 0 and not before and not after:
            pieces.append((Path(path), durations[i]))    # hard cuts on both sides: use the shot as rendered
        elif body_frames > 0:
            body = Path(temporary) / f'body-{i:05d}.mkv'
            graph = (f'[0:v]trim=start_frame={before}:end_frame={frames[i]-after},'
                     f'setpts=PTS-STARTPTS[v];[0:a]atrim=start={before/fps}:'
                     f'duration={body_frames/fps},asetpts=PTS-STARTPTS[a]')
            work.append(['ffmpeg','-v','error','-i',str(path),'-filter_complex_threads','1',
                         '-filter_complex',graph,'-map','[v]','-map','[a]'] + LOSSLESS + [str(body)])
            pieces.append((body, body_frames / fps))
        position += durations[i]
        if not after:
            if i < len(halves):
                boundaries.append(dict(at=position, start=position, duration=0, effect='cut',
                                       handles='none'))
            continue
        half, length = after / fps, 2 * after / fps
        effect = {'push':'smoothleft','zoom_blend':'zoomin','blur':'hblur',
                  'dissolve':'fade'}.get(style)
        if style == 'cinematic':
            effect = ('smoothleft','zoomin','hblur','smoothright')[i % 4]
        if per_cut:
            effect = per_cut[i]
        transition = Path(temporary) / f'blend-{i:05d}.mkv'
        post, pre = handles[i][1], handles[i+1][0]
        inputs = ['-i', str(path), '-i', str(paths[i+1])]
        if post and post[1] >= after:
            inputs += ['-i', str(post[0])]
            x = (f'[0:v]trim=start_frame={frames[i]-after},setpts=PTS-STARTPTS[xa];'
                 f'[{len(inputs)//2-1}:v]trim=end_frame={after},setpts=PTS-STARTPTS[xb];'
                 f'[xa][xb]concat=n=2:v=1:a=0,settb=AVTB[x]')
        else:
            x = (f'[0:v]trim=start_frame={frames[i]-after},setpts=PTS-STARTPTS,'
                 f'tpad=stop_mode=clone:stop_duration={half},trim=end_frame={2*after},settb=AVTB[x]')
        if pre and pre[1] >= after:
            inputs += ['-i', str(pre[0])]
            y = (f'[{len(inputs)//2-1}:v]trim=start_frame={pre[1]-after},setpts=PTS-STARTPTS[ya];'
                 f'[1:v]trim=end_frame={after},setpts=PTS-STARTPTS[yb];'
                 f'[ya][yb]concat=n=2:v=1:a=0,settb=AVTB[y]')
        else:
            y = (f'[1:v]trim=end_frame={after},setpts=PTS-STARTPTS,'
                 f'tpad=start_mode=clone:start_duration={half},trim=end_frame={2*after},settb=AVTB[y]')
        kind = {(True, True): 'source footage', (False, False): 'held edge frames'}.get(
            (bool(post and post[1] >= after), bool(pre and pre[1] >= after)), 'mixed source/held')
        graph = (
            f'{x};{y};'
            f'[x][y]xfade=transition={effect}:duration={length}:offset=0,'
            f'trim=end_frame={2*after},setpts=PTS-STARTPTS[v];'
            f'[0:a]atrim=start={durations[i]-half}:duration={half},asetpts=PTS-STARTPTS,'
            f'afade=t=out:d={half},apad,atrim=duration={length}[a0];'
            f'[1:a]atrim=duration={half},asetpts=PTS-STARTPTS,afade=t=in:d={half},'
            f'adelay={half*1000}:all=1,apad,atrim=duration={length}[a1];'
            f'[a0][a1]amix=inputs=2:duration=first:normalize=0[a]')
        work.append(['ffmpeg','-v','error']+inputs+[
                     '-filter_complex_threads','1','-filter_complex',graph,'-map','[v]','-map','[a]',
                     '-t',str(length)] + LOSSLESS + [str(transition)])
        pieces.append((transition,length))
        boundaries.append(dict(at=position,start=position-half,duration=length,effect=effect,
                               handles=kind))
    # Bodies and blends are independent files: build them concurrently.
    from . import jobs
    jobs.parallel(run, work, 'Compositing transitions • {done} of {total}')
    return pieces, boundaries
