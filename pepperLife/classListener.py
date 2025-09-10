# -*- coding: utf-8 -*-
# classListener.py — Wrapper ALAudioDevice (pré-roll + WAV mémoire)

import time, io, wave, random
from classAudioUtils import agc, trim_tail_silence

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
    def __init__(self, s, speaking_flag, audio_config):
        self.ad = s.service("ALAudioDevice")
        self.name = "PepperASR_%d_%d" % (int(time.time()), random.randint(100,999))
        s.registerService(self.name, self)
        self.SPEAKING = speaking_flag
        self.sr = audio_config['sr']
        self.preroll_chunks = audio_config['preroll_chunks']
        self.agc_target = audio_config['agc_target']

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

        if self.SPEAKING["on"]:
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
        print("[REC] START pre=", len(self.rec))

    def stop(self, stop_thr):
        self.on = False
        if not self.rec: return None
        raw = b"".join(self.rec); self.rec = []
        raw = agc(raw, self.agc_target)
        raw = trim_tail_silence(raw, stop_thr, self.sr, 20)
        buf = io.BytesIO(); wf = wave.open(buf, "wb")
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(self.sr)
        wf.writeframes(raw); wf.close()
        return buf.getvalue()

    def close(self):
        try: self.ad.unsubscribe(self.name)
        except Exception: pass
