#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qianim_player.py — Unified animation player (Python 2.7)
- Joue des .qianim (JSON/XML) ou XAR (.pml / behavior.xar) via xar_parser.parse_xar
- Gère l'ANIMATION (pré-position, units, clamp, interpolation)
- Gère l'AUDIO si audio_override fourni (sinon pas d'audio ici)
- Pas de wakeUp/rest : random_control s'occupe du contexte (stiffness, modules…)
"""

import os
import json
import math
import time as _t
import xml.etree.ElementTree as ET

from services import get_robot_services
from random_control import disable_random_modules, enable_random_modules
from audio_control import play_audio_if_exists, stop_audio
from xar_parser import parse_xar  # stable parser côté projet

# --- Player tuning flags ---
ENABLE_PREPOSITION = True   # disable to skip slow joint-by-joint pre-position
PREPOSITION_SPEED = 1    # speed used if ENABLE_PREPOSITION=True
START_BOOST = True           # send a fast setAngles to first keys
START_BOOST_SPEED = 0.2    # fraction of max speed for the boost
START_MIN_OFFSET = 0      # ensure at least this lead-in before t0


class QianimPlayer(object):
    def __init__(self, session, anim_path, audio_override=None, on_start=None):
        self.session = session
        self.anim_path = anim_path
        self.audio_override = audio_override  # chemin audio explicite (ou None)
        self.on_start = on_start              # callback externe optionnel

        srv = get_robot_services(session)
        self.motion  = srv[0] if len(srv) > 0 else None
        self.life    = srv[1] if len(srv) > 1 else None
        self.tts     = srv[2] if len(srv) > 2 else None
        self.audio   = srv[3] if len(srv) > 3 else None
        self.posture = srv[4] if len(srv) > 4 else None

        self._unit_mode = "rad"

    # ---------- QiAnim parsing ----------
    def _ns_findall(self, node, pattern):
        try:
            tag = node.tag
            if isinstance(tag, basestring) and tag.startswith("{"):
                nsuri = tag.split("}")[0].strip("{")
            else:
                nsuri = None
        except Exception:
            nsuri = None
        if nsuri and "ns:" in pattern:
            pattern = pattern.replace("ns:", "{%s}" % nsuri)
        else:
            pattern = pattern.replace("ns:", "")
        return node.findall(pattern)

    def _parse_xml(self, path):
        print("[QIANIM] Parsing XML: %s" % path)
        tree = ET.parse(path)
        root = tree.getroot()

        fps = 25.0
        try:
            val = root.attrib.get('editor:fps')
            if val: fps = float(val)
        except Exception:
            pass
        if not fps or fps <= 0.0:
            try:
                tl = self._ns_findall(root, ".//ns:Timeline")
                if tl:
                    val = tl[0].attrib.get("fps")
                    if val: fps = float(val)
            except Exception:
                pass
        if not fps or fps <= 0.0:
            fps = 25.0

        names, angleLists, timeLists = [], [], []
        curves = self._ns_findall(root, ".//ns:ActuatorCurve")
        if not curves:
            for e in root.iter():
                try: tag = e.tag.rsplit("}", 1)[-1]
                except Exception: tag = e.tag
                if tag == "ActuatorCurve":
                    curves.append(e)

        for curve in curves:
            actuator = curve.attrib.get("actuator")
            if not actuator: continue
            keys = self._ns_findall(curve, "ns:Key")
            if not keys:
                keys = [k for k in curve if k.tag.rsplit("}", 1)[-1] == "Key"]

            times, angles = [], []
            last_t = 0.0
            for key in keys:
                t_attr = key.attrib.get("time")
                a_attr = key.attrib.get("angle")
                frame  = key.attrib.get("frame")
                value  = key.attrib.get("value")
                t = None; val = None
                if t_attr is not None and a_attr is not None:
                    try: t = float(t_attr); val = float(a_attr)
                    except Exception: t = None; val = None
                if (t is None) or (val is None):
                    if frame is not None and value is not None:
                        try:
                            t = float(frame) / float(fps if fps > 0.0 else 25.0)
                            val = float(value)
                        except Exception:
                            t = None; val = None
                if t is None or val is None: continue
                if t <= 0.0: t = 0.1
                if t <= last_t: t = round(last_t + 0.01, 3)
                times.append(t); angles.append(val); last_t = t
            if times and angles:
                names.append(actuator); angleLists.append(angles); timeLists.append(times)

        return names, angleLists, timeLists

    def _parse_json(self, path):
        print("[QIANIM] Parsing JSON: %s" % path)
        obj = json.load(open(path, "r"))
        if not isinstance(obj, dict) or "actuators" not in obj:
            raise ValueError("QiAnimation JSON expected")
        names, angleLists, timeLists = [], [], []
        for act in obj.get("actuators", []):
            name = act.get("name")
            keys = act.get("keys") or []
            if not name or not keys: continue
            times, angles = [], []
            last_t = 0.0
            for k in keys:
                if isinstance(k, (list, tuple)) and len(k) >= 2:
                    t = float(k[0]); val = float(k[1])
                elif isinstance(k, dict):
                    t = float(k.get("t", k.get("time", 0.0)))
                    val = float(k.get("v", k.get("value", k.get("angle", 0.0))))
                else:
                    continue
                if t <= 0.0: t = 0.1
                if t <= last_t: t = round(last_t + 0.01, 3)
                times.append(t); angles.append(val); last_t = t
            names.append(name); angleLists.append(angles); timeLists.append(times)
        return names, angleLists, timeLists

    # ---------- input detection ----------
    def _find_xar_xml_in_dir(self, folder):
        # priorité: *.pml, puis behavior.xar / *.xar, sinon récursif
        for name in ("timeline.pml", "behavior.xar"):
            p = os.path.join(folder, name)
            if os.path.isfile(p):
                return p
        for fn in os.listdir(folder):
            if fn.lower().endswith(".pml"):
                return os.path.join(folder, fn)
        for fn in os.listdir(folder):
            if fn.lower().endswith(".xar"):
                return os.path.join(folder, fn)
        for root, _, files in os.walk(folder):
            for fn in files:
                if fn.lower().endswith((".pml", ".xar")):
                    return os.path.join(root, fn)
        return None

    def parse_any(self):
        """Parse qianim (json/xml) or XAR (pml/xar) and return (names, angles, times, source)."""
        path = self.anim_path
        if not os.path.exists(path):
            raise IOError("Animation path not found: %s" % path)
        lower = path.lower()

        if os.path.isdir(path):
            xml_path = self._find_xar_xml_in_dir(path)
            if not xml_path:
                print("[QIANIM] No XAR XML found in folder:", path)
                return [], [], [], "xar"
            try:
                names, angles, times = parse_xar(xml_path, self.tts, self.motion)
            except Exception as e:
                print("[ERROR] Impossible de parser le XAR:", e)
                return [], [], [], "xar"
            print("[QIANIM] (XAR mode via parse_xar)")
            return names, angles, times, "xar"

        if lower.endswith((".xar", ".pml")):
            try:
                names, angles, times = parse_xar(path, self.tts, self.motion)
            except Exception as e:
                print("[ERROR] Impossible de parser le XAR:", e)
                return [], [], [], "xar"
            print("[QIANIM] (XAR mode via parse_xar)")
            return names, angles, times, "xar"

        # sinon: .qianim/.json/.xml
        try:
            if lower.endswith(".json") or lower.endswith(".qianim.json"):
                nm, al, tl = self._parse_json(path); what = "qianim"
            elif lower.endswith(".qianim") or lower.endswith(".xml"):
                try:
                    nm, al, tl = self._parse_json(path); what = "qianim"
                except Exception:
                    nm, al, tl = self._parse_xml(path);  what = "qianim"
            else:
                try:
                    nm, al, tl = self._parse_json(path); what = "qianim"
                except Exception:
                    nm, al, tl = self._parse_xml(path);  what = "qianim"
            return nm, al, tl, what
        except Exception as e:
            print("[QIANIM] parse error:", e)
            raise

    # ---------- limits / units ----------
    def _get_limits(self, name):
        lo = hi = None
        try:
            if self.motion:
                try:
                    lim = self.motion.getLimits([name])
                    if isinstance(lim, (list, tuple)) and lim:
                        first = lim[0]
                        if isinstance(first, (list, tuple)) and len(first) >= 2:
                            lo, hi = float(first[0]), float(first[1])
                except Exception:
                    pass
                if lo is None or hi is None:
                    lim = self.motion.getLimits(name)
                    if isinstance(lim, (list, tuple)) and lim:
                        if isinstance(lim[0], (list, tuple)):
                            lo, hi = float(lim[0][0]), float(lim[0][1])
                        elif len(lim) >= 2:
                            lo, hi = float(lim[0]), float(lim[1])
        except Exception:
            pass
        return lo, hi

    def _clamp(self, name, values, eps=1e-4):
        lo, hi = self._get_limits(name)
        vals = list(values)
        if lo is None or hi is None:
            return vals
        out = []
        for v in vals:
            if v < lo + eps: v = lo + eps
            if v > hi - eps: v = hi - eps
            out.append(v)
        return out

    def _unit_decision_global(self, names, angleLists):
        tot_rad = 0.0; tot_deg = 0.0; counted = 0
        for n, vals in zip(names, angleLists):
            if not vals or "Hand" in (n or ""): continue
            lo, hi = self._get_limits(n)
            if lo is None or hi is None: continue
            counted += 1
            for v in vals:
                if v < lo: tot_rad += (lo - v)
                elif v > hi: tot_rad += (v - hi)
                v2 = math.radians(v)
                if v2 < lo: tot_deg += (lo - v2)
                elif v2 > hi: tot_deg += (v2 - hi)
        if counted == 0:
            maxabs = 0.0
            for vals in angleLists:
                if vals:
                    m = max(abs(x) for x in vals); maxabs = m if m > maxabs else maxabs
            mode = "deg" if maxabs > 3.2 else "rad"
        else:
            mode = "deg" if tot_deg < tot_rad else "rad"
        print("[QIANIM] Global unit decision: %s" % mode)
        return mode

    # ---------- positioning ----------
    def _preposition_to_first(self, names, angleLists, speed=0.3):
        """Pré-position séquentielle joint-par-joint avec marge et reprise en cas d'échec."""
        if not (self.motion and names):
            return
        try:
            try:
                self.motion.waitUntilMoveIsFinished()
            except Exception:
                pass

            for name, angles in zip(names, angleLists):
                if not angles:
                    continue
                v = float(angles[0])
                lo, hi = self._get_limits(name)
                if lo is not None and hi is not None:
                    eps   = 1e-3
                    guard = 0.01
                    low   = lo + max(eps, guard)
                    high  = hi - max(eps, guard)
                    if v < low:  v = low
                    if v > high: v = high
                try:
                    self.motion.angleInterpolationWithSpeed([name], [v], float(speed))
                except Exception:
                    try:
                        if lo is not None and hi is not None:
                            v2 = min(max(v, lo + 1e-3), hi - 1e-3)
                            self.motion.angleInterpolationWithSpeed([name], [v2], float(speed))
                        else:
                            print("[QIANIM] prepos skip (no limits): %s" % name)
                            continue
                    except Exception as e2:
                        print("[QIANIM] prepos skip: %s (%s)" % (name, e2))

            try:
                self.motion.waitUntilMoveIsFinished()
            except Exception:
                pass
            _t.sleep(0.15)
        except Exception as e:
            print("[QIANIM] pre-position skipped:", e)

    # ---------- run ----------
    def run(self):
        names = []
        audio_id = {'id': None}
        disable_random_modules(self.session)

        try:
            names, angleLists, timeLists, source = self.parse_any()
            if not names:
                print("[QIANIM] No valid curves found.")
                enable_random_modules(self.session)
                return

            # Units
            if source == "xar":
                self._unit_mode = "rad"
            else:
                self._unit_mode = self._unit_decision_global(names, angleLists)

            conv_angles = []
            for n, a in zip(names, angleLists):
                a2 = list(a)
                if source != "xar" and "Hand" not in (n or "") and self._unit_mode == "deg":
                    a2 = [math.radians(v) for v in a2]
                a2 = self._clamp(n, a2, eps=1e-4)
                conv_angles.append(a2)
            angleLists = conv_angles
            # --- Fast start boost and time lead-in ---
            try:
                if START_BOOST and self.motion:
                    names_boost = []
                    angles_boost = []
                    for n, a in zip(names, angleLists):
                        if a:
                            names_boost.append(n)
                            angles_boost.append(float(a[0]))
                    if names_boost:
                        self.motion.setAngles(names_boost, angles_boost, float(START_BOOST_SPEED))
                        print('[QIANIM] start boost: setAngles to first keys @%.2f' % float(START_BOOST_SPEED))
            except Exception as e:
                print('[QIANIM] start boost skipped:', e)

            # Ensure a small time lead-in so the boost can progress before timed interp
            try:
                if not (START_BOOST and float(START_MIN_OFFSET) > 0):
                    raise Exception('offset disabled (guard)')
                t0 = None
                for tl in timeLists:
                    if tl:
                        t0 = tl[0] if t0 is None else min(t0, tl[0])
                ofs = 0.0
                if t0 is None:
                    ofs = 0.0
                else:
                    if float(t0) < float(START_MIN_OFFSET):
                        ofs = float(START_MIN_OFFSET) - float(t0)
                if ofs > 0.0:
                    timeLists = [[float(v)+ofs for v in tl] if tl else tl for tl in timeLists]
                    print('[QIANIM] start offset: +%.3fs' % ofs)
            except Exception as e:
                print('[QIANIM] start offset skipped:', e)


            print("[QIANIM] Joints: %s" % ", ".join(names))
            for i, n in enumerate(names):
                if angleLists[i]:
                    amin = min(angleLists[i]); amax = max(angleLists[i])
                    print("[QIANIM] %-16s keys=%d amp=[%.3f,%.3f]" % (n, len(angleLists[i]), amin, amax))

            # Pré-position (optional)
            if ENABLE_PREPOSITION:
                self._preposition_to_first(names, angleLists, speed=PREPOSITION_SPEED)
                try:
                    if self.motion: self.motion.waitUntilMoveIsFinished()
                except Exception:
                    pass
                _t.sleep(0.05)
            else:
                print('[QIANIM] pre-position disabled')
            try:
                if self.motion: self.motion.waitUntilMoveIsFinished()
            except Exception:
                pass
            _t.sleep(0.15)

            # Démarrage audio au début réel de l'interpolation
            try:
                if callable(self.on_start):
                    self.on_start()
            except Exception:
                pass
            if self.audio and self.audio_override:
                print('[AUDIO] start ->', self.audio_override)
                th = play_audio_if_exists(self.audio, self.anim_path, override=self.audio_override,
                                          store_id_callback=lambda i: audio_id.__setitem__('id', i))
                if th:
                    try: th.start()
                    except Exception: pass
            else:
                print('[AUDIO] no audio_override or no audio service')

            print("[QIANIM] angleInterpolation start (%d joints)" % len(names))
            self.motion.angleInterpolation(names, angleLists, timeLists, True)

            try:
                if self.motion:
                    self.motion.stopMove()
                    print("[QIANIM] stopMove() right after animation")
            except Exception:
                pass
            try:
                if self.motion: self.motion.waitUntilMoveIsFinished()
            except Exception:
                pass
            _t.sleep(0.35)
            print("[QIANIM] Animation done.")
        except Exception as e:
            print("[QIANIM][ERROR]: %s" % e)
        finally:
            try:
                stop_audio(self.audio, audio_id.get('id'))
            except Exception:
                pass
            try:
                if self.motion:
                    self.motion.waitUntilMoveIsFinished()
            except Exception:
                pass
            enable_random_modules(self.session)

    # compat
    def play(self):
        return self.run()

    def __call__(self):
        return self.run()
