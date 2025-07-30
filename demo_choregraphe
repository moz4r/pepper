# -*- coding: utf-8 -*-
import time
from naoqi import ALProxy

class MyClass(GeneratedClass):
    def __init__(self):
        GeneratedClass.__init__(self)
        self.tts = None
        self.motion = None

    def onLoad(self):
        try:
            # Comme le script tourne directement sur le robot
            robot_ip = "127.0.0.1"
            robot_port = 9559

            self.tts = ALProxy("ALTextToSpeech", robot_ip, robot_port)
            self.motion = ALProxy("ALMotion", robot_ip, robot_port)

            print("[Choregraphe] Services initialisés")
        except Exception as e:
            print("[ERREUR] Impossible d’initialiser les services :", e)

    def onUnload(self):
        print("[Choregraphe] Script déchargé")

    def onInput_onStart(self):
        try:
            self.motion.wakeUp()
            print("[OK] Robot réveillé")

            self.tts.say("Bonjour, je suis Pepper !")

            names = ["HeadYaw", "HeadPitch"]
            angles = [0.5, -0.3]
            self.motion.setAngles(names, angles, 0.2)
            print("[OK] Tête bougée")

            time.sleep(5)

            self.motion.setAngles(names, [0.0, 0.0], 0.2)
            print("[OK] Tête revenue au centre")

            self.tts.say("Test terminé.")
        except Exception as e:
            print("[ERREUR] Problème pendant l’exécution :", e)

        self.onStopped()

    def onInput_onStop(self):
        print("[Choregraphe] Arrêt demandé")
        self.onUnload()
        self.onStopped()
