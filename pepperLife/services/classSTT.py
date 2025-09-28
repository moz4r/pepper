# -*- coding: utf-8 -*-
# classSTT.py - Speech-to-Text using OpenAI

from openai import OpenAI

class STT(object):
    def __init__(self, config, logger=None):
        self.config = config
        self._client = None
        self._log = logger or (lambda *a, **k: None)

    def client(self):
        if self._client is None:
            self._client = OpenAI(timeout=15.0)
        return self._client

    def stt(self, wav_bytes):
        f = ("speech.wav", wav_bytes, "audio/wav")
        model1 = self.config['openai']['stt_model']
        self._log(f"[STT] Tentative de transcription avec le modèle : {model1}", level='debug')
        try:
            r = self.client().audio.transcriptions.create(
                model=model1, file=f, language="fr", temperature=0
            )
            text = (getattr(r, "text", None) or "").strip() or None
            self._log(f"[STT] Succès avec {model1}. Résultat : '{text}'", level='debug')
            return text
        except Exception as e:
            self._log(f"[STT] Échec avec le modèle {model1}: {e}", level='warning')
            self._log("[STT] Basculement vers whisper-1...", level='warning')
            try:
                r = self.client().audio.transcriptions.create(
                    model="whisper-1", file=f, language="fr", temperature=0
                )
                text = (getattr(r, "text", None) or "").strip() or None
                self._log(f"[STT] Succès avec whisper-1. Résultat : '{text}'", level='debug')
                return text
            except Exception as e2:
                self._log(f"[STT] Le modèle de secours whisper-1 a également échoué : {e2}", level='error')
                return None
