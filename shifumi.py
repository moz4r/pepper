# -*- coding: utf-8 -*-
"""
shifumi_dialog.py - Pierre-Feuille-Ciseaux avec Pepper
- Utilise ALDialog pour la reconnaissance
- Coupe l'écoute quand Pepper parle
- Geste plus ample et secouement avant révélation
"""

import qi
import sys
import time
import random

def speak(tts, dialog, phrase):
    """Fait parler Pepper sans qu'il s'écoute."""
    try:
        dialog.unsubscribe("ShifumiGame")
    except:
        pass
    tts.say(phrase)
    dialog.subscribe("ShifumiGame")

def main(session):
    tts = session.service("ALTextToSpeech")
    motion = session.service("ALMotion")
    dialog = session.service("ALDialog")
    memory = session.service("ALMemory")

    try:
        dialog.stopDialog()
    except:
        pass

    topic_content = u"""
    topic: ~shifumi()
    language: frf
    u:(shifumi) shifumi
    u:(pierre) pierre
    u:(feuille) feuille
    u:(ciseaux) ciseaux
    """
    topic_name = dialog.loadTopicContent(topic_content)
    dialog.activateTopic(topic_name)
    dialog.subscribe("ShifumiGame")

    recognized_word = {"word": None}

    def on_input(value):
        if value:
            recognized_word["word"] = value
            print("[DEBUG] reconnu:", value)

    subscriber = memory.subscriber("Dialog/LastInput")
    subscriber.signal.connect(on_input)

    speak(tts, dialog, "Dis 'shifumi' pour commencer à jouer.")

    while True:
        while recognized_word["word"] != "shifumi":
            time.sleep(0.5)

        speak(tts, dialog, "Très bien. Choisis entre pierre, feuille ou ciseaux.")
        recognized_word["word"] = None

        while recognized_word["word"] not in ["pierre", "feuille", "ciseaux"]:
            time.sleep(0.5)

        joueur = recognized_word["word"]
        robot = random.choice(["pierre", "feuille", "ciseaux"])

        # Lever le bras haut
        motion.angleInterpolationWithSpeed("RShoulderPitch", -0.3, 0.2)  # bras vers le haut
        motion.angleInterpolationWithSpeed("RElbowRoll", 1.2, 0.2)

        # Secouer 3 fois
        for _ in range(3):
            motion.angleInterpolationWithSpeed("RWristYaw", 1.0, 0.3)
            motion.angleInterpolationWithSpeed("RWristYaw", -1.0, 0.3)

        speak(tts, dialog, "J'ai choisi...")
        time.sleep(1)
        speak(tts, dialog, robot)

        if joueur == robot:
            resultat = "Égalité."
        elif (joueur == "pierre" and robot == "ciseaux") or \
             (joueur == "feuille" and robot == "pierre") or \
             (joueur == "ciseaux" and robot == "feuille"):
            resultat = "Tu as gagné !"
        else:
            resultat = "J'ai gagné !"

        speak(tts, dialog, resultat)
        recognized_word["word"] = None
        speak(tts, dialog, "Dis 'shifumi' pour rejouer.")

if __name__ == "__main__":
    try:
        connection_url = "tcp://127.0.0.1:9559"
        app = qi.Application(["Shifumi", "--qi-url=" + connection_url])
    except RuntimeError:
        print("Impossible de se connecter à Pepper.")
        sys.exit(1)

    app.start()
    session = app.session
    main(session)
