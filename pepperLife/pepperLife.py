# -*- coding: utf-8 -*-
# pepper_poc_chat_main.py — NAOqi + OpenAI (STT + Chat) réactif
# - Écoute locale via ALAudioDevice (16 kHz mono) + endpointing court
# - STT OpenAI (gpt-4o-mini-transcribe -> fallback whisper-1)
# - Chat court persona Pepper + balises d’actions NAOqi (robot_actions.py)
# - LEDs gérées dans leds_manager.py (oreilles ON quand il écoute, OFF sinon)
# - TTS asynchrone: parle pendant que le robot bouge

import re, qi, sys, time, io, wave, os, subprocess, atexit, random, threading, unicodedata
from openai import OpenAI
from classRobotActions import PepperActions, MARKER_RE
from classLEDs import PepperLEDs
from classRobotBehavior import BehaviorManager
from classSpeak import Speaker
from classListener import Listener
from classASRFilters import is_noise_utterance, is_recent_duplicate
from classAudioUtils import avgabs  # pour le VAD (le reste utilisé dans Listener)


# ===========================
#   OPTIONS / PARAMÈTRES
# ===========================

IP, PORT = "127.0.0.1", 9559
SR = 16000

# VAD / Endpointing
PREROLL_CHUNKS = 16
SILHOLD       = 0.30
FAST_FRAMES   = 3
MIN_UTT       = 0.30
CALIB         = 3.0
SPEAKING = {"on": False}

# Modèles OpenAI (surclassables par ENV)
STT_MODEL  = os.getenv("OPENAI_STT_MODEL",  "gpt-4o-mini-transcribe")
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = (
    "Tu es Pepper, un robot humanoïde très évolué (≈20 DoF). "
    "Tu disposes des moteurs: HeadYaw, HeadPitch, "
    "LShoulderPitch, LShoulderRoll, LElbowYaw, LElbowRoll, LWristYaw, LHand, "
    "RShoulderPitch, RShoulderRoll, RElbowYaw, RElbowRoll, RWristYaw, RHand. "
    "Les mains utilisent 0.0=fermé, 1.0=ouvert. Les autres reçoivent des angles en degrés. "
    "Quand l’utilisateur demande un geste, génère À LA FIN de ta réponse une ou plusieurs balises EXACTES "
    "pour programmer les mouvements. Grammaire autorisée : "
    "  %%HeadYaw(deg)%%, %%HeadPitch(deg)%%, "
    "  %%LShoulderPitch(deg)%%, %%LShoulderRoll(deg)%%, %%LElbowYaw(deg)%%, %%LElbowRoll(deg)%%, %%LWristYaw(deg)%%, %%LHand(val)%%, "
    "  %%RShoulderPitch(deg)%%, %%RShoulderRoll(deg)%%, %%RElbowYaw(deg)%%, %%RElbowRoll(deg)%%, %%RWristYaw(deg)%%, %%RHand(val)%%, "
    "  %%RaiseRightArm()%%, %%RaiseLeftArm()%%, %%RestArm(R|L)%%, %%Wave(R|L)%%, "
    "  %%SetSpeed(x)%% (0.05..1.0). "
    "Tu peux combiner plusieurs balises si nécessaire (ordre d’exécution = ordre d’apparition). "
    "N’écris les balises QUE si une action physique est demandée. "
    "Réponds en français, brièvement (1–2 phrases), pertinent, un peu drôle quand c’est approprié. Pas d’emojis."
)

BLACKLIST_STRICT = {
    "je suis", "c est", "c'est", "je suis.", "c est.", "c'est.",
}

# ===========================
#   UTILITAIRES AUDIO
# ===========================

def _norm_text(t):
    if not t: return ""
    # minuscule + suppression des accents + nettoyage ponctuation redondante
    t = unicodedata.normalize("NFD", t).lower()
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")  # remove accents
    t = t.replace("’", "'")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)      # garde lettres/chiffres/apostrophes/espaces
    t = re.sub(r"\s+", " ", t).strip()
    return t

def is_noise_utterance(txt):
    n = _norm_text(txt)
    if not n: return True
    # blacklist stricte
    if n in BLACKLIST_STRICT: return True
    # heuristiques de brièveté
    if len(n) <= 3: return True
    # un seul mot très court (souvent des bribes de TTS)
    if " " not in n and len(n) <= 5: return True
    # phrase ultra-courte finissant par un point
    if n.endswith(".") and len(n) <= 8: return True
    return False

# déduplication rapprochée (évite répétitions TTS captées)
_NOISE_RECENCY = {"last_norm": "", "t": 0.0}
def is_recent_duplicate(txt, window=2.0):
    n = _norm_text(txt)
    now = time.time()
    if n and n == _NOISE_RECENCY["last_norm"] and (now - _NOISE_RECENCY["t"]) < window:
        return True
    _NOISE_RECENCY["last_norm"] = n
    _NOISE_RECENCY["t"] = now
    return False


def log(*a):
    sys.stdout.write(" ".join(str(x) for x in a) + "\n"); sys.stdout.flush()

def avgabs(b):
    if not b: return 0
    s=n=0; L=len(b)
    for i in range(0, L-1, 2):
        v = b[i] | (b[i+1]<<8)
        if v >= 32768: v -= 65536
        if v < 0: v = -v
        s += v; n += 1
    return s//n if n else 0

def peakabs(b):
    if not b: return 0
    m=0; L=len(b)
    for i in range(0, L-1, 2):
        v = b[i] | (b[i+1]<<8)
        if v >= 32768: v -= 65536
        a = -v if v < 0 else v
        if a > m: m = a
    return m

def agc(raw, target=24000, limit=4.0):
    mx = peakabs(raw)
    if mx <= 0: return raw
    k = min(limit, float(target)/float(mx))
    out = bytearray(); L=len(raw)
    for i in range(0, L-1, 2):
        v = raw[i] | (raw[i+1]<<8)
        if v >= 32768: v -= 65536
        w = int(v*k)
        if   w >  32767: w =  32767
        elif w < -32768: w = -32768
        if w < 0: w += 65536
        out.append(w & 0xFF); out.append((w>>8) & 0xFF)
    return bytes(out)

def trim_tail_silence(raw, stop_thr, frame_ms=20, max_trim_ms=600):
    if not raw: return raw
    step = int(SR * frame_ms / 1000.0) * 2
    cut = 0; L=len(raw); max_steps = int(max_trim_ms / float(frame_ms))
    for _ in range(max_steps):
        a = L - cut - step
        if a <= 0: break
        if avgabs(raw[a:a+step]) >= stop_thr: break
        cut += step
    return raw[:L-cut] if cut>0 else raw

# ===========================
#   OPENAI
# ===========================

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
            model=STT_MODEL, file=f, language="fr", temperature=0
        )
    except Exception:
        r = client().audio.transcriptions.create(
            model="whisper-1", file=f, language="fr", temperature=0
        )
    return (getattr(r, "text", None) or "").strip() or None

def chat(user_text, hist):
    msgs = [{"role":"system","content":SYSTEM_PROMPT}]
    for role, content in hist[-6:]:
        msgs.append({"role": role, "content": content})
    msgs.append({"role":"user","content":user_text})
    resp = client().chat.completions.create(
        model=CHAT_MODEL, messages=msgs, temperature=0.6, max_tokens=60
    )
    return resp.choices[0].message.content.strip().replace("\n"," ").strip()

# ===========================
#   TTS ASYNC (parler en bougeant)
# ===========================

def say_async(tts, leds, cap, text):
    """
    Lance le TTS en non-bloquant si possible (tts.post.say),
    sinon fallback bloquant. Retourne un handle ("post", task_id) ou ("sync", None).
    """
    SPEAKING["on"] = True
    leds.speaking_start()   # oreilles OFF, yeux bleus
    try:
        try:
            cap.mon[:] = []; cap.pre[:] = []  # anti-larsen soft
        except:
            pass
        # Non-bloquant si dispo
        try:
            task_id = tts.post.say(text)
            return ("post", task_id)
        except Exception:
            pass
        # Fallback bloquant
        tts.say(text)
        return ("sync", None)
    except:
        SPEAKING["on"] = False
        try: leds.speaking_stop()
        except: pass
        raise

def wait_tts_end(tts, leds, handle, timeout=8.0):
    kind, tok = handle
    t0 = time.time()

    # Attente propre tant que possible
    if hasattr(tts, "isSpeaking"):
        while time.time() - t0 < timeout:
            try:
                if not tts.isSpeaking():
                    break
            except:
                break
            time.sleep(0.05)
    else:
        # Pas d'API fiable => micro-attente si post.say
        if kind == "post":
            time.sleep(0.35)

    # Fin d'attente (ou timeout) -> on rend l'écoute
    SPEAKING["on"] = False
    try:
        leds.speaking_stop()   # oreilles ON, yeux blancs
    except:
        pass

    # Purge très brève pour éviter d'avaler la fin du TTS
    # (on laisse 'mon' vivant pendant le TTS, ici on nettoie juste 'pre')
    try:
        # cap n'est pas dans la portée ici dans ta version → on ne purge que via l'appelant après
        pass
    except:
        pass

    time.sleep(0.06)


def say_quick(tts, leds, cap, text):
    """Helper pour un TTS bref (non-bloquant si possible, sinon bloquant)."""
    h = say_async(tts, leds, cap, text)
    wait_tts_end(tts, leds, h, timeout=15.0)

# ===========================
#   CAPTURE MICRO (NAOqi)
# ===========================

def _list_audio_clients(ad):
    try:
        return list(ad.getSubscribers())
    except Exception:
        try:
            return list(ad.getClientList())
        except Exception:
            return []

def _free_audio_slots(ad, prefixes=("PepperASR_", "SpeechRecognition", "ASR_", "PepperASR")):
    clients = _list_audio_clients(ad)
    freed = []
    for c in clients:
        sc = str(c)
        if any(sc.startswith(p) for p in prefixes):
            try:
                ad.unsubscribe(sc)
                freed.append(sc)
            except Exception:
                pass
    return freed

class Cap(object):
    """Pré-roll + enregistrement + WAV mémoire, avec subscribe robuste."""
    def __init__(self, s):
        self.ad = s.service("ALAudioDevice")
        self.name = "PepperASR_%d_%d" % (int(time.time()), random.randint(100,999))
        s.registerService(self.name, self)

        freed = _free_audio_slots(self.ad)
        if freed:
            log("[AUDIO] Unsub orphelins:", ", ".join(freed))
            time.sleep(0.15)

        self.ad.setClientPreferences(self.name, SR, 1, 0)
        last_err = None
        for k in range(8):
            try:
                self.ad.subscribe(self.name); last_err=None; break
            except Exception as e:
                last_err = e
                _free_audio_slots(self.ad)
                time.sleep(0.05 * (2 ** k))
        if last_err: raise last_err

        self.mon, self.pre, self.rec = [], [], []
        self.on = False
        self.maxpre = PREROLL_CHUNKS
        log("[AUDIO] 16k mono —", self.name)

    def warmup(self, min_chunks=6, timeout=1.5):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if len(self.mon) >= min_chunks:
                break
            time.sleep(0.03)

    def processRemote(self, ch, ns, ts, buf):
        if not buf: return
        if not isinstance(buf, (bytes, bytearray)):
            try: buf = bytes(buf)
            except: return

        if SPEAKING["on"]:
            # NE PAS couper complètement: on entretient un petit ring pour le VAD
            self.mon.append(buf)
            if len(self.mon) > 24:
                self.mon = self.mon[-24:]
            return

        # Idle/écoute active
        self.mon.append(buf); self.pre.append(buf)
        if len(self.mon) > 24: self.mon = self.mon[-24:]
        if len(self.pre) > self.maxpre: self.pre = self.pre[-self.maxpre:]
        if self.on: self.rec.append(buf)


    def start(self):
        self.rec = list(self.pre)
        self.on = True
        log("[REC] START pre=", len(self.rec))

    def stop(self, stop_thr):
        self.on = False
        if not self.rec: return None
        raw = b"".join(self.rec); self.rec = []
        raw = agc(raw)
        raw = trim_tail_silence(raw, stop_thr, 20)
        buf = io.BytesIO(); wf = wave.open(buf, "wb")
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes(raw); wf.close()
        return buf.getvalue()

    def close(self):
        try: self.ad.unsubscribe(self.name)
        except Exception: pass

# ===========================
#   PARLER + GESTES EN PARALLÈLE
# ===========================

def _has_motion_markers(text):
    return MARKER_RE.search(text) is not None

def speak_and_actions_parallel(tts, leds, cap, rep, acts, beh):
    """
    Parle (async) et exécute les actions en parallèle dans un thread.
    Attente: fin de la parole + fin des gestes (ou timeout court).
    """
    rep_clean = MARKER_RE.sub("", rep).strip()

    def _do_actions():
        if not _has_motion_markers(rep):
            return
        try:
            beh.begin_control()
            _, done = acts.execute_markers(rep)   # bloquant jusqu’à fin des moves
            if done: log("[ACTIONS] exécutées:", done)
        finally:
            beh.end_control()

    th = threading.Thread(target=_do_actions); th.daemon = True

    # Démarrer TTS (async si possible)
    h = say_async(tts, leds, cap, rep_clean)

    # Lancer les gestes en parallèle
    th.start()

    # Attendre fin TTS
    wait_tts_end(tts, leds, h, timeout=20.0)

    # Purge anti-larsen résiduelle avant de repasser en écoute
    try:
        cap.mon[:] = []; cap.pre[:] = []
    except:
        pass

    # Attendre fin gestes (limite de sécurité)
    th.join(timeout=10.0)

# ===========================
#   MAIN
# ===========================

def main():
    app = qi.Application(["PepperMain","--qi-url=tcp://%s:%d"%(IP,PORT)])
    app.start(); s = app.session; log("[OK] NAOqi")

    acts = PepperActions(s)
    beh  = BehaviorManager(s, default_speed=0.5)
    beh.set_actions(acts)
    beh.boot()

    tts  = s.service("ALTextToSpeech"); tts.setLanguage("French"); tts.setVolume(0.85)
    leds = PepperLEDs(s)
    rec  = s.service("ALAudioRecorder")
    try: rec.stopMicrophonesRecording()
    except: pass
    try: subprocess.call(["amixer","sset","Capture","100%"])
    except: pass

    if not os.getenv("OPENAI_API_KEY"):
        tts.say("Clé Open A I absente."); return

    leds.idle()

    cap = Cap(s); atexit.register(cap.close)
    cap.warmup(min_chunks=8, timeout=2.0)  # laisse le ring se remplir avant calibration

    hist = []

    # Calibration bruit
    t0 = time.time(); vals=[]
    while time.time() - t0 < CALIB:
        time.sleep(0.04)
        vals.append(avgabs(b"".join(cap.mon[-8:]) if cap.mon else b""))
    base  = int(sum(vals)/max(1,len(vals)))
    START = max(4, int(base*1.6))
    STOP  = max(3, int(base*0.9))
    log("[VAD] base=%d START=%d STOP=%d"%(base,START,STOP))

    say_quick(tts, leds, cap, "Je suis réveillé !")

    # Boucle: listen → record → STT → chat(+actions) → TTS
    while True:
        # départ
        started=False; since=None; t_wait=time.time()
        while time.time()-t_wait < 5.0:
            vol = avgabs(b"".join(cap.mon[-8:]) if cap.mon else b"")
            if vol >= START:
                if since is None: since = time.time()
                elif time.time()-since >= 0.06: started=True; break
            else:
                since=None
            time.sleep(0.03)
        if not started: continue

        # enregistrement + endpointing agressif
        cap.start(); t0=time.time(); last=t0; low=0
        leds.listening_recording()   # BLEU pendant [REC]
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
            txt = stt(wav); log("[ASR]", txt)
            if not txt:
                continue
            # filtre anti-bruit
            if is_noise_utterance(txt) or is_recent_duplicate(txt):
                log("[ASR] filtré (bruit/blacklist):", txt)
                leds.idle()
                continue
            if not txt: continue
            hist.append(("user", txt)); hist = hist[-8:]

            leds.processing()
            rep = chat(txt, hist); log("[GPT]", rep)

            # speed éventuelle
            rep, _ = beh.apply_speed_markers(rep)

            # parler & bouger en //
            speak_and_actions_parallel(tts, leds, cap, rep, acts, beh)

            # historique: version parlée (nettoyée)
            rep_clean = MARKER_RE.sub("", rep).strip()
            hist.append(("assistant", rep_clean))

            time.sleep(0.5)

        except Exception as e:
            log("[ERR]", e)
            say_quick(tts, leds, cap, "Petit pépin réseau, on réessaie.")

if __name__ == "__main__":
    main()
