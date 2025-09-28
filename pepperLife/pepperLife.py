# -*- coding: utf-8 -*-
# pepper_poc_chat_main.py — NAOqi + OpenAI (STT + Chat + Vision) réactif
# - Écoute locale via ALAudioDevice (16 kHz mono) + endpointing court
# - STT OpenAI (gpt-4o-mini-transcribe -> fallback whisper-1)
# - Chat court persona Pepper + balises d’actions NAOqi (robot_actions.py)
# - LEDs gérées dans leds_manager.py (oreilles ON quand il écoute, OFF sinon)
# - TTS asynchrone: parle pendant que le robot bouge
# - Vision unifiée: prompt configurable dans config.json (comme les moteurs)

import sys, time, os, atexit, json

from services.classSystem import bcolors, build_system_prompt_in_memory
from services.classAnimation import Animation


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


APP_DIR = os.path.dirname(os.path.abspath(__file__))





def install_requirements(packages_to_install):
    import subprocess

    pip_executable = "/home/nao/.local/share/PackageManager/apps/python3nao/bin/pip3"
    if not os.path.exists(pip_executable):
        pip_executable = "pip"  # Fallback for non-pepper env

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





import threading

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
    from services.classGpt4o import Gpt4o
    from services.classVision import Vision

    load_config()

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
        app = qi.Application(["PepperMain", f"--qi-url=tcp://{IP}:{PORT}"])
        app.start()
        s = app.session
        log("[OK] NAOqi", level='info', color=bcolors.OKGREEN)
        robot_version = s.service("ALSystem").systemVersion()
        log(f"Version de NAOqi: {robot_version}", level='info')
    except Exception as e:
        log(f"Erreur de connexion à NAOqi: {e}", level='error', color=bcolors.FAIL)
        sys.exit(1)

    anim = Animation(s, log, robot_version=robot_version)
    anim.health_check()

    try:
        base_prompt = Gpt4o.load_system_prompt(CONFIG.get('openai', {}), APP_DIR)
        prompt_text, _ = build_system_prompt_in_memory(base_prompt, anim)
        SYSTEM_PROMPT = prompt_text
    except Exception as e:
        log(f"[PROMPT] Génération dynamique échouée: {e}", level='warning', color=bcolors.WARNING)
        SYSTEM_PROMPT = Gpt4o.load_system_prompt(CONFIG.get('openai', {}), APP_DIR)

    leds = PepperLEDs(s, _logger)
    cap = Listener(s, CONFIG['audio'], _logger)
    beh = BehaviorManager(s, _logger, default_speed=0.5)
    tts = s.service("ALAnimatedSpeech")
    speaker = Speaker(tts, leds, cap, beh, anim=anim)
    vision_service = Vision(CONFIG, s, _logger)

    atexit.register(cap.close)
    atexit.register(vision_service.stop_camera)

    chat_thread = None
    chat_stop_event = None

    def run_chat_loop(stop_event):
        log("Démarrage du thread du chatbot GPT...", level='info')
        stt_service = STT(CONFIG, _logger)
        chat_service = Gpt4o(CONFIG, system_prompt=SYSTEM_PROMPT)

        api_key = CONFIG['openai'].get('api_key')
        if api_key:
            os.environ['OPENAI_API_KEY'] = api_key
        if not os.getenv("OPENAI_API_KEY"):
            log("Clé OpenAI absente.", level='error', color=bcolors.FAIL)
            speaker.say_quick("Clé OpenAI absente.")
            return

        vision_service.start_camera()
        cap.warmup(min_chunks=8, timeout=2.0)
        hist, hist_vision = [], []

        base = CONFIG['audio'].get('override_base_sensitivity')
        if not base:
            log("Calibration du bruit (2s)...", level='info')
            vals = [avgabs(b"".join(cap.mon[-8:]) if cap.mon else b"") for _ in range(50)]
            base = int(sum(vals) / max(1, len(vals)))
            log(f"Calibration terminée. Bruit de base: {base}", level='info')
        
        START = max(4, int(base * start_mult))
        STOP = max(3, int(base * stop_mult))

        speaker.say_quick("Je suis réveillé !")
        leds.idle()

        try:
            while not stop_event.is_set():
                if not cap.is_micro_enabled() or cap.is_speaking():
                    time.sleep(0.1)
                    continue

                vol = avgabs(b"".join(cap.mon[-8:]) if cap.mon else b"")
                if vol < START:
                    time.sleep(0.05)
                    continue
                
                leds.listening_recording()
                cap.start()
                t0 = time.time(); last = t0
                while time.time() - t0 < 5.0:
                    recent = b"".join(cap.mon[-3:]) if cap.mon else b""
                    fr = recent[-320:] if len(recent) >= 320 else recent
                    e = avgabs(fr)
                    if e >= STOP:
                        last = time.time()
                    if time.time() - last > SILHOLD:
                        break
                    time.sleep(0.02)
                wav = cap.stop(STOP)
                if not wav:
                    leds.idle()
                    continue

                try:
                    txt = stt_service.stt(wav)
                    log("[ASR] " + str(txt), level='info')
                    if not txt or is_noise_utterance(txt, BLACKLIST_STRICT) or is_recent_duplicate(txt):
                        leds.idle()
                        continue

                    leds.processing()
                    if vision_service._utterance_triggers_vision(txt.lower()):
                        png_bytes = vision_service.get_png()
                        if png_bytes:
                            _tablet_ui.set_last_capture(png_bytes)
                            _tablet_ui.show_last_capture_on_tablet()
                            rep = vision_service.vision_chat(txt, png_bytes, hist_vision)
                            hist_vision.extend([("user", txt), ("assistant", rep)])
                            hist_vision = hist_vision[-6:]
                            speaker.say_quick(rep)
                        else:
                            speaker.say_quick("Je n'ai pas réussi à prendre de photo.")
                    else:
                        hist.append(("user", txt))
                        rep = chat_service.chat(txt, hist[:-1])
                        hist.append(("assistant", rep))
                        hist = hist[-8:]
                        speaker.say_quick(rep)

                except Exception as e:
                    log("[ERR] " + str(e), level='error', color=bcolors.FAIL)
                    speaker.say_quick("Petit pépin réseau, on réessaie.")
        finally:
            log("Arrêt du thread du chatbot.", level='info')
            leds.idle()

    def start_chat(mode='gpt'):
        nonlocal chat_thread, chat_stop_event
        if chat_thread and chat_thread.is_alive():
            log("Un chat est déjà en cours, arrêt avant de changer de mode.", level='warning')
            stop_chat()

        if mode == 'gpt':
            chat_stop_event = threading.Event()
            chat_thread = threading.Thread(target=run_chat_loop, args=(chat_stop_event,))
            chat_thread.daemon = True
            chat_thread.start()
        else:
            log("Mode 'basic' activé.", level='info')
            speaker.say_quick("Mode de base activé.")
            leds.idle()

    def stop_chat():
        nonlocal chat_thread, chat_stop_event
        if chat_thread and chat_thread.is_alive():
            log("Demande d'arrêt du thread du chatbot...", level='info')
            chat_stop_event.set()
            chat_thread.join(timeout=5)
        chat_thread = None
        log("Chatbot arrêté. Passage en mode de base.", level='info')
        speaker.say_quick("Le chatbot est arrêté.")
        leds.idle()

    def get_chat_status():
        is_running = chat_thread and chat_thread.is_alive()
        current_mode = 'gpt' if is_running else 'basic'
        return {'mode': current_mode, 'is_running': is_running}

    def toggle_micro():
        is_enabled = cap.toggle_micro()
        if not is_enabled:
            leds.idle()
        return is_enabled

    _tablet_ui = classTablet(
        session=s, logger=_logger, port=8088, version_provider=SysVersion.get,
        mic_toggle_callback=toggle_micro, listener=cap, speaker=speaker, vision_service=vision_service,
        start_chat_callback=start_chat, stop_chat_callback=stop_chat, get_chat_status_callback=get_chat_status
    )
    _tablet_ui.start(show=True)

    beh.boot()
    if CONFIG.get('boot', {}).get('boot_vieAutonome', True):
        try: s.service("ALAutonomousLife").setState("interactive")
        except Exception as e: log("Vie autonome échouée: %s" % e, level='error')
    if CONFIG.get('boot', {}).get('boot_reveille', True):
        try: s.service("ALMotion").wakeUp()
        except Exception as e: log("Réveil échoué: %s" % e, level='error')
    try:
        ba = s.service("ALBasicAwareness")
        ba.setTrackingMode("Head")
        ba.setEngagementMode("SemiEngaged")
        ba.startAwareness()
    except Exception as e: log("BasicAwareness échoué: %s" % e, level='warning')

    if CONFIG.get('boot', {}).get('start_chatbot_on_boot', False):
        start_chat('gpt')
    else:
        log("Chatbot non démarré. Interface web disponible.", level='info', color=bcolors.OKGREEN)
        speaker.say_quick("Je suis prêt.")
        leds.idle()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("\nCtrl+C détecté. Arrêt...", level='info')
        stop_chat()


if __name__ == "__main__":
    main()
