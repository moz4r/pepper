#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
my_xar_player.py
----------------
Lecteur d'animations XAR pour Pepper/NAO.
- Laisse le random ON pendant le TTS
- Coupe le random juste avant l'animation
- Le réactive après
"""

import qi
import sys
import xml.etree.ElementTree as ET
import math
import os
import threading
import time


class XarPlayer:
    def __init__(self, session, xar_path):
        self.session = session
        self.motion = session.service("ALMotion")
        self.life = session.service("ALAutonomousLife")
        self.tts = session.service("ALTextToSpeech")
        self.audio = session.service("ALAudioPlayer")
        self.fps = 25.0
        self.xar_path = xar_path
        self.audio_id = None

    def ensure_awake(self):
        """Réveille Pepper et assure un état interactif"""
        try:
            if not self.motion.robotIsWakeUp():
                print("[INFO] Robot endormi, réveil en cours...")
                self.motion.wakeUp()
                time.sleep(1)
            self.motion.setStiffnesses("Body", 1.0)
            if self.life.getState() != "interactive":
                self.life.setState("interactive")
                print("[OK] AutonomousLife -> interactive")
            print("[OK] Moteurs actifs et robot éveillé")
        except Exception as e:
            print("[ERREUR] ensure_awake :", e)

    def disable_random_modules(self):
        """Coupe les mouvements aléatoires avant l'animation"""
        modules = [
            "ALSpeakingMovement",
            "ALListeningMovement",
            "ALBackgroundMovement",
            "BasicAwareness",
        ]
        for name in modules:
            try:
                srv = self.session.service(name)
                srv.setEnabled(False)
                print("[OK] {} désactivé pour l’animation".format(name))
            except Exception as e:
                print("[--] Impossible de désactiver {} : {}".format(name, e))

    def enable_random_modules(self):
        """Réactive les mouvements aléatoires après l'animation"""
        modules = [
            "ALSpeakingMovement",
            "ALListeningMovement",
            "ALBackgroundMovement",
            "BasicAwareness",
        ]
        for name in modules:
            try:
                srv = self.session.service(name)
                srv.setEnabled(True)
                print("[OK] {} réactivé".format(name))
            except Exception as e:
                print("[--] Impossible d'activer {} : {}".format(name, e))

    def play_audio_if_exists(self):
        base, _ = os.path.splitext(self.xar_path)
        for ext in [".mp3", ".wav", ".ogg"]:
            audio_file = base + ext
            if os.path.exists(audio_file):
                def launch_audio():
                    print("[XAR] Lecture audio:", audio_file)
                    try:
                        self.audio_id = self.audio.playFile(audio_file, 1.0, 0.0)
                    except Exception as e:
                        print("[ERROR] Impossible de jouer le fichier audio:", e)
                return threading.Thread(target=launch_audio)
        return None

    def stop_audio(self):
        if self.audio_id is not None:
            try:
                self.audio.stop(self.audio_id)
                print("[XAR] Audio arrêté.")
            except Exception as e:
                print("[ERROR] Impossible d'arrêter l'audio:", e)

    def parse_xar(self):
        """Parse le XAR et exécute les boîtes Say"""
        try:
            tree = ET.parse(self.xar_path)
            root = tree.getroot()
        except Exception as e:
            print("[ERROR] Impossible de parser le XAR:", e)
            return [], [], []

        names, angleLists, timeLists = [], [], []
        ns = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}

        # Gestion des boîtes Say (random encore ON ici)
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

            print("[XAR] Actuator:", actuator)
            print("   Times :", norm_times[:5], "... total", len(norm_times))
            print("   Angles:", safe_angles[:5], "... total", len(safe_angles))

        return names, angleLists, timeLists

    def run(self):
        self.ensure_awake()

        audio_thread = self.play_audio_if_exists()
        names, angles, times = self.parse_xar()

        # Désactivation random seulement maintenant
        self.disable_random_modules()

        if not names:
            print("[XAR] Aucune courbe trouvée.")
            self.enable_random_modules()
            return

        print("[XAR] Exécution de l'animation avec {} articulateurs...".format(len(names)))
        try:
            if audio_thread:
                audio_thread.start()
            self.motion.angleInterpolation(names, angles, times, True)
            self.stop_audio()
            print("[XAR] Animation terminée.")
        except Exception as e:
            print("[ERROR] Pendant l'exécution:", e)

        self.enable_random_modules()


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
