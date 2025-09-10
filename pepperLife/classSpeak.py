# -*- coding: utf-8 -*-
# classSpeak.py — TTS asynchrone + orchestration "parler & bouger"

import time, threading
from classRobotActions import MARKER_RE

class Speaker(object):
    def __init__(self, tts, leds, listener, speaking_flag, acts, beh):
        self.tts = tts
        self.leds = leds
        self.cap = listener
        self.SPEAKING = speaking_flag
        self.acts = acts
        self.beh = beh

    def _say_async(self, text):
        self.SPEAKING["on"] = True
        self.leds.speaking_start()
        try:
            try:
                self.cap.mon[:] = []; self.cap.pre[:] = []  # anti-larsen soft
            except:
                pass

            # 1) Non-bloquant natif
            try:
                task_id = self.tts.post.say(text)
                return ("post", task_id)
            except Exception:
                pass

            # 2) Fallback non-bloquant via qi.async / qi.async_
            try:
                import qi as _qi
                _async = getattr(_qi, "async", None) or getattr(_qi, "async_", None)
                if _async:
                    fut = _async(self.tts.say, text)
                    return ("future", fut)
            except Exception:
                pass

            # 3) Dernier recours: bloquant
            self.tts.say(text)
            return ("sync", None)

        except:
            self.SPEAKING["on"] = False
            try: self.leds.speaking_stop()
            except: pass
            raise

    def _wait_tts_end(self, handle, timeout=8.0):
        kind, tok = handle
        t0 = time.time()

        # Future qi -> attendre la fin du tts.say lancé via qi.async
        if kind == "future" and hasattr(tok, "value"):
            try:
                tok.value()
            except:
                pass
        else:
            # Attente "classique"
            if hasattr(self.tts, "isSpeaking"):
                while time.time() - t0 < timeout:
                    try:
                        if not self.tts.isSpeaking():
                            break
                    except:
                        break
                    time.sleep(0.05)
            else:
                if kind == "post":
                    time.sleep(0.35)

        self.SPEAKING["on"] = False
        try:
            self.leds.speaking_stop()   # oreilles ON, yeux blancs
        except:
            pass
        time.sleep(0.06)

    def say_quick(self, text):
        """Helper pour un TTS bref (non-bloquant si possible, sinon bloquant)."""
        h = self._say_async(text)
        self._wait_tts_end(h, timeout=15.0)

    def _has_motion_markers(self, text):
        return MARKER_RE.search(text) is not None

    def speak_and_actions_parallel(self, rep):
        rep_clean = MARKER_RE.sub("", rep).strip()

        def _do_actions():
            if not self._has_motion_markers(rep):
                return
            try:
                self.beh.begin_control()
                _, done = self.acts.execute_markers(rep)   # bloquant jusqu’à fin des moves
                if done: print("[ACTIONS] exécutées:", done)
            finally:
                self.beh.end_control()

        th = threading.Thread(target=_do_actions); th.daemon = True

        # ⬇️ lancer les gestes d'abord (ils partiront même si le TTS retombait en bloquant)
        th.start()

        # puis démarrer le TTS (désormais non bloquant via PATCH 1)
        h = self._say_async(rep_clean)

        # attendre la fin de la parole
        self._wait_tts_end(h, timeout=20.0)

        try:
            self.cap.mon[:] = []; self.cap.pre[:] = []
        except:
            pass

        th.join(timeout=10.0)
