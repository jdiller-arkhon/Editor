"""Add a soundtrack from a YouTube or Spotify link into the local music folder.

YouTube: the audio stream is fetched with yt-dlp (optional ``[links]`` extra).
Spotify: audio is DRM-protected and is never downloaded or decrypted. The public track
page supplies title, artist and duration; DRIFT then uses a matching song already in the
music folder, or (only when allowed) the best YouTube match for "artist - title",
checking its duration against Spotify's. Every fetched file gets a provenance sidecar.

Users are responsible for having the rights to use the music. Downloading from YouTube
is generally against YouTube's Terms of Service unless the uploader permits it, and
montages published with copyrighted songs are commonly claimed or muted.
"""
from datetime import datetime, timezone
import glob
import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .music_library import AUDIO, find_songs

NOTICE = ('Only add music you have the right to use. YouTube downloads may breach YouTube’s Terms '
          'unless the uploader allows it; published montages with copyrighted songs are often claimed. '
          'Spotify audio is never downloaded: DRIFT finds the same song locally or on YouTube.')
YOUTUBE_HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be'}
SPOTIFY_TRACK = re.compile(r'^(?:https?://open\.spotify\.com/(?:intl-[a-z-]+/)?track/|spotify:track:)([A-Za-z0-9]{22})')
MAX_SECONDS = 20*60
DURATION_TOLERANCE = 7.0


def classify(link):
    link = link.strip()
    if SPOTIFY_TRACK.match(link):
        return 'spotify'
    parsed = urlparse(link)
    if parsed.scheme in ('http', 'https') and parsed.hostname in YOUTUBE_HOSTS:
        return 'youtube'
    if 'spotify.com' in (parsed.hostname or '') or link.startswith('spotify:'):
        raise ValueError('Only Spotify track links are supported (not playlists, albums or podcasts)')
    raise ValueError('Paste a YouTube video link or a Spotify track link')


def _meta(page, key):
    match = re.search(r'<meta (?:property|name)="%s" content="([^"]*)"' % re.escape(key), page)
    return html.unescape(match.group(1)).strip() if match else None


def spotify_track(link, fetch=None):
    """Title, artist and duration from the public track page (no account, no audio)."""
    track_id = SPOTIFY_TRACK.match(link.strip()).group(1)
    url = f'https://open.spotify.com/track/{track_id}'
    page = fetch(url) if fetch else urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}),
                                            timeout=20).read().decode('utf-8', 'replace')
    title = _meta(page, 'og:title')
    artist = _meta(page, 'music:musician_description')
    description = _meta(page, 'og:description') or ''
    if not artist and ' · ' in description:
        artist = description.split(' · ')[0]
    duration = _meta(page, 'music:duration')
    if not title or not artist:
        raise ValueError('Could not read the Spotify track title and artist')
    return dict(id=track_id, url=url, title=title, artist=artist,
                duration=float(duration) if duration and duration.isdigit() else None)


def _safe(text):
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip(' .')[:120] or 'track'


def _youtube_dl(options):
    try:
        import yt_dlp
    except ImportError as error:
        raise ValueError("Adding music from links needs yt-dlp: pip install -e '.[links]'") from error
    return yt_dlp.YoutubeDL(options)


def download(query, folder, name=None, expected=None, factory=None, extra=None):
    """Fetch one audio stream into ``folder`` without overwriting; returns (path, info)."""
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError('Choose an existing music folder first')
    existing = {p.name for p in folder.iterdir()}

    def acceptable(info, *, incomplete=False):
        if info.get('_type') == 'playlist' or info.get('is_live'):
            return 'Live streams and playlists are not supported'
        length = info.get('duration')
        if length and length > MAX_SECONDS:
            return f'Longer than {MAX_SECONDS//60} minutes'
        if expected and length and abs(length-expected) > DURATION_TOLERANCE:
            return f'Duration {length:.0f}s does not match the Spotify track ({expected:.0f}s)'
        return None
    options = dict(format='bestaudio/best', noplaylist=True, quiet=True, no_warnings=True,
                   noprogress=True, overwrites=False, restrictfilenames=False, windowsfilenames=True,
                   match_filter=acceptable, paths={'home': str(folder)},
                   # Keep the original codec, but in an audio-only file (.opus/.m4a/...).
                   postprocessors=[{'key': 'FFmpegExtractAudio', 'preferredcodec': 'best',
                                    'nopostoverwrites': True}],
                   outtmpl={'default': (_safe(name) if name else '%(artist,uploader|Unknown)s - %(title)s')
                            + ' [%(id)s].%(ext)s'})
    options.update(extra or {})
    with (factory or _youtube_dl)(options) as ydl:
        try:
            info = ydl.extract_info(query, download=False)
            if info and info.get('_type') == 'playlist':
                entries = [e for e in info.get('entries') or [] if e]
                info = entries[0] if entries else None
            if not info:
                raise ValueError('No downloadable audio matched (filtered by duration or availability)')
            stem = Path(ydl.prepare_filename(info)).stem
            already = sorted(p for p in folder.glob(glob.escape(stem)+'.*') if p.suffix.lower() in AUDIO)
            if already:
                path = already[0]   # same source already added: reuse it, never re-download
            else:
                info = ydl.process_ie_result(info, download=True)
                path = Path(info['requested_downloads'][0]['filepath']) if info.get('requested_downloads') \
                    else Path(ydl.prepare_filename(info))
        except ValueError:
            raise
        except Exception as error:
            message = str(error)
            if 'confirm you' in message and 'bot' in message:
                message = 'YouTube asked to confirm you are not a bot; try again later or from another network'
            raise ValueError(f'Could not fetch audio: {message.splitlines()[0][:300]}') from error
    if not path.is_file():
        raise ValueError('The download did not produce an audio file')
    if expected:
        # Sources do not always report duration; measure the file that actually arrived.
        from .pipeline import probe
        measured = probe(path)['duration']
        if abs(measured-expected) > DURATION_TOLERANCE:
            if path.name not in existing:
                path.unlink()
            raise ValueError(f'The best match is {measured:.0f}s but the Spotify track is {expected:.0f}s; '
                             'not using it (it may be a different version)')
        info = dict(info, duration=info.get('duration') or measured)
    return path, info


def add_music(link, folder, allow_youtube_match=True, factory=None, fetch=None, extra=None):
    """Return a dict with the local ``path`` and provenance for a pasted link."""
    kind = classify(link)
    retrieved = datetime.now(timezone.utc).isoformat(timespec='seconds')
    if kind == 'youtube':
        path, info = download(link.strip(), folder, factory=factory, extra=extra)
        provenance = dict(source='youtube', url=info.get('webpage_url') or link.strip())
    else:
        track = spotify_track(link, fetch)
        local = [p for p in find_songs(folder, f'{track["artist"]} {track["title"]}')] if Path(folder).is_dir() else []
        if len(local) == 1:
            return dict(path=str(local[0]), source='local library', spotify=track,
                        note='Used the matching song already in your music folder')
        if not allow_youtube_match:
            raise ValueError(f'“{track["artist"]} – {track["title"]}” is not in your music folder')
        name = f'{track["artist"]} - {track["title"]}'
        path, info = download(f'ytsearch1:{name} audio', folder, name=name, expected=track['duration'],
                              factory=factory, extra=extra)
        provenance = dict(source='youtube match for spotify track', spotify=track,
                          url=info.get('webpage_url'))
    provenance.update(title=info.get('title'), uploader=info.get('uploader') or info.get('channel'),
                      duration=info.get('duration'), license=info.get('license'), retrieved=retrieved,
                      notice=NOTICE)
    sidecar = path.with_name(path.name+'.source.json')
    if not sidecar.exists():
        sidecar.write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    return dict(path=str(path), **provenance)
