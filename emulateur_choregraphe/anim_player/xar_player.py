#!/usr/bin/env python
# -*- coding: utf-8 -*-

from services import get_robot_services
from random_control import disable_random_modules, enable_random_modules
from audio_control import play_audio_if_exists, stop_audio
from xar_parser import parse_xar

class XarPlayer:
    def __init__(self, session, xar_path, audio_override=None):
        self.session = session
        self.motion, self.life, self.tts, self.audio = get_robot_services(session)
        self.xar_path = xar_path
        self.audio_override = audio_override
        self.audio_id = None

    def ensure_awake(self):
        try:
            if not self.motion.robotIsWakeUp():
                print("[INFO] Robot endormi, réveil en cours...")
                self.motion.wakeUp()
            self.motion.setStiffnesses("Body", 1.0)
            if self.life.getState() != "interactive":
                self.life.setState("interactive")
                print("[OK] AutonomousLife -> interactive")
            print("[OK] Moteurs actifs et robot éveillé")
        except Exception as e:
            print("[ERREUR] ensure_awake :", e)

    def run(self):
        self.ensure_awake()

        # Lancer audio (capture ID si dispo)
        audio_thread = play_audio_if_exists(
            self.audio,
            self.xar_path,
            override=self.audio_override,
            store_id_callback=lambda _id: setattr(self, "audio_id", _id)
        )

        names, angles, times = parse_xar(self.xar_path, self.tts, self.motion)

        # Sécurité: aucun doublon d'articulateur
        if len(names) != len(set(names)):
            print("[FATAL] Doublons détectés dans la liste des articulateurs envoyés à ALMotion.")
            seen = {}
            for i, n in enumerate(names):
                seen.setdefault(n, []).append(i)
            for k, idxs in seen.items():
                if len(idxs) > 1:
                    print("  - %s apparait %d fois (indices: %s)" % (k, len(idxs), idxs))
            print("Abandon pour éviter l'erreur NAOqi.")
            return

        disable_random_modules(self.session)

        if not names:
            print("[XAR] Aucune courbe sélectionnée.")
            enable_random_modules(self.session)
            return

        try:
            if audio_thread:
                audio_thread.start()

            self.motion.angleInterpolation(names, angles, times, True)

            # Stop audio
            stop_audio(self.audio, self.audio_id)

            print("[XAR] Animation terminée.")
        except Exception as e:
            print("[ERROR] Pendant l'exécution:", e)

        enable_random_modules(self.session)
