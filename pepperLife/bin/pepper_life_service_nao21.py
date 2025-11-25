#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PepperLifeService (NAOqi 2.1/2.5, Python 2)
Version allégée sans logique spécifique NAOqi 2.9 (ALAnimationPlayer, etc.).
Expose un sous-ensemble compatible des méthodes du service Python3.
"""
from __future__ import print_function
import sys
import os
import logging
import threading
import time
import qi
import re
import random


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
    def __init__(self, session, logger):
        self.session = session
        self.logger = logger
        self._as = None      # ALAnimatedSpeech
        self._tts = None     # ALTextToSpeech
        self._bm = None      # ALBehaviorManager
        self._posture = None # ALRobotPosture
        self._lock = threading.RLock()
        self._speaking = False
        self._running_anim = None
        self._running_think = None
        self._think_thread = None
        self._anim_thread = None
        self._say_future = None
        self.animations = []
        self.animations_families = {}
        self.animations_durations = {}
        self.applications = []
        self.last_resolved_animation = None
        self.onStateChanged = qi.Signal()
        self.logger.info("PepperLifeService Py2 (NAOqi 2.1/2.5) initialisé.")

    # ---------------- Helpers ----------------
    def _connect(self):
        if self._as is None:
            try:
                self._as = self.session.service("ALAnimatedSpeech")
            except Exception as exc:
                self.logger.debug("ALAnimatedSpeech indisponible: %s", exc)
        if self._tts is None:
            try:
                self._tts = self.session.service("ALTextToSpeech")
            except Exception as exc:
                self.logger.warning("ALTextToSpeech indisponible: %s", exc)
        if self._bm is None:
            try:
                self._bm = self.session.service("ALBehaviorManager")
            except Exception as exc:
                self.logger.warning("ALBehaviorManager indisponible: %s", exc)
        if self._posture is None:
            try:
                self._posture = self.session.service("ALRobotPosture")
            except Exception:
                pass

    def _emit(self):
        try:
            self.onStateChanged(self.get_state())
        except Exception:
            pass

    def _scan_apps_and_animations(self):
        """Récupère les comportements installés via ALBehaviorManager."""
        self._connect()
        # Applications (PackageManager)
        try:
            pm = self.session.service("PackageManager")
        except Exception:
            pm = None
        apps = []
        app_names = set()
        if pm:
            def _parse_entry(entry):
                # entry attendu: liste de couples [key, value]
                if isinstance(entry, basestring):
                    return {'name': entry, 'nature': 'interactive'}
                if isinstance(entry, dict):
                    data = entry
                elif isinstance(entry, (list, tuple)):
                    data = {}
                    for item in entry:
                        if isinstance(item, (list, tuple)) and len(item) == 2:
                            key, val = item
                            data[str(key)] = val
                else:
                    return None
                name = data.get('uuid') or data.get('name')
                if not name:
                    lang_names = data.get('langToName') or data.get('names')
                    if isinstance(lang_names, dict) and lang_names:
                        try:
                            name = list(lang_names.values())[0]
                        except Exception:
                            pass
                    elif isinstance(lang_names, (list, tuple)) and lang_names:
                        first = lang_names[0]
                        if isinstance(first, (list, tuple)) and len(first) >= 2:
                            name = first[1]
                if not name and data.get('path'):
                    name = os.path.basename(str(data.get('path')))
                if not name:
                    return None
                nature = 'application'
                behaviors = data.get('behaviors')
                if isinstance(behaviors, (list, tuple)) and behaviors:
                    for beh in behaviors:
                        if isinstance(beh, dict):
                            nature = beh.get('nature') or nature
                        elif isinstance(beh, (list, tuple)):
                            for sub in beh:
                                if isinstance(sub, (list, tuple)) and len(sub) == 2 and sub[0] == 'nature':
                                    nature = sub[1] or nature
                                    break
                return {
                    'name': name,
                    'nature': nature or 'application',
                    'path': data.get('path') or '',
                }

            for attr in ("listPackages", "packages", "getPackages"):
                fn = getattr(pm, attr, None)
                if not callable(fn):
                    continue
                try:
                    result = fn()
                    if result and isinstance(result, (list, tuple)):
                        self.logger.info("PackageManager.%s returned %d entries", attr, len(result))
                        for entry in result:
                            parsed = _parse_entry(entry)
                            if not parsed:
                                self.logger.info("Unparsable package entry: %s", entry)
                            if parsed:
                                apps.append(parsed)
                                if isinstance(parsed, dict) and parsed.get('name'):
                                    app_names.add(parsed.get('name'))
                        break
                except Exception as exc:
                    self.logger.info("PackageManager.%s failed: %s", attr, exc)
                    continue
        self.applications = apps

        self.logger.info("Applications retenues: %d", len(app_names))

        # Animations (behaviors)
        if self._bm:
            try:
                installed = self._bm.getInstalledBehaviors()
                self.logger.info("ALBehaviorManager.getInstalledBehaviors -> %d entries", len(installed) if installed else 0)
                anims = list(installed) if installed else []
                # Filtrer les behaviors appartenant aux apps (PackageManager) par uuid/app_name (pref app_names)
                # S'il ne reste rien après filtre strict, on retombe sur la liste complète.
                if app_names:
                    filtered = []
                    for name in anims:
                        if not isinstance(name, basestring):
                            continue
                        skip = False
                        for app_name in app_names:
                            if app_name == 'animations':
                                continue
                            if name == app_name or name.startswith(app_name + "/"):
                                skip = True
                                break
                        if not skip:
                            filtered.append(name)
                    if filtered:
                        anims = filtered
                    else:
                        self.logger.info("Filtre apps a éliminé toutes les animations, fallback à la liste complète.")
                # Normalisation des noms d'animations (supprime le double préfixe, ajoute 'animations/' si manquant)
                normalized = []
                for name in anims:
                    if not isinstance(name, basestring):
                        continue
                    if name.startswith("animations/animations/"):
                        name = name.replace("animations/animations/", "animations/", 1)
                    elif not name.startswith("animations/"):
                        name = "animations/" + name
                    normalized.append(name)
                anims = list(dict.fromkeys(normalized))  # dédoublonne en conservant l'ordre
                self.logger.info("Animations filtrées (après exclusion apps): %d", len(anims))
                self.animations = anims
                families = {}
                for name in self.animations:
                    if not isinstance(name, basestring):
                        continue
                    if '/' in name:
                        prefix = name.rsplit('/', 1)[0]
                        families.setdefault(prefix, []).append(name)
                self.logger.info("Familles d'animations détectées: %d", len(families))
                self.animations_families = families
                self.animations_durations = {}
            except Exception as exc:
                self.logger.error("Scan animations impossible: %s", exc)
                self.animations = []
                self.animations_families = {}
                self.animations_durations = {}
        # filtre animations en retirant les éventuels noms identiques aux apps
        if app_names and self.animations:
            self.animations = [a for a in self.animations if a not in app_names]

    # ---------------- Speech ----------------
    def say(self, text):
        self._connect()
        if not text:
            return False
        self._speaking = True
        try:
            if self._as:
                self._as.say(text)
            elif self._tts:
                self._tts.say(text)
            return True
        except Exception as exc:
            self.logger.error("say failed: %s", exc)
            return False
        finally:
            self._speaking = False
            self._emit()

    def sayAsync(self, text, preempt=False):
        # preempt ignoré dans cette version simplifiée
        self._connect()
        if not text:
            return False
        def _run():
            try:
                if self._as:
                    self._as.say(text)
                elif self._tts:
                    self._tts.say(text)
            except Exception as exc:
                self.logger.error("sayAsync failed: %s", exc)
            finally:
                self._speaking = False
                self._emit()
        self._speaking = True
        self._emit()
        try:
            t = threading.Thread(target=_run)
            t.daemon = True
            t.start()
            return True
        except Exception as exc:
            self._speaking = False
            self.logger.error("sayAsync thread failed: %s", exc)
            return False

    def sayAnimated(self, text_with_tags, block=True, preempt=False):
        self._connect()

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

        if not anim_name and not clean_text:
            return True
        if not anim_name:
            return self.say(clean_text)
        if not clean_text:
            return self.playAnimation(anim_name, block, False)

        # 2. Lancer la parole et l'animation en parallèle
        say_future = self._tts.say(clean_text, _async=True) if self._tts else None
        with self._lock:
            self._speaking = True
            self._say_future = say_future
            self._emit()

        def _on_say_done(_fut):
            with self._lock:
                self._speaking = False
                self._say_future = None
                self._emit()
            if anim_name:
                duration = self.animations_durations.get(anim_name)
                if not duration or duration <= 0:
                    try:
                        self.logger.info(u"sayAnimated[<2.9]: Fin de la parole, arrêt de l'animation SANS durée '{}'".format(anim_name))
                        self.stopAnimation(anim_name)
                    except Exception:
                        pass
                else:
                    self.logger.info(u"sayAnimated[<2.9]: Fin de la parole, l'animation AVEC durée '{}' continue.".format(anim_name))

        try:
            if say_future:
                say_future.addCallback(_on_say_done)
        except Exception as e:
            self.logger.error(u"sayAnimated[<2.9]: Erreur lors de l'ajout du callback: {}".format(e))
            if block and say_future:
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
            try:
                if say_future:
                    say_future.wait()
                with self._lock: anim_thread_copy = self._anim_thread
                if anim_thread_copy:
                    anim_thread_copy.join(timeout=25.0)
            except Exception as e:
                self.logger.warning(u"sayAnimated[<2.9]: Le wait() a échoué: {}".format(e))

        return True

    def sayAnimatedIsRunning(self):
        return self._speaking

    def stopSayAnimated(self):
        self._connect()
        try:
            if self._as and hasattr(self._as, "stopAll"):
                self._as.stopAll()
            elif self._tts:
                if hasattr(self._tts, "stopAll"):
                    self._tts.stopAll()
            self._speaking = False
            self._emit()
            return True
        except Exception as exc:
            self.logger.error("stopSayAnimated failed: %s", exc)
            return False

    def resolveAnimationTags(self, text):
        """Remplace %%anim%% par ^start(animations/anim) en choisissant une anim connue."""
        self._connect()
        if not self.animations:
            self._scan_apps_and_animations()
        self.last_resolved_animation = None
        def replace_and_track(m):
            return self._reconstruct_animation_tag(m.group(1))
        processed_text = self.RE_ANIMATION_TAG.sub(replace_and_track, text or "")
        if self.last_resolved_animation is None:
            match = self.RE_START_TAG.search(processed_text)
            if match:
                self.last_resolved_animation = match.group(1)
        return processed_text

    def _reconstruct_animation_tag(self, animation_path):
        raw = animation_path.strip()
        if raw.startswith("animations/animations/"):
            raw = raw.replace("animations/animations/", "animations/", 1)
        chosen = None
        family_anims = self.animations_families.get('animations/' + raw)
        if family_anims:
            chosen = random.choice(family_anims)
        else:
            # Nettoyage pour éviter les doublons "animations/animations/"
            key = raw
            if key.startswith("animations/animations/"):
                key = key.replace("animations/animations/", "animations/", 1)
            elif not key.startswith("animations/"):
                key = "animations/" + key
            if key in self.animations:
                chosen = key
            else:
                # fallback: tenter suffixe
                for name in self.animations:
                    if name.endswith("/" + raw) or name.endswith("/" + key):
                        chosen = name
                        break
        if not chosen:
            self.logger.warning("[ANIM] Animation ou famille inconnue (2.1/2.5): '{}'".format(raw))
            chosen = 'animations/' + raw
        self.last_resolved_animation = chosen
        return "^start({})".format(chosen)

    # ---------------- Animations ----------------
    def playAnimation(self, anim, block=True, preempt=False):
        self._connect()
        if not self._bm or not anim:
            return False
        # Normaliser le nom (évite animations/animations/...)
        name = anim.strip()
        if name.startswith("animations/animations/"):
            name = name.replace("animations/animations/", "animations/", 1)
        elif not name.startswith("animations/"):
            name = "animations/" + name

        def resolve_behavior(target):
            """Si startBehavior échoue parce que le nom n'a pas le leaf (behavior_1), on tente de le compléter."""
            base = target.rstrip("/")
            try:
                installed = self._bm.getInstalledBehaviors()
            except Exception:
                installed = None
            if not installed:
                return target
            for beh in installed:
                if not isinstance(beh, basestring):
                    continue
                if beh == base:
                    return beh
                if beh.startswith(base + "/"):
                    self.logger.info("playAnimation: résolution %s -> %s", base, beh)
                    return beh
            return target

        name = resolve_behavior(name)
        with self._lock:
            try:
                if preempt and self._running_anim:
                    try:
                        self._bm.stopBehavior(self._running_anim)
                    except Exception:
                        pass
                self._bm.startBehavior(name)
                self._running_anim = name
                self._emit()
                if block:
                    while self._bm.isBehaviorRunning(name):
                        time.sleep(0.1)
                else:
                    # Thread de suivi pour nettoyer _running_anim
                    def _wait_anim(name):
                        try:
                            while self._bm.isBehaviorRunning(name):
                                time.sleep(0.1)
                        except Exception:
                            pass
                        finally:
                            with self._lock:
                                if self._running_anim == name:
                                    self._running_anim = None
                                    self._emit()
                    t = threading.Thread(target=_wait_anim, args=(anim,))
                    t.daemon = True
                    self._anim_thread = t
                    t.start()
                return True
            except Exception as exc:
                self.logger.error("playAnimation failed: %s", exc)
                return False
            finally:
                if block:
                    self._running_anim = None
                    self._emit()

    def animationIsRunning(self):
        self._connect()
        if self._bm and self._running_anim:
            try:
                return bool(self._bm.isBehaviorRunning(self._running_anim))
            except Exception:
                return False
        return False

    def stopAnimation(self, name=None):
        self._connect()
        target = name or self._running_anim
        if not target or not self._bm:
            return False
        try:
            self._bm.stopBehavior(target)
            self._running_anim = None
            self._emit()
            return True
        except Exception as exc:
            self.logger.error("stopAnimation failed: %s", exc)
            return False

    def getInstalledAnimations(self):
        """Retourne une liste de dicts {name,nature} pour compat UI apps/list."""
        self._connect()
        if not self._bm:
            return []
        try:
            if not self.animations:
                self._scan_apps_and_animations()
            return [{'name': a, 'nature': 'animation'} for a in self.animations]
        except Exception as exc:
            self.logger.error("getInstalledAnimations failed: %s", exc)
            return []

    def getApplications(self):
        """Pas de PackageManager ici; retourne la liste scannée si disponible."""
        if not self.applications:
            self._scan_apps_and_animations()
        processed = []
        for app in self.applications:
            if isinstance(app, dict):
                name = app.get('name')
                if name:
                    processed.append({'name': name, 'nature': app.get('nature', 'interactive')})
            elif isinstance(app, basestring):
                processed.append({'name': app, 'nature': 'interactive'})
        return processed

    def getAnimationFamilies(self):
        if not self.animations_families:
            self._scan_apps_and_animations()
        return list(self.animations_families.keys())

    def getAnimationDurations(self):
        if not self.animations_durations:
            self._scan_apps_and_animations()
        return dict(self.animations_durations)

    # ---------------- Think ----------------
    def think(self, anim, block=True, cancel_anims=False):
        self._connect()
        if not self._bm or not anim:
            return False
        name = anim.strip()
        if name.startswith("animations/animations/"):
            name = name.replace("animations/animations/", "animations/", 1)
        elif not name.startswith("animations/"):
            name = "animations/" + name
        with self._lock:
            try:
                if cancel_anims and self._running_anim:
                    try:
                        self._bm.stopBehavior(self._running_anim)
                    except Exception:
                        pass
                self._bm.startBehavior(name)
                self._running_think = name
                self._emit()
                if block:
                    while self._bm.isBehaviorRunning(name):
                        time.sleep(0.1)
                    self._running_think = None
                    self._emit()
                else:
                    def _wait_think(name):
                        try:
                            while self._bm.isBehaviorRunning(name):
                                time.sleep(0.1)
                        except Exception:
                            pass
                        finally:
                            with self._lock:
                                if self._running_think == name:
                                    self._running_think = None
                                    self._emit()
                    t = threading.Thread(target=_wait_think, args=(anim,))
                    t.daemon = True
                    self._think_thread = t
                    t.start()
                return True
            except Exception as exc:
                self.logger.error("think failed: %s", exc)
                return False
            finally:
                if block:
                    self._running_think = None
                    self._emit()

    def thinkIsRunning(self):
        self._connect()
        if self._bm and self._running_think:
            try:
                return bool(self._bm.isBehaviorRunning(self._running_think))
            except Exception:
                return False
        return False

    def stopThink(self, name=None):
        self._connect()
        target = name or self._running_think
        if not target or not self._bm:
            return False
        try:
            self._bm.stopBehavior(target)
            self._running_think = None
            self._emit()
            return True
        except Exception as exc:
            self.logger.error("stopThink failed: %s", exc)
            return False

    def startRandomThinkingGesture(self):
        self._connect()
        try:
            # Choisir directement dans la liste des animations contenant Think/Scratch
            thinking_anims = [a for a in self.animations if isinstance(a, basestring) and ("Think" in a or "Scratch" in a)]
            if not thinking_anims:
                self.logger.warning("Aucune animation 'Think' ou 'Scratch' trouvée pour le geste de réflexion.")
                return ""
            anim_to_run = random.choice(thinking_anims)
            if anim_to_run.startswith("animations/animations/"):
                anim_to_run = anim_to_run.replace("animations/animations/", "animations/", 1)
            self.logger.info(u"Lancement du geste de réflexion aléatoire: {}".format(anim_to_run))
            self.think(anim_to_run, False, True) # non-blocking, preemptive
            return anim_to_run
        except Exception as e:
            self.logger.error(u"Erreur lors du lancement du geste de réflexion: {}".format(e))
        return ""

    def getRunningAnimations(self):
        self._connect()
        try:
            running = self._bm.getRunningBehaviors() if self._bm else []
            return [b for b in running if isinstance(b, basestring) and b.startswith("animations/")]
        except Exception as e:
            self.logger.warning("Impossible de récupérer les comportements en cours: {}".format(e))
            return []

    def getAnimationStats(self):
        self._connect()
        # S'assurer que les listes sont chargées
        if not self.animations:
            self._scan_apps_and_animations()
        return {
            'animation_count': len(self.animations),
            'family_count': len(self.animations_families),
        }

    def getNaoqiVersion(self):
        self._connect()
        # Pas de version fournie par le lanceur ici; on renvoie '2.x'
        return os.environ.get('PEPPER_NAOQI_VERSION') or "2.x"

    # ---------------- State / misc ----------------
    def get_state(self):
        return {
            'speaking': bool(self._speaking),
            'animating': bool(self._running_anim),
            'thinking': bool(self._running_think),
        }

    def stopAll(self):
        ok = True
        ok = self.stopAnimation() and ok
        ok = self.stopThink() and ok
        ok = self.stopSayAnimated() and ok
        return ok

    def flushQueue(self):
        return 0

    def setBodyLanguageMode(self, mode):
        # Non supporté sur NAOqi 2.1/2.5 pour ce service simplifié
        return False


def main():
    logger = setup_logging()
    try:
        app = qi.Application(sys.argv)
        app.start()
    except Exception as e:
        logger.error("Impossible de démarrer l'application NAOqi: {}".format(e))
        sys.exit(1)
    
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
            try:
                app.session.unregisterService(sid)
            except Exception:
                pass
        app.stop()


if __name__ == '__main__':
    main()
