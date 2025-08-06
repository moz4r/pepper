#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
my_xar_player.py
----------------
Lecteur d'animations XAR pour Pepper/NAO.
- Laisse le random ON pendant le TTS
- Coupe le random juste avant l'animation
- Le réactive après
- FPS dynamique si défini dans <Timeline>
- Lecture audio intelligente
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

        try:
            self.available_joints = set(self.motion.getBodyNames("Body"))
        except Exception as e:
            print("[ERROR] Impossible d'obtenir les articulateurs disponibles :", e)
            self.available_joints = set()

    def ensure_awake(self):
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
        audio_extensions = [".mp3", ".wav", ".ogg"]

        for ext in audio_extensions:
            audio_file = base + ext
            if os.path.exists(audio_file):
                def launch_audio():
                    print("[XAR] Lecture audio (même nom):", audio_file)
                    try:
                        self.audio_id = self.audio.playFile(audio_file, 1.0, 0.0)
                    except Exception as e:
                        print("[ERROR] Impossible de jouer le fichier audio:", e)
                return threading.Thread(target=launch_audio)

        folder = os.path.dirname(self.xar_path)
        try:
            for file in os.listdir(folder):
                if file.lower().endswith(tuple(audio_extensions)):
                    audio_file = os.path.join(folder, file)
                    def launch_audio():
                        print("[XAR] Lecture audio (fallback dossier):", audio_file)
                        try:
                            self.audio_id = self.audio.playFile(audio_file, 1.0, 0.0)
                        except Exception as e:
                            print("[ERROR] Impossible de jouer le fichier audio:", e)
                    return threading.Thread(target=launch_audio)
        except Exception as e:
            print("[WARN] Impossible de lire le dossier pour trouver un fichier audio :", e)

        return None

    def stop_audio(self):
        if self.audio_id is not None:
            try:
                self.audio.stop(self.audio_id)
                print("[XAR] Audio arrêté.")
            except Exception as e:
                print("[ERROR] Impossible d'arrêter l'audio:", e)

    def parse_xar(self):
        try:
            tree = ET.parse(self.xar_path)
            root = tree.getroot()
        except Exception as e:
            print("[ERROR] Impossible de parser le XAR:", e)
            return []

        ns = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}

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

        blocks = []
        diagrams = root.findall(".//Diagram")
        for i, diagram in enumerate(diagrams, 1):
            print("[XAR] Bloc {} sur {}".format(i, len(diagrams)))

            timeline = diagram.find("../Timeline")
            local_fps = self.fps
            if timeline is not None and 'fps' in timeline.attrib:
                try:
                    local_fps = float(timeline.attrib['fps'])
                    if local_fps > 0:
                        print("[XAR] FPS local utilisé dans ce bloc:", local_fps)
                except ValueError:
                    pass

            curves = diagram.findall(".//ns:ActuatorCurve", ns) if ns else diagram.findall(".//ActuatorCurve")

            joint_map = {}
            actuators_in_xar = set()

            for curve in curves:
                actuator = curve.attrib.get("actuator")
                unit = curve.attrib.get("unit", "0")
                if not actuator:
                    continue

                actuators_in_xar.add(actuator)
                if actuator not in self.available_joints:
                    print("[WARN] Articulateur inconnu sur ce robot :", actuator)
                    continue

                keys = curve.findall("ns:Key", ns) if ns else curve.findall("Key")
                if not keys:
                    continue

                times = [int(k.attrib["frame"]) / local_fps for k in keys]
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
                    if actuator not in joint_map:
                        joint_map[actuator] = ([], [])
                    joint_map[actuator][0].extend(safe_angles)
                    joint_map[actuator][1].extend(norm_times)

                print("[XAR] Actuator:", actuator)
                print("   Times :", norm_times[:5], "... total", len(norm_times))
                print("   Angles:", safe_angles[:5], "... total", len(safe_angles))

            names, angleLists, timeLists = [], [], []
            for joint, (angles, times) in joint_map.items():
                sorted_pairs = sorted(zip(times, angles), key=lambda x: x[0])
                times_sorted, angles_sorted = zip(*sorted_pairs)
                names.append(joint)
                angleLists.append(list(angles_sorted))
                timeLists.append(list(times_sorted))

            blocks.append((names, angleLists, timeLists))

        return blocks

    def run(self):
        self.ensure_awake()
        audio_thread = self.play_audio_if_exists()
        blocks = self.parse_xar()
        self.disable_random_modules()

        if not blocks:
            print("[XAR] Aucune courbe trouvée.")
            self.enable_random_modules()
            return

        try:
            if audio_thread:
                audio_thread.start()

            for names, angles, times in blocks:
                print("[XAR] Exécution d’un bloc avec {} articulateurs...".format(len(names)))
                print("[DEBUG] Articulateurs utilisés :", names)
                print("[DEBUG] Total :", len(names))
                print("[DEBUG] Articulateurs inconnus dans ce bloc :", set(names) - self.available_joints)
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
