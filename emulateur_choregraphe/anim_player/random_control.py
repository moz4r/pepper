#!/usr/bin/env python
# -*- coding: utf-8 -*-

# random_control.py : gère l'init/stop des mouvements aléatoires et l'état général du robot.
# (XarPlayer importe directement ces deux fonctions)

def disable_random_modules(session):
    """Prépare le robot pour l'animation : wakeUp + StandInit, AutonomousLife interactive,
    coupe les micro-mouvements (sans tuer complètement la vie autonome)."""
    try:
        motion = session.service("ALMotion")
        motion.wakeUp()
        print("[RC] WakeUp OK")
    except Exception as e:
        print("[RC] WakeUp KO:", e)

    try:
        posture = session.service("ALRobotPosture")
        posture.goToPosture("StandInit", 0.6)
        print("[RC] StandInit OK")
    except Exception as e:
        print("[RC] StandInit KO:", e)

    try:
        life = session.service("ALAutonomousLife")
        life.setState("interactive")
        print("[RC] AutonomousLife -> interactive")
    except Exception as e:
        print("[RC] AutonomousLife KO:", e)

    modules = [
        "ALSpeakingMovement",
        "ALListeningMovement",
        "ALAutonomousBlinking",
        "ALBackgroundMovement",
    ]
    for name in modules:
        try:
            proxy = session.service(name)
            if hasattr(proxy, "setEnabled"):
                proxy.setEnabled(False)
                print("[RC] {} désactivé".format(name))
            elif hasattr(proxy, "pause"):
                proxy.pause(True)
                print("[RC] {} paused".format(name))
        except Exception as e:
            print("[RC] Disable {}: {}".format(name, e))


def enable_random_modules(session):
    """Fin d'animation : StandInit, réactive les micro-mouvements, AutonomousLife interactive."""
    try:
        posture = session.service("ALRobotPosture")
        posture.goToPosture("StandInit", 0.4)
        print("[RC] StandInit end OK")
    except Exception as e:
        print("[RC] StandInit end KO:", e)

    modules = [
        "ALSpeakingMovement",
        "ALListeningMovement",
        "ALAutonomousBlinking",
        "ALBackgroundMovement",
    ]
    for name in modules:
        try:
            proxy = session.service(name)
            if hasattr(proxy, "setEnabled"):
                proxy.setEnabled(True)
                print("[RC] {} réactivé".format(name))
            elif hasattr(proxy, "pause"):
                proxy.pause(False)
                print("[RC] {} unpaused".format(name))
        except Exception as e:
            print("[RC] Enable {}: {}".format(name, e))

    try:
        life = session.service("ALAutonomousLife")
        life.setState("interactive")
        print("[RC] AutonomousLife -> interactive")
    except Exception as e:
        print("[RC] Life end KO:", e)
