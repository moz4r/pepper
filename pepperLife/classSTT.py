# -*- coding: utf-8 -*-
# classSTT.py - Speech-to-Text using OpenAI

from openai import OpenAI

class STT(object):
    def __init__(self, config):
        self.config = config
        self._client = None

    def client(self):
        if self._client is None:
            self._client = OpenAI(timeout=15.0)
        return self._client

    def stt(self, wav_bytes):
        f = ("speech.wav", wav_bytes, "audio/wav")
        try:
            r = self.client().audio.transcriptions.create(
                model=self.config['openai']['stt_model'], file=f, language="fr", temperature=0
            )
        except Exception:
            r = self.client().audio.transcriptions.create(
                model="whisper-1", file=f, language="fr", temperature=0
            )
        return (getattr(r, "text", None) or "").strip() or None
