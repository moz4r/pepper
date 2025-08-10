#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import ast
import threading
import time
import math

# ---------- Compatibilité Py2/Py3 ----------
try:
    basestring  # Py2
except NameError:
    basestring = (str,)  # Py3 shim

def _is_str(x):
    try:
        return isinstance(x, basestring)
    except Exception:
        return isinstance(x, str)

def _fmt(v):
    try:
        return ("%.4f" % float(v))
    except Exception:
        return str(v)

# Vitesses physiques max (m/s, rad/s) pour normalisation -> fractions [-1,1] exigées par moveToward
MAX_VX   = float(os.environ.get("PMT_MAX_VX",   "0.50"))  # m/s
MAX_VY   = float(os.environ.get("PMT_MAX_VY",   "0.35"))  # m/s
MAX_VTH  = float(os.environ.get("PMT_MAX_VTH",  "2.00"))  # rad/s (2.0 recommandé Pepper)
SPEED_K  = float(os.environ.get("PMT_SPEED_K",  "1.00"))  # 1.0 = temps d'origine (frames & durées)

# Modes / logs
DEBUG       = os.environ.get("PMT_DEBUG", "0") in ("1","true","True","YES","yes","on","ON")
CHORE_EXACT = os.environ.get("PMT_CHORE_EXACT", "1") in ("1","true","True","YES","yes","on","ON")

def _clip01(x):
    if x > 1.0: return 1.0
    if x < -1.0: return -1.0
    return x

def _is_num(x):
    try:
        float(x)
        return True
    except Exception:
        return False

def _short(obj, limit=120):
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)
    return s if len(s) <= limit else s[:limit] + u"…"

class PMTTrajectoryPlayer(object):
    def __init__(self, session):
        self.session = session
        self.motion = session.service("ALMotion")

    # ---------- Chargement ----------
    @staticmethod
    def _load_pmt(path):
        with open(path, "rb") as f:
            s = f.read().decode("utf-8", errors="ignore").strip()
        try:
            return json.loads(s)
        except Exception:
            return ast.literal_eval(s)

    # ---------- Racine & flatten ----------
    @classmethod
    def _segments_from_root(cls, data):
        if isinstance(data, (list, tuple)) and data:
            if data[0] == "Composed":
                return list(data[1:])
            first = data[0]
            if (isinstance(first, (list, tuple)) and len(first) == 4 and all(_is_num(v) for v in first)) or                (isinstance(first, dict) and any(k in first for k in ("t","time","timestamp","x","y","theta","th","yaw"))):
                return [ {"type":"Trajectory","name":"segment_0","frames": list(data)} ]
            return list(data)
        if isinstance(data, dict):
            t = data.get("type") or data.get("Type")
            for key in ("items","children","segments","sequence","seq","parts"):
                if key in data and isinstance(data[key], (list, tuple)):
                    return list(data[key])
            if t == "Composed":
                return list(data.get("items", []))
            if t in ("Trajectory","trajectory") or any(k in data for k in ("frames","points","poses")):
                return [data]
            return [data]
        return []

    @classmethod
    def _flatten_composed(cls, seglist):
        out = []
        for seg in seglist:
            if isinstance(seg, (list, tuple)) and seg and seg[0] == "Composed":
                out.extend(cls._flatten_composed(list(seg[1:])))
                continue
            if isinstance(seg, dict) and _is_str(seg.get("type","")) and seg.get("type","").strip().lower() == "composed":
                kids = None
                for key in ("items","children","segments","sequence","seq","parts"):
                    if key in seg and isinstance(seg[key], (list, tuple)):
                        kids = list(seg[key]); break
                if kids is None:
                    kids = []
                    for v in seg.values():
                        if isinstance(v, (list, tuple)):
                            kids.extend(v if isinstance(v, list) else list(v))
                out.extend(cls._flatten_composed(kids))
                continue
            out.append(seg)
        return out

    # ---------- Attentes ----------
    def _maybe_wait(self, seg):
        if _is_num(seg):
            dur = float(seg)
            if dur > 0:
                if DEBUG:
                    print("[PMT][WAIT] sleep ", _fmt(dur / max(SPEED_K, 1e-6)), "s (scaled)")
                time.sleep(dur / max(SPEED_K, 1e-6))
            return True
        if isinstance(seg, (list, tuple)) and len(seg) >= 2 and _is_str(seg[0]) and _is_num(seg[1]):
            if seg[0].strip().lower() in ("wait","pause","sleep"):
                if DEBUG:
                    print("[PMT][WAIT] sleep ", _fmt(float(seg[1]) / max(SPEED_K, 1e-6)), "s (scaled)")
                time.sleep(float(seg[1]) / max(SPEED_K, 1e-6))
                return True
        if isinstance(seg, dict):
            ttype = seg.get("type","") or seg.get("Type","")
            if _is_str(ttype) and ttype.strip().lower() in ("wait","pause","sleep"):
                dur = seg.get("duration", seg.get("time", seg.get("t", 0)))
                if _is_num(dur) and float(dur) > 0:
                    if DEBUG:
                        print("[PMT][WAIT] sleep ", _fmt(float(dur) / max(SPEED_K, 1e-6)), "s (scaled)")
                    time.sleep(float(dur) / max(SPEED_K, 1e-6))
                    return True
        return False

    # ---------- Exécution pas ----------
    def _moveTo_chain(self, dx, dy, dtheta):
        # Pure rotation > π -> découpage en tranches < π (sinon NAOqi renormalise)
        if abs(dx) < 1e-9 and abs(dy) < 1e-9 and abs(dtheta) > math.pi:
            remain = float(dtheta)
            step_limit = math.pi - 1e-3
            if DEBUG:
                print("[PMT][moveTo] full-rot split: dtheta=", _fmt(dtheta), " -> steps of ", _fmt(step_limit))
            while abs(remain) > 1e-6:
                step = max(min(remain, step_limit), -step_limit)
                if DEBUG:
                    print("  [PMT][moveTo] step=", _fmt(step))
                try:
                    self.motion.post.moveTo(0.0, 0.0, step)
                except TypeError:
                    self.motion.post.moveTo(0.0, 0.0, step)
                self.motion.waitUntilMoveIsFinished()
                remain -= step
            return

        if DEBUG:
            print("[PMT][moveTo] dx=", _fmt(dx), " dy=", _fmt(dy), " dth=", _fmt(dtheta))
        try:
            self.motion.post.moveTo(dx, dy, dtheta)
        except TypeError:
            self.motion.post.moveTo(dx, dy, dtheta)
        self.motion.waitUntilMoveIsFinished()

    def _diag_timed(self, dx, dy, dth, dur, vx_p, vy_p, vth_p, vx_n, vy_n, vth_n):
        if not DEBUG:
            return
        print("[PMT][timed][DIAG] dur=", _fmt(dur),
              " need_phys(vx,vy,vth)=(", _fmt(vx_p), ",", _fmt(vy_p), ",", _fmt(vth_p), ")",
              " norm=(", _fmt(vx_n), ",", _fmt(vy_n), ",", _fmt(vth_n), ")",
              " MAX_V=( ", _fmt(MAX_VX), ",", _fmt(MAX_VY), ",", _fmt(MAX_VTH), " )",
              " req=(dx,dy,dth)=(", _fmt(dx), ",", _fmt(dy), ",", _fmt(dth), ")")
        # Heuristique: si grosse rotation demandée et fraction trop faible -> avertir
        try:
            need_vth = abs(float(dth)) / max(float(dur), 1e-6)
        except Exception:
            need_vth = 0.0
        frac = abs(need_vth / max(MAX_VTH, 1e-9))
        if abs(dth) > (math.pi/2.0) and frac < 0.3:
            print("[PMT][timed][WARN] vth_norm trop faible (", _fmt(frac), "). ",
                  "Augmente PMT_MAX_VTH (ex: 2.0) pour reproduire Choregraphe.")

    def _play_step_timed(self, dx, dy, dth, duration):
        # Timed => stream pendant exactement 'dur' (comme Choregraphe).
        dur = max(0.0, float(duration)) / max(SPEED_K, 1e-6)
        if dur <= 0.0:
            if DEBUG:
                print("[PMT][timed] no duration -> moveTo path")
            self._moveTo_chain(dx, dy, dth)
            return

        vx_phys  = (dx  / dur) if dur > 0 else 0.0     # m/s
        vy_phys  = (dy  / dur) if dur > 0 else 0.0     # m/s
        vth_phys = (dth / dur) if dur > 0 else 0.0     # rad/s

        # Fractions normalisées pour l'API moveToward
        vx = vx_phys / MAX_VX if MAX_VX > 0 else 0.0
        vy = vy_phys / MAX_VY if MAX_VY > 0 else 0.0
        vth = vth_phys / MAX_VTH if MAX_VTH > 0 else 0.0

        # Clip ONLY to satisfy API [-1,1]; no extra clamp in exact mode
        vx_s = _clip01(vx) if CHORE_EXACT else _clip01(vx)
        vy_s = _clip01(vy) if CHORE_EXACT else _clip01(vy)
        vth_s = _clip01(vth) if CHORE_EXACT else _clip01(vth)

        self._diag_timed(dx, dy, dth, dur, vx_phys, vy_phys, vth_phys, vx_s, vy_s, vth_s)

        try:
            self.motion.moveToward(vx_s, vy_s, vth_s)
            time.sleep(dur)
        finally:
            try:
                self.motion.stopMove()
            except Exception:
                pass
        # Pas de correction résiduelle: fidèle à Choregraphe.

    def _play_holonomic_line(self, seg):
        if not (isinstance(seg, (list, tuple)) and len(seg) >= 4 and _is_str(seg[0])):
            return False
        tag = seg[0].strip().lower()
        if tag != "holonomic":
            return False

        line = seg[1]
        dx = dy = None
        if isinstance(line, (list, tuple)) and len(line) >= 2:
            if _is_str(line[0]) and line[0].strip().lower() == "line" and isinstance(line[1], (list, tuple)) and len(line[1]) == 2:
                if _is_num(line[1][0]) and _is_num(line[1][1]):
                    dx, dy = float(line[1][0]), float(line[1][1])
            elif len(line) == 2 and _is_num(line[0]) and _is_num(line[1]):
                dx, dy = float(line[0]), float(line[1])

        if dx is None or dy is None:
            return False

        dth = float(seg[2]) if _is_num(seg[2]) else 0.0
        duration = float(seg[3]) if _is_num(seg[3]) else 0.0

        if duration > 0:
            if DEBUG:
                print("[PMT][Holonomic] dx=", _fmt(dx), " dy=", _fmt(dy), " dth=", _fmt(dth), " dur=", _fmt(duration))
            if abs(dx) < 1e-9 and abs(dy) < 1e-9 and abs(dth) < 1e-9:
                time.sleep(duration / max(SPEED_K, 1e-6))
            else:
                self._play_step_timed(dx, dy, dth, duration)
        else:
            if DEBUG:
                print("[PMT][Holonomic] moveTo path dx=", _fmt(dx), " dy=", _fmt(dy), " dth=", _fmt(dth))
            self._moveTo_chain(dx, dy, dth)
        return True

    def _extract_generic_step(self, seg):
        if isinstance(seg, (list, tuple)) and len(seg) >= 3 and all(_is_num(x) for x in seg[:3]):
            dx, dy, dth = float(seg[0]), float(seg[1]), float(seg[2])
            dur = float(seg[3]) if (len(seg) >= 4 and _is_num(seg[3])) else None
            return dx, dy, dth, dur
        if isinstance(seg, dict) and all(k in seg for k in ("dx","dy")) and any(k in seg for k in ("dtheta","theta","yaw","rotation","rot","angle")):
            dth_key = "dtheta" if "dtheta" in seg else ("theta" if "theta" in seg else ("yaw" if "yaw" in seg else ("rotation" if "rotation" in seg else ("rot" if "rot" in seg else "angle"))))
            dx, dy, dth = float(seg["dx"]), float(seg["dy"]), float(seg[dth_key])
            dur = seg.get("duration")
            dur = float(dur) if _is_num(dur) else None
            return dx, dy, dth, dur
        return None

    def _play_step_or_frames(self, seg):
        if self._maybe_wait(seg):
            return True
        if self._play_holonomic_line(seg):
            return True
        got = self._extract_generic_step(seg)
        if got:
            dx, dy, dth, dur = got
            if dur is not None and dur > 0:
                self._play_step_timed(dx, dy, dth, dur)
            else:
                if DEBUG:
                    print("[PMT][StepList] moveTo path dx=", _fmt(dx), " dy=", _fmt(dy), " dth=", _fmt(dth))
                self._moveTo_chain(dx, dy, dth)
            return True
        frames = self._frames_from_segment(seg)
        if frames:
            if DEBUG:
                print("[PMT][Frames] n=", len(frames))
            self._play_frames_stream(frames)
            return True
        if DEBUG:
            print("[PMT] Segment non reconnu:", _short(seg))
        return False

    # ---------- Frames ----------
    @staticmethod
    def _norm_frame(entry, idx):
        def F(v, name):
            try:
                return float(v)
            except Exception:
                raise ValueError("Frame#%d: %s non numérique (%r)" % (idx, name, v))
        if isinstance(entry, dict):
            t  = entry.get("t", entry.get("time", entry.get("timestamp")))
            x  = entry.get("x")
            y  = entry.get("y")
            th = entry.get("theta", entry.get("th", entry.get("yaw")))
            if t is None or x is None or y is None or th is None:
                raise ValueError("Frame#%d: clés manquantes (t/x/y/theta)" % idx)
            return (F(t,"t"), F(x,"x"), F(y,"y"), F(th,"theta"))
        if isinstance(entry, (list, tuple)) and len(entry) == 4:
            a,b,c,d = entry
            try:
                return (F(a,"t"), F(b,"x"), F(c,"y"), F(d,"theta"))
            except Exception:
                return (F(d,"t"), F(a,"x"), F(b,"y"), F(c,"theta"))
        raise ValueError("Frame#%d: format non supporté (%s)" % (idx, type(entry).__name__))

    def _frames_from_segment(self, seg):
        frames = None
        if isinstance(seg, dict):
            frames = seg.get("frames") or seg.get("points") or seg.get("poses")
        elif isinstance(seg, (list, tuple)):
            if seg and isinstance(seg[0], (list, tuple, dict)):
                first = seg[0]
                if (isinstance(first, (list, tuple)) and len(first) == 4 and all(_is_num(v) for v in first)) or                    (isinstance(first, dict) and any(k in first for k in ("t","time","timestamp","x","y","theta","th","yaw"))):
                    frames = seg
        if frames is None:
            return None
        out = [ self._norm_frame(fr, i) for i, fr in enumerate(frames) ]
        out.sort(key=lambda x: x[0])
        norm = []
        last_t = None
        for t,x,y,th in out:
            if (last_t is None) or (t > last_t):
                norm.append((t,x,y,th))
                last_t = t
        return norm

    def _play_frames_stream(self, frames):
        if not frames or len(frames) < 2:
            return
        try:
            t0, x0, y0, th0 = frames[0]
            for i in range(1, len(frames)):
                t1, x1, y1, th1 = frames[i]
                # unwrap de th1 autour de th0 pour continuité
                adj_th1 = th1
                while (adj_th1 - th0) > math.pi:
                    adj_th1 -= 2.0*math.pi
                while (adj_th1 - th0) < -math.pi:
                    adj_th1 += 2.0*math.pi
                dt = (t1 - t0) / max(SPEED_K, 1e-6)
                if dt <= 0:
                    t0, x0, y0, th0 = t1, x1, y1, adj_th1
                    continue
                dx, dy, dth = (x1-x0), (y1-y0), (adj_th1-th0)

                # vitesses physiques
                vx_p = dx/dt
                vy_p = dy/dt
                vth_p = dth/dt

                # normalisées
                vx = vx_p / MAX_VX if MAX_VX > 0 else 0.0
                vy = vy_p / MAX_VY if MAX_VY > 0 else 0.0
                vth = vth_p / MAX_VTH if MAX_VTH > 0 else 0.0

                vx_s = _clip01(vx) if CHORE_EXACT else _clip01(vx)
                vy_s = _clip01(vy) if CHORE_EXACT else _clip01(vy)
                vth_s = _clip01(vth) if CHORE_EXACT else _clip01(vth)

                if DEBUG:
                    print("[PMT][frames] dt=", _fmt(dt), " phys(vx,vy,vth)=",
                          "(", _fmt(vx_p), ",", _fmt(vy_p), ",", _fmt(vth_p), ") -> norm (",
                          _fmt(vx), ",", _fmt(vy), ",", _fmt(vth), ") -> sent (",
                          _fmt(vx_s), ",", _fmt(vy_s), ",", _fmt(vth_s), ")")

                self.motion.moveToward(vx_s, vy_s, vth_s)
                time.sleep(dt)
                t0, x0, y0, th0 = t1, x1, y1, adj_th1
        finally:
            try:
                self.motion.stopMove()
            except Exception:
                pass

    # ---------- Orchestration ----------
    def _run_pmt_trajectory(self, pmt_path):
        try:
            data = self._load_pmt(pmt_path)
            segments = self._segments_from_root(data)
            if not segments:
                print("[PMT] Aucun segment lisible dans:", pmt_path)
                return
            segments = self._flatten_composed(segments)

            any_played = False
            for idx, seg in enumerate(segments):
                if DEBUG:
                    print("[PMT] --- Segment#%d --- (CHORE_EXACT=%s)" % (idx, str(CHORE_EXACT)))
                if self._play_step_or_frames(seg):
                    print("[PMT] Segment#%d exécuté" % idx)
                    any_played = True
                else:
                    print("[PMT] Segment#%d ignoré (%s): %s" % (idx, type(seg).__name__, _short(seg)))
            if any_played:
                print("[PMT] Trajectoire terminée.")
            else:
                print("[PMT] Rien à exécuter (segments non reconnus).")
        except Exception as e:
            print("[PMT] Impossible d'exécuter la trajectoire :", e)

    def run_if_present(self, xar_path):
        try:
            base_dir = os.path.dirname(xar_path)
            hint_file = os.path.join(base_dir, "DTTrajectoryFileName.py")
            if not os.path.exists(hint_file):
                return False
            with open(hint_file, "r") as f:
                pmt_name = f.read().strip()
            if not pmt_name:
                return False
            pmt_path = os.path.join(base_dir, pmt_name)
            if not os.path.exists(pmt_path):
                print("[PMT] Fichier PMT introuvable :", pmt_path)
                return False
            t = threading.Thread(target=self._run_pmt_trajectory, args=(pmt_path,))
            t.daemon = True
            t.start()
            print("[PMT] Trajectoire base lancée :", pmt_path)
            if DEBUG:
                print("[PMT][DEBUG] CHORE_EXACT=", CHORE_EXACT,
                      " MAX_VX=", _fmt(MAX_VX), " MAX_VY=", _fmt(MAX_VY), " MAX_VTH=", _fmt(MAX_VTH),
                      " SPEED_K=", _fmt(SPEED_K))
            return True
        except Exception as e:
            print("[PMT] Skip, erreur :", e)
            return False
