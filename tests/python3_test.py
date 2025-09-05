#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test local minimal pour Pepper en Python 3
Connexion directe à la session locale (tcp://127.0.0.1:9559).
Il vous faud le package python 3 avant ! Dispo sur 2.5 et 2.9
Commande : /home/nao/.local/share/PackageManager/apps/python3nao/bin/runpy3.sh python3_test.py
"""

import time
import qi

def main():
    # Connexion directe à la session NAOqi locale
    session = qi.Session()
    session.connect("tcp://127.0.0.1:9559")

    tts = session.service("ALTextToSpeech")
    motion = session.service("ALMotion")
    posture = session.service("ALRobotPosture")
    leds = session.service("ALLeds")
    system = session.service("ALSystem")

    try:
        print("NAOqi:", system.getVersion())
        print("Robot :", system.robotName())
    except Exception:
        pass

    tts.setLanguage("French")
    tts.setVolume(0.7)

    tts.say("Bonjour. Je lance un test simple.")
    motion.wakeUp()
    posture.goToPosture("Stand", 0.5)

    motion.setAngles("HeadYaw", 0.3, 0.2)
    time.sleep(1.2)
    motion.setAngles("HeadYaw", 0.0, 0.2)

    leds.fadeRGB("FaceLeds", "green", 1.0)

    tts.say("Test terminé. Je passe au repos.")
    motion.rest()
    print("OK")

if __name__ == "__main__":
    main()
