#!/usr/bin/env python
# -*- coding: utf-8 -*-

def get_robot_services(session):
    motion = session.service("ALMotion")
    life = session.service("ALAutonomousLife")
    tts = session.service("ALTextToSpeech")
    audio = session.service("ALAudioPlayer")
    return motion, life, tts, audio
