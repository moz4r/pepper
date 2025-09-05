# -*- coding: utf-8 -*-
# classListener.py — Wrapper ALAudioDevice (pré-roll + WAV mémoire)

import time, io, wave, random
from classAudioUtils import agc, trim_tail_silence

class Listener(object):
    def __init__(self, session, sr, speaking_flag, preroll_chunks=16, client_prefix="PepperASR"):
        self.sr = sr
        self.SPEAKING = speaking_flag
        self.ad = session.service("ALAudioDevice")
        self.name = "%s_%d_%d" % (client_prefix, int(time.time()), random.randint(100,999))
        session.registerService(self.name, self)

        self._free_audio_slots()
        self.ad.setClientPreferences(self.name, sr, 1, 0)

        last_err = None
        for k in range(8):
            try:
                self.ad.subscribe(self.name); last_err = None; break
            except Exception as e:
                last_err = e
                self._free_audio_slots()
                time.sleep(0.05 * (2 ** k))
        if last_err: raise last_err

        self.mon, self.pre, self.rec = [], [], []
        self.maxpre = preroll_chunks
        self.on = False
        print("[AUDIO] %dk mono — %s" % (sr//1000, self.name))

    # ---- utils slots ----
    def _list_audio_clients(self):
        try: return list(self.ad.getSubscribers())
        except Exception:
            try: return list(self.ad.getClientList())
            except Exception: return []

    def _free_audio_slots(self, prefixes=("PepperASR_", "SpeechRecognition", "ASR_", "PepperASR")):
        freed=[]
        for c in self._list_audio_clients():
            sc=str(c)
            if any(sc.startswith(p) for p in prefixes):
                try: self.ad.unsubscribe(sc); freed.append(sc)
                except: pass
        if freed:
            print("[AUDIO] Unsub orphelins:", ", ".join(freed))
            time.sleep(0.15)

    # ---- helpers publics ----
    def flush_ring(self):
        try:
            self.mon[:] = []; self.pre[:] = []
        except: pass

    def warmup(self, min_chunks=6, timeout=1.5):
        t0 = time.time()
        while time.time()-t0 < timeout:
            if len(self.mon) >= min_chunks: break
            time.sleep(0.03)

    # ---- callback ALAudioDevice ----
    def processRemote(self, ch, ns, ts, buf):
        if not buf: return
        if not isinstance(buf, (bytes, bytearray)):
            try: buf = bytes(buf)
            except: return

        if self.SPEAKING["on"]:
            return  # ignore pendant TTS (anti-larsen)
        self.mon.append(buf); self.pre.append(buf)
        if len(self.mon) > 24: self.mon = self.mon[-24:]
        if len(self.pre) > self.maxpre: self.pre = self.pre[-self.maxpre:]
        if self.on: self.rec.append(buf)

    # ---- enregistrement ----
    def start(self):
        self.rec = list(self.pre)
        self.on = True
        print("[REC] START pre=", len(self.rec))

    def stop(self, stop_thr):
        self.on = False
        if not self.rec: return None
        raw = b"".join(self.rec); self.rec = []
        raw = agc(raw)
        raw = trim_tail_silence(raw, stop_thr, 20, sr=self.sr)
        buf = io.BytesIO()
        wf = wave.open(buf, "wb")
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(self.sr)
        wf.writeframes(raw); wf.close()
        return buf.getvalue()

    def close(self):
        try: self.ad.unsubscribe(self.name)
        except: pass
