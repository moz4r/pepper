# -*- coding: utf-8 -*-
# classSTT.py - Speech-to-Text engine abstraction (OpenAI ou Whisper local)

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from openai import OpenAI

from .chatBots.ollama import normalize_base_url


class STT(object):
    def __init__(self, config: Dict[str, Any], logger=None):
        self.config = config or {}
        self._client: Optional[OpenAI] = None
        self._log = logger or (lambda *a, **k: None)

        stt_cfg = dict(self.config.get('stt', {}))
        self.engine = (stt_cfg.get('engine') or 'openai').lower()
        self.language = stt_cfg.get('language') or 'fr'
        self.timeout = int(stt_cfg.get('timeout') or 15)
        if self.timeout <= 0:
            self.timeout = 15

        self._openai_model = (
            stt_cfg.get('model')
            or self.config.get('openai', {}).get('stt_model')
            or 'gpt-4o-transcribe'
        )

        self._local_base_url = normalize_base_url(stt_cfg.get('local_server_url') or "")
        self._local_health = self._normalize_endpoint(stt_cfg.get('health_endpoint') or '/health')
        self._local_transcribe = self._normalize_endpoint(stt_cfg.get('transcribe_endpoint') or '/transcribe')

    @staticmethod
    def _normalize_endpoint(path: str) -> str:
        if not path:
            return '/'
        if not path.startswith('/'):
            return '/' + path
        return path

    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(timeout=self.timeout)
        return self._client

    def _log_msg(self, message, level='info'):
        try:
            self._log(message, level=level)
        except TypeError:
            method = getattr(self._log, level, None)
            if callable(method):
                method(message)

    def _transcribe_openai(self, wav_bytes: bytes, model_override: Optional[str] = None) -> Optional[str]:
        model = model_override or self._openai_model or 'gpt-4o-transcribe'
        file_tuple = ("speech.wav", wav_bytes, "audio/wav")
        self._log_msg(f"[STT] Tentative OpenAI ({model})", level='debug')
        try:
            response = self.client().audio.transcriptions.create(
                model=model,
                file=file_tuple,
                language=self.language,
                temperature=0
            )
            text = (getattr(response, "text", None) or "").strip() or None
            self._log_msg(f"[STT] OpenAI ({model}) OK -> '{text}'", level='debug')
            return text
        except Exception as exc:
            self._log_msg(f"[STT] OpenAI ({model}) a échoué: {exc}", level='warning')
            return None

    def _transcribe_local(self, wav_bytes: bytes) -> Optional[str]:
        if not self._local_base_url:
            raise RuntimeError("Serveur Whisper local non configuré.")
        url = urljoin(self._local_base_url + '/', self._local_transcribe.lstrip('/'))
        boundary = "----pepperlife{}".format(uuid.uuid4().hex)
        head = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="speech.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode('utf-8')
        tail = f"\r\n--{boundary}--\r\n".encode('utf-8')
        body = head + wav_bytes + tail
        headers = {
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Accept': 'application/json, text/plain'
        }
        req = Request(url, data=body, headers=headers)
        self._log_msg(f"[STT] Tentative Whisper local: {url}", level='debug')
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                content_type = resp.headers.get('Content-Type', '')
        except HTTPError as err:
            raise RuntimeError(f"HTTP {err.code} {err.reason}") from err
        except URLError as err:
            raise RuntimeError(f"Connexion échouée: {err.reason}") from err

        text: Optional[str] = None
        if 'application/json' in (content_type or '').lower():
            try:
                data = json.loads(raw.decode('utf-8', 'ignore'))
                text = (
                    data.get('text')
                    or data.get('transcript')
                    or data.get('result')
                    or ""
                ).strip() or None
                if not text and isinstance(data.get('segments'), list):
                    try:
                        text = " ".join((seg.get('text') or '') for seg in data['segments']).strip() or None
                    except Exception:
                        text = None
            except Exception as exc:
                self._log_msg(f"[STT] JSON invalide du serveur local: {exc}", level='warning')
                text = None
        else:
            text = raw.decode('utf-8', 'ignore').strip() or None

        if text:
            self._log_msg(f"[STT] Whisper local OK -> '{text}'", level='debug')
        else:
            self._log_msg("[STT] Whisper local n'a pas renvoyé de texte exploitable.", level='warning')
        return text

    def stt(self, wav_bytes: bytes) -> Optional[str]:
        """
        Retourne la transcription selon l'engin configuré.
        """
        engine = self.engine or 'openai'
        if engine == 'local':
            try:
                return self._transcribe_local(wav_bytes)
            except Exception as exc:
                self._log_msg(f"[STT] Whisper local indisponible: {exc}", level='error')
                return None

        # Mode OpenAI par défaut
        result = self._transcribe_openai(wav_bytes)
        if result:
            return result

        if self._openai_model != 'whisper-1':
            self._log_msg("[STT] Retry avec whisper-1.", level='warning')
            return self._transcribe_openai(wav_bytes, model_override='whisper-1')
        return None
