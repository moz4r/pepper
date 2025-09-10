# -*- coding: utf-8 -*- 
# pepper_poc_chat_main.py — NAOqi + OpenAI (STT + Chat) réactif
# - Écoute locale via ALAudioDevice (16 kHz mono) + endpointing court
# - STT OpenAI (gpt-4o-mini-transcribe -> fallback whisper-1)
# - Chat court persona Pepper + balises d’actions NAOqi (robot_actions.py)
# - LEDs gérées dans leds_manager.py (oreilles ON quand il écoute, OFF sinon)
# - TTS asynchrone: parle pendant que le robot bouge

import sys, time, io, wave, os, atexit, random, json
from openai import OpenAI
from classRobotActions import PepperActions, MARKER_RE
from classLEDs import PepperLEDs
from classRobotBehavior import BehaviorManager
from classListener import Listener
from classSpeak import Speaker
from classASRFilters import is_noise_utterance, is_recent_duplicate
from classAudioUtils import avgabs
from classSystem import bcolors

_client = None
def client():
    global _client
    if _client is None:
        _client = OpenAI(timeout=15.0)
    return _client

def stt(wav_bytes):
    f = ("speech.wav", wav_bytes, "audio/wav")
    try:
        r = client().audio.transcriptions.create(
            model=CONFIG['openai']['stt_model'], file=f, language="fr", temperature=0
        )
    except Exception:
        r = client().audio.transcriptions.create(
            model="whisper-1", file=f, language="fr", temperature=0
        )
    return (getattr(r, "text", None) or "").strip() or None

def chat(user_text, hist):
    msgs = [{"role":"system","content":CONFIG['openai']['system_prompt']}]
    for role, content in hist:
        msgs.append({"role": role, "content": content})
    msgs.append({"role":"user","content":user_text})
    resp = client().chat.completions.create(
        model=CONFIG['openai']['chat_model'], messages=msgs, temperature=0.6, max_tokens=60
    )
    return resp.choices[0].message.content.strip().replace("\n"," ").strip()

CONFIG = {
    "log": {
        "verbosity": 2
    }
}

def log(msg, level='info', color=None):
    verbosity_map = {'error': 0, 'warning': 1, 'info': 2, 'debug': 3}
    level_num = verbosity_map.get(level, 2)
    if CONFIG['log']['verbosity'] >= level_num:
        if color:
            print(color + msg + bcolors.ENDC)
        else:
            print(msg)

def load_config():
    global CONFIG
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, 'config.json')
    default_config_path = os.path.join(script_dir, 'config.json.default')

    if not os.path.exists(config_path):
        log("Le fichier config.json n'existe pas, création à partir de config.json.default...", level='warning', color=bcolors.WARNING)
        import shutil
        shutil.copy(default_config_path, config_path)

    with open(default_config_path, 'r') as f:
        default_config = json.load(f)

    with open(config_path, 'r') as f:
        user_config = json.load(f)

    # Vérifier les clés manquantes
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
        with open(config_path, 'w') as f:
            json.dump(user_config, f, indent=2)

    CONFIG = user_config

def main():
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
    SPEAKING = {"on": False}
    s = None
    try:
        import qi
        app = qi.Application(["PepperMain", "--qi-url=tcp://%s:%d" % (IP, PORT)])
        app.start()
        s = app.session
        log("[OK] NAOqi", level='info', color=bcolors.OKGREEN)

        system_service = s.service("ALSystem")
        robot_version = system_service.systemVersion()
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


    acts = PepperActions(s)
    beh  = BehaviorManager(s, default_speed=0.5)
    beh.set_actions(acts)
    beh.boot()

    tts  = s.service("ALTextToSpeech"); tts.setLanguage("French"); tts.setVolume(0.85)
    leds = PepperLEDs(s)
    cap = Listener(s, SPEAKING, CONFIG['audio']); atexit.register(cap.close)
    speaker = Speaker(tts, leds, cap, SPEAKING, acts, beh)


    api_key = CONFIG['openai'].get('api_key')
    if api_key:
        os.environ['OPENAI_API_KEY'] = api_key

    if not os.getenv("OPENAI_API_KEY"):
        log("Clé OpenAI absente. Veuillez la définir dans config.json ou via la variable d'environnement OPENAI_API_KEY.", level='error', color=bcolors.FAIL)
        tts.say("Clé OpenAI absente."); return

    leds.idle()

    cap.warmup(min_chunks=8, timeout=2.0)

    hist = []

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

    speaker.say_quick("Je suis réveillé !")

    # Boucle: listen → record → STT → chat(+actions) → TTS
    while True:
        # départ
        started=False; since=None; t_wait=time.time()
        while time.time()-t_wait < 5.0:
            if SPEAKING.get("on"):
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

        # STT -> Chat -> parler & bouger
        try:
            txt = stt(wav); log("[ASR] " + txt, level='info')
            if not txt:
                continue
            if is_noise_utterance(txt, BLACKLIST_STRICT) or is_recent_duplicate(txt):
                log("[ASR] filtré (bruit/blacklist): " + txt, level='info', color=bcolors.WARNING)
                leds.idle()
                continue
            if not txt: continue
            hist.append(("user", txt)); hist = hist[-8:]

            leds.processing()
            rep = chat(txt, hist[:-1]); log("[GPT] " + rep, level='info', color=bcolors.OKCYAN)

            rep, _ = beh.apply_speed_markers(rep)

            speaker.speak_and_actions_parallel(rep)

            rep_clean = MARKER_RE.sub("", rep).strip()
            hist.append(("assistant", rep_clean))

            time.sleep(0.5)

        except Exception as e:
            log("[ERR] " + str(e), level='error', color=bcolors.FAIL)
            speaker.say_quick("Petit pépin réseau, on réessaie.")

if __name__ == "__main__":
    main()