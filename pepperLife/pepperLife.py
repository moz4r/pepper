# -*- coding: utf-8 -*-
import faulthandler
faulthandler.enable() 
# pepper_poc_chat_main.py — NAOqi + OpenAI (STT + Chat + Vision) réactif

import sys, time, os, atexit, json, threading

from services.classSystem import bcolors, build_system_prompt_in_memory, load_config, handle_exception
from services.classLEDs import PepperLEDs, led_management_thread

# Forcer l'I/O Python en UTF-8 (évite les erreurs d'encodage sur NAOqi 2.5)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

CONFIG = {
    "log": { "verbosity": 2 }
}

def _get_env_naoqi_version():
    version = os.environ.get('PEPPER_NAOQI_VERSION')
    is_flag = os.environ.get('PEPPER_NAOQI_IS29')
    if version:
        is_29 = (is_flag == '1') if is_flag in ('0', '1') else False
        return version, is_29
    return None, False

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
    script_dir = os.path.dirname(os.path.abspath(__file__))
    naoqi_version, _ = _get_env_naoqi_version()

    def _ensure_executable(path):
        try:
            st = os.stat(path)
            if not (st.st_mode & 0o111):
                os.chmod(path, st.st_mode | 0o755)
        except Exception:
            pass

    def _runner_env():
        # Env minimal pour laisser runpy3.sh poser ses propres variables (LD_LIBRARY_PATH, etc.)
        env = {
            "PIP_SKIP_UNAME": "1",
            "HOME": os.environ.get("HOME", "/home/nao"),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        return env

    def _ensure_local_site(path):
        if path and os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)
            try:
                import site
                site.addsitedir(path)
            except Exception:
                pass

    # Cas NAOqi 2.1 : utiliser runpy3 de python3nao + PIP_SKIP_UNAME + target local
    if naoqi_version and naoqi_version.startswith("2.1"):
        runner = "/home/nao/.local/share/PackageManager/apps/python3nao/bin/runpy3.sh"
        if os.path.exists(runner):
            _ensure_executable(runner)
        else:
            runner = None
        target_dir = os.path.join(script_dir, "lib", "python3.9", "site-packages")
        if not runner:
            log("runpy3.sh (python3nao) introuvable, fallback pip classique.", level='warning', color=bcolors.WARNING)
        else:
            env = _runner_env()
            if not os.path.isdir(target_dir):
                try:
                    os.makedirs(target_dir)
                except Exception:
                    pass
            _ensure_local_site(target_dir)  # s'assurer que le target local est utilisable juste après création
            try:
                log("Mise à jour de pip (NAOqi 2.1)...", level='info')
                subprocess.check_call([runner, "-m", "pip", "install", "--upgrade", "--no-cache-dir", "pip"], env=env)
            except Exception as e:
                log("Impossible de mettre pip à jour (continu): {}".format(e), level='warning', color=bcolors.WARNING)
            for req in packages_to_install:
                try:
                    log("Installation de {} (target local)...".format(req), level='info')
                    subprocess.check_call([runner, "-m", "pip", "install", "--upgrade", "--no-cache-dir", "--target", target_dir, req], env=env)
                except subprocess.CalledProcessError as e:
                    log("Erreur lors de l'installation de {}: {}".format(req, e), level='error', color=bcolors.FAIL)
                    sys.exit(1)
                except Exception as e:
                    log("Une erreur inattendue est survenue: {}".format(e), level='error', color=bcolors.FAIL)
                    sys.exit(1)
            _ensure_local_site(target_dir)
            log("Dépendances installées (NAOqi 2.1).", level='info', color=bcolors.OKGREEN)
            return

    # Cas NAOqi 2.5 : utiliser runpy3 packagé dans pepperlife + PIP_SKIP_UNAME + target local
    if naoqi_version and naoqi_version.startswith("2.5"):
        runner = "/home/nao/.local/share/PackageManager/apps/pepperlife/bin/runpy3.sh"
        if os.path.exists(runner):
            _ensure_executable(runner)
        else:
            runner = None
        target_dir = os.path.join(script_dir, "lib", "python3.9", "site-packages")
        if not runner:
            log("runpy3.sh (pepperlife) introuvable, fallback pip classique.", level='warning', color=bcolors.WARNING)
        else:
            env = _runner_env()
            if not os.path.isdir(target_dir):
                try:
                    os.makedirs(target_dir)
                except Exception:
                    pass
            _ensure_local_site(target_dir)  # assure la dispo immédiate du site-packages local après création
            try:
                log("Mise à jour de pip (NAOqi 2.5)...", level='info')
                subprocess.check_call([runner, "-m", "pip", "install", "--upgrade", "pip"], env=env)
            except Exception as e:
                log("Impossible de mettre pip à jour: {}".format(e), level='warning', color=bcolors.WARNING)
            for req in packages_to_install:
                try:
                    log("Installation de {} (target local)...".format(req), level='info')
                    subprocess.check_call([runner, "-m", "pip", "install", "--upgrade", "--target", target_dir, req], env=env)
                except subprocess.CalledProcessError as e:
                    log("Erreur lors de l'installation de {}: {}".format(req, e), level='error', color=bcolors.FAIL)
                    sys.exit(1)
                except Exception as e:
                    log("Une erreur inattendue est survenue: {}".format(e), level='error', color=bcolors.FAIL)
                    sys.exit(1)
            _ensure_local_site(target_dir)
            log("Dépendances installées (NAOqi 2.5).", level='info', color=bcolors.OKGREEN)
            return

    # Cas par défaut (NAOqi 2.9+) : pip3 standard
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
            subprocess.check_call([pip_executable, "install", "--upgrade", req])
        except subprocess.CalledProcessError as e:
            log("Erreur lors de l'installation de {}: {}".format(req, e), level='error', color=bcolors.FAIL)
            sys.exit(1)
        except Exception as e:
            log("Une erreur inattendue est survenue: {}".format(e), level='error', color=bcolors.FAIL)
            sys.exit(1)
    log("Dépendances installées.", level='info', color=bcolors.OKGREEN)
    try:
        import importlib
        import pkg_resources
        pkg_resources = importlib.reload(pkg_resources)
        fresh_working_set = pkg_resources.WorkingSet()
        for req in packages_to_install:
            fresh_working_set.require(req)
        log("Vérification des dépendances réussie.", level='info', color=bcolors.OKGREEN)
    except Exception as e:
        log("Erreur de vérification après installation: {}".format(e), level='error', color=bcolors.FAIL)
        sys.exit(1)

def check_requirements():
    import os
    import importlib
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
    # S'assurer que les site-packages locaux (2.1/2.5) sont dans sys.path
    local_site = os.path.join(script_dir, "lib", "python3.9", "site-packages")
    if os.path.isdir(local_site) and local_site not in sys.path:
        sys.path.insert(0, local_site)
        try:
            import site
            site.addsitedir(local_site)
        except Exception:
            pass
        try:
            pkg_resources = importlib.reload(pkg_resources)
            _, is_29 = _get_env_naoqi_version()
            if not is_29:
                fresh_ws = pkg_resources.WorkingSet([local_site])
                pkg_resources._initialize_master_working_set()  # refresh default
        except Exception:
            pass

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

    from services.chatBots.chatGPT import chatGPT
    from services.chatBots.ollama import ChatOllama
    from services.classChat import ChatManager

    from services.classListener import Listener
    from services.classSpeak import Speaker
    from services.classTablet import classTablet
    from services.classSystem import version as SysVersion
    from services.classVision import Vision

    log(r"""
   .----.
  /      \
 |  () ()    PepperLife
  \   -  /    ==========
    """, level='info', color=bcolors.OKCYAN)

    IP = CONFIG['connection']['ip']
    PORT = CONFIG['connection']['port']
    s = None
    try:
        import qi
        app = qi.Application(["PepperMain", "--qi-url=tcp://{}:{}".format(IP, PORT)])
        app.start()
        s = app.session
        log("[OK] NAOqi", level='info', color=bcolors.OKGREEN)
        robot_version, is_29_version = _get_env_naoqi_version()
        if not robot_version:
            robot_version = "unknown"
        log("Version NAOqi (depuis le lanceur): {} (>=2.9: {})".format(
            robot_version, 'oui' if is_29_version else 'non'), level='info')

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
    try:
        al_memory = s.service("ALMemory")
    except Exception as e:
        log("Impossible de récupérer ALMemory: {}".format(e), level='warning')
        al_memory = None
    chat_manager = None

    autolife_stop_event = threading.Event()
    aldialog_watchdog_pause = threading.Event()
    def autolife_watchdog(stop_event, is_29_version):
        log("Démarrage du watchdog pour ALAutonomousLife et ALDialog.", level='info')

        def _mem_flag_as_bool(value):
            # ALMemory peut renvoyer 0/1, bool, ou des chaînes "0"/"1" ; normaliser pour éviter les faux positifs
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return value != 0
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in ('', '0', 'false', 'none', 'no', 'non', 'off'):
                    return False
                return True
            return bool(value)

        try:
            autolife = s.service("ALAutonomousLife")
            last_dialog_restart = 0.0
            last_dialog_stop = 0.0
            while not stop_event.is_set():
                if aldialog_watchdog_pause.is_set():
                    stop_event.wait(1.0)
                    continue
                try:
                    is_gpt_running = chat_manager.is_running() if chat_manager else False
                    
                    # Déterminer si ALDialog est actif en utilisant la méthode appropriée
                    is_dialog_active = False
                    status_checked = False
                    try:
                        if al_memory:
                            mem_flag = al_memory.getData("Dialog/IsStarted")
                            is_dialog_active = _mem_flag_as_bool(mem_flag)
                            status_checked = True
                            log("Watchdog: ALMemory Dialog/IsStarted (brut) -> {} | interprété -> {}".format(mem_flag, is_dialog_active), level='debug')
                    except Exception as e:
                        log("Watchdog: Impossible de vérifier l'état de ALDialog via ALMemory: {}".format(e), level='debug')

                    if not status_checked:
                        try:
                            status_info = None
                            if hasattr(al_dialog, 'getStatus'):
                                status_info = al_dialog.getStatus()
                                log("Watchdog: ALDialog.getStatus() -> {}".format(status_info), level='debug')
                            state_label = None
                            if isinstance(status_info, dict):
                                state_label = status_info.get('state') or status_info.get('status')
                            elif isinstance(status_info, (list, tuple)) and status_info:
                                state_label = status_info[0]
                            elif isinstance(status_info, str):
                                state_label = status_info
                            if isinstance(state_label, str):
                                lowered = state_label.lower()
                                if any(token in lowered for token in ('run', 'running', 'actif', 'active', 'start', 'listening')):
                                    is_dialog_active = True
                            if not is_dialog_active and hasattr(al_dialog, 'getAllLoadedTopics'):
                                try:
                                    topics = al_dialog.getAllLoadedTopics()
                                    log("Watchdog: ALDialog.getAllLoadedTopics() -> {}".format(topics), level='debug')
                                except Exception:
                                    pass
                            if not is_dialog_active and hasattr(al_dialog, 'isDialogRunning'):
                                try:
                                    is_dialog_active = bool(al_dialog.isDialogRunning())
                                except Exception:
                                    pass
                            if not is_dialog_active and hasattr(al_dialog, 'isListening'):
                                try:
                                    is_dialog_active = bool(al_dialog.isListening())
                                except Exception:
                                    pass
                        except Exception as e:
                            log("Watchdog: Impossible de vérifier l'état de ALDialog: {}".format(e), level='debug')

                    if is_gpt_running:
                        if not is_29_version and is_dialog_active:
                            now = time.time()
                            if now - last_dialog_stop > 15.0:
                                log("Watchdog: Le chatbot est actif, mais ALDialog semble tourner. Arrêt de ALDialog (uniquement pour < 2.9).", level='warning')
                                try:
                                    al_dialog.stopDialog()
                                except Exception as e:
                                    log("Watchdog: Erreur en tentant d'arrêter ALDialog: {}".format(e), level='debug')
                                finally:
                                    last_dialog_stop = now
                            else:
                                remaining = max(0.0, 15.0 - (now - last_dialog_stop))
                                log("Watchdog: ALDialog encore détecté actif, nouvel essai dans {:.1f}s.".format(remaining), level='debug')
                    else:
                        if not is_29_version:
                            if not is_dialog_active:
                                now = time.time()
                                if now - last_dialog_restart > 15.0:
                                    log("Watchdog: Le chatbot est inactif et ALDialog ne semble pas tourner. Redémarrage de ALDialog.", level='info')
                                    try:
                                        al_dialog.resetAll()
                                        al_dialog.runDialog()
                                        last_dialog_restart = now
                                    except Exception as e:
                                        log("Watchdog: Erreur en tentant de redémarrer ALDialog: {}".format(e), level='error')
                                else:
                                    log("Watchdog: Redémarrage ALDialog déjà tenté récemment, on attend.", level='debug')
                            else:
                                log("Watchdog: ALDialog est déjà actif (mode < 2.9).", level='debug')
                except Exception as e:
                    log("Erreur dans le watchdog: {}".format(e), level='error')
                stop_event.wait(30.0)
        except Exception as e:
            log("Le service ALAutonomousLife n'est pas disponible: {}".format(e), level='error')    
    watchdog_thread = threading.Thread(target=autolife_watchdog, args=(autolife_stop_event, is_29_version))
    watchdog_thread.daemon = True
    watchdog_thread.start()

    def pause_aldialog_watchdog():
        if not aldialog_watchdog_pause.is_set():
            aldialog_watchdog_pause.set()
            log("Watchdog ALDialog mis en pause pour la chorégraphie.", level='info')

    def resume_aldialog_watchdog():
        if aldialog_watchdog_pause.is_set():
            aldialog_watchdog_pause.clear()
            log("Watchdog ALDialog réactivé.", level='info')

    leds = PepperLEDs(s, _logger)
    cap = Listener(s, CONFIG['audio'], _logger)
    SYSTEM_PROMPT = "Ton nom est Pepper."
    SYSTEM_PROMPT_OLLAMA = "Ton nom est Pepper."

    try:
        pls = s.service("PepperLifeService")
        anim_families = pls.getAnimationFamilies()
        base_prompt = chatGPT.get_base_prompt(config=CONFIG, logger=_logger)
        prompt_text, _ = build_system_prompt_in_memory(base_prompt, anim_families)
        SYSTEM_PROMPT = prompt_text
        ollama_base_prompt = ChatOllama.get_base_prompt(config=CONFIG, logger=_logger)
        prompt_text_ollama, _ = build_system_prompt_in_memory(ollama_base_prompt, anim_families)
        SYSTEM_PROMPT_OLLAMA = prompt_text_ollama
        log("[PROMPT] Prompt système généré avec {} familles d'animations.".format(len(anim_families)), level='debug')
    except Exception as e:
        log("[PROMPT] Génération dynamique ÉCHOUÉE: {}".format(e), level='error', color=bcolors.FAIL)
        SYSTEM_PROMPT = "Ton nom est Pepper."
        SYSTEM_PROMPT_OLLAMA = "Ton nom est Pepper."

    speaker = Speaker(s, _logger, CONFIG)
    vision_service = Vision(CONFIG, s, _logger)

    chat_manager = ChatManager(
        config=CONFIG,
        session=s,
        log_fn=log,
        logger=_logger,
        speaker=speaker,
        leds=leds,
        listener=cap,
        vision_service=vision_service,
        led_thread_fn=led_management_thread,
        al_dialog=al_dialog
    )
    chat_manager.set_system_prompts(SYSTEM_PROMPT, SYSTEM_PROMPT_OLLAMA)

    def _reload_config(reason=None):
        global CONFIG
        nonlocal SYSTEM_PROMPT, SYSTEM_PROMPT_OLLAMA
        try:
            updated_config = load_config(_logger)
            CONFIG = updated_config
            msg = "Configuration rechargée."
            if reason:
                msg = f"{msg} ({reason})"
            log(msg, level='info')
        except Exception as e:
            log("Échec du rechargement de la configuration: {}".format(e), level='error')
            return

        try:
            pls = s.service("PepperLifeService")
            anim_families = pls.getAnimationFamilies()
            base_prompt = chatGPT.get_base_prompt(config=CONFIG, logger=_logger)
            SYSTEM_PROMPT, _ = build_system_prompt_in_memory(base_prompt, anim_families)
            ollama_base_prompt = ChatOllama.get_base_prompt(config=CONFIG, logger=_logger)
            SYSTEM_PROMPT_OLLAMA, _ = build_system_prompt_in_memory(ollama_base_prompt, anim_families)
        except Exception as e:
            log("Impossible de régénérer les prompts systèmes après rechargement config: {}".format(e), level='warning')

        chat_manager.update_config(CONFIG)
        chat_manager.set_system_prompts(SYSTEM_PROMPT, SYSTEM_PROMPT_OLLAMA)
        speaker.config = CONFIG
        if hasattr(vision_service, 'config'):
            vision_service.config = CONFIG
        try:
            web_srv = getattr(_tablet_ui, 'web_server', None)
            if web_srv:
                web_srv.update_runtime_config(CONFIG)
        except Exception:
            pass

    def start_chat(mode='gpt'):
        _reload_config(f"démarrage du chat ({mode})")
        chat_manager.start(mode)

    def stop_chat():
        chat_manager.stop()

    def on_config_changed(_patch):
        _reload_config("mise à jour via l'interface")

    atexit.register(cap.close)
    atexit.register(vision_service.stop_camera)

    def toggle_micro():
        is_enabled = cap.toggle_micro()
        if not is_enabled:
            leds.idle()
        return is_enabled

    _tablet_ui = classTablet(
        session=s, logger=_logger, port=8088, version_provider=SysVersion.get,
        mic_toggle_callback=toggle_micro, listener=cap, speaker=speaker, vision_service=vision_service,
        start_chat_callback=start_chat, stop_chat_callback=stop_chat,
        get_chat_status_callback=chat_manager.get_status,
        get_detailed_chat_status_callback=chat_manager.get_detailed_status,
        chat_send_callback=chat_manager.send_debug_prompt,
        config_changed_callback=on_config_changed
    )
    try:
        _tablet_ui.web_server.set_aldialog_watchdog_controller(
            pause_aldialog_watchdog,
            resume_aldialog_watchdog
        )
    except Exception as e:
        log("Impossible de configurer le contrôleur du watchdog ALDialog: {}".format(e), level='warning')
    _tablet_ui.start(show=True)
    chat_manager.attach_tablet(_tablet_ui)

    _reload_config("initialisation")

    # beh.boot() # No longer needed as it's part of the service
    if CONFIG.get('boot', {}).get('boot_vieAutonome', True):
        try: s.service("ALAutonomousLife").setState("interactive")
        except Exception as e: log("Vie autonome échouée: {}".format(e), level='error')
    if CONFIG.get('boot', {}).get('boot_reveille', True):
        try: s.service("ALMotion").wakeUp()
        except Exception as e: log("Réveil échoué: {}".format(e), level='error')

    auto_chat_mode = (CONFIG.get('boot', {}).get('auto_chat_mode') or '').strip().lower()
    if auto_chat_mode in ('gpt', 'ollama'):
        start_chat(auto_chat_mode)
    elif CONFIG.get('boot', {}).get('start_chatbot_on_boot', False):
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
