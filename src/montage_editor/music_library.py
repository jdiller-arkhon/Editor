"""Resolve a typed song name to local audio files. Link downloads live in music_sources."""
from pathlib import Path
import re
import unicodedata

AUDIO = {'.wav','.mp3','.flac','.m4a','.aac','.ogg','.opus'}
VIDEO = {'.mp4','.mkv','.mov','.webm','.avi','.m4v'}


def normalize(text):
    text=unicodedata.normalize('NFKD',text).casefold()
    return ' '.join(re.findall(r'\w+', ''.join(c for c in text if not unicodedata.combining(c))))


def find_songs(folder,query):
    query=normalize(query)
    if not query:
        raise ValueError('Type a song title or drop an audio file.')
    root=Path(folder)
    if not root.is_dir():
        raise ValueError('Choose your music folder once, or drop the song file alongside your clips.')
    matches=[];exact=[]
    for count,path in enumerate(root.rglob('*')):
        if count>=10000:
            raise ValueError('Music folder is too large. Choose a smaller folder with at most 10,000 entries.')
        if path.is_file() and path.suffix.lower() in AUDIO:
            title=normalize(path.stem)
            if title==query:exact.append(path.resolve())
            elif all(token in title.split() for token in query.split()):matches.append(path.resolve())
    return sorted(exact or matches,key=lambda p:str(p).casefold())


def default_library():
    """Where DRIFT keeps songs added from links when no music folder was chosen."""
    return Path.home()/'Music'/'DRIFT'


def interpret_song(text):
    """What the user typed or pasted into the one song box.

    ('link', url) for web links, ('file', path) for an existing audio/video file,
    ('title', text) for anything else, ('empty', '') for nothing.
    """
    text = (text or '').strip().strip('"\'')
    if not text:
        return 'empty', ''
    if re.match(r'(?i)^(https?://|spotify:|www\.|youtu\.be/|open\.spotify\.com/)', text):
        return 'link', text if '://' in text or text.startswith('spotify:') else 'https://'+text
    candidate = Path(text).expanduser()
    try:
        if candidate.is_file() and candidate.suffix.lower() in AUDIO | VIDEO:
            return 'file', str(candidate.resolve())
    except OSError:
        pass
    return 'title', text


def search_libraries(folders, query):
    """find_songs across several folders (missing ones skipped), duplicates removed."""
    found, seen = [], set()
    for folder in folders:
        if folder and Path(folder).is_dir():
            for path in find_songs(folder, query):
                if path not in seen:
                    seen.add(path); found.append(path)
    return found
