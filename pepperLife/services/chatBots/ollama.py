#! -*- coding: utf-8 -*-
"""
Utilities for interacting with an Ollama server without relying on external
HTTP dependencies. Helpers in this module are shared by the web backend and
chat runtime when Ollama mode is enabled.
"""
from __future__ import annotations

import json
import ssl
from typing import Any, Callable, Dict, List, Optional, Tuple
import re
import os
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

DEFAULT_TIMEOUT = 6


def _build_request(url: str, data: Any = None) -> Request:
    headers = {'Accept': 'application/json'}
    payload = None
    if data is not None:
        payload = json.dumps(data).encode('utf-8') + b"\n"
        headers['Content-Type'] = 'application/json'
    return Request(url, data=payload, headers=headers)


def normalize_base_url(base_url: str) -> str:
    """
    Normalise une URL de serveur Ollama.
    - Ajoute http:// si le schéma est absent.
    - Supprime les slashs de fin.
    """
    if not base_url:
        return ""
    url = base_url.strip()
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else "http://" + url)
    scheme = parsed.scheme or "http"
    netloc = parsed.netloc or parsed.path
    path = parsed.path if parsed.netloc else ""
    normalized = "{}://{}".format(scheme, netloc)
    if path:
        normalized += path
    return normalized.rstrip("/")


def _prepare_request(base_url: str, path: str, data: Any = None):
    """
    Prépare un objet Request et le payload encodé.
    """
    normalized = normalize_base_url(base_url)
    if not normalized:
        raise RuntimeError("URL du serveur Ollama invalide ou absente.")
    url = normalized + path
    payload = None
    req = _build_request(url, data=None)
    if data is not None:
        payload = json.dumps(data).encode('utf-8') + b"\n"
        req.data = payload
        req.add_header('Content-Type', 'application/json')
    else:
        req.data = None
    return url, req


def call_ollama_api(base_url: str, path: str, data: Any = None, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """
    Effectue un appel JSON (GET si data est None, sinon POST) vers le serveur Ollama.
    Lève RuntimeError si l'appel échoue.
    """
    url, req = _prepare_request(base_url, path, data)
    kwargs = {'timeout': timeout}
    if url.lower().startswith("https://"):
        kwargs['context'] = ssl.create_default_context()
    try:
        with urlopen(req, **kwargs) as resp:
            raw = resp.read().decode('utf-8') or "{}"
            return json.loads(raw)
    except HTTPError as e:
        raise RuntimeError("Réponse HTTP {} depuis {}: {}".format(e.code, url, e.read().decode('utf-8', 'ignore'))) from e
    except URLError as e:
        raise RuntimeError("Impossible de contacter {}: {}".format(url, e.reason)) from e
    except ValueError as e:
        raise RuntimeError("Réponse JSON invalide depuis {}: {}".format(url, e)) from e


def stream_ollama_api(base_url: str, path: str, data: Any = None, timeout: int = DEFAULT_TIMEOUT):
    """
    Générateur qui renvoie chaque objet JSON dans un flux NDJSON d'Ollama.
    """
    url, req = _prepare_request(base_url, path, data)
    headers = dict(req.headers)
    headers['Accept'] = 'application/x-ndjson'
    req.headers = headers
    kwargs = {'timeout': timeout}
    if url.lower().startswith("https://"):
        kwargs['context'] = ssl.create_default_context()
    try:
        with urlopen(req, **kwargs) as resp:
            for raw_line in resp:
                if not raw_line:
                    continue
                try:
                    line = raw_line.decode('utf-8').strip()
                except Exception:
                    continue
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception as e:
                    raise RuntimeError("Flux JSON invalide depuis {}: {}".format(url, e)) from e
    except HTTPError as e:
        raise RuntimeError("Réponse HTTP {} depuis {}: {}".format(e.code, url, e.read().decode('utf-8', 'ignore'))) from e
    except URLError as e:
        raise RuntimeError("Impossible de contacter {}: {}".format(url, e.reason)) from e


def get_server_metadata(base_url: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """
    Récupère des métadonnées du serveur (version + modèles).
    """
    info: Dict[str, Any] = {}
    try:
        info['version'] = call_ollama_api(base_url, "/api/version", timeout=timeout).get('version')
    except Exception as e:
        info['version_error'] = str(e)
    try:
        info['models'], info['models_raw'] = list_models(base_url, timeout=timeout)
    except Exception as e:
        info['models_error'] = str(e)
        info['models'] = []
    return info


def list_models(base_url: str, timeout: int = DEFAULT_TIMEOUT) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Retourne la liste des modèles disponibles et la réponse brute.
    """
    response = call_ollama_api(base_url, "/api/tags", timeout=timeout)
    models: List[Dict[str, Any]] = []

    for entry in response.get('models', []):
        raw_name = entry.get('name') or entry.get('model') or entry.get('alias') or ""
        if not raw_name:
            continue
        base_name = raw_name.splitlines()[0].strip()
        if not base_name:
            continue
        models.append({
            'name': base_name,
            'alias': entry.get('model') or base_name,
            'modified_at': entry.get('modified_at'),
            'size': entry.get('size'),
            'digest': entry.get('digest'),
            'details': entry.get('details', {})
        })
    return models, response


def build_chat_messages(
    user_text: str,
    history: List[Tuple[str, str]],
    system_prompt: str,
    history_length: int
) -> List[Dict[str, str]]:
    """
    Construit la liste des messages pour l'API chat d'Ollama.
    """
    trimmed = (history or [])[-history_length:]
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for role, content in trimmed:
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_text})
    return messages


def _collect_text_chunks(payload) -> List[str]:
    """
    Parcourt récursivement les structures de réponse Ollama pour extraire du texte.
    """
    chunks: List[str] = []
    if payload is None:
        return chunks
    if isinstance(payload, str):
        stripped = payload.strip()
        if stripped:
            chunks.append(stripped)
        return chunks
    if isinstance(payload, list):
        for item in payload:
            chunks.extend(_collect_text_chunks(item))
        return chunks
    if isinstance(payload, dict):
        for key in ('text', 'content', 'response', 'message', 'data'):
            if key in payload:
                chunks.extend(_collect_text_chunks(payload.get(key)))
        return chunks
    return chunks


class ChatOllama(object):
    """
    Client minimal pour l'API /api/chat d'Ollama.
    La signature `chat(user_text, hist)` reste compatible avec les autres
    backends de PepperLife.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, system_prompt: Optional[str] = None, logger=None):
        self.config = config or {}
        self.log = logger or (lambda msg, **kwargs: None)
        self.ollama_cfg: Dict[str, Any] = dict(self.config.get('ollama', {}))

        candidates = [
            self.ollama_cfg.get('active_server'),
            self.ollama_cfg.get('server'),
            self.ollama_cfg.get('server_url'),
        ]
        preferred = self.ollama_cfg.get('preferred_servers') or []
        candidates.extend(preferred if isinstance(preferred, list) else [])

        self.base_url = ""
        for candidate in candidates:
            normalized = normalize_base_url(candidate or "")
            if normalized:
                self.base_url = normalized
                break

        self.history_length = int(self.ollama_cfg.get('history_length', 4) or 4)
        if self.history_length < 1:
            self.history_length = 1
        self.temperature = self._safe_float(self.ollama_cfg.get('temperature'), default=0.4)
        self.top_p = self._safe_float(self.ollama_cfg.get('top_p'), default=0.9)
        self.top_k = self._safe_int(self.ollama_cfg.get('top_k'), default=35)
        self.min_p = self._safe_float(self.ollama_cfg.get('min_p'), default=0.08)
        self.repeat_penalty = self._safe_float(self.ollama_cfg.get('repeat_penalty'), default=1.25)
        self.repeat_last_n = self._safe_int(self.ollama_cfg.get('repeat_last_n'), default=512)
        self.mirostat = self._safe_int(self.ollama_cfg.get('mirostat'), default=2)
        self.mirostat_tau = self._safe_float(self.ollama_cfg.get('mirostat_tau'), default=5.0)
        self.mirostat_eta = self._safe_float(self.ollama_cfg.get('mirostat_eta'), default=0.1)
        self.seed = self._safe_int(self.ollama_cfg.get('seed'), default=42)
        self.num_ctx = self._safe_int(self.ollama_cfg.get('num_ctx'), default=2048)
        self.max_tokens = self._safe_int(self.ollama_cfg.get('max_output_tokens'))
        self.stop_sequences = self._coerce_stop_list(self.ollama_cfg.get('stop'), default=["<|eot_id|>", "<|end_of_text|>"])
        self.keep_alive = (self.ollama_cfg.get('keep_alive') or "").strip()
        self.timeout = self._safe_int(self.ollama_cfg.get('timeout'), default=15)
        if not self.timeout or self.timeout <= 0:
            self.timeout = 15
        self.stream_mode = self._safe_bool(self.ollama_cfg.get('stream'), default=True)

        custom_prompt = (self.ollama_cfg.get('custom_prompt') or "").strip()
        base_prompt = (system_prompt or "Tu es Pepper.").strip()

        catalogue_text = ""
        marker = "CATALOGUE DES ANIMATIONS"
        if base_prompt and marker in base_prompt:
            after = base_prompt.split(marker, 1)[1]
            lines = after.splitlines()
            while lines and not lines[0].strip():
                lines.pop(0)
            if lines and "utilise" in lines[0].lower():
                lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)
            catalogue_text = "\n".join(line for line in lines if line.strip())

        effective_system = base_prompt

        if custom_prompt:
            effective_system = "{}\n\n{}".format(custom_prompt, effective_system).strip()

        self.system_prompt = effective_system

    @staticmethod
    def get_base_prompt(config: Optional[Dict[str, Any]] = None, logger=None) -> str:
        """
        Charge le prompt système de base pour Ollama depuis prompts/system_prompt_OLLAMA.txt.
        Fallback sur la valeur historique si le fichier est absent.
        """
        log = logger or (lambda msg, **kwargs: None)
        prompts: List[str] = []
        prompt_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "prompts"))
        candidates = ["system_prompt_OLLAMA.txt", "system_prompt.txt"]
        for filename in candidates:
            path = os.path.join(prompt_dir, filename)
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8-sig") as f:
                        text = f.read().strip()
                        if text:
                            prompts.append(text)
                            break
                except Exception as e:
                    log("Lecture de {} échouée: {}".format(filename, e), level='warning')
        if prompts:
            return "\n\n".join(prompts)
        return "Ton nom est Pepper."

    @staticmethod
    def _safe_float(value, default=None):
        try:
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _safe_int(value, default=None):
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _safe_bool(value, default=True):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ('true', '1', 'yes', 'on'):
                return True
            if lowered in ('false', '0', 'no', 'off'):
                return False
        return default

    @staticmethod
    def _coerce_stop_list(value, default=None) -> Optional[List[str]]:
        source = value if value is not None else default
        if source is None:
            return None
        if isinstance(source, str):
            items = [source]
        elif isinstance(source, (list, tuple, set)):
            items = list(source)
        else:
            return None
        normalized = [item.strip() for item in items if isinstance(item, str) and item.strip()]
        return normalized or None

    def _parse_text(self, aggregated):
        text = ""
        if isinstance(aggregated, dict):
            parts = _collect_text_chunks(aggregated.get('message'))
            if not parts:
                parts = _collect_text_chunks(aggregated.get('messages'))
            if not parts:
                parts = _collect_text_chunks(aggregated.get('response'))
            if not parts:
                parts = _collect_text_chunks(aggregated.get('text'))
            if not parts:
                parts = _collect_text_chunks(aggregated)
            if parts:
                text = "\n".join(part for part in parts if part).strip()
                if text.startswith('```') and text.endswith('```'):
                    text = text.strip('`').strip()
        return text

    @staticmethod
    def _strip_animation(text: str) -> str:
        if not text:
            return ""
        return re.sub(r'^%%[^%]+%%', '', text or '').strip()

    @staticmethod
    def _is_low_quality_text(text: str) -> bool:
        if not text:
            return True
        stripped = text.strip()
        if not stripped:
            return True
        unique_chars = set(stripped)
        if len(unique_chars) == 1 and len(stripped) >= 5:
            return True
        return False

    def _fallback_message(self) -> str:
        return "%%Stand/BodyTalk/Listening/Listening%% Je suis prêt, mais je n'ai pas compris. Peux-tu reformuler ?"

    def _chat_stream(self, payload, on_chunk: Optional[Callable[[Dict[str, Any]], None]] = None):
        raw_chunks: List[Dict[str, Any]] = []
        text_parts: List[str] = []
        final_chunk: Dict[str, Any] = {}
        done_seen = False
        chunk_index = 0
        for chunk in stream_ollama_api(self.base_url, "/api/chat", payload, timeout=self.timeout):
            raw_chunks.append(chunk)
            try:
                self.log("[OLLAMA_RAW] {}".format(chunk), level='debug')
            except Exception:
                pass
            content = ""
            if isinstance(chunk, dict):
                message = chunk.get('message')
                if isinstance(message, dict):
                    content = message.get('content', '')
                elif isinstance(message, str):
                    content = message
                if not content:
                    content = chunk.get('response', '') or chunk.get('text', '')
            if content:
                text_parts.append(content)
            try:
                preview = content[:16] if isinstance(content, str) else ""
                self.log(
                    "[OLLAMA_STREAM_CHUNK] idx={} done={} len={} preview='{}'".format(
                        chunk_index,
                        chunk.get('done') if isinstance(chunk, dict) else None,
                        len(content) if isinstance(content, str) else None,
                        preview
                    ),
                    level='debug'
                )
            except Exception:
                pass
            if on_chunk:
                try:
                    on_chunk({
                        'type': 'chunk',
                        'index': chunk_index,
                        'delta': content or '',
                        'done': bool(chunk.get('done')) if isinstance(chunk, dict) else False,
                        'raw': chunk
                    })
                except Exception:
                    pass
            if isinstance(chunk, dict) and chunk.get('done'):
                final_chunk = chunk
                done_seen = True
                break
            chunk_index += 1
        if raw_chunks and not done_seen:
            try:
                self.log("[OLLAMA_WARN] Flux terminé sans chunk 'done'. Dernier chunk: {}".format(raw_chunks[-1]), level='warning')
            except Exception:
                pass
        aggregated_source: Dict[str, Any] = final_chunk or (raw_chunks[-1] if raw_chunks else {})
        aggregated: Dict[str, Any] = {}
        if isinstance(aggregated_source, dict):
            aggregated = dict(aggregated_source)
        combined_text = "".join(part for part in text_parts if part)
        if aggregated.setdefault('message', {}):
            if isinstance(aggregated['message'], dict):
                aggregated['message'] = dict(aggregated['message'])
                aggregated['message']['content'] = combined_text
            elif isinstance(aggregated['message'], str):
                aggregated['message'] = {'role': 'assistant', 'content': combined_text or aggregated['message']}
        else:
            aggregated['message'] = {'role': 'assistant', 'content': combined_text}
        aggregated['chunks'] = raw_chunks
        try:
            if raw_chunks:
                self.log("[OLLAMA_FULL] {}".format(aggregated), level='debug')
        except Exception:
            pass
        text = combined_text.strip()
        if text.startswith('```') and text.endswith('```'):
            text = text.strip('`').strip()
        if not text:
            text = self._parse_text(aggregated)
        return text, aggregated

    @staticmethod
    def _normalize_response_text(text: str) -> str:
        if not text:
            return text

        def fix_animation(match):
            raw = match.group(1)
            cleaned = raw.replace('\n', ' ').replace('\r', ' ')
            cleaned = re.sub(r'\s*/\s*', '/', cleaned)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            cleaned = cleaned.lstrip('/')
            if cleaned.lower().startswith('animations/'):
                cleaned = cleaned.split('/', 1)[1] if '/' in cleaned else cleaned
            elif cleaned.lower().startswith('animation/'):
                cleaned = cleaned.split('/', 1)[1] if '/' in cleaned else cleaned
            return f"%%{cleaned}%%"

        def fix_single(match):
            raw = match.group(1)
            cleaned = raw.replace('\n', ' ').replace('\r', ' ')
            cleaned = re.sub(r'\s*/\s*', '/', cleaned)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            cleaned = cleaned.lstrip('/')
            if cleaned.lower().startswith('animations/'):
                cleaned = cleaned.split('/', 1)[1] if '/' in cleaned else cleaned
            elif cleaned.lower().startswith('animation/'):
                cleaned = cleaned.split('/', 1)[1] if '/' in cleaned else cleaned
            return f"%%{cleaned}%%"

        normalized = re.sub(r'(?<!%)%\s*([^%]+?)\s*%(?!%)', fix_single, text)
        normalized = re.sub(r'%%\s*([^%]+?)\s*%%', fix_animation, normalized)
        if normalized:
            idx = normalized.find('%%')
            if idx > 0:
                prefix = normalized[:idx]
                if not prefix.strip():
                    normalized = normalized[idx:]
        if normalized:
            tokens = []
            for match in re.finditer(r'%%([^%]+?)%%', normalized):
                token_raw = match.group(1).strip()
                if token_raw:
                    tokens.append((token_raw, match.start(), match.end()))
            def _is_listening(token):
                return token.replace(' ', '').lower() == 'stand/bodytalk/listening/listening'
            first_non_listening = None
            for token, start, end in tokens:
                if not _is_listening(token):
                    first_non_listening = (token, start, end)
                    break
            if first_non_listening:
                desired_token = "%%{}%%".format(first_non_listening[0])
                idx_desired = normalized.find(desired_token)
                if idx_desired > 0:
                    normalized = desired_token + normalized[idx_desired + len(desired_token):]
                elif idx_desired == -1:
                    normalized = desired_token + " " + normalized
                normalized = re.sub(r'^\s*%%\s*Stand/BodyTalk/Listening/Listening\s*%%\s*', '', normalized, flags=re.IGNORECASE)
                normalized = normalized.strip()
                if not normalized.startswith(desired_token):
                    normalized = "{} {}".format(desired_token, normalized.lstrip('% ')).strip()
        if normalized:
            normalized = re.sub(r'%%%%+', '%%', normalized)
        if normalized:
            match = re.match(r'^\s*(%%[^%]+%%)(.*)$', normalized)
            if match:
                animation = match.group(1).strip()
                remainder = match.group(2).strip()
                if remainder:
                    sentences = re.split(r'(?<=[.!?])\s+', remainder)
                    trimmed = []
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if not sentence:
                            continue
                        trimmed.append(sentence)
                        if len(trimmed) >= 2:
                            break
                    remainder = " ".join(trimmed).strip()
                normalized = "{} {}".format(animation, remainder).strip() if remainder else animation
        if not re.match(r'^\s*%%[^%]+%%', normalized or ''):
            normalized = "%%Stand/BodyTalk/Listening/Listening%% {}".format(normalized or "").strip()
        return normalized.replace("\n", " ").replace("\r", " ").strip()

    def _chat_single(self, payload):
        aggregated = call_ollama_api(self.base_url, "/api/chat", payload, timeout=self.timeout)
        try:
            self.log("[OLLAMA_RAW] {}".format(aggregated), level='debug')
        except Exception:
            pass
        text = self._parse_text(aggregated)
        try:
            if isinstance(aggregated, dict):
                self.log("[OLLAMA_FULL] {}".format(aggregated), level='debug')
        except Exception:
            pass
        return text, aggregated

    def chat(
        self,
        user_text: str,
        hist: Optional[List[Tuple[str, str]]] = None,
        *,
        model: Optional[str] = None,
        on_chunk: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Envoie une requête chat à Ollama et renvoie (réponse, payload_brut).
        """
        if not self.base_url:
            raise RuntimeError("Serveur Ollama non configuré. Vérifie la section chat.")
        model_name = model or self.ollama_cfg.get('chat_model')
        if not model_name:
            raise RuntimeError("Aucun modèle Ollama configuré.")

        messages = build_chat_messages(
            user_text=user_text,
            history=hist or [],
            system_prompt=self.system_prompt,
            history_length=self.history_length
        )

        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": self.stream_mode
        }

        options: Dict[str, Any] = {}
        if self.temperature is not None:
            options['temperature'] = self.temperature
        if self.max_tokens:
            options['num_predict'] = self.max_tokens
        if self.top_p is not None:
            options['top_p'] = self.top_p
        if self.top_k is not None:
            options['top_k'] = self.top_k
        if self.min_p is not None:
            options['min_p'] = self.min_p
        if self.repeat_penalty is not None:
            options['repeat_penalty'] = self.repeat_penalty
        if self.repeat_last_n is not None:
            options['repeat_last_n'] = self.repeat_last_n
        if self.mirostat is not None:
            options['mirostat'] = self.mirostat
        if self.mirostat_tau is not None:
            options['mirostat_tau'] = self.mirostat_tau
        if self.mirostat_eta is not None:
            options['mirostat_eta'] = self.mirostat_eta
        if self.num_ctx is not None:
            options['num_ctx'] = self.num_ctx
        if self.seed is not None:
            options['seed'] = self.seed
        if self.stop_sequences:
            options['stop'] = self.stop_sequences
        if options:
            payload['options'] = options
        if self.keep_alive:
            payload['keep_alive'] = self.keep_alive

        self.log("[OLLAMA_DEBUG] Payload initial: {}".format(payload), level='debug')

        if self.stream_mode:
            text, aggregated = self._chat_stream(payload, on_chunk=on_chunk)
        else:
            text, aggregated = self._chat_single(payload)

        text = self._normalize_response_text(text)
        clean_text = self._strip_animation(text)

        chunks_count = 0
        done_flag = False
        if isinstance(aggregated, dict):
            message = aggregated.get('message')
            normalized = self._normalize_response_text(message.get('content', text) if isinstance(message, dict) else text)
            if isinstance(message, dict):
                message['content'] = normalized
            elif isinstance(message, str):
                aggregated['message'] = normalized
            else:
                aggregated['message'] = {'role': 'assistant', 'content': normalized}
            if isinstance(aggregated.get('chunks'), list):
                chunks_count = len(aggregated['chunks'])
            done_flag = bool(aggregated.get('done'))
            aggregated['clean_text'] = clean_text

        if self._is_low_quality_text(clean_text):
            unique_chars = "".join(sorted(set(clean_text.strip())))
            preview = clean_text[:32]
            self.log(
                "[OLLAMA_WARN] Réponse faible (unique chars). preview='{}' unique_chars='{}' chunks={}".format(
                    preview, unique_chars, chunks_count
                ),
                level='warning'
            )
            if isinstance(aggregated, dict):
                aggregated['low_quality_warning'] = {
                    'preview': preview,
                    'unique_chars': unique_chars,
                    'chunks': chunks_count,
                    'done_flag': done_flag
                }

        self.log("[OLLAMA_DEBUG] done={} chunks={} text='{}'".format(done_flag, chunks_count, clean_text), level='debug')

        try:
            self.log("[OLLAMA_PARSED] {}".format(text), level='debug')
        except Exception:
            pass
        if isinstance(aggregated, dict) and aggregated.get('error'):
            raise RuntimeError(aggregated.get('error'))

        if not text:
            text = "Je n'ai pas reçu de réponse du modèle Ollama."
            try:
                self.log("[OLLAMA_WARNING] Texte vide après parsing.", level='warning')
            except Exception:
                pass
        return text, aggregated
