#!/usr/bin/env python
# -*- coding: utf-8 -*-

def disable_random_modules(session):
    modules = [
        "ALSpeakingMovement",
        "ALListeningMovement",
        "ALBackgroundMovement",
        "BasicAwareness",
    ]
    for name in modules:
        try:
            session.service(name).setEnabled(False)
            print("[OK] {} désactivé".format(name))
        except Exception as e:
            print("[--] Impossible de désactiver {} : {}".format(name, e))

def enable_random_modules(session):
    modules = [
        "ALSpeakingMovement",
        "ALListeningMovement",
        "ALBackgroundMovement",
        "BasicAwareness",
    ]
    for name in modules:
        try:
            session.service(name).setEnabled(True)
            print("[OK] {} réactivé".format(name))
        except Exception as e:
            print("[--] Impossible d'activer {} : {}".format(name, e))
