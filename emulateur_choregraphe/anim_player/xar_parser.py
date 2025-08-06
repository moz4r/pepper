#!/usr/bin/env python
# -*- coding: utf-8 -*-

import xml.etree.ElementTree as ET
import math

FPS = 25.0

def parse_xar(xar_path, tts, motion):
    try:
        tree = ET.parse(xar_path)
        root = tree.getroot()
    except Exception as e:
        print("[ERROR] Impossible de parser le XAR:", e)
        return [], [], []

    names, angleLists, timeLists = [], [], []
    ns = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}

    boxes = root.findall(".//ns:Box", ns) if ns else root.findall(".//Box")
    for box in boxes:
        if box.attrib.get("name") == "Say":
            params = {p.attrib['name']: p.attrib.get('value', '') for p in box.findall("ns:Parameter", ns)}
            text = params.get("Text", "")
            speed = params.get("Speed (%)", "100")
            shaping = params.get("Voice shaping (%)", "100")
            sentence = "\\RSPD={}\\ \\VCT={}\\ {} \\RST\\".format(speed, shaping, text)
            use_blocking = any(r.attrib.get('type') == 'Lock' for r in box.findall("ns:Resource", ns))
            try:
                if use_blocking:
                    print("[XAR] TTS (bloquant):", text)
                    tts.say(sentence)
                else:
                    print("[XAR] TTS (non bloquant):", text)
                    tts.post.say(sentence)
            except Exception as e:
                print("[ERROR] Impossible d'exécuter TTS:", e)

    curves = root.findall(".//ns:ActuatorCurve", ns) if ns else root.findall(".//ActuatorCurve")
    for curve in curves:
        actuator = curve.attrib.get("actuator")
        unit = curve.attrib.get("unit", "0")
        if not actuator:
            continue

        keys = curve.findall("ns:Key", ns) if ns else curve.findall("Key")
        if not keys:
            continue

        times = [int(k.attrib["frame"]) / FPS for k in keys]
        angles = [float(k.attrib["value"]) for k in keys]

        if unit == "0":
            angles = [math.radians(a) for a in angles]

        norm_times, norm_angles = [], []
        last_t = -1.0
        for t, a in zip(times, angles):
            if t > last_t:
                norm_times.append(round(t, 2))
                norm_angles.append(a)
                last_t = t

        try:
            limits = motion.getLimits(actuator)
            min_angle, max_angle = limits[0][0], limits[0][1]
            safe_angles = [max(min(a, max_angle), min_angle) for a in norm_angles]
        except Exception:
            safe_angles = norm_angles

        if norm_times:
            names.append(actuator)
            angleLists.append(safe_angles)
            timeLists.append(norm_times)

        print("[XAR] Actuator:", actuator)
        print("   Times :", norm_times[:5], "... total", len(norm_times))
        print("   Angles:", safe_angles[:5], "... total", len(safe_angles))

    return names, angleLists, timeLists
