# -*- coding: utf-8 -*-
"""
MyAnimationPlayer
-----------------
Permet de lire et exécuter une animation au format .qianim
directement sur le robot Pepper/NAO via ALMotion.

Usage :
    python my_anim_player.py /chemin/vers/animation.qianim
"""

import xml.etree.ElementTree as ET
import qi
import sys


class MyAnimationPlayer:
    def __init__(self, session, qianim_path):
        """
        Initialise le lecteur avec :
        - une session Qi (connexion à NAOqi)
        - le chemin du fichier .qianim
        """
        self.motion = session.service("ALMotion")
        self.qianim_path = qianim_path

    def parse_qianim(self):
        """
        Parse le fichier .qianim et prépare les listes pour angleInterpolation :
        - names      : noms des articulations
        - angleLists : liste des positions angulaires
        - timeLists  : liste des temps (croissants, corrigés)
        """
        print("[MyAnimationPlayer] Parsing: {}".format(self.qianim_path))
        tree = ET.parse(self.qianim_path)
        root = tree.getroot()

        # Récupère le framerate défini dans le fichier (par défaut 25 fps)
        fps = float(root.attrib.get('editor:fps', 25))

        names, angleLists, timeLists = [], [], []

        # Boucle sur toutes les courbes d’articulateurs
        for curve in root.findall("ActuatorCurve"):
            actuator = curve.attrib.get("actuator")
            keys = curve.findall("Key")

            if not actuator or not keys:
                continue

            times, angles = [], []
            last_t = 0.0

            # Extraction des keyframes
            for key in keys:
                frame = int(key.attrib["frame"])
                val = float(key.attrib["value"])
                t = round(frame / fps, 3)

                # Correction pour garantir des temps strictement croissants
                if t <= 0.0:
                    t = 0.1
                if t <= last_t:
                    t = round(last_t + 0.01, 3)

                times.append(t)
                angles.append(val)
                last_t = t

            names.append(actuator)
            angleLists.append(angles)
            timeLists.append(times)

            # Debug : affiche les 5 premières valeurs
            print("Actuator: {}".format(actuator))
            print("  Times (first 5): {} ... total {}".format(times[:5], len(times)))
            print("  Angles (first 5): {} ... total {}".format(angles[:5], len(angles)))

        return names, angleLists, timeLists

    def run(self):
        """Exécute l’animation synchronisée sur le robot."""
        names, angleLists, timeLists = self.parse_qianim()

        if not names:
            print("[MyAnimationPlayer] No valid keyframes found.")
            return

        # Vérifie que toutes les timelines sont strictement croissantes
        for i, tlist in enumerate(timeLists):
            for j in range(1, len(tlist)):
                if tlist[j] <= tlist[j - 1]:
                    print("[ERROR] Timeline not increasing for {} at index {}: {} -> {}".format(
                        names[i], j, tlist[j - 1], tlist[j]))
                    return

        print("[MyAnimationPlayer] Executing synchronized motion...")
        self.motion.angleInterpolation(names, angleLists, timeLists, True)
        print("[MyAnimationPlayer] Animation done.")


def main():
    if len(sys.argv) < 2:
        print("Usage: python my_anim_player.py path/to/animation.qianim")
        sys.exit(1)

    path = sys.argv[1]

    # Connexion à NAOqi
    app = qi.Application(["MyAnimationPlayer", "--qi-url=tcp://127.0.0.1:9559"])
    app.start()
    session = app.session

    # Lecture et exécution
    player = MyAnimationPlayer(session, path)
    player.run()

    app.stop()


if __name__ == "__main__":
    main()
