# -*- coding: utf-8 -*-
# pepper_poc_chat_fast.py — NAOqi + OpenAI (STT + Chat) optimisé latence
# Changements: modèle STT rapide (si dispo), endpointing + trim, pré-roll réduit, historique court.

import qi, sys, time, io, wave, os, atexit, subprocess
from openai import OpenAI

IP, PORT = "127.0.0.1", 9559
SR = 16000

# --------- VAD / capture (latence réduite) ----------
PREROLL_CHUNKS = 16        # ~0.8–1.0 s de marge (suffisant pour ne pas rater le début)
SILHOLD = 0.16             # stop si silence net ≥ 180 ms
FAST_FRAMES = 7            # ~80–100 ms de “silence” consécutif
MIN_UTT = 0.35             # durée mini avant fast-stop
COOLDOWN = 0.9
CALIB = 0.7
SPEAKING = {"on": False}

# ---------- Modèles OpenAI ----------
STT_MODEL  = os.getenv("OPENAI_STT_MODEL",  "gpt-4o-mini-transcribe")  # fallback automatique si pas dispo
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = (
    "Tu es Pepper, un robot humanoïde très évolué. "
    "Réponds STRICTEMENT en français. "
    "Réponses brèves (1–2 phrases), pertinentes, et un peu drôles quand c’est approprié. "
    "Ton chaleureux, sans emojis."
)

# ---------- utils ----------
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
    mx=0; L=len(b)
    for i in range(0, L-1, 2):
        v = b[i] | (b[i+1]<<8)
        if v >= 32768: v -= 65536
        a = -v if v < 0 else v
        if a > mx: mx = a
    return mx

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

# Trim doux du silence de fin (réduit le fichier → upload + ASR plus rapides)
def trim_tail_silence(raw, stop_thr, frame_ms=20, max_trim_ms=600):
    if not raw: return raw
    step = int((SR * frame_ms / 1000.0)) * 2  # bytes
    max_steps = int(max_trim_ms / float(frame_ms))
    L = len(raw)
    cut = 0
    for i in range(1, max_steps+1):
        a = L - i*step
        if a <= 0: break
        fr = raw[a:a+step]
        if avgabs(fr) < stop_thr:
            cut += step
        else:
            break
    if cut > 0:
        return raw[:max(0, L - cut)]
    return raw

# ---------- OpenAI ----------
_client = None
def client():
    global _client
    if _client is None:
        _client = OpenAI(timeout=15.0)  # keep-alive court
    return _client

def stt(wav_bytes):
    # tente modèle rapide, sinon fallback whisper-1
    t0 = time.time()
    f = ("speech.wav", wav_bytes, "audio/wav")
    try:
        r = client().audio.transcriptions.create(
            model=STT_MODEL, file=f, language="fr", temperature=0
            log("stt model:".STT_MODEL)
        )
    except Exception:
        r = client().audio.transcriptions.create(
            model="whisper-1", file=f, language="fr", temperature=0
            log("stt model:whisper")
        )
    txt = (getattr(r, "text", None) or "").strip() or None
    return txt, int((time.time()-t0)*1000)

def chat_answer(user_text, history):
    msgs = [{"role":"system","content":SYSTEM_PROMPT}]
    for role, content in history[-8:]:  # petit contexte si besoin
        msgs.append({"role": role, "content": content})
    msgs.append({"role":"user","content":user_text})
    t0 = time.time()
    resp = client().chat.completions.create(
        model=CHAT_MODEL,
        messages=msgs,
        temperature=0.6,
        max_tokens=60
    )
    out = resp.choices[0].message.content.strip().replace("\n"," ").strip()
    return out, int((time.time()-t0)*1000)

# ---------- TTS anti-larsen ----------
def say(tts, audio, text, cap):
    prev = None; t0 = time.time()
    try:
        SPEAKING["on"] = True
        try: prev = audio.getOutputVolume()
        except: pass
        try: audio.setOutputVolume(28)
        except: pass
        try:
            cap.mon[:] = []; cap.pre[:] = []
        except: pass
        tts.say(text)
    finally:
        time.sleep(0.12)
        try: audio.setOutputVolume(prev if prev is not None else 75)
        except: pass
        SPEAKING["on"] = False
    return int((time.time()-t0)*1000)

# ---------- capture ----------
class Cap(object):
    def __init__(self, session):
        self.ad = session.service("ALAudioDevice")
        self.name = "PepperASR_%d" % int(time.time()%100000)
        session.registerService(self.name, self)  # impératif sur ton firmware

        # Nettoyage
        try:
            subs = []
            try: subs = self.ad.getSubscribers()
            except: subs = self.ad.getClientList()
            for n in list(subs):
                if str(n).startswith("PepperASR_"):
                    try: self.ad.unsubscribe(n)
                    except: pass
        except: pass

        self.ad.setClientPreferences(self.name, SR, 1, 0)  # mono 16 k
        err=None
        for k in range(3):
            try:
                self.ad.subscribe(self.name); err=None; break
            except Exception as e:
                err=e; time.sleep(0.25*(k+1))
        if err: raise err

        self.mon, self.pre, self.rec = [], [], []
        self.on = False
        self.maxpre = PREROLL_CHUNKS
        log("[AUDIO] MONO @16k prêt —", self.name)

    def processRemote(self, ch, ns, ts, buf):
        if not buf: return
        if not isinstance(buf, (bytes, bytearray)):
            try: buf = bytes(buf)
            except: return
        if SPEAKING["on"]:
            if len(self.mon) < 2: self.mon.append(buf)
            return
        self.mon.append(buf); self.pre.append(buf)
        if len(self.mon) > 24: self.mon = self.mon[-24:]
        if len(self.pre) > self.maxpre: self.pre = self.pre[-self.maxpre:]
        if self.on: self.rec.append(buf)

    def start(self):
        self.rec = list(self.pre); self.on = True; log("[REC] START (pre=%d)"%len(self.rec))

    def stop(self, stop_thr):
        self.on = False
        if not self.rec: return None
        raw = b"".join(self.rec); self.rec = []
        # AGC léger
        raw = agc(raw)
        # Trim du silence de fin (80–600 ms max)
        raw = trim_tail_silence(raw, stop_thr=stop_thr, frame_ms=20, max_trim_ms=600)
        # WAV
        buf = io.BytesIO(); wf = wave.open(buf, "wb")
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes(raw); wf.close()
        return buf.getvalue()

    def close(self):
        try: self.ad.unsubscribe(self.name)
        except: pass

# ---------- main ----------
def main():
    app = qi.Application(["PepperPOCfast","--qi-url=tcp://%s:%d"%(IP,PORT)])
    app.start(); s = app.session; log("[OK] NAOqi")

    tts   = s.service("ALTextToSpeech"); tts.setLanguage("French"); tts.setVolume(0.85)
    audio = s.service("ALAudioDevice")
    rec   = s.service("ALAudioRecorder")
    try: rec.stopMicrophonesRecording(); log("[RESET] Recorder.stop OK")
    except: pass
    try: subprocess.call(["amixer","sset","Capture","100%"])
    except: pass

    if not os.getenv("OPENAI_API_KEY"):
        tts.say("Clé OpenAI absente."); return

    cap = Cap(s); atexit.register(cap.close)
    history = []  # [(role, content), ...]

    # Calibration
    t0 = time.time(); vals=[]
    while time.time()-t0 < CALIB:
        time.sleep(0.04)
        vals.append(avgabs(b"".join(cap.mon[-8:]) if cap.mon else b""))
    base = int(sum(vals)/max(1,len(vals)))
    START = max(4, int(base*1.6))
    STOP  = max(3, int(base*0.9))
    log("[VAD] base=%d START=%d STOP=%d"%(base, START, STOP))

    say(tts, audio, "Prêt pour la démo turbo.", cap)

    while True:
        # Départ (~60 ms)
        started=False; since=None; t_wait=time.time()
        while time.time()-t_wait < 5.0:
            vol = avgabs(b"".join(cap.mon[-8:]) if cap.mon else b"")
            if vol >= START:
                if since is None: since = time.time()
                elif time.time()-since >= 0.06: started=True; break
            else: since=None
            time.sleep(0.03)
        if not started:
            continue

        # Enregistrement + endpointing rapide
        cap.start()
        t_rec0 = time.time(); last_voice = t_rec0; low = 0
        while time.time()-t_rec0 < 3.0:
            recent = b"".join(cap.mon[-3:]) if cap.mon else b""
            fr = recent[-320:] if len(recent)>=320 else recent  # ~10 ms @16k
            e = avgabs(fr)
            if e >= STOP:
                last_voice = time.time(); low = 0
            else:
                low += 1
            if time.time()-last_voice >= SILHOLD: break
            if (low >= FAST_FRAMES) and (time.time()-t_rec0 >= MIN_UTT): break
            time.sleep(0.01)

        t_rec1 = time.time()
        wav = cap.stop(stop_thr=STOP)
        if not wav:
            log("[DROP] vide"); continue

        # STT -> Chat -> TTS (timings)
        try:
            txt, asr_ms = stt(wav)
            rec_ms  = int((t_rec1 - t_rec0)*1000)
            prep_ms = 0  # négligeable ici
            log("[ASR]", txt)
            if not txt:
                continue

            # Historique court (4 tours max)
            history.append(("user", txt))
            if len(history) > 8: history = history[-8:]

            rep, llm_ms = chat_answer(txt, history)
            log("[GPT]", rep)
            history.append(("assistant", rep))
            tts_ms = say(tts, audio, rep, cap)

            total_ms = rec_ms + prep_ms + asr_ms + llm_ms + tts_ms
            log("[TIMING] rec=%dms asr=%dms llm=%dms tts=%dms total=%dms" %
                (rec_ms, asr_ms, llm_ms, tts_ms, total_ms))

            time.sleep(COOLDOWN)

        except Exception as e:
            log("[ERR]", e)
            say(tts, audio, "Petit pépin réseau, on réessaie.", cap)

if __name__ == "__main__":
    main()
