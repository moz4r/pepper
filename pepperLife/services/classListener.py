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

        self.sr = 16000
        self.preroll_chunks = audio_config.get('preroll_chunks', 16)
        self.agc_target = audio_config['agc_target']
        self.log = logger
        self.microEnabled = {"on": True}
        self.is_subscribed = False

        self.lock = threading.Lock()
        self.speaking = False
        self.speech_stop_time = 0
        configured_cooldown = audio_config.get('speech_cooldown', 2.0)
        try:
            configured_cooldown = float(configured_cooldown)
        except Exception:
            configured_cooldown = 2.0
        self.speech_cooldown = max(1.0, configured_cooldown)

        self.memory = s.service("ALMemory")
        self.tts_subscriber = self.memory.subscriber("ALTextToSpeech/Status")
        self.anim_subscriber = self.memory.subscriber("ALAnimatedSpeech/Status")
        self.anim_subscriber_id = self.anim_subscriber.signal.connect(self.on_tts_status)
        self.tts_subscriber_id = self.tts_subscriber.signal.connect(self.on_tts_status)

        self.mon, self.pre, self.rec = [], [], []
        self.on = False # This is for recording state
        self.maxpre = self.preroll_chunks
        self.log("[AUDIO] Listener initialized: %s" % self.name, level='info')

    def start(self):
        """Subscribes to the audio device."""
        if self.is_subscribed:
            return
        self.log("[AUDIO] Subscribing to ALAudioDevice...", level='info')
        freed = _free_audio_slots(self.ad)
        if freed:
            self.log("[AUDIO] Unsubscribed orphan clients: %s" % ", ".join(freed), level='warning')
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
        self.is_subscribed = True
        self.log("[AUDIO] Subscribed to ALAudioDevice.", level='info')

    def stop(self):
        """Unsubscribes from the audio device."""
        if not self.is_subscribed:
            return
        self.log("[AUDIO] Unsubscribing from ALAudioDevice...", level='info')
        try:
            self.ad.unsubscribe(self.name)
            self.is_subscribed = False
            self.log("[AUDIO] Unsubscribed from ALAudioDevice.", level='info')
        except Exception as e:
            self.log(f"[AUDIO] Error unsubscribing: {e}", level='error')

    def on_tts_status(self, status):
        if not isinstance(status, (list, tuple)) or len(status) < 2:
            return
        status_string = status[1]
        with self.lock:
            if status_string == 'started':
                self.speaking = True
                self.mon[:] = []
                self.pre[:] = []
            elif status_string == 'done':
                self.speaking = False
                self.speech_stop_time = time.time()
                self.pre = list(self.mon[-self.maxpre:])

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
            micro_on = self.microEnabled.get("on", True)
            is_recording = self.on

        time_since_stop = time.time() - stop_time

        if is_speaking or (time_since_stop < self.speech_cooldown) or not micro_on:
            return

        with self.lock:
            self.mon.append(buf)
            self.pre.append(buf)
            if len(self.mon) > 24: self.mon = self.mon[-24:]
            if len(self.pre) > self.maxpre: self.pre = self.pre[-self.maxpre:]
            if is_recording: self.rec.append(buf)

    def get_last_audio_chunk(self):
        with self.lock:
            if not self.mon:
                return b''
            return self.mon[-1]

    def start_recording(self):
        self.rec = list(self.pre)
        self.on = True
        self.log("[REC] START pre=%d" % len(self.rec), level='debug')

    def stop_recording(self, stop_thr):
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
        self.stop()
        try:
            self.tts_subscriber.signal.disconnect(self.tts_subscriber_id)
        except Exception:
            pass
        try:
            self.anim_subscriber.signal.disconnect(self.anim_subscriber_id)
        except Exception:
            pass
