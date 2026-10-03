"""Local AI runtime helpers: is Ollama running, which models can see images, and model downloads.

Everything talks to Ollama on this computer only (loopback, no proxy, no redirects). Model
downloads are performed by Ollama itself from its registry when the user asks for one.
"""
import json
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from .ai_director import NoRedirect

HOST = 'http://127.0.0.1:11434'
INSTALL_URL = 'https://ollama.com/download'
# Vision models for DRIFT's local director, best first. Sizes are Ollama's downloads. Only the
# first was measured here (16 hand-labelled Xonotic strips, CPU): 4/5 death screens, 0 false flags,
# fight-vs-movement AUC 0.70, ~43 s per strip. qwen2.5vl:7b scored 0/5 and 0.70 at ~89 s per strip.
RECOMMENDED = [
    dict(name='qwen3.5:9b', size_gb=6.6, note='Recommended: best measured here; ~8 GB GPU for fast reviews'),
    dict(name='qwen3.5:27b', size_gb=17, note='Larger Qwen 3.5 for 24 GB GPUs (not measured here)'),
    dict(name='qwen3.5:4b', size_gb=3.4, note='Smaller machines (not measured here)'),
]


def valid_name(model):
    """Ollama model references: letters, digits and ._-:/ only (e.g. qwen3.5:9b, user/model:tag)."""
    import re
    return isinstance(model, str) and 0 < len(model) <= 200 and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]*', model) \
        is not None and '..' not in model


def readiness(model, host=HOST):
    """(ready, message) for using ``model`` as the local director."""
    state = status(host)
    if not state['running']:
        return False, f'Ollama is not running on this computer. Install it from {INSTALL_URL} and start it.'
    if model not in state['models'] and f'{model}:latest' not in state['models']:
        return False, f'{model} is not downloaded yet. Use "Set up local AI" to download it.'
    if model not in state['vision_models'] and f'{model}:latest' not in state['vision_models']:
        return False, f'{model} cannot see images; choose a vision model such as {RECOMMENDED[0]["name"]}.'
    return True, f'{model} is ready on this computer (Ollama {state["version"]}).'


def _open(path, payload=None, timeout=10, host=HOST):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(host.rstrip('/')+path, data=data, headers={'Content-Type': 'application/json'})
    return build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout)


def status(host=HOST):
    """{'running': bool, 'version': str|None, 'vision_models': [names], 'models': [names]}"""
    try:
        with _open('/api/version', host=host) as reply:
            version = json.load(reply).get('version')
        with _open('/api/tags', host=host) as reply:
            models = [m['name'] for m in json.load(reply).get('models', [])]
    except (URLError, OSError, ValueError):
        return dict(running=False, version=None, models=[], vision_models=[])
    vision = []
    for name in models:
        try:
            with _open('/api/show', {'model': name}, host=host) as reply:
                if 'vision' in json.load(reply).get('capabilities', []):
                    vision.append(name)
        except (URLError, OSError, ValueError):
            continue
    return dict(running=True, version=version, models=models, vision_models=vision)


def pull(model, progress=None, host=HOST, timeout=3600):
    """Ask Ollama to download ``model``; ``progress(fraction, message)`` is called as it streams."""
    if not valid_name(model):
        raise ValueError('Choose a model name such as qwen3.5:9b')
    try:
        with _open('/api/pull', {'model': model, 'stream': True}, timeout=timeout, host=host) as reply:
            for line in reply:
                event = json.loads(line or b'{}')
                if event.get('error'):
                    raise ValueError(f'Ollama could not download {model}: {event["error"]}')
                total, done = event.get('total'), event.get('completed')
                if progress and total:
                    progress(min(1.0, done/total), f'Downloading {model}')
                if event.get('status') == 'success':
                    return True
    except URLError as error:
        raise ValueError(f'Ollama is not running on this computer; install it from {INSTALL_URL}') from error
    raise ValueError(f'The download of {model} did not finish')
