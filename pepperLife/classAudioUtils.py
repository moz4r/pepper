# -*- coding: utf-8 -*-
# classAudioUtils.py — utilitaires audio (16-bit PCM LE)

def avgabs(b):
    if not b: return 0
    s=n=0; L=len(b)
    for i in range(0, L-1, 2):
        v = b[i] | (b[i+1] << 8)
        if v >= 32768: v -= 65536
        if v < 0: v = -v
        s += v; n += 1
    return s//n if n else 0

def peakabs(b):
    if not b: return 0
    m=0; L=len(b)
    for i in range(0, L-1, 2):
        v = b[i] | (b[i+1] << 8)
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
        v = raw[i] | (raw[i+1] << 8)
        if v >= 32768: v -= 65536
        w = int(v * k)
        if   w >  32767: w =  32767
        elif w < -32768: w = -32768
        if w < 0: w += 65536
        out.append(w & 0xFF); out.append((w>>8) & 0xFF)
    return bytes(out)

def trim_tail_silence(raw, stop_thr, frame_ms=20, max_trim_ms=600, sr=16000):
    if not raw: return raw
    step = int(sr * frame_ms / 1000.0) * 2
    cut = 0; L=len(raw); max_steps = int(max_trim_ms / float(frame_ms))
    for _ in range(max_steps):
        a = L - cut - step
        if a <= 0: break
        if avgabs(raw[a:a+step]) >= stop_thr: break
        cut += step
    return raw[:L-cut] if cut>0 else raw
