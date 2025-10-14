# -*- coding: utf-8 -*-
import faulthandler
faulthandler.enable() 
# pepper_poc_chat_main.py — NAOqi + OpenAI (STT + Chat + Vision) réactif

import sys, time, os, atexit, json, random, traceback, threading

from services.classSystem import bcolors, build_system_prompt_in_memory, load_config, handle_exception
from services.classLEDs import led_management_thread

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

def install_requirements(packages_to_install):
    import subprocess
    pip_executable = "/home/nao/.local/share/PackageManager/apps/python3nao/bin/pip3"
    if not os.path.exists(pip_executable):
        pip_executable = "pip"
    try:
        log("Mise à jour de pip...", level='info')
        subprocess.check_call([pip_executable, "install", "--upgrade", "pip"])
    except Exception as e:
        log("Impossible de mettre pip à jour: {}".format(e), level='warning', color=bcolors.WARNING)
    for req in packages_to_install:
        try:
            log("Installation de {}...".format(req), level='info')
            subprocess.check_call([pip_executable, "install", req])
        except subprocess.CalledProcessError as e:
            log("Erreur lors de l'installation de {}: {}".format(req, e), level='error', color=bcolors.FAIL)
            sys.exit(1)
        except Exception as e:
            log("Une erreur inattendue est survenue: {}".format(e), level='error', color=bcolors.FAIL)
            sys.exit(1)
    log("Dépendances installées.", level='info', color=bcolors.OKGREEN)
    try:
        import pkg_resources
        for req in packages_to_install:
            pkg_resources.require(req)
        log("Vérification des dépendances réussie.", level='info', color=bcolors.OKGREEN)
    except Exception as e:
        log("Erreur de vérification après installation: {}".format(e), level='error', color=bcolors.FAIL)
        sys.exit(1)

def check_requirements():
    import os
    try:
        import pkg_resources
    except ImportError:
        log("pkg_resources introuvable. Installation...", level='warning', color=bcolors.WARNING)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        requirements_path = os.path.join(script_dir, 'requirements.txt')
        with open(requirements_path, 'r') as f:
            requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        install_requirements(requirements)
        return
    script_dir = os.path.dirname(os.path.abspath(__file__))
    requirements_path = os.path.join(script_dir, 'requirements.txt')
    if not os.path.exists(requirements_path):
        log("requirements.txt introuvable.", level='warning', color=bcolors.WARNING)
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
        except Exception:
            missing_packages.append(req)
    if missing_packages:
        log("Dépendances manquantes. Installation...", level='warning', color=bcolors.WARNING)
        install_requirements(missing_packages)

threading.excepthook = handle_exception

def main():
    global CONFIG
    CONFIG = load_config(_logger)
    check_requirements()

    from services.classLEDs import PepperLEDs
    from services.classListener import Listener
    from services.classSpeak import Speaker
    from services.classASRFilters import is_noise_utterance, is_recent_duplicate
    from services.classAudioUtils import avgabs
    from services.classTablet import classTablet
    from services.classSystem import version as SysVersion
    from services.classSTT import STT
    from services.chatBots.chatGPT import chatGPT
    from services.classVision import Vision

    log(r"""
   .----.
  /      \
 |  () ()    PepperLife
  \   -  /    ==========
    """, level='info', color=bcolors.OKCYAN)

    IP = CONFIG['connection']['ip']
    PORT = CONFIG['connection']['port']
    BLACKLIST_STRICT = set(CONFIG['asr_filters']['blacklist_strict'])

    VAD_PROFILES = {
        1: (1.3, 1.05, 0.8), 2: (1.6, 1.1, 0.6), 3: (2.0, 1.2, 0.5),
        4: (2.5, 1.3, 0.4), 5: (3.0, 1.5, 0.3)
    }
    vad_level = CONFIG['audio'].get('vad_level', 3)
    start_mult, stop_mult, SILHOLD = VAD_PROFILES.get(vad_level, VAD_PROFILES[3])

    s = None
    try:
        import qi
        app = qi.Application(["PepperMain", "--qi-url=tcp://{}:{}".format(IP, PORT)])
        app.start()
        s = app.session
        log("[OK] NAOqi", level='info', color=bcolors.OKGREEN)
        robot_version = s.service("ALSystem").systemVersion()
        log("Version de NAOqi: {}".format(robot_version), level='info')

        # Afficher les stats d'animation
        try:
            pls = s.service("PepperLifeService")
            stats = pls.getAnimationStats()
            anim_count = stats.get('animation_count', 'N/A')
            fam_count = stats.get('family_count', 'N/A')
            log_msg = u"Statistiques animations : {} animations chargées, {} familles.".format(anim_count, fam_count)
            log(log_msg, color=bcolors.WARNING) # WARNING est jaune
        except Exception as e:
            log("Impossible de récupérer les stats d'animation: {}".format(e), level='warning')

    except Exception as e:
        log("Erreur de connexion à NAOqi: {}".format(e), level='error', color=bcolors.FAIL)
        sys.exit(1)

    al_dialog = s.service("ALDialog")

    chat_thread = None
    chat_stop_event = None
    led_thread = None
    led_stop_event = None
    CHAT_STATE = {'status': 'stopped'}

    autolife_stop_event = threading.Event()
    def autolife_watchdog(stop_event, robot_version_str):
        log("Démarrage du watchdog pour ALAutonomousLife et ALDialog.", level='info')
        
        is_29 = False
        try:
            version_parts = robot_version_str.split('.')
            major = int(version_parts[0])
            minor = int(version_parts[1])
            is_29 = (major == 2 and minor >= 9) or major > 2
        except Exception:
            pass # Garde is_29 à False en cas d'erreur de parsing

        try:
            autolife = s.service("ALAutonomousLife")
            while not stop_event.is_set():
                try:
                    is_gpt_running = chat_thread and chat_thread.is_alive()
                    
                    # Déterminer si ALDialog est actif en utilisant la méthode appropriée
                    is_dialog_active = False
                    try:
                        if is_29:
                            is_dialog_active = bool(al_dialog.getAllLoadedTopics())
                        else:
                            is_dialog_active = al_dialog.isListening()
                    except Exception as e:
                        log("Watchdog: Impossible de vérifier l'état de ALDialog: {}".format(e), level='debug')

                    if is_gpt_running:
                        if is_dialog_active and not is_29:
                            log("Watchdog: Le chatbot est actif, mais ALDialog semble tourner. Arrêt de ALDialog (uniquement pour < 2.9).", level='warning')
                            try:
                                al_dialog.stopDialog()
                            except Exception as e:
                                log("Watchdog: Erreur en tentant d'arrêter ALDialog: {}".format(e), level='debug')
                    else:
                        # Si le chatbot est inactif, ne redémarrer ALDialog que sur les anciennes versions
                        if not is_dialog_active and not is_29:
                            log("Watchdog: Le chatbot est inactif et ALDialog ne semble pas tourner. Redémarrage de ALDialog.", level='info')
                            try:
                                al_dialog.resetAll()
                                al_dialog.runDialog()
                            except Exception as e:
                                log("Watchdog: Erreur en tentant de redémarrer ALDialog: {}".format(e), level='error')
                except Exception as e:
                    log("Erreur dans le watchdog: {}".format(e), level='error')
                stop_event.wait(2.0)
        except Exception as e:
            log("Le service ALAutonomousLife n'est pas disponible: {}".format(e), level='error')    
    watchdog_thread = threading.Thread(target=autolife_watchdog, args=(autolife_stop_event, robot_version))
    watchdog_thread.daemon = True
    watchdog_thread.start()

    leds = PepperLEDs(s, _logger)
    cap = Listener(s, CONFIG['audio'], _logger)
    
    try:
        pls = s.service("PepperLifeService")
        anim_families = pls.getAnimationFamilies()
        base_prompt = chatGPT.get_base_prompt(config=CONFIG, logger=_logger)
        prompt_text, _ = build_system_prompt_in_memory(base_prompt, anim_families)
        SYSTEM_PROMPT = prompt_text
        log("[PROMPT] Prompt système généré avec {} familles d'animations.".format(len(anim_families)), level='debug')
    except Exception as e:
        log("[PROMPT] Génération dynamique ÉCHOUÉE: {}".format(e), level='error', color=bcolors.FAIL)
        SYSTEM_PROMPT = "Ton nom est Pepper."

    speaker = Speaker(s, _logger, CONFIG)
    vision_service = Vision(CONFIG, s, _logger)

    atexit.register(cap.close)
    atexit.register(vision_service.stop_camera)

    def run_chat_loop(stop_event, s):
        try:
            posture_service = s.service("ALRobotPosture")
            posture_service.goToPosture("Stand", 0.8)
        except Exception as e:
            log("Impossible de réinitialiser la posture: {}".format(e), level='warning')

        CHAT_STATE['status'] = 'starting'
        try:
            log("Démarrage du thread du chatbot GPT...", level='info')
            model_used = CONFIG.get('openai', {}).get('chat_model', 'gpt-4o-mini (default)')
            log("[Chat] Utilisation du modèle : {}".format(model_used), level='info', color=bcolors.OKCYAN)
            stt_service = STT(CONFIG, _logger)
            chat_service = chatGPT(CONFIG, system_prompt=SYSTEM_PROMPT, logger=_logger)
            api_key = CONFIG['openai'].get('api_key')
            if api_key: os.environ['OPENAI_API_KEY'] = api_key
            if not os.getenv("OPENAI_API_KEY"):
                log("Clé OpenAI absente.", level='error', color=bcolors.FAIL)
                speaker.say_quick("Clé OpenAI absente.")
                CHAT_STATE['status'] = 'error'
                return

            cap.start()
            vision_service.start_camera()
            cap.warmup(min_chunks=8, timeout=2.0)
            hist, hist_vision = [], []
            base = CONFIG['audio'].get('override_base_sensitivity')
            if not base:
                log("Calibration du bruit (2s)...", level='info')
                vals = []
                for _ in range(50):
                    with cap.lock:
                        audio_chunk = b"" if not cap.mon else b"".join(cap.mon[-8:])
                    vals.append(avgabs(audio_chunk))
                    time.sleep(0.04)
                base = int(sum(vals) / max(1, len(vals)))
                log("Calibration terminée. Bruit de base: {}".format(base), level='info')
            
            START = max(4, int(base * start_mult))
            STOP = max(3, int(base * stop_mult))

            def say_and_wait(text):
                speaker.say_quick(text)
                try:
                    pls = s.service("PepperLifeService")
                    start_wait = time.time()
                    while pls.get_state()['speaking']:
                        if stop_event.is_set() or (time.time() - start_wait > 15):
                            log("Timeout en attente de la fin de la parole.", level='warning')
                            break
                        time.sleep(0.1)
                except Exception as e:
                    log("Erreur en attente de la fin de la parole: {}".format(e), level='error')
                
                # Ajout d'un nettoyage explicite pour éviter l'auto-écoute
                log("Parole terminée, nettoyage des tampons audio et petite pause.", level='debug')
                with cap.lock:
                    cap.mon[:] = []
                    cap.pre[:] = []
                time.sleep(0.2) # Petite pause pour laisser le son se dissiper

            if CONFIG.get('animations', {}).get('enable_startup_animation', True):
                try:
                    log("Génération d'une phrase de démarrage pour le chatbot...", level='info')
                    startup_phrase, _ = chat_service.chat("tu viens de te reveiller dis quelque chose", [])
                    say_and_wait(startup_phrase)
                except Exception as e:
                    log("Impossible de générer la phrase de démarrage: {}".format(e), level='error')
                    say_and_wait("Je suis réveillé !")
            else:
                say_and_wait("Je suis prêt.")
            
            CHAT_STATE['status'] = 'running'

            try:
                pls = s.service("PepperLifeService")
            except Exception as e:
                log("Impossible de se connecter à PepperLifeService. Les états ne seront pas vérifiés. Erreur: {}".format(e), level='error')
                pls = None

            while not stop_event.is_set():
                asr_duration, gpt_duration, tts_duration = 0.0, 0.0, 0.0

                if pls:
                    try:
                        state = pls.get_state()
                        if not cap.is_micro_enabled() or state['speaking'] or state['animating']:
                            time.sleep(0.1)
                            continue
                    except Exception as e:
                        log("Erreur lors de la récupération de l'état de PepperLifeService: {}".format(e), level='warning')
                        time.sleep(0.5) # Pause en cas d'erreur
                        continue
                else: # Fallback si le service n'est pas dispo
                    if not cap.is_micro_enabled() or cap.is_speaking():
                        time.sleep(0.1)
                        continue

                with cap.lock:
                    audio_chunk = b"" if not cap.mon else b"".join(cap.mon[-8:])
                vol = avgabs(audio_chunk)
                if vol < START:
                    time.sleep(0.05)
                    continue

                thinking_anim_name = ""
                if CONFIG.get('animations', {}).get('enable_thinking_gesture', True):
                    try:
                        pls = s.service("PepperLifeService")
                        thinking_anim_name = pls.startRandomThinkingGesture()
                    except Exception as e:
                        log("[ANIM] Échec du démarrage de l'action de réflexion via le service: {}".format(e), level='warning')

                rep = None
                try:
                    cap.start_recording()
                    t0 = time.time(); last = t0
                    while time.time() - t0 < 5.0:
                        with cap.lock:
                            recent = b"" if not cap.mon else b"".join(cap.mon[-3:])
                        fr = recent[-320:] if len(recent) >= 320 else recent
                        e = avgabs(fr)
                        if e >= STOP: last = time.time()
                        if time.time() - last > SILHOLD: break
                        time.sleep(0.02)
                    wav = cap.stop_recording(STOP)

                    if wav:
                        t_before_stt = time.time()
                        txt = stt_service.stt(wav)
                        t_after_stt = time.time()
                        asr_duration = t_after_stt - t_before_stt
                        log("[ASR] " + str(txt), level='info')

                        if txt and not is_noise_utterance(txt, BLACKLIST_STRICT) and not is_recent_duplicate(txt):
                            t_before_chat = time.time()
                            if vision_service._utterance_triggers_vision(txt.lower()):
                                png_bytes = vision_service.get_png()
                                if png_bytes:
                                    _tablet_ui.set_last_capture(png_bytes)
                                    _tablet_ui.show_last_capture_on_tablet()
                                    rep = vision_service.vision_chat(txt, png_bytes, hist_vision)
                                    hist_vision.extend([("user", txt), ("assistant", rep)])
                                    hist_vision = hist_vision[-6:]
                                else:
                                    rep = "Je n'ai pas réussi à prendre de photo."
                            else:
                                hist.append(("user", txt))
                                rep, raw_rep = chat_service.chat(txt, hist[:-1])
                                log("[GPT] {}".format(rep), level='info', color=bcolors.OKGREEN)
                                log("[GPT_FULL] {}".format(repr(raw_rep)), level='debug')
                                hist.append(("assistant", rep))
                                hist = hist[-8:]
                            t_after_chat = time.time()
                            gpt_duration = t_after_chat - t_before_chat
                except Exception as e:
                    log("[ERR] " + str(e), level='error', color=bcolors.FAIL)
                    rep = "Petit pépin réseau, on réessaie."
                finally:
                    if thinking_anim_name:
                        try:
                            pls = s.service("PepperLifeService")
                            pls.stopThink(thinking_anim_name)
                        except Exception as e:
                            log("[ANIM] Impossible d'arrêter la réflexion: {}".format(e), level='warning')

                if rep:
                    t_before_say_quick = time.time()
                    speaker.say_quick(rep)
                    
                    try:
                        pls = s.service("PepperLifeService")
                        start_wait = time.time()
                        while pls.get_state()['speaking']:
                            if stop_event.is_set() or (time.time() - start_wait > 15):
                                log("Timeout en attente de la fin de la parole.", level='warning')
                                break
                            time.sleep(0.1)
                    except Exception as e:
                        log("Erreur en attente de la fin de la parole: {}".format(e), level='error')

                    t_after_say_quick = time.time()
                    tts_duration = t_after_say_quick - t_before_say_quick
                    log("Durée du chat : ASR {:.2f}s / GPT {:.2f}s / TTS {:.2f}s".format(asr_duration, gpt_duration, tts_duration), level='info', color=bcolors.OKCYAN)
        finally:
            log("Arrêt du thread du chatbot.", level='info')
            if CHAT_STATE['status'] != 'error':
                CHAT_STATE['status'] = 'stopped'
            cap.stop()

    def start_chat(mode='gpt'):
        nonlocal chat_thread, chat_stop_event, led_thread, led_stop_event
        if chat_thread and chat_thread.is_alive():
            log("Un chat est déjà en cours.", level='warning')
            stop_chat()
        
        if mode == 'gpt':
            log("Arrêt de ALDialog pour le mode GPT.", level='info')
            try: al_dialog.stopDialog()
            except Exception as e: log("Erreur lors de l'arrêt de ALDialog: {}".format(e), level='error')
            
            led_stop_event = threading.Event()
            led_thread = threading.Thread(target=led_management_thread, args=(led_stop_event, s, leds, cap))
            led_thread.daemon = True
            led_thread.start()

            chat_stop_event = threading.Event()
            chat_thread = threading.Thread(target=run_chat_loop, args=(chat_stop_event, s))
            chat_thread.daemon = True
            chat_thread.start()
        else:
            log("Mode 'basic' activé.", level='info')
            try:
                al_dialog.resetAll()
                al_dialog.runDialog()
            except Exception as e: log("Erreur au démarrage de ALDialog: {}".format(e), level='error')
            speaker.say_quick("Mode de base activé.")

    def stop_chat():
        nonlocal chat_thread, chat_stop_event, led_thread, led_stop_event
        if led_thread and led_thread.is_alive():
            log("Arrêt du thread de gestion des LEDs...", level='info')
            led_stop_event.set()
            led_thread.join(timeout=2)
        led_thread = None

        if chat_thread and chat_thread.is_alive():
            log("Demande d'arrêt du thread du chatbot...", level='info')
            chat_stop_event.set()
            chat_thread.join(timeout=5)
        chat_thread = None
        
        CHAT_STATE['status'] = 'stopped'
        log("Chatbot arrêté. Passage en mode de base.", level='info')
        try:
            al_dialog.resetAll()
            al_dialog.runDialog()
        except Exception as e: log("Erreur au démarrage de ALDialog: {}".format(e), level='error')
        speaker.say_quick("Le chatbot est arrêté.")

    def get_chat_status():
        is_running = chat_thread and chat_thread.is_alive()
        current_mode = 'gpt' if is_running else 'basic'
        return {'mode': current_mode, 'is_running': is_running}

    def get_detailed_chat_status():
        return CHAT_STATE

    def toggle_micro():
        is_enabled = cap.toggle_micro()
        if not is_enabled:
            leds.idle()
        return is_enabled

    _tablet_ui = classTablet(
        session=s, logger=_logger, port=8088, version_provider=SysVersion.get,
        mic_toggle_callback=toggle_micro, listener=cap, speaker=speaker, vision_service=vision_service,
        start_chat_callback=start_chat, stop_chat_callback=stop_chat, get_chat_status_callback=get_chat_status,
        get_detailed_chat_status_callback=get_detailed_chat_status
    )
    _tablet_ui.start(show=True)

    # beh.boot() # No longer needed as it's part of the service
    if CONFIG.get('boot', {}).get('boot_vieAutonome', True):
        try: s.service("ALAutonomousLife").setState("interactive")
        except Exception as e: log("Vie autonome échouée: {}".format(e), level='error')
    if CONFIG.get('boot', {}).get('boot_reveille', True):
        try: s.service("ALMotion").wakeUp()
        except Exception as e: log("Réveil échoué: {}".format(e), level='error')

    if CONFIG.get('boot', {}).get('start_chatbot_on_boot', False):
        start_chat('gpt')
    else:
        log("Chatbot non démarré. ALDialog sera activé après la phrase de démarrage.", level='info', color=bcolors.OKGREEN)
        
        speaker.say_quick("Je suis prêt.")

        try:
            pls = s.service("PepperLifeService")
            start_wait = time.time()
            while pls.get_state()['speaking']:
                if (time.time() - start_wait > 15):
                    log("Timeout en attente de la fin de la parole.", level='warning')
                    break
                time.sleep(0.1)
        except Exception as e:
            log("Erreur en attente de la fin de la parole: {}".format(e), level='error')

        try:
            log("Activation de ALDialog.", level='info')
            al_dialog.resetAll()
            al_dialog.runDialog()
        except Exception as e:
            log("Erreur au démarrage de ALDialog: {}".format(e), level='error')

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("\nCtrl+C détecté. Arrêt...", level='info')
    finally:
        log("Arrêt des services...", level='info')
        autolife_stop_event.set()
        stop_chat()

if __name__ == "__main__":
    main()
