# -*- coding: utf-8 -*-
# classSpeak.py

import os
import re
import threading

class Speaker(object):
    def __init__(self, session, logger, config=None):
        """
        Initialise le Speaker. Ne dépend que de la session NAOqi et d'un logger.
        """
        self.s = session
        self.logger = logger
        self.config = config or {}
        self.tts_lock = threading.Lock()
        self.pls = None  # Proxy pour le service PepperLifeService
        self.tts_replacements = self._load_tts_replacements()

    def _load_tts_replacements(self):
        """
        Charge le fichier de remplacements TTS (one-shot). Format attendu :
        mot_original=mot_remplacé, lignes vides ou débutant par # ignorées.
        """
        map_path = None
        try:
            map_path = self.config.get('audio', {}).get('tts_map_path')
        except Exception:
            map_path = None

        if map_path:
            candidate = os.path.abspath(map_path)
        else:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lang', 'map'))
            candidate = os.path.join(base_dir, 'tts_replacements.txt')

        mapping = {}
        try:
            if os.path.exists(candidate):
                with open(candidate, 'r', encoding='utf-8') as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' not in line:
                            continue
                        original, replacement = line.split('=', 1)
                        original = original.strip()
                        replacement = replacement.strip()
                        if original:
                            mapping[original] = replacement
                if mapping:
                    self.logger("[TTS] {} remplacements chargés depuis {}".format(len(mapping), candidate), level='debug')
        except Exception as e:
            self.logger("Impossible de charger la carte TTS '{}': {}".format(candidate, e), level='warning')
        return mapping

    def _apply_tts_replacements(self, text):
        """Applique les remplacements TTS avant envoi au service NAOqi."""
        if not text or not self.tts_replacements:
            return text
        updated = text
        for original, replacement in self.tts_replacements.items():
            try:
                pattern = r'\b{}\b'.format(re.escape(original))
                updated = re.sub(pattern, replacement, updated)
            except Exception:
                # fallback simple en cas de souci regex
                updated = updated.replace(original, replacement)
        return updated

    def _connect_to_service(self):
        """Établit la connexion au PepperLifeService si elle n'existe pas."""
        if self.pls is None:
            try:
                self.pls = self.s.service("PepperLifeService")
            except Exception as e:
                self.logger("Impossible de se connecter à PepperLifeService depuis Speaker: {}".format(e), level='error')
                raise

    def say_quick(self, text, stop_event=None):
        """
        Prend un texte brut, le fait résoudre par le service, puis demande au service de le dire.
        Si configuré, ajoute un tag ^wait(anim) en réutilisant l'animation du tag ^start.
        """
        try:
            self._connect_to_service()

            with self.tts_lock:
                # 1. Résoudre les balises (%%...%%) en ^start(...)
                resolved_text = self.pls.resolveAnimationTags(text)

                # 2. Si l'option est activée, extraire l'animation de ^start() et l'ajouter à ^wait()
                wait_flag = self.config.get('audio', {}).get('add_wait_tag', False)
                self.logger("[TTS-DEBUG] 'add_wait_tag' config value is: {}".format(wait_flag), level='debug')

                if wait_flag:
                    try:
                        text_to_search = resolved_text.strip()
                        # Utiliser la manipulation de chaînes de caractères, plus robuste
                        if text_to_search.startswith('^start('):
                            start_index = text_to_search.find('(')
                            end_index = text_to_search.find(')', start_index)
                            if end_index != -1:
                                anim_name = text_to_search[start_index + 1 : end_index]
                                self.logger("[TTS-DEBUG] String search found! Animation name: '{}'".format(anim_name), level='debug')
                                resolved_text += " ^wait({})".format(anim_name)
                                self.logger("[TTS-DEBUG] Appended wait tag. New text: '{}'".format(resolved_text), level='debug')
                            else:
                                self.logger("[TTS-DEBUG] String search: Closing parenthesis NOT found!", level='debug')
                        else:
                            self.logger("[TTS-DEBUG] String search: '^start(' NOT found at the beginning!", level='debug')
                    except Exception as e:
                        self.logger("Could not extract and append wait animation (string method): {}".format(e), level='warning')

                resolved_text = self._apply_tts_replacements(resolved_text)
                self.logger(u"[TTS] Texte original: '{}' -> Résolu: '{}'".format(text, resolved_text), level='info')
                self.pls.sayAnimated(resolved_text, False, True)

        except Exception as e:
            self.logger("Erreur dans say_quick: {}".format(e), level='error')
