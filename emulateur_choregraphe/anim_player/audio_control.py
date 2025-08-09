#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import threading

def _has_async_post(audio_service):
    try:
        return hasattr(audio_service, "post") and hasattr(audio_service.post, "playFile")
    except Exception:
        return False

def play_audio_if_exists(audio_service, hint_path, override=None, store_id_callback=None):
    """
    Joue un audio (override prioritaire, sinon basename du XAR).
    Essaie de récupérer un ID de lecture ; sinon on s'appuiera sur stopAll().
    """
    def launch_audio(path, cb):
        audio_id = None
        try:
            print("[XAR] Lecture audio : {}".format(path))
            # Essai 1 : API synchrone
            try:
                try:
                    audio_id = audio_service.playFile(path, 1.0, 0.0)
                except TypeError:
                    audio_id = audio_service.playFile(path)
            except Exception:
                audio_id = None
            # Essai 2 : via .post si dispo
            if (audio_id is None) and _has_async_post(audio_service):
                try:
                    try:
                        audio_id = audio_service.post.playFile(path, 1.0, 0.0)
                    except TypeError:
                        audio_id = audio_service.post.playFile(path)
                except Exception:
                    audio_id = None
            # Reporter l'ID si on l'a
            if cb and (audio_id is not None):
                try:
                    cb(audio_id)
                except Exception:
                    pass
        except Exception as e:
            print("[ERROR] Impossible de jouer le fichier audio:", e)

    # Priorité à l'override
    if override and os.path.exists(override):
        return threading.Thread(target=launch_audio, args=(override, store_id_callback))

    # Fallback: basename du XAR
    base, _ = os.path.splitext(hint_path)
    for ext in [".mp3", ".wav", ".ogg"]:
        audio_file = base + ext
        if os.path.exists(audio_file):
            return threading.Thread(target=launch_audio, args=(audio_file, store_id_callback))
    return None

def stop_audio(audio_service, audio_id):
    try:
        if audio_id is not None:
            audio_service.stop(audio_id)
            print("[XAR] Audio arrêté (par ID {}).".format(audio_id))
        else:
            audio_service.stopAll()
            print("[XAR] Audio arrêté (stopAll).")
    except Exception as e:
        print("[ERROR] Impossible d'arrêter l'audio:", e)
