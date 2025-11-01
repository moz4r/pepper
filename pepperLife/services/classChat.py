# -*- coding: utf-8 -*-
# classChat.py — Gestion centralisée du chatbot PepperLife

from __future__ import annotations

import copy
import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .classASRFilters import is_noise_utterance, is_recent_duplicate
from .classAudioUtils import avgabs
import re
from .classSTT import STT
from .classSystem import bcolors, build_system_prompt_in_memory
from .chatBots.chatGPT import chatGPT
from .chatBots.ollama import ChatOllama


class ChatManager(object):
    """
    Encapsule les fonctions principales liées au chatbot (boucle, debug, statut).
    """

    _VAD_PROFILES = {
        1: (1.3, 1.05, 0.8),
        2: (1.6, 1.1, 0.6),
        3: (2.0, 1.2, 0.5),
        4: (2.5, 1.3, 0.4),
        5: (3.0, 1.5, 0.3),
    }

    def __init__(
        self,
        config: Dict[str, Any],
        session,
        log_fn: Callable[..., None],
        logger,
        speaker,
        leds,
        listener,
        vision_service,
        led_thread_fn: Callable[..., None],
        al_dialog,
    ):
        self.session = session
        self.log = log_fn
        self.logger = logger
        self.speaker = speaker
        self.leds = leds
        self.listener = listener
        self.vision_service = vision_service
        self.led_thread_fn = led_thread_fn
        self.al_dialog = al_dialog

        self.chat_thread: Optional[threading.Thread] = None
        self.chat_stop_event: Optional[threading.Event] = None
        self.led_thread: Optional[threading.Thread] = None
        self.led_stop_event: Optional[threading.Event] = None

        self.chat_state: Dict[str, Any] = {'status': 'stopped', 'mode': 'basic'}
        self.current_mode: str = 'basic'
        self.tablet_ui = None

        self.system_prompt_gpt = "Ton nom est Pepper."
        self.system_prompt_ollama = "Ton nom est Pepper."

        self.update_config(config)

    # ------------------------------------------------------------------ Prompts & UI
    def set_system_prompts(self, gpt_prompt: str, ollama_prompt: str):
        self.system_prompt_gpt = gpt_prompt or "Ton nom est Pepper."
        self.system_prompt_ollama = ollama_prompt or "Ton nom est Pepper."

    def attach_tablet(self, tablet_ui):
        self.tablet_ui = tablet_ui

    def update_config(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        vad_level = self.config.get('audio', {}).get('vad_level', 3)
        self.start_mult, self.stop_mult, self.silhold = self._VAD_PROFILES.get(
            vad_level, self._VAD_PROFILES[3]
        )
        self.blacklist_strict = set(self.config.get('asr_filters', {}).get('blacklist_strict', []))

    # ------------------------------------------------------------------ Statut utilitaires
    def is_running(self) -> bool:
        return self.chat_thread is not None and self.chat_thread.is_alive()

    def get_status(self) -> Dict[str, Any]:
        running = self.is_running()
        mode = self.current_mode if running else 'basic'
        return {'mode': mode, 'is_running': running}

    def get_detailed_status(self) -> Dict[str, Any]:
        return dict(self.chat_state)

    # ------------------------------------------------------------------ Gestion du chat
    def start(self, mode: str = 'gpt'):
        if self.is_running():
            self.log("Un chat est déjà en cours, arrêt avant redémarrage.", level='warning')
            self.stop()

        if mode in ('gpt', 'ollama'):
            try:
                self.log("Arrêt de ALDialog pour le mode {}.".format(mode.upper()), level='info')
                self.al_dialog.stopDialog()
            except Exception as e:
                self.log("Erreur lors de l'arrêt de ALDialog: {}".format(e), level='error')

            self._start_leds()

            self.chat_stop_event = threading.Event()
            self.chat_thread = threading.Thread(
                target=self._run_chat_loop,
                args=(self.chat_stop_event, mode)
            )
            self.chat_thread.daemon = True
            self.chat_thread.start()
            self.current_mode = mode
        else:
            self.log("Mode 'basic' activé.", level='info')
            try:
                self.al_dialog.resetAll()
                self.al_dialog.runDialog()
            except Exception as e:
                self.log("Erreur au démarrage de ALDialog: {}".format(e), level='error')
            self.speaker.say_quick("Mode de base activé.")
            self.current_mode = 'basic'
            self.chat_state = {'status': 'stopped', 'mode': 'basic'}

    def stop(self):
        self._stop_leds()

        if self.is_running():
            self.log("Demande d'arrêt du thread du chatbot...", level='info')
            if self.chat_stop_event:
                self.chat_stop_event.set()
            self.chat_thread.join(timeout=5)
        self.chat_thread = None
        self.chat_stop_event = None

        self.chat_state = {'status': 'stopped', 'mode': 'basic'}
        self.log("Chatbot arrêté. Passage en mode de base.", level='info')
        try:
            self.al_dialog.resetAll()
            self.al_dialog.runDialog()
        except Exception as e:
            self.log("Erreur au démarrage de ALDialog: {}".format(e), level='error')
        self.speaker.say_quick("Le chatbot est arrêté.")
        self.current_mode = 'basic'

    # ------------------------------------------------------------------ Debug API
    def send_debug_prompt(self, payload, stream_observer=None):
        data = dict(payload or {})
        data.pop('debug_stream', None)

        message = (data.get('message') or '').strip()
        if not message:
            return {'error': "Message vide."}

        mode = (data.get('mode') or self.current_mode or 'basic').strip().lower()
        if mode not in ('gpt', 'ollama'):
            return {'error': f"Mode '{mode}' non pris en charge pour le debug."}

        if mode == 'gpt' and not (
            self.config.get('openai', {}).get('api_key') or os.getenv("OPENAI_API_KEY")
        ):
            return {'error': "Clé OpenAI absente pour le mode GPT."}

        history: List[Tuple[str, str]] = []
        for item in data.get('history') or []:
            if not isinstance(item, dict):
                continue
            role = item.get('role')
            content = item.get('content')
            if role in ('user', 'assistant') and isinstance(content, str):
                history.append((role, content))

        anim_families: List[str] = []
        try:
            pls = self.session.service("PepperLifeService")
            if pls:
                anim_families = pls.getAnimationFamilies()
        except Exception as e:
            self.log("[PROMPT] Impossible de récupérer les familles pour le debug: {}".format(e), level='debug')

        custom_prompt = (data.get('custom_prompt') or '').strip()
        system_prompt_override = (data.get('system_prompt') or '').strip()
        prompt_parts = [part for part in (custom_prompt, system_prompt_override) if part]

        def _serialize_debug(value):
            if value is None:
                return None
            for attr in ('model_dump', 'to_dict'):
                try:
                    method = getattr(value, attr)
                    return method()
                except AttributeError:
                    continue
            try:
                json.dumps(value)
                return value
            except TypeError:
                return str(value)

        if mode == 'gpt':
            base_prompt_text = "\n\n".join(prompt_parts) if prompt_parts else self.system_prompt_gpt
            final_prompt, _ = build_system_prompt_in_memory(base_prompt_text, anim_families)
            chat_service = chatGPT(self.config, system_prompt=final_prompt, logger=self.logger)

            model_override = data.get('model')
            if isinstance(model_override, str):
                model_override = model_override.strip() or None
            else:
                model_override = None

            temp_override = data.get('temperature')
            try:
                temp_override = None if temp_override in (None, '') else float(temp_override)
            except (TypeError, ValueError):
                temp_override = None

            max_tokens_override = data.get('max_output_tokens')
            try:
                max_tokens_override = None if max_tokens_override in (None, '') else int(max_tokens_override)
            except (TypeError, ValueError):
                max_tokens_override = None

            stream_requested = callable(stream_observer) and bool(data.get('stream'))

            chat_kwargs = {}
            if stream_requested:
                chat_kwargs['on_chunk'] = stream_observer
                chat_kwargs['stream'] = True

            try:
                reply, raw_resp = chat_service.chat(
                    message,
                    history,
                    model=model_override,
                    temperature=temp_override,
                    max_output_tokens=max_tokens_override,
                    **chat_kwargs
                )
            except Exception as e:
                self.log("[debug_chat] Erreur lors de l'appel du chatbot: {}".format(e), level='error')
                return {'error': str(e)}

            updated_history = history + [('user', message), ('assistant', reply)]
            return {
                'reply': reply,
                'mode': mode,
                'history': [{'role': role, 'content': content} for (role, content) in updated_history],
                'used_prompt': final_prompt,
                'raw': _serialize_debug(raw_resp)
            }

        # Mode Ollama
        ollama_cfg = copy.deepcopy(self.config.get('ollama') or {})
        server_override = (data.get('server') or '').strip()
        if server_override:
            ollama_cfg['active_server'] = server_override

        for field in ('temperature', 'history_length', 'max_output_tokens'):
            if field in data:
                try:
                    value = float(data[field]) if field == 'temperature' else int(data[field])
                    if value > 0:
                        ollama_cfg[field] = value
                except (TypeError, ValueError):
                    pass

        if 'stream' in data:
            ollama_cfg['stream'] = bool(data['stream'])

        model_override = (data.get('model') or '').strip()
        if model_override:
            ollama_cfg['chat_model'] = model_override

        derived_config = copy.deepcopy(self.config)
        derived_config['ollama'] = ollama_cfg

        base_prompt_text = "\n\n".join(prompt_parts) if prompt_parts else self.system_prompt_ollama
        final_prompt, _ = build_system_prompt_in_memory(base_prompt_text, anim_families)

        chat_service = ChatOllama(derived_config, system_prompt=final_prompt, logger=self.logger)

        chat_kwargs = {}
        if callable(stream_observer) and bool(ollama_cfg.get('stream', True)):
            chat_kwargs['on_chunk'] = stream_observer

        try:
            reply, raw_resp = chat_service.chat(
                message,
                history,
                model=model_override or None,
                **chat_kwargs
            )
        except Exception as e:
            self.log("[debug_chat] Erreur Ollama: {}".format(e), level='error')
            return {'error': str(e)}

        updated_history = history + [('user', message), ('assistant', reply)]
        return {
            'reply': reply,
            'mode': mode,
            'history': [{'role': role, 'content': content} for (role, content) in updated_history],
            'used_prompt': final_prompt,
            'raw': _serialize_debug(raw_resp),
            'server': chat_service.base_url,
            'model': ollama_cfg.get('chat_model')
        }

    # ------------------------------------------------------------------ Threads utilitaires
    def _start_leds(self):
        self._stop_leds()
        self.led_stop_event = threading.Event()
        self.led_thread = threading.Thread(
            target=self.led_thread_fn,
            args=(self.led_stop_event, self.session, self.leds, self.listener)
        )
        self.led_thread.daemon = True
        self.led_thread.start()

    def _stop_leds(self):
        if self.led_thread and self.led_thread.is_alive():
            self.log("Arrêt du thread de gestion des LEDs...", level='info')
            if self.led_stop_event:
                self.led_stop_event.set()
            self.led_thread.join(timeout=2)
        self.led_thread = None
        self.led_stop_event = None

    # ------------------------------------------------------------------ Boucle principale
    def _run_chat_loop(self, stop_event: threading.Event, mode: str):
        chat_service = None
        audio_cfg = self.config.setdefault('audio', {})
        original_wait_tag = audio_cfg.get('add_wait_tag', False)
        try:
            posture_service = self.session.service("ALRobotPosture")
            posture_service.goToPosture("Stand", 0.8)
        except Exception as e:
            self.log("Impossible de réinitialiser la posture: {}".format(e), level='warning')

        self.chat_state['status'] = 'starting'
        self.chat_state['mode'] = mode

        try:
            backend_tag = "GPT" if mode == 'gpt' else "OLLAMA"
            self.log("Démarrage du thread du chatbot {}...".format(backend_tag), level='info')

            stt_service = STT(self.config, self.logger)
            stt_engine = getattr(stt_service, 'engine', 'openai')
            if stt_engine == 'local':
                local_info = getattr(stt_service, '_local_base_url', '')
                self.log("[STT] Moteur actif : whisper local ({})".format(local_info or "serveur non défini"), level='info')
            else:
                model = getattr(stt_service, '_openai_model', 'gpt-4o-transcribe')
                self.log("[STT] Moteur actif : openai ({}).".format(model), level='info')

            engine_cfg = self.config.get('ollama', {}) if mode == 'ollama' else self.config.get('openai', {})
            animations_cfg = self.config.get('animations', {}) or {}
            enable_startup_animation = animations_cfg.get('enable_startup_animation', True)
            enable_thinking_gesture = animations_cfg.get('enable_thinking_gesture', True)

            override_startup = engine_cfg.get('enable_startup_animation')
            if override_startup is not None:
                enable_startup_animation = bool(override_startup)
            override_thinking = engine_cfg.get('enable_thinking_gesture')
            if override_thinking is not None:
                enable_thinking_gesture = bool(override_thinking)

            wait_override = engine_cfg.get('add_wait_tag')
            if wait_override is not None:
                audio_cfg['add_wait_tag'] = bool(wait_override)

            if mode == 'ollama':
                chat_service = ChatOllama(self.config, system_prompt=self.system_prompt_ollama, logger=self.logger)
                server_url = chat_service.base_url
                model_used = chat_service.ollama_cfg.get('chat_model') or ""
                if not server_url:
                    err = "Serveur Ollama non configuré."
                    self._report_fatal(err)
                    return
                if not model_used:
                    err = "Modèle Ollama non configuré."
                    self._report_fatal(err)
                    return
                self.log("[Chat] Serveur Ollama : {}".format(server_url), level='info', color=bcolors.OKCYAN)
                self.log("[Chat] Modèle Ollama : {}".format(model_used), level='info', color=bcolors.OKCYAN)
            else:
                chat_service = chatGPT(self.config, system_prompt=self.system_prompt_gpt, logger=self.logger)
                model_used = self.config.get('openai', {}).get('chat_model', 'gpt-4o-mini (default)')
                self.log("[Chat] Utilisation du modèle : {}".format(model_used), level='info', color=bcolors.OKCYAN)
                api_key = self.config.get('openai', {}).get('api_key')
                if api_key:
                    os.environ['OPENAI_API_KEY'] = api_key
                if not os.getenv("OPENAI_API_KEY"):
                    err = "Clé OpenAI absente."
                    self._report_fatal(err, speak=True)
                    return

            self.listener.start()
            self.vision_service.start_camera()
            self.listener.warmup(min_chunks=8, timeout=2.0)

            history: List[Tuple[str, str]] = []
            vision_history: List[Tuple[str, str]] = []

            base_override = self.config.get('audio', {}).get('override_base_sensitivity')
            if not base_override:
                self.log("Calibration du bruit (2s)...", level='info')
                vals = []
                for _ in range(50):
                    with self.listener.lock:
                        audio_chunk = b"" if not self.listener.mon else b"".join(self.listener.mon[-8:])
                    vals.append(avgabs(audio_chunk))
                    time.sleep(0.04)
                base_override = int(sum(vals) / max(1, len(vals)))
                self.log("Calibration terminée. Bruit de base: {}".format(base_override), level='info')

            start_threshold = max(4, int(base_override * self.start_mult))
            stop_threshold = max(3, int(base_override * self.stop_mult))

            def say_and_wait(text: str) -> float:
                start_time = time.time()
                self.speaker.say_quick(text)
                try:
                    pls_local = self.session.service("PepperLifeService")
                    start_wait = time.time()
                    speaking_started = False
                    status = {}
                    while True:
                        status = pls_local.get_state()
                        if status.get('speaking'):
                            speaking_started = True
                            break
                        if stop_event.is_set() or (time.time() - start_wait > 2.0):
                            break
                        time.sleep(0.05)
                    if not speaking_started:
                        time.sleep(0.15)
                        status = pls_local.get_state()
                    while status.get('speaking'):
                        if stop_event.is_set() or (time.time() - start_wait > 15):
                            self.log("Timeout en attente de la fin de la parole.", level='warning')
                            break
                        time.sleep(0.1)
                        status = pls_local.get_state()
                except Exception as exc:
                    self.log("Erreur en attente de la fin de la parole: {}".format(exc), level='error')
                self.log("Parole terminée, nettoyage des tampons audio et petite pause.", level='debug')
                with self.listener.lock:
                    self.listener.mon[:] = []
                    self.listener.pre[:] = []
                time.sleep(0.2)
                return time.time() - start_time

            class StreamingResponder(object):
                def __init__(self, speak_fn: Callable[[str], float], logger, on_first_sentence: Optional[Callable[[], None]] = None):
                    self.say_fn = speak_fn
                    self.log = logger or (lambda *a, **k: None)
                    self.on_first_sentence = on_first_sentence
                    self.buffer: str = ""
                    self.animation_tag: str = ""
                    self.animation_applied: bool = False
                    self.sentences: List[str] = []
                    self.total_duration: float = 0.0
                    self.has_spoken: bool = False

                def _extract_animation(self):
                    if self.animation_tag:
                        return
                    start = self.buffer.find('%%')
                    if start == -1:
                        return
                    end = self.buffer.find('%%', start + 2)
                    if end == -1:
                        return
                    prefix = self.buffer[:start]
                    if prefix.strip():
                        return
                    self.animation_tag = self.buffer[start:end + 2].strip()
                    self.buffer = (prefix + self.buffer[end + 2:]).lstrip()

                def _find_sentence_break(self) -> Optional[int]:
                    for idx, ch in enumerate(self.buffer):
                        if ch in '.?!':
                            if idx == len(self.buffer) - 1:
                                return idx + 1
                            if self.buffer[idx + 1].isspace():
                                return idx + 1
                    return None

                def _stop_thinking(self):
                    if not self.has_spoken and callable(self.on_first_sentence):
                        try:
                            self.on_first_sentence()
                        except Exception:
                            pass

                def _emit(self, sentence: str):
                    if not sentence:
                        return
                    sentence = sentence.strip()
                    if not sentence:
                        return

                    self._stop_thinking()

                    payload = sentence
                    if self.animation_tag:
                        if sentence.startswith(self.animation_tag):
                            self.animation_applied = True
                        elif not self.animation_applied:
                            payload = "{} {}".format(self.animation_tag, sentence).strip()
                            self.animation_applied = True

                    self.sentences.append(payload)
                    try:
                        duration = self.say_fn(payload)
                    except Exception as exc:
                        self.log("[STREAM] say_quick failed: {}".format(exc), level='error')
                        duration = None
                    if isinstance(duration, (int, float)):
                        self.total_duration += duration
                    self.has_spoken = True

                def _drain(self, final: bool):
                    while True:
                        idx = self._find_sentence_break()
                        if idx is None:
                            break
                        current = self.buffer[:idx].strip()
                        self.buffer = self.buffer[idx:].lstrip()
                        if current:
                            self._emit(current)
                    if final and self.buffer.strip():
                        self._emit(self.buffer.strip())
                        self.buffer = ""

                def feed(self, chunk: str):
                    if not isinstance(chunk, str) or not chunk:
                        return
                    self.buffer += chunk
                    self._extract_animation()
                    self._drain(final=False)

                def finish(self, final_text: Optional[str] = None) -> str:
                    if final_text and not self.animation_tag:
                        match = re.search(r'%%[^%]+%%', final_text)
                        if match:
                            self.animation_tag = match.group(0).strip()
                    self._drain(final=True)
                    return self.full_text()

                def full_text(self) -> str:
                    return " ".join(self.sentences).strip()

                def has_output(self) -> bool:
                    return bool(self.sentences)

            if enable_startup_animation:
                try:
                    self.log("Génération d'une phrase de démarrage pour le chatbot...", level='info')
                    startup_phrase, _ = chat_service.chat("tu viens de te reveiller, dis une seule phrase en rapport avec cet événement", [])
                    say_and_wait(startup_phrase)
                except Exception as exc:
                    self.log("Impossible de générer la phrase de démarrage: {}".format(exc), level='error')
                    say_and_wait("Je suis réveillé !")
            else:
                say_and_wait("Je suis prêt.")

            self.chat_state.update({'status': 'running', 'mode': mode, 'engine': model_used, 'last_error': None})

            try:
                pls = self.session.service("PepperLifeService")
            except Exception as e:
                self.log("Impossible de se connecter à PepperLifeService. Les états ne seront pas vérifiés. Erreur: {}".format(e), level='error')
                pls = None

            while not stop_event.is_set():
                asr_duration = gpt_duration = tts_duration = 0.0

                if pls:
                    try:
                        state = pls.get_state()
                        if not self.listener.is_micro_enabled() or state['speaking'] or state['animating']:
                            time.sleep(0.1)
                            continue
                    except Exception as e:
                        self.log("Erreur lors de la récupération de l'état de PepperLifeService: {}".format(e), level='warning')
                        time.sleep(0.5)
                        continue
                else:
                    if not self.listener.is_micro_enabled() or self.listener.is_speaking():
                        time.sleep(0.1)
                        continue

                with self.listener.lock:
                    audio_chunk = b"" if not self.listener.mon else b"".join(self.listener.mon[-8:])
                if avgabs(audio_chunk) < start_threshold:
                    time.sleep(0.05)
                    continue

                thinking_anim_name = ""
                reply_text = None
                stream_spoken = False
                stream_tts_duration = 0.0
                try:
                    self.listener.start_recording()
                    t0 = time.time()
                    last = t0
                    while time.time() - t0 < 5.0:
                        with self.listener.lock:
                            recent = b"" if not self.listener.mon else b"".join(self.listener.mon[-3:])
                        fr = recent[-320:] if len(recent) >= 320 else recent
                        energy = avgabs(fr)
                        if energy >= stop_threshold:
                            last = time.time()
                        if time.time() - last > self.silhold:
                            break
                        time.sleep(0.02)
                    wav = self.listener.stop_recording(stop_threshold)

                    if wav:
                        t_before_stt = time.time()
                        txt = stt_service.stt(wav)
                        t_after_stt = time.time()
                        asr_duration = t_after_stt - t_before_stt
                        self.log("[ASR] {}".format(txt), level='info')

                        if txt and not is_noise_utterance(txt, self.blacklist_strict) and not is_recent_duplicate(txt):
                            thinking_anim_name = ""
                            if enable_thinking_gesture:
                                try:
                                    pls = self.session.service("PepperLifeService")
                                    thinking_anim_name = pls.startRandomThinkingGesture()
                                    if thinking_anim_name:
                                        self.log("[ANIM] Geste de réflexion déclenché: {}".format(thinking_anim_name), level='debug')
                                except Exception as e:
                                    self.log("[ANIM] Échec du démarrage de l'action de réflexion via le service: {}".format(e), level='warning')

                            t_before_chat = time.time()
                            if self.vision_service._utterance_triggers_vision(txt.lower()):
                                png_bytes = self.vision_service.get_png()
                                if png_bytes:
                                    if self.tablet_ui:
                                        try:
                                            self.tablet_ui.set_last_capture(png_bytes)
                                            self.tablet_ui.show_last_capture_on_tablet()
                                        except Exception as e:
                                            self.log("[Tablet] Impossible de mettre à jour la capture: {}".format(e), level='warning')
                                    reply_text = self.vision_service.vision_chat(txt, png_bytes, vision_history)
                                    vision_history.extend([("user", txt), ("assistant", reply_text)])
                                    vision_history = vision_history[-6:]
                                else:
                                    reply_text = "Je n'ai pas réussi à prendre de photo."
                            else:
                                history.append(("user", txt))
                                streaming_enabled = False
                                if mode == 'ollama':
                                    try:
                                        streaming_enabled = bool(chat_service.ollama_cfg.get('stream', True))
                                    except Exception:
                                        streaming_enabled = False
                                else:
                                    streaming_enabled = bool(self.config.get('openai', {}).get('stream', False))

                                stream_responder = None
                                chat_kwargs = {}

                                if streaming_enabled:
                                    def stop_thinking_early():
                                        nonlocal thinking_anim_name
                                        if not thinking_anim_name:
                                            return
                                        try:
                                            pls_stop = self.session.service("PepperLifeService")
                                            pls_stop.stopThink(thinking_anim_name)
                                        except Exception as err:
                                            self.log("[ANIM] Impossible d'arrêter la réflexion en streaming: {}".format(err), level='warning')
                                        thinking_anim_name = ""

                                    stream_responder = StreamingResponder(
                                        speak_fn=say_and_wait,
                                        logger=self.log,
                                        on_first_sentence=stop_thinking_early
                                    )

                                    def _on_stream_chunk(event):
                                        if not isinstance(event, dict):
                                            return
                                        delta = event.get('delta')
                                        if isinstance(delta, str) and delta:
                                            stream_responder.feed(delta)

                                    if mode == 'gpt':
                                        chat_kwargs.update({'on_chunk': _on_stream_chunk, 'stream': True})
                                    else:
                                        chat_kwargs['on_chunk'] = _on_stream_chunk

                                reply_text, raw_reply = chat_service.chat(txt, history[:-1], **chat_kwargs)

                                if stream_responder:
                                    reply_text = stream_responder.finish(reply_text)
                                    stream_spoken = stream_responder.has_output()
                                    stream_tts_duration = stream_responder.total_duration

                                self.log("[GPT] {}".format(reply_text), level='info', color=bcolors.OKGREEN)
                                self.log("[GPT_FULL] {}".format(repr(raw_reply)), level='debug')
                                history.append(("assistant", reply_text))
                                history = history[-8:]
                            t_after_chat = time.time()
                            gpt_duration = t_after_chat - t_before_chat
                except Exception as exc:
                    self.log("[ERR] {}".format(exc), level='error', color=bcolors.FAIL)
                    reply_text = "Petit pépin réseau, on réessaie."
                    self.chat_state['last_error'] = str(exc)
                finally:
                    if thinking_anim_name:
                        try:
                            pls = self.session.service("PepperLifeService")
                            pls.stopThink(thinking_anim_name)
                        except Exception as e:
                            self.log("[ANIM] Impossible d'arrêter la réflexion: {}".format(e), level='warning')

                if reply_text:
                    if thinking_anim_name:
                        try:
                            pls_stop = self.session.service("PepperLifeService")
                            pls_stop.stopThink(thinking_anim_name)
                        except Exception as e:
                            self.log("[ANIM] Impossible d'arrêter la réflexion avant TTS: {}".format(e), level='warning')
                        thinking_anim_name = ""

                    if stream_spoken:
                        tts_duration = stream_tts_duration
                    else:
                        t_before_tts = time.time()
                        self.speaker.say_quick(reply_text)

                        try:
                            pls = self.session.service("PepperLifeService")
                            start_wait = time.time()
                            while pls.get_state()['speaking']:
                                if stop_event.is_set() or (time.time() - start_wait > 15):
                                    self.log("Timeout en attente de la fin de la parole.", level='warning')
                                    break
                                time.sleep(0.1)
                        except Exception as e:
                            self.log("Erreur en attente de la fin de la parole: {}".format(e), level='error')

                        t_after_tts = time.time()
                        tts_duration = t_after_tts - t_before_tts
                    self.log(
                        "Durée du chat : ASR {:.2f}s / GPT {:.2f}s / TTS {:.2f}s".format(
                            asr_duration, gpt_duration, tts_duration
                        ),
                        level='info',
                        color=bcolors.OKCYAN
                    )
        finally:
            audio_cfg['add_wait_tag'] = original_wait_tag
            self.log("Arrêt du thread du chatbot.", level='info')
            if self.chat_state.get('status') != 'error':
                self.chat_state['status'] = 'stopped'
            try:
                self.listener.stop()
            except Exception:
                pass

    # ------------------------------------------------------------------ Helpers
    def _report_fatal(self, message: str, speak: bool = False):
        self.log(message, level='error', color=bcolors.FAIL)
        if speak:
            self.speaker.say_quick(message)
        self.chat_state.update({'status': 'error', 'mode': 'basic', 'last_error': message})
        self.current_mode = 'basic'
