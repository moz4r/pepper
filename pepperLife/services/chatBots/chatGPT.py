# -*- coding: utf-8 -*-
# chatGPT.py - Chat logic using OpenAI GPT

from openai import OpenAI
import os
import logging

logging.basicConfig(level=logging.DEBUG)

class chatGPT(object):
    @staticmethod
    def _read_text_file(path):
        try:
            # utf-8-sig enlève un éventuel BOM
            with open(path, 'r', encoding='utf-8-sig') as f:
                return f.read()
        except Exception:
            return None

    @staticmethod
    def load_system_prompt(openai_cfg, base_dir):
        # 1) on lit le fichier de base
        base_prompt = ""
        base_prompt_path = os.path.join(base_dir, "prompts", "system_prompt.txt")
        content = chatGPT._read_text_file(base_prompt_path)
        if content is not None:
            base_prompt = content.strip()
        else:
            print("[PROMPT] WARNING: impossible de lire prompts/system_prompt.txt")

        # 2) on ajoute le prompt de la config
        sp = openai_cfg.get('custom_prompt')
        if isinstance(sp, str):
            base_prompt += "\n" + sp.strip()

        return base_prompt

    def __init__(self, config, system_prompt=None):
        """
        :param config: dict global de configuration
        :param system_prompt: texte du prompt système déjà chargé (ex: depuis system_prompt_file).
                              S'il est None, on tentera de lire config['openai'].get('system_prompt', '').
        """
        self.config = config
        self._client = None
        # priorité au prompt passé par l'appelant; fallback sur la conf; sinon vide
        self.system_prompt = system_prompt or ''

    def client(self):
        if self._client is None:
            self._client = OpenAI(timeout=15.0)
        return self._client

    def chat(self, user_text, hist):
        """
        :param user_text: texte utilisateur (str)
        :param hist: historique sous forme de liste de tuples (role, content)
                     où role ∈ {"user","assistant"}.
        :return: str (réponse de l'assistant en une seule ligne)
        """
        msgs = []
        if self.system_prompt:
            msgs.append({"role": "system", "content": self.system_prompt})
        # historique
        for role, content in (hist or []):
            msgs.append({"role": role, "content": content})
        # message courant
        msgs.append({"role": "user", "content": user_text})

        try:
            resp = self.client().chat.completions.create(
                model=self.config['openai']['chat_model'],
                messages=msgs,
                temperature=1,
                **({'max_completion_tokens': 60} if self.config['openai']['chat_model'] in ['gpt-5', 'gpt-5-mini'] else {'max_tokens': 60}),
            )
            logging.debug(f"OpenAI API Response: {resp}")
            return (resp.choices[0].message.content or "").replace("\n", " ").strip()
        except Exception as e:
            logging.error(f"Chatbot error: {e}")
            # En cas d'erreur avec l'API, retourner un message d'erreur simple
            return "Désolé, une erreur est survenue avec le service de chat."
