# -*- coding: utf-8 -*-
# chatGPT.py — Client OpenAI Responses API (non-stream)
# - Modèle dynamique (config.json / constructeur / override par appel)
# - Reasoning minimal UNIQUEMENT si modèle = GPT-5*
# - Pas de 'temperature' pour GPT-5 (retry auto si l'API le refuse)
# - Historique tronqué à 2 échanges pour réduire latence/coût
# - Logs détaillés: texte, usage, cached_tokens

from __future__ import annotations
from typing import List, Tuple, Dict, Any, Optional
from openai import OpenAI
import os
import json

# -----------------------------------------------------------------------------
# Config par défaut (surchargée par config.json et/ou arguments du ctor)
# -----------------------------------------------------------------------------
DEFAULT_OPENAI_CFG: Dict[str, Any] = {
    "api_key": None,                 # si None, on lira OPENAI_API_KEY
    "chat_model": "gpt-4o-mini",     # défaut rapide; tu peux mettre "gpt-5" via config
    "temperature": 0.2,              # utilisé seulement si le modèle le supporte
    "max_output_tokens": 96,
    "reasoning_effort": "minimal",   # pris en compte si modèle = gpt-5*
    "text_verbosity": "low",
    "parallel_tool_calls": False,
    "store": False
}

# -----------------------------------------------------------------------------
# Utils
# -----------------------------------------------------------------------------
def _load_json_if_exists(path: str, logger) -> Optional[Dict[str, Any]]:
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception as e:
        logger("Impossible de charger %s: %s" % (path, e), level='warning')
    return None


def _merge_openai_cfg(base: Dict[str, Any], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = dict(base)
    if override and isinstance(override, dict):
        for k, v in override.items():
            cfg[k] = v
    return cfg


def _model_caps(model_name: str) -> Dict[str, bool]:
    """
    Capacités selon le modèle choisi dynamiquement.
    - GPT-5* (incl. nano) => reasoning param supporté, 'temperature' non supporté.
    - 4o / 4o-mini / etc. => pas de reasoning, 'temperature' OK, 'verbosity' non supporté.
    """
    name = (model_name or "").lower()
    is_gpt5_family = "gpt-5" in name
    return {
        "supports_reasoning": is_gpt5_family,
        "supports_temperature": not is_gpt5_family,
        "supports_verbosity": "gpt-4o" not in name,
    }

# -----------------------------------------------------------------------------
# Classe principale
# -----------------------------------------------------------------------------
class chatGPT(object):
    """
    API simple, avec modèle dynamique:
      chat(user_text, hist, *, model=None, temperature=None, max_output_tokens=None) -> str

    - 'hist' est une liste de tuples (role, content), role ∈ {"user","assistant"}.
    - si 'model' est fourni à l'appel, il override la config.
    """

    # ---------- Système / client ----------
    def __init__(self, config: Optional[Dict[str, Any]] = None, system_prompt: Optional[str] = None, logger=None):
        self.config = config or {}
        self.log = logger or (lambda msg, **kwargs: print(msg))
        # API key
        if not self.config.get("openai", {}).get("api_key"):
            env = os.getenv("OPENAI_API_KEY")
            if env:
                if "openai" not in self.config:
                    self.config["openai"] = {}
                self.config["openai"]["api_key"] = env

        self._client: Optional[OpenAI] = None
        self.system_prompt = system_prompt or "Ton nom est pepper"

    @staticmethod
    def get_base_prompt(config=None, logger=None):
        """
        Construit le prompt de base en combinant le custom_prompt de config.json
        et le contenu de system_prompt.txt.
        """
        log = logger or (lambda msg, **kwargs: print(msg))
        prompts = []

        # 1. Charger le custom_prompt depuis config.json
        if config and isinstance(config.get("openai"), dict):
            custom_prompt = config["openai"].get("custom_prompt")
            if custom_prompt and custom_prompt.strip():
                prompts.append(custom_prompt.strip())

        # 2. Charger le prompt système depuis le fichier
        prompt_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "system_prompt.txt"))
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, "r", encoding='utf-8-sig') as f:
                    text = f.read().strip()
                    if text:
                        prompts.append(text)
            except Exception as e:
                log("Lecture de system_prompt.txt échouée: %s" % e, level='warning')

        # 3. Combiner ou retourner un défaut
        if prompts:
            return "\n\n".join(prompts)
        else:
            return "Ton nom est pepper"  # Fallback si tout est vide

    def client(self) -> OpenAI:
        if self._client is None:
            api_key = self.config["openai"].get("api_key")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY manquant (config.openai.api_key)")
            self._client = OpenAI(api_key=api_key)
        return self._client

    # ---------- Construction des messages ----------
    def _build_messages_without_system(self, user_text: str, hist: List[Tuple[str, str]]) -> List[Dict[str, str]]:
        """
        Construit les messages SANS 'system' (on passe system via `instructions`).
        La longueur de l'historique est maintenant configurable.
        """
        history_len = self.config.get("openai", {}).get("history_length", 4)
        trimmed = (hist or [])[-history_len:]
        msgs = [{"role": r, "content": c} for (r, c) in trimmed if r in ("user", "assistant")]
        msgs.append({"role": "user", "content": user_text})
        return msgs

    # ---------- Appel au modèle ----------
    def chat(
        self,
        user_text: str,
        hist: Optional[List[Tuple[str, str]]] = None,
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None
    ) -> Tuple[str, Any]:
        """
        Renvoie une réponse courte et l'objet réponse brut de l'API.
        - Modèle DYNAMIQUE (config ou override `model=...`)
        - Reasoning minimal si et seulement si GPT-5*
        - 'temperature' seulement si supporté
        - Retry auto si l'API refuse 'temperature'
        - Logs usage + cache + texte
        """
        oai = self.config["openai"]

        # modèle dynamique: override > config > défaut
        model_name = model or oai.get("chat_model") or "gpt-4o-mini"
        caps = _model_caps(model_name)

        messages = self._build_messages_without_system(user_text, hist or [])

        # Base de la requête
        req: Dict[str, Any] = {
            "model": model_name,
            "instructions": self.system_prompt,
            "input": messages,
            "max_output_tokens": oai.get("max_output_tokens") if max_output_tokens is None else max_output_tokens,
            "parallel_tool_calls": oai.get("parallel_tool_calls", False),
            "store": oai.get("store", False),
        }

        # Verbosity seulement si le modèle le supporte
        if caps["supports_verbosity"]:
            req["text"] = {"verbosity": oai.get("text_verbosity", "low")}

        # Temperature seulement si le modèle le supporte
        temp_value = oai.get("temperature") if temperature is None else temperature
        if caps["supports_temperature"] and temp_value is not None:
            req["temperature"] = temp_value

        # Reasoning uniquement si GPT-5 et si l'effort n'est pas désactivé
        reasoning_effort = oai.get("reasoning_effort")
        if caps["supports_reasoning"] and reasoning_effort and reasoning_effort.lower() != 'none':
            req["reasoning"] = {"effort": reasoning_effort}
        # --- Appel + retry si refus de 'temperature' ---
        resp = None
        try:
            resp = self.client().responses.create(**req)
        except Exception as e:
            msg = str(e)
            if "Unsupported parameter" in msg and "temperature" in msg and "not supported" in msg:
                self.log("Retry sans 'temperature' (modèle ne le supporte pas): %s" % msg, level='warning')
                req.pop("temperature", None)
                resp = self.client().responses.create(**req)
            else:
                self.log("Responses API error: %s" % e, level='error')
                return "Désolé, une erreur est survenue avec le service de chat.", {"error": str(e)}

        # Texte retourné
        text = (getattr(resp, "output_text", "") or "").strip()
        self.log(f"CHAT TEXT: {text}", level='debug')

        # Usage + cache (si dispo)
        u = getattr(resp, "usage", None)
        cached = None
        input_tokens = None
        output_tokens = None
        try:
            input_tokens = getattr(u, "input_tokens", None)
            output_tokens = getattr(u, "output_tokens", None)
            details = getattr(u, "input_tokens_details", None)
            if details:
                cached = getattr(details, "cached_tokens", None)
        except Exception:
            pass
        self.log(f"USAGE: input={input_tokens} cached={cached} output={output_tokens}", level='info')

        # Fallback de sécurité pour ne pas rester muet
        if not text:
            text = "%%Stand/BodyTalk/Listening/Listening%% Je t’écoute."

        return text.replace("\n", " ").strip(), resp
