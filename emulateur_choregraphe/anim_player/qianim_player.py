#!/usr/bin/env python
# -*- coding: ascii -*-
"""
qianim_player.py
Simple QiAnimation player with a class named QianimPlayer.
- XML (namespace-aware) and JSON formats supported
- No global speed scaling, no unit conversion
- Ensures strictly increasing times
- Soft pre-position to the first key (respecting joint max velocities), then plays the animation as-is
"""

import os
import json
import xml.etree.ElementTree as ET

from random_control import disable_random_modules, enable_random_modules
from audio_control import play_audio_if_exists, stop_audio


class QianimPlayer(object):
    def __init__(self, session, qianim_path, audio_override=None):
        self.session = session
        self.qianim_path = qianim_path
        self.audio_override = audio_override
        # services
        self.motion = session.service("ALMotion")
        # audio service best-effort
        try:
            self.audio = session.service("ALAudioPlayer")
        except Exception:
            try:
                self.audio = session.service("ALSoundPlayer")
            except Exception:
                self.audio = None

    # ---------- parsing ----------
    def _parse_xml(self, path):
        print("[QIANIM] Parsing XML:", path)
        tree = ET.parse(path)
        root = tree.getroot()

        # namespace-aware findall
        if '}' in root.tag:
            ns_uri = root.tag.split('}')[0].strip('{')
            ns = {'ns': ns_uri}
            def findall(node, pattern):
                return node.findall(pattern, ns)
        else:
            def findall(node, pattern):
                return node.findall(pattern.replace("ns:", ""))

        # fps: editor:fps or Timeline fps, else 25.0
        fps = 25.0
        try:
            fps = float(root.attrib.get('editor:fps', 25))
        except Exception:
            pass
        if not fps or fps <= 0:
            try:
                tl = findall(root, ".//ns:Timeline")
                if tl:
                    val = tl[0].attrib.get("fps")
                    if val:
                        fps = float(val)
            except Exception:
                pass
        if not fps or fps <= 0:
            fps = 25.0

        names, angleLists, timeLists = [], [], []
        for curve in findall(root, ".//ns:ActuatorCurve"):
            actuator = curve.attrib.get("actuator")
            keys = findall(curve, "ns:Key")
            if not actuator or not keys:
                continue
            times, angles = [], []
            last_t = 0.0
            for key in keys:
                try:
                    frame = float(key.attrib.get("frame", "0"))
                    val = float(key.attrib.get("value", "0"))
                except Exception:
                    continue
                t = round(frame / max(1e-6, fps), 3)
                if t <= 0.0:
                    t = 0.1
                if t <= last_t:
                    t = round(last_t + 0.01, 3)
                times.append(t)
                angles.append(val)
                last_t = t
            names.append(actuator)
            angleLists.append(angles)
            timeLists.append(times)
        return names, angleLists, timeLists

    def _parse_json(self, path):
        print("[QIANIM] Parsing JSON:", path)
        obj = json.load(open(path, "r"))
        if not isinstance(obj, dict) or "actuators" not in obj:
            raise ValueError("QiAnimation JSON expected")
        names, angleLists, timeLists = [], [], []
        for act in obj.get("actuators", []):
            name = act.get("name")
            keys = act.get("keys") or []
            if not name or not keys:
                continue
            times, angles = [], []
            last_t = 0.0
            for k in keys:
                if isinstance(k, (list, tuple)) and len(k) >= 2:
                    t = float(k[0]); val = float(k[1])
                elif isinstance(k, dict):
                    t = float(k.get("t", k.get("time", 0.0)))
                    val = float(k.get("value", k.get("angle", 0.0)))
                else:
                    continue
                if t <= 0.0:
                    t = 0.1
                if t <= last_t:
                    t = round(last_t + 0.01, 3)
                times.append(t)
                angles.append(val)
                last_t = t
            names.append(name)
            angleLists.append(angles)
            timeLists.append(times)
        return names, angleLists, timeLists

    def parse_qianim(self):
        # detect JSON vs XML by first byte
        first = open(self.qianim_path, "rb").read(1)
        if first in (b"{", b"["):
            return self._parse_json(self.qianim_path)
        return self._parse_xml(self.qianim_path)

    # ---------- run ----------
    def run(self):
        # prepare robot and cut random modules
        disable_random_modules(self.session)

        audio_thread = play_audio_if_exists(self.audio, self.qianim_path, override=self.audio_override)

        try:
            names, angleLists, timeLists = self.parse_qianim()
            if not names:
                print("[QIANIM] No valid curves found.")
                return

            # amplitude debug
            print("[QIANIM] Joints:", ", ".join(names))
            for i, n in enumerate(names):
                if angleLists[i]:
                    amin = min(angleLists[i]); amax = max(angleLists[i])
                    print("[QIANIM] {0:<16s} keys={1} amp=[{2:.3f},{3:.3f}]".format(n, len(angleLists[i]), amin, amax))

            # soft pre-position on first key (respect joint max velocity), do not change animation timings
            try:
                cur = self.motion.getAngles(names, True)
                first_targets = [alist[0] for alist in angleLists]
                safety = 0.98
                Tlead = 0.0
                for n, a0, c0 in zip(names, first_targets, cur):
                    try:
                        lim = self.motion.getLimits(n)
                        if isinstance(lim, (list, tuple)) and lim and isinstance(lim[0], (list, tuple)):
                            lim = lim[0]
                        vmax = float(lim[2]) * safety
                        need = abs(a0 - c0) / max(1e-6, vmax)
                        if need > Tlead:
                            Tlead = need
                    except Exception:
                        pass
                if Tlead < 0.25:
                    Tlead = 0.25
                if Tlead > 2.0:
                    Tlead = 2.0
                self.motion.angleInterpolation(
                    names,
                    [[t] for t in first_targets],
                    [[Tlead] for _ in names],
                    True
                )
            except Exception as e:
                print("[QIANIM] pre-position skipped:", e)

            if audio_thread:
                audio_thread.start()

            print("[QIANIM] angleInterpolation start ({0} joints)".format(len(names)))
            self.motion.angleInterpolation(names, angleLists, timeLists, True)
            print("[QIANIM] Animation done.")
        except Exception as e:
            print("[QIANIM][ERROR]:", e)
        finally:
            try:
                stop_audio(self.audio, None)
            except Exception:
                pass
            enable_random_modules(self.session)
