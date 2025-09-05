# -*- coding: utf-8 -*-
# classSpeak.py — TTS asynchrone + orchestration "parler & bouger"

import time, threading
from classRobotActions import MARKER_RE  # même regex globale

class Speaker(object):
    def __init__(self, tts, leds, listener, speaking_flag):
        self.tts = tts
        self.leds = leds
        self.cap = listener
        self.SPEAKING = speaking_flag

    def _say_async(self, text):
        self.SPEAKING["on"] = True
        self.leds.speaking_start()
        try:
            try: self.cap.flush_ring()
            except: pass
            try:
                task_id = self.tts.post.say(text)
                return ("post", task_id)
            except Exception:
                pass
            self.tts.say(text)  # fallback
            return ("sync", None)
        except:
            self.SPEAKING["on"] = False
            try: self.leds.speaking_stop()
            except: pass
            raise

    def _wait_tts_end(self, handle, timeout=12.0):
        kind, _ = handle
        t0 = time.time()
        if hasattr(self.tts, "isSpeaking"):
            while time.time()-t0 < timeout:
                try:
                    if not self.tts.isSpeaking(): break
                except: break
                time.sleep(0.05)
        else:
            if kind == "post": time.sleep(0.4)
        self.SPEAKING["on"] = False
        try: self.leds.speaking_stop()
        except: pass
        time.sleep(0.06)

    def say_quick(self, text):
        h = self._say_async(text)
        self._wait_tts_end(h, timeout=12.0)

    def speak_and_actions_parallel(self, rep_text, acts, beh):
        rep_clean = MARKER_RE.sub("", rep_text).strip()

        def _do_actions():
            if not MARKER_RE.search(rep_text): return
            try:
                beh.begin_control()
                _, done = acts.execute_markers(rep_text)
                if done: print("[ACTIONS] exécutées:", done)
            finally:
                beh.end_control()

        th = threading.Thread(target=_do_actions); th.daemon=True
        h = self._say_async(rep_clean)
        th.start()
        self._wait_tts_end(h, timeout=20.0)
        try: self.cap.flush_ring()
        except: pass
        th.join(timeout=10.0)
