"""Resolve a typed song name to user-supplied local audio; never download songs."""
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
