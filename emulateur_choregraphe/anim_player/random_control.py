#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os

def _reset_body_speed_and_safety(session):
    """
    Réinitialise les vitesses max et la raideur du corps.
    Met aussi XAR_VEL_SAFETY=1.0 pour éviter un ralentissement artificiel.
    """
    try:
        os.environ["XAR_VEL_SAFETY"] = "1.0"
        print("[OK] XAR_VEL_SAFETY=1.0")
    except Exception as e:
        print("[--] Impossible de fixer XAR_VEL_SAFETY :", e)

    try:
        motion = session.service("ALMotion")
    except Exception as e:
        print("[--] ALMotion indisponible :", e)
        return

    try:
        motion.setStiffnesses("Body", 1.0)
        print("[OK] Stiffness Body = 1.0")
    except Exception as e:
        print("[--] setStiffnesses Body :", e)

    try:
        body_names = motion.getBodyNames("Body")
        motion.setMaxVelocity(body_names, [1.0] * len(body_names))
        print("[OK] Vitesses max réinitialisées pour tout le corps.")
    except Exception as e:
        print("[--] Impossible de réinitialiser les vitesses :", e)

def _postroll_neutral_pose(session):
    """Raccourci NAOqi : replacer le robot en posture neutre StandInit."""
    try:
        posture = session.service("ALRobotPosture")
        posture.goToPosture("StandInit", 0.3)
        print("[POSTROLL] StandInit OK.")
    except Exception as e:
        print("[--] Impossible de remettre StandInit :", e)

def disable_random_modules(session):
    """Couper les mouvements aléatoires et remettre les vitesses à fond."""
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

    _reset_body_speed_and_safety(session)

def enable_random_modules(session):
    """Fin d'animation : StandInit, réactivation modules, AutonomousLife interactive."""
    _postroll_neutral_pose(session)

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

    try:
        life = session.service("ALAutonomousLife")
        life.setState("interactive")
        print("[OK] AutonomousLife -> interactive")
    except Exception as e:
        print("[--] AutonomousLife non réactivée :", e)
