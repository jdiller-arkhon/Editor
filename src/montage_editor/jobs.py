"""Cancellation and progress for long jobs without threading parameters through every call.

A worker thread enters ``job(cancel=Event, progress=callback)``. Every FFmpeg call made by
the pipeline goes through ``run``, which polls the cancel event and kills the process
promptly. ``report`` maps stage-local fractions into the overall 0-1 range set by ``span``.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import os
import signal
import subprocess

_cancel = ContextVar('drift_cancel', default=None)
_progress = ContextVar('drift_progress', default=None)
_span = ContextVar('drift_span', default=(0.0, 1.0))


class Cancelled(Exception):
    """The user cancelled the job; partial temporary output has been discarded."""


@contextmanager
def job(cancel=None, progress=None):
    tokens = (_cancel.set(cancel), _progress.set(progress), _span.set((0.0, 1.0)))
    try:
        yield
    finally:
        _span.reset(tokens[2]); _progress.reset(tokens[1]); _cancel.reset(tokens[0])


@contextmanager
def span(start, end):
    """Nest a stage: fractions reported inside map onto [start, end] of the enclosing span."""
    outer = _span.get()
    width = outer[1]-outer[0]
    token = _span.set((outer[0]+width*start, outer[0]+width*end))
    try:
        yield
    finally:
        _span.reset(token)


def check():
    event = _cancel.get()
    if event is not None and event.is_set():
        raise Cancelled('Cancelled')


def report(fraction, message):
    check()
    callback = _progress.get()
    if callback is not None:
        a, b = _span.get()
        callback(a+(b-a)*max(0.0, min(1.0, fraction)), message)


def run(args, cwd=None, input=None):
    """subprocess.run(check=True, capture_output=True) that stops promptly on cancel."""
    check()
    # Own process group/session so cancel can stop wrapper launchers (e.g. Chocolatey or Scoop
    # shims that start the real ffmpeg as a child) together with everything they spawned.
    group = dict(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == 'nt' else dict(start_new_session=True)
    process = subprocess.Popen(args, cwd=cwd, stdin=subprocess.PIPE if input is not None else None,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, **group)
    pending = input
    while True:
        try:
            stdout, stderr = process.communicate(input=pending, timeout=.2)
            break
        except subprocess.TimeoutExpired:
            pending = None   # input was delivered on the first call
            event = _cancel.get()
            if event is not None and event.is_set():
                _kill_tree(process); process.communicate()
                raise Cancelled('Cancelled')
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, args, stdout, stderr)
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def _kill_tree(process):
    """Stop the process and all of its children."""
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], capture_output=True)
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    if process.poll() is None:
        process.kill()
