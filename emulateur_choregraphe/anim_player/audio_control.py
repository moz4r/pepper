#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import threading

def play_audio_if_exists(audio_service, xar_path):
    base, _ = os.path.splitext(xar_path)
    for ext in [".mp3", ".wav", ".ogg"]:
        audio_file = base + ext
        if os.path.exists(audio_file):
            def launch_audio():
                try:
                    print("[XAR] Lecture audio : {}".format(audio_file))
                    audio_service.playFile(audio_file, 1.0, 0.0)
                except Exception as e:
                    print("[ERROR] Impossible de jouer le fichier audio:", e)
            return threading.Thread(target=launch_audio)
    return None

def stop_audio(audio_service, audio_id):
    if audio_id is not None:
        try:
            audio_service.stop(audio_id)
            print("[XAR] Audio arrêté.")
        except Exception as e:
            print("[ERROR] Impossible d'arrêter l'audio:", e)
