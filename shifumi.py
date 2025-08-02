# -*- coding: utf-8 -*-
"""
shifumi_dialog.py - Pierre-Feuille-Ciseaux avec Pepper
- Utilise ALDialog pour la reconnaissance
- Coupe l'écoute quand Pepper parle
- Désactive Autonomous Life seulement après le choix pierre/feuille/ciseaux
- Fait secouer le bras et tourner le poignet rapidement pendant environ 2 secondes avant la révélation
- Réactive Autonomous Life à la fin du jeu
"""

import qi
import sys
import time
import random

def speak(tts, dialog, phrase):
    try:
        dialog.unsubscribe("ShifumiGame")
    except:
        pass
    tts.say(phrase)
    dialog.subscribe("ShifumiGame")

def reset_position(motion):
    names  = ["RShoulderPitch", "RShoulderRoll", "RElbowRoll", "RWristYaw", "RHand"]
    angles = [1.5, 0.0, 0.5, 0.0, 0.0]
    speeds = [1.0, 1.0, 1.0, 1.0, 1.0]
    for n, a, s in zip(names, angles, speeds):
        motion.angleInterpolationWithSpeed(n, a, s)

def geste_shifumi(motion, choix):
    motion.angleInterpolationWithSpeed("RShoulderPitch", 0.2, 1.0)
    motion.angleInterpolationWithSpeed("RShoulderRoll", -0.2, 1.0)
    motion.angleInterpolationWithSpeed("RElbowRoll", 1.2, 1.0)

    start_time = time.time()
    while time.time() - start_time < 2.0:  # secoue pendant 2 secondes
        motion.angleInterpolation(["RWristYaw"], [[1.0], [-1.0]], [[0.5], [0.5]], True)
        motion.angleInterpolation(["RElbowRoll"], [[1.0], [1.2]], [[0.5], [0.5]], True)

    if choix == "pierre":
        motion.angleInterpolationWithSpeed("RHand", 0.0, 1.0)
    elif choix == "feuille":
        motion.angleInterpolationWithSpeed("RHand", 1.0, 1.0)
    elif choix == "ciseaux":
        motion.angleInterpolationWithSpeed("RHand", 0.5, 1.0)

def main(session):
    tts = session.service("ALTextToSpeech")
    motion = session.service("ALMotion")
    dialog = session.service("ALDialog")
    memory = session.service("ALMemory")
    life = session.service("ALAutonomousLife")

    motion.setStiffnesses("Body", 1.0)
    reset_position(motion)

    try:
        dialog.stopDialog()
    except:
        pass

    dialog.activateTopic(dialog.loadTopicContent(u"""
    topic: ~shifumi()
    language: frf
    u:(shifumi) shifumi
    u:(pierre) pierre
    u:(feuille) feuille
    u:(ciseaux) ciseaux
    """))
    dialog.subscribe("ShifumiGame")

    recognized_word = {"word": None}

    def on_input(value):
        if value:
            recognized_word["word"] = value
            print("[DEBUG] reconnu:", value)

    subscriber = memory.subscriber("Dialog/LastInput")
    subscriber.signal.connect(on_input)

    speak(tts, dialog, "Dis 'shifumi' pour commencer à jouer.")

    try:
        while True:
            while recognized_word["word"] != "shifumi":
                time.sleep(0.1)

            speak(tts, dialog, "Très bien. Choisis entre pierre, feuille ou ciseaux.")
            recognized_word["word"] = None

            while recognized_word["word"] not in ["pierre", "feuille", "ciseaux"]:
                time.sleep(0.1)

            # Une fois le choix dit, couper Autonomous Life
            try:
                life.stopAll()
                life.setAutonomousAbilityEnabled("All", False)
            except:
                pass

            joueur = recognized_word["word"]
            robot = random.choice(["pierre", "feuille", "ciseaux"])

            geste_shifumi(motion, robot)

            speak(tts, dialog, "J'ai choisi...")
            time.sleep(0.7)
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
            reset_position(motion)
            speak(tts, dialog, "Dis 'shifumi' pour rejouer.")
    finally:
        try:
            life.setAutonomousAbilityEnabled("All", True)
            tts.say("Fin du jeu, Autonomous Life réactivé.")
        except:
            pass

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
