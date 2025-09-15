# -*- coding: utf-8 -*-
# pepper_poc_chat_main.py — NAOqi + OpenAI (STT + Chat + Vision) réactif
# - Écoute locale via ALAudioDevice (16 kHz mono) + endpointing court
# - STT OpenAI (gpt-4o-mini-transcribe -> fallback whisper-1)
# - Chat court persona Pepper + balises d’actions NAOqi (robot_actions.py)
# - LEDs gérées dans leds_manager.py (oreilles ON quand il écoute, OFF sinon)
# - TTS asynchrone: parle pendant que le robot bouge
# - Vision unifiée: prompt configurable dans config.json (comme les moteurs)

import sys, time, os, atexit, json

from services.classSystem import bcolors

CONFIG = {
    "log": { "verbosity": 2 }
}

def log(msg, level='info', color=None):
    verbosity_map = {'error': 0, 'warning': 1, 'info': 2, 'debug': 3}
    level_num = verbosity_map.get(level, 2)
    if CONFIG['log']['verbosity'] >= level_num:
        if color:
            print(color + msg + bcolors.ENDC)
        else:
            print(msg)

def _logger(msg, **kwargs):
    try:
        log(msg, **kwargs)
    except Exception:
        print(msg)

def load_config():
    global CONFIG

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, 'config.json')
    default_config_path = os.path.join(script_dir, 'config.json.default')

    if not os.path.exists(config_path):
        log("Le fichier config.json n'existe pas, création à partir de config.json.default...", level='warning', color=bcolors.WARNING)
        with open(default_config_path, 'r', encoding='utf-8') as f:
            default_config_content = f.read()
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(default_config_content)

    with open(default_config_path, 'r', encoding='utf-8') as f:
        default_config = json.load(f)

    with open(config_path, 'r', encoding='utf-8') as f:
        user_config = json.load(f)

    # Vérifier les clés manquantes (merge superficiel + sous-dictionnaires)
    updated = False
    for key, value in default_config.items():
        if key not in user_config:
            log(f"Clé manquante '{key}' dans config.json, ajout...", level='warning', color=bcolors.WARNING)
            user_config[key] = value
            updated = True
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if sub_key not in user_config[key]:
                    log(f"Clé manquante '{key}.{sub_key}' dans config.json, ajout...", level='warning', color=bcolors.WARNING)
                    user_config[key][sub_key] = sub_value
                    updated = True

    if updated:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(user_config, f, indent=2, ensure_ascii=False)

    CONFIG = user_config

def install_requirements(packages_to_install):
    import subprocess
    
    pip_executable = "/home/nao/.local/share/PackageManager/apps/python3nao/bin/pip3"
    if not os.path.exists(pip_executable):
        pip_executable = "pip" # Fallback for non-pepper env

    for req in packages_to_install:
        try:
            log(f"Installation de {req}...", level='info')
            subprocess.check_call([pip_executable, "install", req])
        except subprocess.CalledProcessError as e:
            log(f"Erreur lors de l'installation de {req}: {e}", level='error', color=bcolors.FAIL)
            log("Veuillez installer manuellement les dépendances.", level='error', color=bcolors.FAIL)
            sys.exit(1)
        except Exception as e:
            log(f"Une erreur inattendue est survenue lors de l'installation de {req}: {e}", level='error', color=bcolors.FAIL)
            sys.exit(1)

    log("Toutes les dépendances manquantes ont été installées.", level='info', color=bcolors.OKGREEN)
    # Re-vérification après installation
    try:
        import pkg_resources
        for req in packages_to_install:
            pkg_resources.require(req)
        log("Vérification des dépendances réussie après installation.", level='info', color=bcolors.OKGREEN)
    except (pkg_resources.DistributionNotFound, pkg_resources.VersionConflict) as e:
        log(f"Erreur de vérification après installation: {e}", level='error', color=bcolors.FAIL)
        sys.exit(1)

def check_requirements():
    try:
        import pkg_resources
    except ImportError:
        log("Le module 'pkg_resources' est introuvable. Tentative d'installation des dépendances...", level='warning', color=bcolors.WARNING)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        requirements_path = os.path.join(script_dir, 'requirements.txt')
        with open(requirements_path, 'r') as f:
            requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        install_requirements(requirements)
        return

    script_dir = os.path.dirname(os.path.abspath(__file__))
    requirements_path = os.path.join(script_dir, 'requirements.txt')

    if not os.path.exists(requirements_path):
        log("Le fichier requirements.txt est introuvable.", level='warning', color=bcolors.WARNING)
        return

    with open(requirements_path, 'r') as f:
        requirements = f.readlines()

    missing_packages = []
    for req in requirements:
        req = req.strip()
        if not req or req.startswith('#'):
            continue
        try:
            pkg_resources.require(req)
        except (pkg_resources.DistributionNotFound, pkg_resources.VersionConflict):
            missing_packages.append(req)
        except Exception as e:
            log(f"Erreur lors de la vérification de {req}: {e}", level='error', color=bcolors.FAIL)

    if missing_packages:
        log("Certaines dépendances sont manquantes ou en conflit. Tentative d'installation...", level='warning', color=bcolors.WARNING)
        install_requirements(missing_packages)

def main():
    check_requirements()
    
    from services.classLEDs import PepperLEDs
    from services.classRobotBehavior import BehaviorManager
    from services.classListener import Listener
    from services.classSpeak import Speaker
    from services.classASRFilters import is_noise_utterance, is_recent_duplicate
    from services.classAudioUtils import avgabs

    from services.classTablet import classTablet
    from services.classSystem import version as SysVersion
    from services.classSTT import STT
    from services.classChat import Chat
    from services.classVision import Vision
    
    load_config()

    log("Lancement de pepperLife", level='info', color=bcolors.OKCYAN)

    IP = CONFIG['connection']['ip']
    PORT = CONFIG['connection']['port']
    STT_MODEL = CONFIG['openai']['stt_model']
    CHAT_MODEL = CONFIG['openai']['chat_model']
    SYSTEM_PROMPT = CONFIG['openai']['system_prompt']
    SILHOLD = CONFIG['audio']['silhold']
    FAST_FRAMES = CONFIG['audio']['fast_frames']
    MIN_UTT = CONFIG['audio']['min_utt']
    CALIB = CONFIG['audio']['calib']
    BLACKLIST_STRICT = set(CONFIG['asr_filters']['blacklist_strict'])

    s = None
    try:
        import qi
        app = qi.Application(["PepperMain", "--qi-url=tcp://%s:%d" % (IP, PORT)])
        app.start()
        s = app.session
        log("[OK] NAOqi", level='info', color=bcolors.OKGREEN)

        system_service = s.service("ALSystem")
        robot_version = system_service.systemVersion()
        # Désactiver sorties autonomes ALDialog
        try:
            dialog = s.service("ALDialog")
            try: dialog.setSolitaryMode(False)
            except: pass
            try: dialog.setSpeakingMovementEnabled(True)
            except: pass
            try: dialog.stopDialog()
            except: pass
        except Exception as e:
            log("ALDialog non disponible: %s" % e, level='warning')

        log(f"Version de NAOqi: {robot_version}", level='info')

    except ImportError as e:
        log(f"Le module 'qi' est introuvable: {e}", level='error', color=bcolors.FAIL)
        sys.exit(2)
    except Exception as e:
        log(f"Erreur lors de la connexion à NAOqi ou à l'un de ses services: {e}", level='error', color=bcolors.FAIL)
        if s is None:
            raise Exception("Impossible de se connecter à NAOqi.")
        else:
            raise Exception("Impossible de se connecter à un service NAOqi.")

    leds = PepperLEDs(s, _logger)
    cap = Listener(s, CONFIG['audio'], _logger); atexit.register(cap.close)
    
    def toggle_micro():
        is_enabled = cap.toggle_micro()
        if not is_enabled:
            leds.idle()
        return is_enabled

    _tablet_ui = classTablet(
        session=s,
        logger=_logger,
        port=8088,
        version_provider=SysVersion.get,
        mic_toggle_callback=toggle_micro,
        listener=cap
    )
    _tablet_ui.start(show=True)

    beh  = BehaviorManager(s, _logger, default_speed=0.5)
    beh.boot()

    stt_service = STT(CONFIG)
    chat_service = Chat(CONFIG)
    vision_service = Vision(CONFIG, s, _logger)
    tts  = s.service("ALTextToSpeech"); tts.setLanguage("French");
    speaker = Speaker(tts, leds, cap, beh)

    api_key = CONFIG['openai'].get('api_key')
    if api_key:
        os.environ['OPENAI_API_KEY'] = api_key

    if not os.getenv("OPENAI_API_KEY"):
        log("Clé OpenAI absente. Veuillez la définir dans config.json ou via la variable d'environnement OPENAI_API_KEY.", level='error', color=bcolors.FAIL)
        tts.say("Clé OpenAI absente."); return

    leds.idle()

    vision_service.start_camera()
    _tablet_ui.cam = vision_service
    atexit.register(vision_service.stop_camera)

    cap.warmup(min_chunks=8, timeout=2.0)

    hist = []            # historique chat texte
    hist_vision = []     # historique dédié à la vision (optionnel)

    # Calibration bruit
    log("Calibration du bruit...", level='info')
    t0 = time.time(); vals=[]
    while time.time() - t0 < CALIB:
        time.sleep(0.04)
        vals.append(avgabs(b"".join(cap.mon[-8:]) if cap.mon else b""))
    base  = int(sum(vals)/max(1,len(vals)))
    START = max(4, int(base*1.6))
    STOP  = max(3, int(base*0.9))
    log("[VAD] base=%d START=%d STOP=%d"%(base,START,STOP), level='debug')

    # Boot options
    if CONFIG.get('boot', {}).get('boot_vieAutonome', True):
        try:
            life_service = s.service("ALAutonomousLife")
            if life_service.getState() == "disabled":
                life_service.setState("interactive")
        except Exception as e:
            log("Impossible de définir la vie autonome: %s" % e, level='error')

    if CONFIG.get('boot', {}).get('boot_reveille', True):
        try:
            motion_service = s.service("ALMotion")
            if not motion_service.robotIsWakeUp():
                motion_service.wakeUp()
        except Exception as e:
            log("Impossible de réveiller le robot: %s" % e, level='error')

    speaker.say_quick("Je suis réveillé !")


    # --- Tracking / BasicAwareness au démarrage ---
    try:
        ba = s.service("ALBasicAwareness")
        # Modes utiles : "Head", "BodyRotation", "WholeBody"
        ba.setTrackingMode("Head")
        # Niveaux possibles : "Unengaged", "SemiEngaged", "FullyEngaged"
        ba.setEngagementMode("FullyEngaged")
        # Active la détection (faces, sons, mouvement, toucher)
        ba.startAwareness()
        log("[BA] BasicAwareness démarré (tracking=Head, engagement=FullyEngaged)", level='info')
    except Exception as e:
        log("[BA] Impossible de démarrer BasicAwareness: %s" % e, level='warning')



    # Boucle: listen → record → STT → (vision ? chat) → TTS/Actions
    while True:
        # départ écoute
        started=False; since=None; t_wait=time.time()
        while time.time()-t_wait < 5.0:
            if cap.is_speaking():
                time.sleep(0.05)
                continue

            vol = avgabs(b"".join(cap.mon[-8:]) if cap.mon else b"")
            if vol >= START:
                if since is None:
                    since = time.time()
                elif time.time()-since >= 0.06:
                    started=True; break
            else:
                since=None
            time.sleep(0.03)
        if not started: continue

        if not cap.is_micro_enabled():
            continue

        if cap.is_speaking():
            continue

        # enregistrement + endpointing agressif
        cap.start(); t0=time.time(); last=t0; low=0
        leds.listening_recording()
        while time.time()-t0 < 3.0:
            recent = b"".join(cap.mon[-3:]) if cap.mon else b""
            fr = recent[-320:] if len(recent)>=320 else recent
            e = avgabs(fr)
            if e >= STOP: last=time.time(); low=0
            else: low+=1
            if time.time()-last >= SILHOLD: break
            if low >= FAST_FRAMES and time.time()-t0 >= MIN_UTT: break
            time.sleep(0.01)

        wav = cap.stop(STOP)
        if not wav: continue

        # STT -> Routeur (vision/chat) -> parler & bouger
        try:
            txt = stt_service.stt(wav); log("[ASR] " + str(txt), level='info')
            if not txt:
                continue

            txt_lower = txt.lower()

            # ----- Commandes explicites d'affichage caméra (optionnel) -----
            if "affiche la caméra" in txt_lower or "affiche le flux" in txt_lower:
                log("[VISION] Affichage du flux vidéo...", level='info')
                _tablet_ui.show_video_feed()
                speaker.say_quick("Voilà ce que je vois en direct.")
                continue

            # ----- Déclencheur générique vision (configurable) -----
            if vision_service._utterance_triggers_vision(txt_lower):
                log("[VISION] Déclenchement par triggers-config.", level='info')
                png_bytes = vision_service.get_png()
                _tablet_ui.set_last_capture(png_bytes)
                _tablet_ui.show_last_capture_on_tablet()

                if not png_bytes:
                    speaker.say_quick("Je n'ai pas réussi à prendre de photo.")
                    continue

                leds.processing()
                log("Appel à vision_chat en cours...", level='info')
                rep = vision_service.vision_chat(txt, png_bytes, hist_vision)
                log(f"Retour de vision_chat. Réponse: '{rep}'", level='info')
                log("[GPT-V] " + rep, level='info', color=bcolors.OKCYAN)
                speaker.say_quick(rep)
                # Historique vision (nettoyé des marqueurs éventuels)
                hist_vision.append(("user", txt))
                hist_vision.append(("assistant", rep))
                # on garde court
                hist_vision[:] = hist_vision[-6:]
                continue

            # ----- Filtrage bruit / doublons -----
            if is_noise_utterance(txt, BLACKLIST_STRICT) or is_recent_duplicate(txt):
                log("[ASR] filtré (bruit/blacklist): " + txt, level='info', color=bcolors.WARNING)
                leds.idle()
                continue

            # ----- Chat texte standard -----
            hist.append(("user", txt)); hist = hist[-8:]
            leds.processing()
            rep = chat_service.chat(txt, hist[:-1]); log("[GPT] " + rep, level='info', color=bcolors.OKCYAN)
            speaker.say_quick(rep)
            hist.append(("assistant", rep))
            time.sleep(0.5)

        except Exception as e:
            log("[ERR] " + str(e), level='error', color=bcolors.FAIL)
            speaker.say_quick("Petit pépin réseau, on réessaie.")


if __name__ == "__main__":
    main()
