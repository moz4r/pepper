# -*- coding: utf-8 -*-
# classASRFilters.py — heuristiques anti-bruit / anti-écho

import time, re, unicodedata

def _norm_text(t):
    if not t: return ""
    t = unicodedata.normalize("NFD", t).lower()
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    t = t.replace("’", "'")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def is_noise_utterance(txt, blacklist_strict):
    n = _norm_text(txt)
    if not n: return True
    if n in blacklist_strict: return True
    if len(n) <= 3: return True
    if " " not in n and len(n) <= 5: return True
    if n.endswith(".") and len(n) <= 8: return True
    return False

_NOISE_RECENCY = {"last_norm": "", "t": 0.0}
def is_recent_duplicate(txt, window=2.0):
    n = _norm_text(txt); now = time.time()
    if n and n == _NOISE_RECENCY["last_norm"] and (now - _NOISE_RECENCY["t"]) < window:
        return True
    _NOISE_RECENCY["last_norm"] = n; _NOISE_RECENCY["t"] = now
    return False
