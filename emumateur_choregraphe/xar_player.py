#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
my_xar_player.py
----------------
Lecteur d'animations XAR (Choregraphe) pour Pepper/NAO sans ALBehaviorManager.

- Parse les fichiers .xar exportés par Choregraphe
- Extrait les courbes d'articulateurs et les boîtes Say
- Convertit les angles en radians si nécessaire
- Clippe automatiquement les valeurs aux limites mécaniques du robot
- Met uniquement les moteurs raides (sans forcer wakeUp pour éviter le cycle dormir/réveil)
- Exécute l'animation avec ALMotion.angleInterpolation
- Supporte les boîtes Say avec gestion du lock (attente si nécessaire)

Usage :
    python my_xar_player.py /home/nao/.local/share/PackageManager/apps/demo/behavior_1/behavior.xar
"""

import qi
import sys
import xml.etree.ElementTree as ET
import math


class XarPlayer:
    def __init__(self, session, xar_path):
        self.session = session
        self.motion = session.service("ALMotion")
        self.life = session.service("ALAutonomousLife")
        self.tts = session.service("ALTextToSpeech")
        self.fps = 25.0
        self.xar_path = xar_path

    def prepare_robot(self):
        try:
            current_state = self.life.getState()
            print("[XAR] Autonomous Life actuel:", current_state)
            if current_state != "disabled":
                self.life.setState("disabled")
                print("[XAR] Autonomous Life désactivé.")
        except Exception as e:
            print("[WARN] Impossible de gérer Autonomous Life:", e)

        try:
            self.motion.setStiffnesses("Body", 1.0)
            print("[XAR] Moteurs rendus raides (sans wakeUp).")
        except Exception as e:
            print("[ERROR] Impossible d’activer les moteurs:", e)

    def parse_xar(self):
        try:
            tree = ET.parse(self.xar_path)
            root = tree.getroot()
        except Exception as e:
            print("[ERROR] Impossible de parser le XAR:", e)
            return [], [], []

        names, angleLists, timeLists = [], [], []
        ns = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}

        # Gestion des boîtes Say
        boxes = root.findall(".//ns:Box", ns) if ns else root.findall(".//Box")
        for box in boxes:
            if box.attrib.get("name") == "Say":
                params = {p.attrib['name']: p.attrib.get('value', '') for p in box.findall("ns:Parameter", ns)}
                text = params.get("Text", "")
                speed = params.get("Speed (%)", "100")
                shaping = params.get("Voice shaping (%)", "100")
                sentence = "\\RSPD={}\\ \\VCT={}\\ {} \\RST\\".format(speed, shaping, text)
                use_blocking = any(r.attrib.get('type') == 'Lock' for r in box.findall("ns:Resource", ns))
                try:
                    if use_blocking:
                        print("[XAR] TTS (bloquant):", text)
                        self.tts.say(sentence)
                    else:
                        print("[XAR] TTS (non bloquant):", text)
                        self.tts.post.say(sentence)
                except Exception as e:
                    print("[ERROR] Impossible d'exécuter TTS:", e)

        # Gestion des actuateurs
        curves = root.findall(".//ns:ActuatorCurve", ns) if ns else root.findall(".//ActuatorCurve")
        for curve in curves:
            actuator = curve.attrib.get("actuator")
            unit = curve.attrib.get("unit", "0")
            if not actuator:
                continue

            keys = curve.findall("ns:Key", ns) if ns else curve.findall("Key")
            if not keys:
                continue

            times = [int(k.attrib["frame"]) / self.fps for k in keys]
            angles = [float(k.attrib["value"]) for k in keys]

            if unit == "0":
                angles = [math.radians(a) for a in angles]

            norm_times, norm_angles = [], []
            last_t = -1.0
            for t, a in zip(times, angles):
                if t > last_t:
                    norm_times.append(round(t, 2))
                    norm_angles.append(a)
                    last_t = t

            try:
                limits = self.motion.getLimits(actuator)
                min_angle, max_angle = limits[0][0], limits[0][1]
                safe_angles = [max(min(a, max_angle), min_angle) for a in norm_angles]
            except Exception:
                safe_angles = norm_angles

            if norm_times:
                names.append(actuator)
                angleLists.append(safe_angles)
                timeLists.append(norm_times)

            print("[XAR] Actuator: {}".format(actuator))
            print("   Times : {} ... total {}".format(norm_times[:5], len(norm_times)))
            print("   Angles: {} ... total {}".format(safe_angles[:5], len(safe_angles)))

        return names, angleLists, timeLists

    def run(self):
        self.prepare_robot()
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

    app = qi.Application(["XarPlayer", "--qi-url=tcp://127.0.0.1:9559"])
    app.start()
    session = app.session

    player = XarPlayer(session, xar_path)
    player.run()


if __name__ == "__main__":
    main()
