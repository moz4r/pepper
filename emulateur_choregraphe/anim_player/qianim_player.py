#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qianim_player.py — QiAnimation player (Python 2.7 compatible)

Features:
- Parse .qianim (JSON or XML with ActuatorCurve/Key)
- Decide ONCE per file if keys are in degrees or radians (global decision)
- Convert if needed, then clamp to joint limits
- Filter out joints unsupported by the robot (e.g., legs on Pepper)
- Soft pre-position to first key, then angleInterpolation
- Back-compat: run() alias -> play()
"""

import os
import math
import json
import xml.etree.ElementTree as ET

from random_control import disable_random_modules, enable_random_modules
from services import get_robot_services
from audio_control import play_audio_if_exists, stop_audio

class QianimPlayer(object):
    def __init__(self, session, qianim_path, audio_override=None, soft_preposition=True, strict_limits=True, allow_unsupported=True):
        self.session = session
        self.qianim_path = qianim_path
        self.audio_override = audio_override
        self.soft_preposition = soft_preposition

        self.motion = None
        self.life = None
        self.tts = None
        self.audio = None

        self.strict_limits = strict_limits
        self.allow_unsupported = allow_unsupported

        srv = get_robot_services(session)
        self.motion = srv[0] if len(srv) > 0 else None
        self.life   = srv[1] if len(srv) > 1 else None
        self.tts    = srv[2] if len(srv) > 2 else None
        self.audio  = srv[3] if len(srv) > 3 else None

        self._unit_mode = "rad"

    # ---------- Parsing ----------

    def _ns_findall(self, node, pattern):
        # helper namespace-aware findall with optional "ns:" prefix
        # If root has a namespace, pattern can contain "ns:" which we replace
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
        tree = ET.parse(path)
        root = tree.getroot()

        # fps
        fps = 25.0
        try:
            attr = root.attrib.get("editor:fps")
            if attr:
                fps = float(attr)
        except Exception:
            pass
        if not fps or fps <= 0.0:
            try:
                tls = self._ns_findall(root, ".//ns:Timeline")
                if tls:
                    v = tls[0].attrib.get("fps")
                    if v:
                        fps = float(v)
            except Exception:
                pass
        if not fps or fps <= 0.0:
            fps = 25.0

        names, angleLists, timeLists = [], [], []
        # Try namespaced lookup, else localname fallback
        curves = self._ns_findall(root, ".//ns:ActuatorCurve")
        if not curves:
            # localname fallback
            curves = []
            for e in root.iter():
                try:
                    tag = e.tag.rsplit("}", 1)[-1]
                except Exception:
                    tag = e.tag
                if tag == "ActuatorCurve":
                    curves.append(e)

        for curve in curves:
            actuator = curve.attrib.get("actuator")
            if not actuator:
                continue
            # Keys: prefer time/angle else frame/value
            keys = self._ns_findall(curve, "ns:Key")
            if not keys:
                keys = [k for k in curve if k.tag.rsplit("}",1)[-1] == "Key"]

            times, angles = [], []
            last_t = 0.0
            for k in keys:
                t_attr = k.attrib.get("time")
                a_attr = k.attrib.get("angle")
                frame  = k.attrib.get("frame")
                value  = k.attrib.get("value")
                t = None; val = None
                if t_attr is not None and a_attr is not None:
                    try:
                        t = float(t_attr); val = float(a_attr)
                    except Exception:
                        t = None; val = None
                if (t is None) or (val is None):
                    if frame is not None and value is not None:
                        try:
                            t = float(frame) / float(fps if fps > 0.0 else 25.0)
                            val = float(value)
                        except Exception:
                            t = None; val = None
                if t is None or val is None:
                    continue

                if t <= 0.0: t = 0.1
                if t <= last_t: t = round(last_t + 0.01, 3)
                times.append(t); angles.append(val); last_t = t

            if times and angles:
                names.append(actuator); angleLists.append(angles); timeLists.append(times)

        return names, angleLists, timeLists

    def _parse_json(self, path):
        with open(path, "r") as f:
            obj = json.load(f)
        if not isinstance(obj, dict) or "actuators" not in obj:
            raise ValueError("QiAnimation JSON expected: missing 'actuators' key")
        names, angleLists, timeLists = [], [], []
        acts = obj.get("actuators", [])
        for act in acts:
            name = act.get("name")
            keys = act.get("keys") or []
            if not name or not isinstance(keys, list):
                continue
            times, angles = [], []
            last_t = 0.0
            for k in keys:
                if isinstance(k, list) and len(k) >= 2:
                    t, val = float(k[0]), float(k[1])
                elif isinstance(k, dict):
                    t = float(k.get("t", k.get("time", 0.0)))
                    val = float(k.get("v", k.get("value", k.get("angle", 0.0))))
                else:
                    continue
                if t <= 0.0: t = 0.1
                if t <= last_t: t = round(last_t + 0.01, 3)
                times.append(t); angles.append(val); last_t = t
            if times and angles:
                names.append(name); angleLists.append(angles); timeLists.append(times)
        return names, angleLists, timeLists

    def parse_qianim(self):
        path = self.qianim_path
        if not os.path.isfile(path):
            raise IOError("QiAnimation path not found: %s" % path)
        lower = path.lower()
        # Try JSON first for .qianim, then XML
        try:
            if lower.endswith(".json") or lower.endswith(".qianim.json"):
                return self._parse_json(path)
            elif lower.endswith(".qianim") or lower.endswith(".xml"):
                try:
                    return self._parse_json(path)
                except Exception:
                    return self._parse_xml(path)
            else:
                try:
                    return self._parse_json(path)
                except Exception:
                    return self._parse_xml(path)
        except Exception as e:
            print("[QIANIM] parse error:", e)
            raise

    # ---------- Limits / units / filtering ----------

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
        if lo is None or hi is None:
            if self.strict_limits:
                raise RuntimeError("No limits for joint '%s' from ALMotion (strict mode)" % name)
        return lo, hi

    def _interpret_units_global(self, names, angleLists):
        """Decide once: 'rad' vs 'deg' based on joint limits across all joints (ignore Hands)."""
        total_rad = 0.0
        total_deg = 0.0
        for name, vals in zip(names, angleLists):
            if not vals:
                continue
            if "Hand" in (name or ""):
                continue
            lo, hi = self._get_limits(name)
            if lo is None or hi is None:
                # cannot score this joint; skip
                continue
            # Score raw (rad) vs deg->rad hypothesis
            for v in vals:
                if v < lo: total_rad += (lo - v)
                elif v > hi: total_rad += (v - hi)
                v2 = math.radians(v)
                if v2 < lo: total_deg += (lo - v2)
                elif v2 > hi: total_deg += (v2 - hi)
        mode = "deg" if total_deg < total_rad else "rad"
        print("[QIANIM] Global unit decision:", mode, "(score rad=%.4f, deg=%.4f)" % (total_rad, total_deg))
        return mode

    def _clamp_to_limits(self, name, values):
        lo, hi = self._get_limits(name)
        if lo is None or hi is None:
            return list(values)
        eps = 1e-6
        out = []
        for v in values:
            if v < lo + eps: v = lo + eps
            if v > hi - eps: v = hi - eps
            out.append(v)
        return out

    def _get_supported_joints(self):
        names = []
        try:
            if self.motion:
                try:
                    names = self.motion.getBodyNames("Body")
                except Exception:
                    names = self.motion.getJointNames("Body")
        except Exception:
            names = []
        try:
            return set(names)
        except Exception:
            return set()

    def _filter_supported(self, names, angleLists, timeLists):
        supported = self._get_supported_joints()
        if not supported:
            return names, angleLists, timeLists
        kept_n, kept_a, kept_t = [], [], []
        dropped = []
        for n, a, t in zip(names, angleLists, timeLists):
            if n in supported:
                kept_n.append(n); kept_a.append(a); kept_t.append(t)
            else:
                dropped.append(n)
        if dropped:
            if not self.allow_unsupported:
                raise RuntimeError("Unsupported joints (strict): " + ", ".join(dropped))
            print("[QIANIM] Dropped unsupported joints: " + ", ".join(dropped))
        return kept_n, kept_a, kept_t

    def _soft_preposition(self, names, angleLists, timeLists):
        if not (self.motion and names):
            return
        try:
            first_angles = []
            for name, angles in zip(names, angleLists):
                if not angles:
                    first_angles.append(0.0)
                    continue
                v = float(angles[0])
                lo, hi = self._get_limits(name)
                if lo is not None and hi is not None:
                    eps = 1e-6
                    if v < lo + eps: v = lo + eps
                    if v > hi - eps: v = hi - eps
                first_angles.append(v)
            self.motion.angleInterpolationWithSpeed(names, first_angles, 0.2)
        except Exception as e:
            print("[QIANIM] Pre-position skipped:", e)

    def _prepare_lists(self, names, angleLists, timeLists):
        new_names, new_angles, new_times = [], [], []
        self._unit_mode = self._interpret_units_global(names, angleLists)
        for name, angles, times in zip(names, angleLists, timeLists):
            a2 = list(angles)
            if "Hand" not in (name or "") and self._unit_mode == "deg":
                a2 = [math.radians(v) for v in a2]
            a2 = self._clamp_to_limits(name, a2)
            new_names.append(name); new_angles.append(a2); new_times.append(times)
        return new_names, new_angles, new_times

    def _log_summary(self, names, angleLists):
        try:
            print("[QIANIM] Joints:", ", ".join(names))
            for n, a in zip(names, angleLists):
                if not a: 
                    continue
                mn, mx = min(a), max(a)
                # On affiche les amplitudes telles qu'elles viennent du fichier (avant conversion)
                # mais ici on est déjà après prepare; on affiche néanmoins pour debug
                print("[QIANIM] %-15s keys=%d amp=[%.3f,%.3f]" % (n, len(a), mn, mx))
        except Exception:
            pass

    # ---------- Play ----------

    def play(self):
        if not self.motion:
            raise RuntimeError("ALMotion service unavailable")

        names, angleLists, timeLists = self.parse_qianim()
        if self.strict_limits:
            print("[QIANIM] Strict limits: ON (no approximations)")
        else:
            print("[QIANIM] Strict limits: OFF (fallback table allowed)")
        print("[QIANIM] Parsing XML:" if self.qianim_path.lower().endswith((".qianim",".xml")) else "[QIANIM] Parsing JSON:", self.qianim_path)

        # Units + clamp then filter
        names, angleLists, timeLists = self._prepare_lists(names, angleLists, timeLists)
        names, angleLists, timeLists = self._filter_supported(names, angleLists, timeLists)

        # Log post-check ranges
        self._log_summary(names, angleLists)

        audio_id_holder = {"id": None}
        try:
            disable_random_modules(self.session)

            if self.audio:
                def store_id(i):
                    audio_id_holder["id"] = i
                play_audio_if_exists(self.audio, self.qianim_path, override=self.audio_override, store_id_callback=store_id)

            if self.soft_preposition:
                self._soft_preposition(names, angleLists, timeLists)

            print("[QIANIM] angleInterpolation start ({0} joints)".format(len(names)))
            self.motion.angleInterpolation(names, angleLists, timeLists, True)
            print("[QIANIM] Animation done.")
        except Exception as e:
            print("[QIANIM][ERROR]:", e)
            raise
        finally:
            try:
                stop_audio(self.audio, audio_id_holder.get("id"))
            except Exception:
                pass
            enable_random_modules(self.session)

    # Back-compat
    def run(self):
        return self.play()
