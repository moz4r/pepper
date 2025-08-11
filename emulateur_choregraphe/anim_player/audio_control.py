#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import threading

AUDIO_EXTS = (".ogg", ".mp3", ".wav", ".aac", ".flac")  # support large set; NAOqi handles ogg/mp3/wav

def _has_async_post(audio_service):
    try:
        return hasattr(audio_service, "post") and hasattr(audio_service.post, "playFile")
    except Exception:
        return False

def _candidate_audio_paths(hint_path, override=None):
    """Return a list of candidate audio file paths based on the hint path (.qianim or .xar).
    Rules:
      - If override is a file, use it first.
      - Else try same basename as hint_path with common audio extensions in the same folder.
      - Then try ./audio/<basename>.<ext> and ./sounds/<basename>.<ext> beside the hint.
    """
    cands = []
    if override:
        if os.path.isfile(override):
            cands.append(override)
        else:
            # allow override as a directory: look inside for same basename
            if os.path.isdir(override):
                hint_base = os.path.splitext(os.path.basename(hint_path))[0]
                for ext in AUDIO_EXTS:
                    p = os.path.join(override, hint_base + ext)
                    if os.path.isfile(p):
                        cands.append(p)

    folder = os.path.dirname(os.path.abspath(hint_path))
    base = os.path.splitext(os.path.basename(hint_path))[0]

    # same folder, same basename
    for ext in AUDIO_EXTS:
        p = os.path.join(folder, base + ext)
        if os.path.isfile(p):
            cands.append(p)

    # ./audio and ./sounds subfolders
    for sub in ("audio", "sounds"):
        subdir = os.path.join(folder, sub)
        for ext in AUDIO_EXTS:
            p = os.path.join(subdir, base + ext)
            if os.path.isfile(p):
                cands.append(p)

    # remove duplicates preserving order
    seen = set()
    out = []
    for p in cands:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out

def play_audio_if_exists(audio_service, hint_path, override=None, store_id_callback=None):
    """If an audio file matching the animation exists, play it.
    Returns a thread or None. The thread is used only when we must
    call playFile synchronously; we wrap it to keep non-blocking behavior.
    """
    if not audio_service:
        return None
    cands = _candidate_audio_paths(hint_path, override=override)
    if not cands:
        return None

    audio_path = cands[0]

    # Prefer async NAOqi task if available
    if _has_async_post(audio_service):
        try:
            task_id = audio_service.post.playFile(audio_path)
            if callable(store_id_callback):
                try:
                    store_id_callback(task_id)
                except Exception:
                    pass
            return None
        except Exception:
            pass

    # Fallback: synchronous playFile; run it in a thread to avoid blocking
    def _run():
        try:
            audio_service.playFile(audio_path)
        except Exception:
            pass
    th = threading.Thread(target=_run)
    th.daemon = True
    # do not start here; let caller decide
    return th

def stop_audio(audio_service, audio_id):
    """Try to stop audio playback if possible. If audio_id is known, use it; else try stopAll()."""
    if not audio_service:
        return
    try:
        if audio_id is not None and hasattr(audio_service, "stop"):
            try:
                audio_service.stop(audio_id)
                return
            except Exception:
                pass
        # Some versions expose stopAll()
        if hasattr(audio_service, "stopAll"):
            try:
                audio_service.stopAll()
                return
            except Exception:
                pass
    except Exception:
        pass
