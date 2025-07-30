# -*- coding: utf-8 -*-
# demo_simple.py
import qi
import time

def main():
    session = qi.Session()
    session.connect("tcp://127.0.0.1:9559")
    print("[OK] Connecté à NAOqi")

    tts = session.service("ALTextToSpeech")
    motion = session.service("ALMotion")

    # Réveiller le robot
    motion.wakeUp()
    print("[OK] Robot réveillé")

    # Test parole
    tts.say("Bonjour, je suis Pepper !")

    # Test mouvement tête
    names = ["HeadYaw", "HeadPitch"]
    angles = [0.5, -0.3]   # tourner la tête à droite et baisser légèrement
    fractionMaxSpeed = 0.2
    motion.setAngles(names, angles, fractionMaxSpeed)
    print("[OK] Tête bougée")

    time.sleep(5)

    # Retour position neutre
    motion.setAngles(names, [0.0, 0.0], 0.2)
    print("[OK] Tête revenue au centre")

    tts.say("Test terminé.")

if __name__ == "__main__":
    main()
