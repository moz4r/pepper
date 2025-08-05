#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
my_xar_player.py
----------------
Lecteur d'animations XAR (Choregraphe) pour Pepper/NAO sans ALBehaviorManager.

- Parse les fichiers .xar exportés par Choregraphe
- Extrait les courbes d'articulateurs
- Convertit les angles en radians si nécessaire
- Clippe automatiquement les valeurs aux limites mécaniques du robot
- Exécute l'animation avec ALMotion.angleInterpolation

Usage :
    python my_xar_player.py /home/nao/.local/share/PackageManager/apps/demo/behavior_1/behavior.xar
"""

import qi
import sys
import xml.etree.ElementTree as ET
import math


class XarPlayer:
    def __init__(self, session, xar_path):
        """Initialise le lecteur avec une session Qi et le chemin du XAR."""
        self.session = session
        self.motion = session.service("ALMotion")
        self.fps = 25.0   # Framerate par défaut des timelines Choregraphe
        self.xar_path = xar_path

    def parse_xar(self):
        """
        Parse le fichier XAR pour extraire les timelines d'angles.
        Retourne :
            names      -> liste des noms d'articulateurs
            angleLists -> liste des valeurs d'angles (en radians, clipées)
            timeLists  -> liste des temps correspondants
        """
        try:
            tree = ET.parse(self.xar_path)
            root = tree.getroot()
        except Exception as e:
            print("[ERROR] Impossible de parser le XAR:", e)
            return [], [], []

        names, angleLists, timeLists = [], [], []
        ns = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}

        # Recherche toutes les courbes d'articulateurs
        curves = root.findall(".//ns:ActuatorCurve", ns) if ns else root.findall(".//ActuatorCurve")

        for curve in curves:
            actuator = curve.attrib.get("actuator")
            unit = curve.attrib.get("unit", "0")  # 0 = degrés, 1 = radians

            if not actuator:
                continue

            keys = curve.findall("ns:Key", ns) if ns else curve.findall("Key")
            if not keys:
                continue

            # Extraction des frames -> temps, et des angles
            times = [int(k.attrib["frame"]) / self.fps for k in keys]
            angles = [float(k.attrib["value"]) for k in keys]

            # Conversion en radians si nécessaire
            if unit == "0":  
                angles = [math.radians(a) for a in angles]

            # Normalisation des temps (suppression des doublons)
            norm_times, norm_angles = [], []
            last_t = -1.0
            for t, a in zip(times, angles):
                if t > last_t:
                    norm_times.append(round(t, 2))
                    norm_angles.append(a)
                    last_t = t

            # Récupération des limites articulaires et clipping
            try:
                limits = self.motion.getLimits(actuator)
                min_angle, max_angle = limits[0][0], limits[0][1]
                safe_angles = [max(min(a, max_angle), min_angle) for a in norm_angles]
            except Exception:
                # Si on ne peut pas obtenir les limites (rare), on ne clippe pas
                safe_angles = norm_angles

            if norm_times:
                names.append(actuator)
                angleLists.append(safe_angles)
                timeLists.append(norm_times)

            # Debug print
            print("[XAR] Actuator: {}".format(actuator))
            print("   Times : {} ... total {}".format(norm_times[:5], len(norm_times)))
            print("   Angles: {} ... total {}".format(safe_angles[:5], len(safe_angles)))

        return names, angleLists, timeLists

    def run(self):
        """Exécute l'animation sur le robot."""
        names, angles, times = self.parse_xar()
        if not names:
            print("[XAR] Aucune courbe d'actuateur trouvée.")
            return

        print("[XAR] Exécution de l'animation avec {} articulateurs...".format(len(names)))
        try:
            self.motion.angleInterpolation(names, angles, times, True)
            print("[XAR] Animation terminée.")
        except Exception as e:
            print("[ERROR] Pendant l'exécution:", e)


def main():
    if len(sys.argv) < 2:
        print("Usage: python my_xar_player.py path/to/behavior.xar")
        sys.exit(1)

    xar_path = sys.argv[1]

    # Démarrage d'une application Qi pour se connecter à NAOqi
    app = qi.Application(["XarPlayer", "--qi-url=tcp://127.0.0.1:9559"])
    app.start()
    session = app.session

    # Instanciation du lecteur et exécution
    player = XarPlayer(session, xar_path)
    player.run()


if __name__ == "__main__":
    main()
