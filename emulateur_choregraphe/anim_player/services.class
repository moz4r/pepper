#!/usr/bin/env python
# -*- coding: utf-8 -*-

# services.py — utilitaires génériques (pas d'état/"random" ici).

def get_robot_services(session):
    """Retourne quelques proxys utiles; tolère les absences."""
    motion = session.service("ALMotion")
    try:
        life = session.service("ALAutonomousLife")
    except Exception:
        life = None
    try:
        tts = session.service("ALTextToSpeech")
    except Exception:
        tts = None
    try:
        audio = session.service("ALAudioPlayer")
    except Exception:
        audio = None
    try:
        posture = session.service("ALRobotPosture")
    except Exception:
        posture = None
    return motion, life, tts, audio, posture
