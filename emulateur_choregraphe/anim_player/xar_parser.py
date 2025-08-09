#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import xml.etree.ElementTree as ET
import math

# Optionally allow a global speed factor (e.g., 1.0 normal, 0.5 twice as fast, 2.0 half speed)
SPEED_FACTOR = float(os.environ.get("XAR_SPEED_FACTOR", "1.0"))

def parse_xar(xar_path, tts, motion):
    """
    Lit un fichier .xar et renvoie (names, angleLists, timeLists) prêts pour ALMotion.angleInterpolation.
    - Calcule le FPS *par courbe* via la Timeline parente pour respecter la vitesse originale.
    - Évite de sur-arrondir les timestamps (précision 3 décimales).
    - Applique SPEED_FACTOR sur les temps (1.0 = vitesse originale).
    """
    try:
        tree = ET.parse(xar_path)
        root = tree.getroot()
    except Exception as e:
        print("[ERROR] Impossible de parser le XAR:", e)
        return [], [], []

    names, angleLists, timeLists = [], [], []
    ns = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}

    # --- Construire une table: courbe -> fps de sa Timeline parente ---
    def findall(pat):
        return root.findall(pat, ns) if ns else root.findall(pat.replace("ns:", ""))

    # Collecte des timelines avec leur fps (ignore fps invalides)
    timelines = findall(".//ns:Timeline")
    timeline_fps = []
    for t in timelines:
        raw = t.attrib.get("fps")
        try:
            f = float(raw)
        except (TypeError, ValueError):
            f = None
        if f and f > 0:
            timeline_fps.append((t, f))

    # Table d'association id(courbe) -> fps
    curve_fps = {}
    for t, f in timeline_fps:
        curves_under_tl = t.findall(".//ns:ActuatorCurve", ns) if ns else t.findall(".//ActuatorCurve")
        for c in curves_under_tl:
            curve_fps[id(c)] = f

    # Fallback global
    fallback_fps = max([f for (_, f) in timeline_fps], default=25.0) if timeline_fps else 25.0

    uniq = sorted({f for (_, f) in timeline_fps}) or [fallback_fps]
    print("[DEBUG] FPS détectés par Timeline :", ", ".join(str(x) for x in uniq))

    # TTS depuis les boîtes "Say"
    boxes = findall(".//ns:Box")
    for box in boxes:
        if box.attrib.get("name") == "Say":
            params = {p.attrib.get('name'): p.attrib.get('value', '') for p in (box.findall("ns:Parameter", ns) if ns else box.findall("Parameter"))}
            text = params.get("Text", "")
            speed = params.get("Speed (%)", "100")
            shaping = params.get("Voice shaping (%)", "100")
            sentence = "\\RSPD={}\\ \\VCT={}\\ {} \\RST\\".format(speed, shaping, text)
            use_blocking = any(r.attrib.get('type') == 'Lock' for r in (box.findall("ns:Resource", ns) if ns else box.findall("Resource")))
            try:
                if use_blocking:
                    print("[XAR] TTS (bloquant):", text)
                    tts.say(sentence)
                else:
                    print("[XAR] TTS (non bloquant):", text)
                    tts.post.say(sentence)
            except Exception as e:
                print("[ERROR] Impossible d'exécuter TTS:", e)

    # Actuator curves
    curves = findall(".//ns:ActuatorCurve")
    print("----- [DEBUG] Détails des courbes par articulateur -----")
    per_act = {}
    for idx, curve in enumerate(curves):
        actuator = curve.attrib.get("actuator")
        unit = curve.attrib.get("unit", "0")
        fps = curve_fps.get(id(curve), fallback_fps)
        keys = curve.findall("ns:Key", ns) if ns else curve.findall("Key")
        if not keys or not actuator:
            continue
        frames = [float(k.attrib.get("frame")) for k in keys if "frame" in k.attrib]
        if not frames:
            continue
        fmin, fmax = min(frames), max(frames)
        per_act.setdefault(actuator, []).append((curve, fps, unit, len(keys), fmin, fmax))

    ignored = 0
    selected_info = {}
    for actuator, lst in per_act.items():
        print("[CURVES] {} : {} courbe(s)".format(actuator, len(lst)))
        lst_sorted = sorted(lst, key=lambda x: (x[5]-x[4], x[4]), reverse=True)
        for i, (curve, fps, unit, nk, fmin, fmax) in enumerate(lst_sorted):
            mark = " <-- ignorée (doublon)" if i > 0 else ""
            print("  - curve#{}  unit={}  keys={}  frames=[{:.0f}..{:.0f}] [{:.2f}s → {:.2f}s]  fps={}{}".format(
                i, unit, nk, fmin, fmax, fmin/float(fps), fmax/float(fps), fps, mark
            ))
        curve, fps, unit, nk, fmin, fmax = lst_sorted[0]
        selected_info[actuator] = (curve, fps, unit)
        ignored += max(0, len(lst_sorted)-1)
    print("[DEBUG] Doublons évités :", ignored)

    for actuator, (curve, fps, unit) in selected_info.items():
        keys = curve.findall("ns:Key", ns) if ns else curve.findall("Key")
        if not keys:
            continue
        ks = sorted(keys, key=lambda k: float(k.attrib["frame"]))
        times = [float(k.attrib["frame"]) / float(fps) for k in ks]
        if SPEED_FACTOR and SPEED_FACTOR > 0:
            times = [t * SPEED_FACTOR for t in times]
        values = [float(k.attrib["value"]) for k in ks]
        if unit == "0":
            values = [math.radians(v) for v in values]
        final_t, final_v = [], []
        last_t = None
        for t, v in zip(times, values):
            if (last_t is None) or (t > last_t):
                final_t.append(round(t, 3))
                final_v.append(v)
                last_t = t
        try:
            limits = motion.getLimits(actuator)
            min_angle, max_angle = limits[0][0], limits[0][1]
            vmax = limits[0][2] if len(limits[0]) > 2 else None
            safe_vals = [max(min(a, max_angle), min_angle) for a in final_v]
        except Exception:
            vmax = None
            safe_vals = final_v
        VEL_SAFETY = float(os.environ.get("XAR_VEL_SAFETY", "0.98"))
        if vmax:
            vmax_eff = vmax * VEL_SAFETY
            vmax_obs = 0.0
            for i in range(1, len(final_t)):
                dt = final_t[i] - final_t[i-1]
                if dt > 0:
                    v = abs(safe_vals[i] - safe_vals[i-1]) / dt
                    if v > vmax_obs:
                        vmax_obs = v
            if vmax_obs > vmax_eff:
                scale = vmax_obs / vmax_eff
                final_t = [round(t * scale, 3) for t in final_t]
                print("[SAFE] {}: vmax={:.3f}, obs={:.3f} -> ralentissement x{:.3f}".format(
                    actuator, vmax_eff, vmax_obs, scale
                ))
        if final_t:
            names.append(actuator)
            angleLists.append(safe_vals)
            timeLists.append(final_t)
        print("[XAR] Actuator (sélection): {}".format(actuator))
        print("   Times  :", final_t[:5], "... total", len(final_t))
        print("   Angles :", safe_vals[:5], "... total", len(safe_vals))
    return names, angleLists, timeLists
