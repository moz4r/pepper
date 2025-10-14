# -*- coding: utf-8 -*-
"""
PepperLifeService  **Minimal v5** (NAOqi 2.9)

Objectif: service NAOqi *fiable et simple*, sans file d'attente, qui expose
les primitives suivantes (toutes **positionnelles** pour qi):

Parole:
- say(text)
- sayAsync(text, preempt)
- sayAnimated(text, block, preempt)
- sayAnimatedIsRunning() -> bool
- stopSayAnimated() -> bool
- resolveAnimationTags(text) -> str

Animations:
- playAnimation(anim_path_or_file, block, preempt)  # on passe juste le chemin
- animationIsRunning() -> bool
- stopAnimation(name) -> bool
- getInstalledAnimations() -> [str]
- getApplications() -> [str]
- getAnimationFamilies() -> [str]
- getAnimationDurations() -> {str: float}

Pensif (loop):
- think(anim_path_or_file, block, cancel_anims)
- thinkIsRunning() -> bool
- stopThink(name) -> bool
- startRandomThinkingGesture() -> bool

Divers:
- get_state() -> {speaking, animating, thinking}
- stopAll() -> bool
- flushQueue() -> 0 (compat tests)
- setBodyLanguageMode(mode) -> bool  (False si non support)

"""
from __future__ import print_function
import qi
import sys
import threading
import logging
import os
import time
import re
import random
from pathlib import Path
import glob
import xml.etree.ElementTree as ET

def setup_logging():
    """Configure logging to a file, erasing it on each start."""
    log_dir = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(log_dir, 'pepper_life_service.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename=log_file,
        filemode='w'
    )
    return logging.getLogger(__name__)


class PepperLifeService(object):
    RE_ANIMATION_TAG = re.compile(r'%%([^%]+)%%', re.IGNORECASE)
    RE_START_TAG = re.compile(r'\^start\(([^)]+)\)', re.IGNORECASE)
    RE_SUFFIX_NUM = re.compile(r'_(\d+)$')

    def __init__(self, session, logger):
        self.session = session
        self.logger = logger
        self._as = None      # ALAnimatedSpeech
        self._ap = None      # ALAnimationPlayer
        self._tts = None     # ALTextToSpeech
        self._posture = None # ALRobotPosture
        self._bm = None      # ALBehaviorManager (pour compat < 2.9)
        self._system = None  # ALSystem (pour la version)

        # Info version
        self.naoqi_version = "0.0.0.0"
        self.is_29 = False

        # Etats / futures
        self._speaking = False
        self._say_future = None
        self._anim_future = None
        self._think_future = None
        self._anim_thread = None # Pour join() < 2.9
        self._running_anim_name = None
        self._running_think_name = None
        self._lock = threading.RLock()
        
        # Dictionnaire des apps et animations
        self.applications = []
        self.animations = []
        self.animations_by_prefix = {}
        self.animations_families = {}
        self.animations_durations = {}
        self.animations_body_language = set()
        self.last_resolved_animation = None

        # Signal (optionnel)
        self.onStateChanged = qi.Signal()
        self.logger.info("PepperLifeService - Minimal v5 initialisé.")

    # -------------------- helpers --------------------
    def _connect(self):
        # Détection de la version (une seule fois)
        if self._system is None:
            try:
                self._system = self.session.service("ALSystem")
                self.naoqi_version = self._system.systemVersion()
                version_parts = self.naoqi_version.split('.')
                major = int(version_parts[0])
                minor = int(version_parts[1])
                self.is_29 = (major == 2 and minor >= 9) or major > 2
                self.logger.info("Version NAOqi détectée: {}. Utilisation des méthodes pour 2.9+: {}".format(self.naoqi_version, self.is_29))
            except Exception as e:
                self.logger.error("Impossible de détecter la version de NAOqi, suppose < 2.9. Erreur: {}".format(e))
                self.is_29 = False # Fallback

        # Connexion aux services communs
        if self._as is None: self._as = self.session.service("ALAnimatedSpeech")
        if self._tts is None: self._tts = self.session.service("ALTextToSpeech")
        if self._posture is None: self._posture = self.session.service("ALRobotPosture")

        # Connexion aux services spécifiques à la version
        if self.is_29:
            if self._ap is None: self._ap = self.session.service("ALAnimationPlayer")
        else:
            if self._bm is None: self._bm = self.session.service("ALBehaviorManager")

        # Lancer le scan des animations une seule fois
        if not self.animations and not self.applications:
            self._scan_apps_and_animations()

    def _emit(self):
        try: self.onStateChanged(self.get_state())
        except Exception: pass

    def _cancel_anim(self, name=None):
        with self._lock:
            anim_name = name or self._running_anim_name or self.last_resolved_animation
            if not anim_name: return

            if self.is_29:
                if self._running_anim_name == anim_name and self._anim_future and self._anim_future.isRunning():
                    try: self._anim_future.cancel()
                    except Exception: pass
            else:
                self.logger.info(u"_cancel_anim[<2.9]: Tentative d'arrêt inconditionnel du comportement '{}'...".format(anim_name))
                try:
                    # isBehaviorRunning n'est pas fiable pour les boucles, on arrête sans condition.
                    self._bm.stopBehavior(anim_name)
                except Exception as e:
                    self.logger.error(u"L'arrêt du comportement '{}' a échoué: {}".format(anim_name, e))
            
            if self._running_anim_name == anim_name:
                self._anim_future = None
                self._running_anim_name = None
            
            if self.last_resolved_animation == anim_name:
                self.last_resolved_animation = None
            self._emit()

    def _stop_thinking(self, name=None):
        with self._lock:
            think_name = name or self._running_think_name or self.last_resolved_animation
            if not think_name: return

            if self.is_29:
                if self._running_think_name == think_name and self._think_future and self._think_future.isRunning():
                    try: self._think_future.cancel()
                    except Exception: pass
            else:
                self.logger.info(u"_stop_thinking[<2.9]: Tentative d'arrêt inconditionnel du comportement '{}'...".format(think_name))
                try:
                    # isBehaviorRunning n'est pas fiable pour les boucles, on arrête sans condition.
                    self._bm.stopBehavior(think_name)
                except Exception as e:
                    self.logger.error(u"L'arrêt du comportement '{}' a échoué: {}".format(think_name, e))

            if self._running_think_name == think_name:
                self._think_future = None
                self._running_think_name = None

            if self.last_resolved_animation == think_name:
                self.last_resolved_animation = None
            self._emit()

    def _stop_speaking(self):
        try:
            if self._as is not None:
                for m in ("stopAll", "stop"): 
                    try: 
                        getattr(self._as, m)()
                        break
                    except Exception: pass
        except Exception: pass
        try:
            if self._tts is not None:
                for m in ("stopAll", "stop"): 
                    try: 
                        getattr(self._tts, m)()
                        break
                    except Exception: pass
        except Exception: pass
        with self._lock:
            self._speaking = False
            self._emit()

    # -------------------- API Publique --------------------
    def get_state(self):
        with self._lock:
            speaking = self.sayAnimatedIsRunning()
            animating = self.animationIsRunning()
            thinking = self.thinkIsRunning()
            return {
                'speaking': speaking,
                'animating': animating,
                'thinking': thinking,
            }

    def say(self, text_with_tags):
        self._connect()
        with self._lock: self._speaking = True; self._emit()
        try: self._as.say(text_with_tags)
        finally: 
            with self._lock: self._speaking = False; self._emit()
        return True

    def sayAsync(self, text_with_tags, preempt):
        self._connect()
        if preempt: self.stopAll()
        with self._lock: self._speaking = True; self._emit()
        self._say_future = self._as.say(text_with_tags, _async=True)
        def _on_done(_): 
            with self._lock: self._speaking = False; self._emit()
        try: self._say_future.addCallback(_on_done)
        except Exception: pass
        return True

    def sayAnimated(self, text_with_tags, block, preempt):
        self._connect()

        if self.is_29:
            self.logger.info(u"sayAnimated[2.9]: Lancement custom (TTS + Animation Player)...")
            anim_name = None
            clean_text = text_with_tags

            # 1. Parser le texte pour extraire l'animation et nettoyer le texte
            loop_until_done = False
            anim_match = re.search(r'\^(start|wait)\(([^)]+)\)', text_with_tags)
            if anim_match:
                anim_name = anim_match.group(2)
                clean_text = re.sub(r'\^(start|wait)\([^)]+\)', '', text_with_tags).strip()
            loop_until_done = "^wait(" in text_with_tags

            if not anim_name and not clean_text: return True
            if not anim_name: return self.say(clean_text)
            if not clean_text: return self.playAnimation(anim_name, block, False)

            # 2. Lancer la parole et l'animation en parallèle
            say_future = self._tts.say(clean_text, _async=True)
            with self._lock:
                self._speaking = True
                self._say_future = say_future
                self._emit()
            
            def _on_say_done(_):
                with self._lock:
                    self._speaking = False
                    self._say_future = None
                    self._emit()
            say_future.addCallback(_on_say_done)

            self.playAnimation(anim_name, False, False)

            if loop_until_done:
                with self._lock:
                    initial_future = self._anim_future

                def _restart_if_needed(_fut):
                    try:
                        with self._lock:
                            still_speaking = bool(
                                self._speaking or (self._say_future and self._say_future.isRunning())
                            )
                    except Exception:
                        still_speaking = False

                    if still_speaking:
                        self.logger.debug(u"[ANIM] Relance de l'animation de parole '{}' (wait actif).".format(anim_name))
                        self.playAnimation(anim_name, False, False)
                        with self._lock:
                            next_future = self._anim_future
                        if next_future:
                            try:
                                next_future.addCallback(_restart_if_needed)
                            except Exception:
                                pass

                if initial_future:
                    try:
                        initial_future.addCallback(_restart_if_needed)
                    except Exception:
                        pass

            if block:
                try:
                    say_future.wait()
                    with self._lock: anim_future_copy = self._anim_future
                    if anim_future_copy: anim_future_copy.wait()
                except Exception as e:
                    self.logger.warning(u"sayAnimated[2.9]: Le wait() a échoué: {}".format(e))
        
        else: # Logique pour < 2.9
            self.logger.info(u"sayAnimated[<2.9]: Lancement custom (TTS + BehaviorManager)...")
            anim_name = None
            clean_text = text_with_tags

            # 1. Parser le texte pour extraire l'animation et nettoyer le texte
            loop_until_done = False
            anim_match = re.search(r'\^(start|wait)\(([^)]+)\)', text_with_tags)
            if anim_match:
                anim_name = anim_match.group(2)
                clean_text = re.sub(r'\^(start|wait)\([^)]+\)', '', text_with_tags).strip()
            loop_until_done = "^wait(" in text_with_tags

            if not anim_name and not clean_text: return True
            if not anim_name: return self.say(clean_text)
            if not clean_text: return self.playAnimation(anim_name, block, False)

            # 2. Lancer la parole et l'animation en parallèle
            say_future = self._tts.say(clean_text, _async=True)
            with self._lock:
                self._speaking = True
                self._say_future = say_future
                self._emit()
            
            def _on_say_done(fut):
                self.logger.debug(u"sayAnimated: _on_say_done callback triggered.")
                with self._lock:
                    self._speaking = False
                    self._say_future = None
                    self._emit()
                
                # Stop animation at the end of speech ONLY if it has no known duration
                if anim_name:
                    duration = self.animations_durations.get(anim_name)
                    if not duration or duration <= 0:
                        self.logger.info(u"sayAnimated[<2.9]: Fin de la parole, arrêt de l'animation SANS durée '{}'".format(anim_name))
                        self.stopAnimation(anim_name)
                    else:
                        self.logger.info(u"sayAnimated[<2.9]: Fin de la parole, l'animation AVEC durée '{}' continue.".format(anim_name))

            try:
                say_future.addCallback(_on_say_done)
            except Exception as e:
                self.logger.error(u"sayAnimated[<2.9]: Erreur lors de l'ajout du callback: {}".format(e))
                # Fallback sans callback
                if block:
                    try: say_future.wait()
                    except Exception: pass

            self.playAnimation(anim_name, False, False)

            if loop_until_done:
                def _loop_anim_behaviors():
                    while True:
                        with self._lock:
                            speaking_flag = bool(self._speaking or (self._say_future and hasattr(self._say_future, 'isRunning') and self._say_future.isRunning()))
                        if not speaking_flag:
                            break
                        local_thread = None
                        with self._lock:
                            local_thread = self._anim_thread
                        if local_thread:
                            local_thread.join()
                        else:
                            time.sleep(0.05)
                        with self._lock:
                            speaking_flag = bool(self._speaking or (self._say_future and hasattr(self._say_future, 'isRunning') and self._say_future.isRunning()))
                        if not speaking_flag:
                            break
                        self.logger.debug(u"[ANIM] Relance du comportement de parole '{}' (wait actif).".format(anim_name))
                        self.playAnimation(anim_name, False, False)
                        time.sleep(0.01)
                loop_thread = threading.Thread(target=_loop_anim_behaviors)
                loop_thread.daemon = True
                loop_thread.start()

            if block:
                self.logger.debug(u"sayAnimated: Mode bloquant activé.")
                try:
                    self.logger.debug(u"sayAnimated: Attente de la fin de la parole...")
                    say_future.wait()
                    self.logger.debug(u"sayAnimated: Parole terminée.")
                    
                    with self._lock: anim_thread_copy = self._anim_thread
                    if anim_thread_copy:
                        self.logger.debug(u"sayAnimated: Attente de la fin de l'animation (thread join)...")
                        anim_thread_copy.join(timeout=25.0) # Augmentation du timeout pour le debug
                        if anim_thread_copy.is_alive():
                            self.logger.warning(u"sayAnimated: Le thread d'animation est toujours en vie après le timeout du join.")
                        else:
                            self.logger.debug(u"sayAnimated: Le thread d'animation s'est terminé.")
                    else:
                        self.logger.warning(u"sayAnimated: Impossible de trouver le thread d'animation à attendre.")

                except Exception as e:
                    self.logger.warning(u"sayAnimated[<2.9]: Le wait() a échoué: {}".format(e))
                self.logger.debug(u"sayAnimated: Fin du mode bloquant.")
            
        return True

    def sayAnimatedIsRunning(self):
        self._connect()
        with self._lock:
            if self.is_29:
                return bool(self._speaking) or bool(self._say_future and self._say_future.isRunning())
            else:
                # NAOqi < 2.9: privilégie l'état interne (_speaking) avant d'interroger ALTextToSpeech
                speaking_flag = bool(self._speaking)
                fut_running = False
                if self._say_future is not None:
                    try:
                        fut_running = bool(self._say_future.isRunning())
                    except Exception:
                        fut_running = False
                if speaking_flag or fut_running:
                    return True
                try:
                    return bool(self._tts.isSpeaking())
                except Exception:
                    return False

    def stopSayAnimated(self): self._stop_speaking(); return True

    def _start_security_timer(self, anim_name, future=None):
        duration = self.animations_durations.get(anim_name)
        if not duration or duration <= 0:
            return

        self.logger.debug(u"[ANIM] Minuteur de sécurité activé pour {} ({}s)".format(anim_name, duration))

        def callback():
            self.logger.debug(u"[ANIM] Minuteur de sécurité déclenché pour {}.".format(anim_name))
            
            def do_cancel_29():
                try:
                    if future and future.isRunning():
                        self.logger.warning(u"[ANIM] L'animation 2.9 {} a dépassé sa durée. Annulation programmée.".format(anim_name))
                        future.cancel()
                except Exception as e:
                    self.logger.error(u"[ANIM] Erreur dans do_cancel_29: {}".format(e))

            try:
                if self.is_29:
                    # Annule directement depuis le thread Python; le Future gère l'accès multi-thread.
                    do_cancel_29()
                else:
                    if self._bm.isBehaviorRunning(anim_name):
                        self.logger.warning(u"[ANIM] Le comportement <2.9 {} a dépassé sa durée. Arrêt forcé.".format(anim_name))
                        self._bm.stopBehavior(anim_name)
            except Exception as e:
                self.logger.error(u"[ANIM] Erreur dans le callback du minuteur pour {}: {}".format(anim_name, e))

        timer = threading.Timer(duration + 1.0, callback)
        timer.daemon = True
        timer.start()

    def playAnimation(self, anim_name, block, preempt):
        self._connect()
        if preempt: self.stopAll()

        if self.is_29:
            self.logger.info(u"playAnimation[2.9]: Lancement de l'animation {}...".format(anim_name))
            fut = self._ap.run(anim_name, _async=True)
            with self._lock: self._anim_future = fut; self._running_anim_name = anim_name; self._emit()
            def _on_done(_): 
                with self._lock: 
                    if self._running_anim_name == anim_name: self._anim_future = None; self._running_anim_name = None; self._emit()
            try: fut.addCallback(_on_done)
            except Exception: pass
            
            self._start_security_timer(anim_name, future=fut)

            if block: 
                try: fut.wait()
                except Exception: pass
        else: # Logique pour < 2.9
            self.logger.info(u"playAnimation[<2.9]: Lancement du comportement {}...".format(anim_name))

            def run_and_clear():
                self.logger.debug(u"playAnimation thread started for '{}'.".format(anim_name))
                try: 
                    with self._lock: self._running_anim_name = anim_name
                    self._bm.runBehavior(anim_name)
                    self.logger.debug(u"playAnimation: runBehavior finished for '{}'.".format(anim_name))
                except Exception as e:
                    self.logger.error(u"playAnimation: runBehavior failed for '{}': {}".format(anim_name, e))
                finally: 
                    self.logger.debug(u"playAnimation thread finished for '{}'.".format(anim_name))
                    with self._lock: 
                        if self._running_anim_name == anim_name: self._running_anim_name = None
            
            if block: 
                run_and_clear()
            else: 
                th = threading.Thread(target=run_and_clear)
                th.daemon = True
                with self._lock: self._anim_thread = th
                th.start()
                
                self._start_security_timer(anim_name)
        return True

    def animationIsRunning(self):
        self._connect()
        with self._lock:
            if self.is_29: return bool(self._anim_future and self._anim_future.isRunning())
            else: 
                if self._running_anim_name: 
                    try: return self._bm.isBehaviorRunning(self._running_anim_name)
                    except Exception as e: self.logger.warning("Impossible de vérifier le statut de {}: {}".format(self._running_anim_name, e)); return False
                return False

    def stopAnimation(self, name=""):
        self._cancel_anim(name)
        return True

    def think(self, anim_name, block, cancel_anims):
        self._connect()
        if cancel_anims: self._stop_speaking(); self._cancel_anim()
        if self.thinkIsRunning():
            if block: 
                try: 
                    if self.is_29: 
                        if self._think_future: self._think_future.wait()
                    else: 
                        if self._think_future: self._think_future.join()
                except Exception: pass
            return True

        if self.is_29:
            self.logger.info(u"think[2.9]: Lancement de {}...".format(anim_name))
            fut = self._ap.run(anim_name, _async=True)
            with self._lock: self._think_future = fut; self._running_think_name = anim_name; self._emit()
            def _on_done(_): 
                with self._lock: 
                    if self._running_think_name == anim_name: self._think_future = None; self._running_think_name = None; self._emit()
            try: fut.addCallback(_on_done)
            except Exception: pass
            if block: 
                try: fut.wait()
                except Exception: pass
        else:
            self.logger.info(u"think[<2.9]: Lancement de {}...".format(anim_name))
            def run_and_clear():
                try: self._bm.runBehavior(anim_name)
                finally: 
                    with self._lock: 
                        if self._running_think_name == anim_name: self._running_think_name = None; self._think_future = None; self._emit()
            thread = threading.Thread(target=run_and_clear)
            thread.daemon = True
            with self._lock: self._think_future = thread; self._running_think_name = anim_name; self._emit()
            thread.start()
            if block: thread.join()
        return True

    def thinkIsRunning(self):
        self._connect()
        with self._lock:
            if self.is_29: return bool(self._think_future and self._think_future.isRunning())
            else: return bool(self._think_future and self._think_future.is_alive())

    def stopThink(self, name=""):
        self._stop_thinking(name)
        return True

    def startRandomThinkingGesture(self):
        self._connect()
        try:
            families = self.getAnimationFamilies()
            thinking_families = [f for f in families if "Scratch" in f or "Think" in f]
            if not thinking_families:
                self.logger.warning("Aucune famille d'animation 'Think' ou 'Scratch' trouvée pour le geste de réflexion.")
                return ""
            chosen_family = random.choice(thinking_families)
            tag = self._reconstruct_animation_tag(chosen_family)
            match = re.search(r'\(([^)]+)\)', tag)
            if match:
                anim_to_run = match.group(1)
                self.logger.info(u"Lancement du geste de réflexion aléatoire: {}".format(anim_to_run))
                self.think(anim_to_run, False, True) # non-blocking, preemptive
                return anim_to_run
        except Exception as e:
            self.logger.error(u"Erreur lors du lancement du geste de réflexion: {}".format(e))
        return "" 

    def flushQueue(self): return 0

    def setBodyLanguageMode(self, mode):
        self._connect()
        try: 
            try: mode_to_set = int(mode)
            except (ValueError, TypeError): mode_to_set = mode
            self._as.setBodyLanguageMode(mode_to_set)
            return True
        except Exception: return False

    def getRunningAnimations(self):
        self._connect()
        with self._lock:
            if self.is_29:
                running = []
                if self._running_anim_name and self._anim_future and self._anim_future.isRunning(): running.append(self._running_anim_name)
                if self._running_think_name and self._think_future and self._think_future.isRunning(): running.append(self._running_think_name)
                return running
            else: 
                try: 
                    all_behaviors = self._bm.getRunningBehaviors()
                    return [b for b in all_behaviors if b.startswith("animations/")]
                except Exception as e: self.logger.warning(u"Impossible de récupérer les comportements en cours: {}".format(e)); return []

    def stopAll(self):
        self._connect()
        if self.is_29:
            self.logger.info("stopAll[2.9]: Arrêt des futurs d'animation et de la parole...")
            self._stop_thinking(); self._cancel_anim(); self._stop_speaking()
        else:
            self.logger.info("stopAll[<2.9]: Arrêt de tous les comportements et de la parole...")
            try: self._bm.stopAllBehaviors()
            except Exception as e: self.logger.error(u"stopAllBehaviors a échoué: {}".format(e))
            self._stop_speaking()
        return True

    def getInstalledAnimations(self):
        self._connect()
        return self.animations

    def getApplications(self):
        self._connect()
        return self.applications

    def getAnimationFamilies(self):
        self._connect()
        return sorted([k.replace('animations/', '') for k in self.animations_families.keys()])

    def getAnimationDurations(self):
        self._connect()
        return self.animations_durations

    def getAnimationStats(self):
        """Retourne le nombre d'animations et de familles chargées."""
        self._connect() # Assure que le scan a été fait
        return {
            'animation_count': len(self.animations),
            'family_count': len(self.animations_families)
        }

    def getNaoqiVersion(self):
        self._connect()
        return self.naoqi_version

    def _get_qianim_duration(self, qianim_file_path):
        """Calculates the duration of a .qianim animation."""
        try:
            tree = ET.parse(qianim_file_path)
            root = tree.getroot()
            
            max_frame = 0
            fps = 25 # Default fps

            for actuator_curve in root.findall('ActuatorCurve'):
                if 'fps' in actuator_curve.attrib:
                    try:
                        fps = int(actuator_curve.get('fps'))
                    except (ValueError, TypeError):
                        pass

                for key in actuator_curve.findall('Key'):
                    try:
                        frame = int(key.get('frame'))
                        if frame > max_frame:
                            max_frame = frame
                    except (ValueError, TypeError):
                        continue
            
            if max_frame > 0 and fps > 0:
                duration = float(max_frame) / float(fps)
                self.logger.debug(u"[ANIM] Durée calculée pour {}: {:.2f}s".format(os.path.basename(qianim_file_path), duration))
                return duration
                
            return 0.0
        except Exception as e:
            self.logger.error(u"[ANIM] Erreur lors du calcul de la durée pour {}: {}".format(qianim_file_path, e))
            return 0.0

    def _get_xar_duration(self, xar_file_path):
        """Calcule la durée d'une animation .xar en se basant sur sa timeline."""
        try:
            tree = ET.parse(xar_file_path)
            root = tree.getroot()
            timeline_element = None
            # Itération robuste pour trouver la timeline, quel que soit le namespace
            for elem in root.iter():
                if elem.tag.endswith('Timeline'):
                    timeline_element = elem
                    break
            
            if timeline_element is not None:
                fps = float(timeline_element.get('fps', 25))
                size = float(timeline_element.get('size', 0))
                if fps > 0 and size > 0:
                    # La durée est le nombre de frames divisé par le framerate
                    duration = size / fps
                    self.logger.debug(u"[ANIM] Durée calculée pour {}: {:.2f}s".format(os.path.basename(xar_file_path), duration))
                    return duration
            return 0.0
        except Exception as e:
            self.logger.error(u"[ANIM] Erreur lors du calcul de la durée pour {}: {}".format(xar_file_path, e))
            return 0.0

    def _scan_apps_and_animations(self):
        self.logger.info("Lancement du scan des applications et animations...")
        self.applications = []
        self.animations = []
        self.animations_by_prefix = {}
        self.animations_families = {}
        self.animations_durations.clear() # On vide avant de remplir
        self.animations_body_language = set()

        if not self.is_29:
            self.logger.info("[scan] Utilisation de la logique < 2.9 (ALBehaviorManager)")
            try:
                installed_behaviors = self._bm.getInstalledBehaviors()
                # Scan des durées des animations .xar
                try:
                    # Le chemin sur le robot est /home/nao/.local/share/PackageManager/apps/
                    xar_base_dir = os.path.expanduser('~nao/.local/share/PackageManager/apps/')
                    if os.path.isdir(xar_base_dir):
                        for xar_file_path in glob.glob(os.path.join(xar_base_dir, "**", "behavior.xar"), recursive=True):
                            duration = self._get_xar_duration(xar_file_path)
                            if duration > 0:
                                # Construit la clé de comportement à partir du chemin du fichier
                                # ex: /path/to/apps/animations/Stand/Gestures/Hey_1/behavior.xar -> animations/Stand/Gestures/Hey_1
                                relative_path = os.path.relpath(os.path.dirname(xar_file_path), xar_base_dir)
                                behavior_key = relative_path.replace(os.path.sep, '/')
                                if behavior_key.startswith("animations/"):
                                    self.animations_durations[behavior_key] = duration
                except Exception as e:
                    self.logger.error("Erreur lors du scan des durées des .xar: {}".format(e))

                for behavior in installed_behaviors:
                    try:
                        nature = self._bm.getBehaviorNature(behavior)
                        b_info = {'name': behavior, 'nature': nature}
                        if nature in ['interactive', 'solitary']:
                            self.applications.append(b_info)
                        else:
                            self.animations.append(b_info)
                        if behavior.startswith("animations/"):
                            fam = self.RE_SUFFIX_NUM.sub("_", behavior)
                            self.animations_by_prefix.setdefault(fam, []).append(behavior)
                    except Exception:
                        continue
            except Exception as e:
                self.logger.error("Erreur lors du scan des comportements (<2.9): {}".format(e))
        else:
            self.logger.info("[scan] Utilisation de la logique 2.9+ (pm.db + filesystem)")
            # 1. Récupérer les applications depuis la base de données
            try:
                db_path = '/home/nao/.local/share/PackageManager/pm.db'
                if os.path.exists(db_path):
                    import sqlite3
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT uuid FROM packages")
                    for pkg in cursor.fetchall():
                        if pkg[0]:
                            # On suppose que les packages dans la DB sont des applications principales
                            self.applications.append({'name': pkg[0], 'nature': 'interactive'})
                    conn.close()
                else:
                    self.logger.warning("Fichier pm.db introuvable, la liste d'applications sera peut-être incomplète.")
            except Exception as e:
                self.logger.error("Erreur lors de la lecture de pm.db: {}".format(e))

            # 2. Récupérer les animations depuis le système de fichiers
            try:
                base = Path.home() / ".local/share/PackageManager/apps/animations"
                if base.is_dir():
                    for p in base.rglob("*.qianim"):
                        # Le nom de l'animation est son chemin relatif depuis 'animations'
                        rel_path = p.relative_to(base).as_posix()
                        full_name = self._emit29(rel_path)
                        self.animations.append({'name': full_name, 'nature': 'animation'})
                        
                        # Calculer et stocker la durée
                        duration = self._get_qianim_duration(str(p))
                        if duration > 0:
                            self.animations_durations[full_name] = duration

                        # Remplir les familles pour la résolution de tags
                        noext = rel_path[:-7] # retire .qianim
                        fam = self.RE_SUFFIX_NUM.sub("_", noext)
                        self.animations_by_prefix.setdefault(fam, []).append(rel_path)
            except Exception as e:
                self.logger.error("Erreur lors du scan des fichiers .qianim: {}".format(e))

        # Familles unifiées (pour la résolution de tags type %%anim%%)
        for fam_underscore, anims in self.animations_by_prefix.items():
            clean_fam = fam_underscore.rstrip('_')
            self.animations_families[clean_fam] = anims
        
        # Log récapitulatif
        anim_count = len(self.animations)
        fam_count = len(self.animations_families)
        log_msg = u"{} animations chargées, compressées en {} familles.".format(anim_count, fam_count)
        self.logger.info(u"\033[93m{}\033[0m".format(log_msg)) # Message en jaune

        self.logger.info("Scan terminé: {} applications et {} animations trouvées.".format(len(self.applications), len(self.animations)))

    def resolveAnimationTags(self, text):
        self.last_resolved_animation = None
        def replace_and_track(m):
            return self._reconstruct_animation_tag(m.group(1))
        processed_text = self.RE_ANIMATION_TAG.sub(replace_and_track, text or "")
        if self.last_resolved_animation is None:
            match = self.RE_START_TAG.search(processed_text)
            if match: self.last_resolved_animation = match.group(1)
        return processed_text

    def _reconstruct_animation_tag(self, animation_path):
        chosen = None
        raw = animation_path.strip()
        if self.is_29:
            key_rel = self._to_qianim_relative(raw)
            family_anims = self.animations_families.get(key_rel)
            if family_anims:
                chosen = random.choice(family_anims)
            else:
                installed_anims = [a['name'] for a in self.animations]
                full_candidate = self._emit29(key_rel)
                if full_candidate in installed_anims:
                    chosen = key_rel
                elif key_rel in installed_anims:
                    chosen = key_rel
                elif f"{key_rel}.qianim" in installed_anims:
                    chosen = f"{key_rel}.qianim"
                elif full_candidate.endswith(".qianim") and full_candidate[:-7] in installed_anims:
                    chosen = full_candidate
            if not chosen:
                self.logger.warning(f"[ANIM] Animation ou famille inconnue (2.9): '{raw}'")
                chosen = key_rel
            emit = self._emit29(chosen)
            self.last_resolved_animation = emit
            return f"^start({emit})"
        else:
            family_anims = self.animations_families.get('animations/' + raw)
            if family_anims: chosen = random.choice(family_anims)
            else:
                key = 'animations/' + raw
                installed_anims = [a['name'] for a in self.animations]
                if key in installed_anims: chosen = key
            if not chosen: self.logger.warning(f"[ANIM] Animation ou famille inconnue (2.7): '{raw}'"); chosen = 'animations/' + raw
            self.last_resolved_animation = chosen
            return f"^start({chosen})"

    @staticmethod
    def _to_qianim_relative(k):
        k = k.strip()
        k = k[2:] if k.startswith("./") else k
        if k.startswith("animations/"): k = k.split("animations/", 1)[1]
        elif k.startswith("animation/"): k = k.split("animation/", 1)[1]
        return k

    def _emit29(self, rel_path):
        rp = rel_path
        if not rp.endswith(".qianim"): rp = rp + ".qianim"
        return rp if rp.startswith("animations/") else ("animations/" + rp)

# -------------------- bootstrap --------------------

def main():
    logger = setup_logging()
    try:
        app = qi.Application(sys.argv); app.start()
    except Exception as e:
        logger.error("Impossible de démarrer l'application NAOqi: {}".format(e)); sys.exit(1)
    
    service = PepperLifeService(app.session, logger)
    sid = -1
    try:
        sid = app.session.registerService('PepperLifeService', service)
        logger.info("Service 'PepperLifeService' enregistré id={}".format(sid))
        app.run()
    except KeyboardInterrupt:
        logger.info("Arrêt manuel demandé.")
    finally:
        logger.info("Arrêt du service...")
        if sid != -1:
            try: app.session.unregisterService(sid)
            except Exception: pass
        app.stop()


if __name__ == '__main__':
    main()
