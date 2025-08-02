# -*- coding: utf-8 -*-
"""
shifumi_dialog.py - Pierre-Feuille-Ciseaux avec Pepper
- Utilise ALDialog pour la reconnaissance
- Coupe l'écoute quand Pepper parle
- Réveille Pepper au démarrage
- Met Pepper en mode interactif (solitary) au lieu de disabled pour éviter qu'il s'endorme
- Active la raideur complète du corps pour vitesse maximale
- Bras levé rapidement à mi-hauteur
- Mouvements rapides (poignet et coude)
- Révélation après 3 secondes
- Gestes spécifiques selon pierre, feuille, ciseaux
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

def geste_shifumi(motion, life, choix, tts):
    # Met en mode interactif pour garder Pepper réveillé
    try:
        life.setState("solitary")
        tts.post.say("Je me concentre sur le jeu.")
    except:
        pass

    # Lever le bras rapidement
    motion.angleInterpolationWithSpeed("RShoulderPitch", 0.2, 1.0)
    motion.angleInterpolationWithSpeed("RShoulderRoll", -0.2, 1.0)
    motion.angleInterpolationWithSpeed("RElbowRoll", 1.2, 1.0)

    # Secouement rapide
    for _ in range(4):
        motion.angleInterpolationWithSpeed("RWristYaw", 1.0, 1.0)
        motion.angleInterpolationWithSpeed("RElbowRoll", 1.0, 1.0)
        motion.angleInterpolationWithSpeed("RWristYaw", -1.0, 1.0)
        motion.angleInterpolationWithSpeed("RElbowRoll", 1.2, 1.0)

    # Gestes spécifiques selon le choix
    if choix == "pierre":
        motion.angleInterpolationWithSpeed("RHand", 0.0, 1.0)
    elif choix == "feuille":
        motion.angleInterpolationWithSpeed("RHand", 1.0, 1.0)
    elif choix == "ciseaux":
        motion.angleInterpolationWithSpeed("RHand", 0.5, 1.0)

    # Reste en mode solitary pour qu'il ne s'endorme pas
    try:
        life.setState("solitary")
    except:
        pass

def main(session):
    tts = session.service("ALTextToSpeech")
    motion = session.service("ALMotion")
    dialog = session.service("ALDialog")
    memory = session.service("ALMemory")
    life = session.service("ALAutonomousLife")

    # Réveille Pepper au démarrage
    try:
        life.setState("solitary")
        tts.say("Je suis réveillé et prêt à jouer.")
    except:
        pass

    # Active la raideur du corps pour vitesse max
    motion.setStiffnesses("Body", 1.0)

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
            time.sleep(0.1)

        speak(tts, dialog, "Très bien. Choisis entre pierre, feuille ou ciseaux.")
        recognized_word["word"] = None

        while recognized_word["word"] not in ["pierre", "feuille", "ciseaux"]:
            time.sleep(0.1)

        joueur = recognized_word["word"]
        robot = random.choice(["pierre", "feuille", "ciseaux"])

        # Geste suspense + choix visuel
        geste_shifumi(motion, life, robot, tts)

        speak(tts, dialog, "J'ai choisi...")
        #time.sleep(3)
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
