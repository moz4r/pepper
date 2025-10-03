# -*- coding: utf-8 -*-
# classSpeak.py — TTS asynchrone + orchestration "parler & bouger"

import time

class Speaker(object):
    def __init__(self, tts, leds, listener, beh, anim=None):
        self.tts = tts
        self.leds = leds
        self.cap = listener
        self.beh = beh
        self.anim = anim

    def _say_async(self, text):
        self.leds.speaking_start()
        try: self.cap.microEnabled["on"] = False
        except: pass
        with self.cap.lock:
            self.cap.speaking = True
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
            try: self.leds.speaking_stop()
            except: pass
            raise

    def _wait_tts_end(self, handle, timeout=8.0):
        kind, tok = handle

        # Attendre la fin de la tâche TTS si un future est disponible
        if tok and hasattr(tok, 'wait'):
            try:
                tok.wait(timeout)
            except Exception:
                # En cas d'erreur ou de timeout, on continue pour ne pas bloquer
                pass
        elif kind == "post":
            # Fallback très simple si .post ne retourne pas de future
            time.sleep(0.5)

        try: self.cap.microEnabled["on"] = True
        except: pass

        try:
            self.leds.speaking_stop()   # oreilles ON, yeux blancs
        except:
            pass


    def _prep_text(self, text, intent=None):
        if self.anim:
            try:
                return self.anim.normalize_text(text, intent=intent)
            except Exception as e:
                self.beh.log("[ANIM] normalize err: %s" % e, level='warning')
        # fallback: strip les balises si AnimatedSpeech indispo
        import re
        return re.sub(r'\^(start|wait)\([^)]+\)', '', text, flags=re.IGNORECASE)

    def say_quick(self, text, intent=None):
        text = self._prep_text(text, intent=intent)
        self.beh.log(f"[TTS] {text}", level='info')
        h = self._say_async(text)
        self._wait_tts_end(h, timeout=15.0)
