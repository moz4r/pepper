# -*- coding: utf-8 -*-
# classListener.py — Wrapper ALAudioDevice (pré-roll + WAV mémoire)

import time, io, wave, random, threading
from .classAudioUtils import agc, trim_tail_silence

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

class Listener(object):
    """Pré-roll + enregistrement + WAV mémoire, avec subscribe robuste."""
    def __init__(self, s, audio_config, logger):
        self.ad = s.service("ALAudioDevice")
        self.name = "PepperASR_%d_%d" % (int(time.time()), random.randint(100,999))
        s.registerService(self.name, self)

        self.sr = audio_config['sr']
        self.preroll_chunks = audio_config['preroll_chunks']
        self.agc_target = audio_config['agc_target']
        self.log = logger
        self.microEnabled = {"on": True}

        # État partagé et synchronisation
        self.lock = threading.Lock()
        self.speaking = False
        self.speech_stop_time = 0
        self.speech_cooldown = 0.8 # 400ms

        # Abonnement à l'état du TTS
        self.memory = s.service("ALMemory")
        self.tts_subscriber = self.memory.subscriber("ALTextToSpeech/Status")
        self.anim_subscriber = self.memory.subscriber("ALAnimatedSpeech/Status")
        self.anim_subscriber_id = self.anim_subscriber.signal.connect(self.on_tts_status)
        self.tts_subscriber_id = self.tts_subscriber.signal.connect(self.on_tts_status)

        freed = _free_audio_slots(self.ad)
        if freed:
            print("[AUDIO] Unsub orphelins:", ", ".join(freed))
            time.sleep(0.15)

        self.ad.setClientPreferences(self.name, self.sr, 1, 0)
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
        self.maxpre = self.preroll_chunks
        print("[AUDIO] %dk mono — %s" % (self.sr//1000, self.name))

    def on_tts_status(self, status):
        if not isinstance(status, (list, tuple)) or len(status) < 2:
            return

        status_string = status[1]
        with self.lock:
            if status_string == 'started':
                self.speaking = True
            elif status_string == 'done':
                self.speaking = False
                self.speech_stop_time = time.time()

    def toggle_micro(self):
        self.microEnabled["on"] = not self.microEnabled["on"]
        self.log(f"Microphone enabled: {self.microEnabled['on']}", level='info')
        return self.microEnabled["on"]

    def is_micro_enabled(self):
        return self.microEnabled.get("on", False)

    def is_speaking(self):
        with self.lock:
            return self.speaking

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

        with self.lock:
            is_speaking = self.speaking
            stop_time = self.speech_stop_time

        time_since_stop = time.time() - stop_time

        if is_speaking or (time_since_stop < self.speech_cooldown) or not self.microEnabled["on"]:
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
        print("[REC] START pre=", len(self.rec))

    def stop(self, stop_thr):
        self.on = False
        if not self.rec: return None
        raw = b"".join(self.rec); self.rec = []
        raw = agc(raw, self.agc_target)
        raw = trim_tail_silence(raw, stop_thr, self.sr, 20)
        buf = io.BytesIO()
        wf = wave.open(buf, "wb")
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(self.sr)
        wf.writeframes(raw)
        wf.close()
        return buf.getvalue()

    def close(self):
        try:
            self.tts_subscriber.signal.disconnect(self.tts_subscriber_id)
        except Exception:
            pass
        try: self.ad.unsubscribe(self.name)
        except Exception: pass

        # Bool direct (si dispo)
        try:
            self.isspk_sub = self.memory.subscriber("ALTextToSpeech/IsSpeaking")
            self.isspk_sub_id = self.isspk_sub.signal.connect(lambda v: self._set_speaking(bool(v)))
        except Exception:
            self.isspk_sub = None; self.isspk_sub_id = None
