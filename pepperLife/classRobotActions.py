# -*- coding: utf-8 -*-
# robot_actions.py — Source de vérité des commandes robot (parsing + exécution + FIN DE MOUVEMENT)
#
# Nouveautés:
# - Commandes unitaires par joint en degrés: HeadYaw/HeadPitch, L*/R* Shoulder/Elbow/Wrist, LHand/RHand (0..1)
# - Toujours bloquant (angleInterpolation) -> on attend la fin d’un mouvement avant de rendre la main
# - Barrière de fin pour s’assurer qu’aucune tâche motrice ne traîne
# - Markers existants conservés: RaiseRightArm, RaiseLeftArm, RestArm, Wave, MoveLeftHand/MoveRightHand
#
# NB: On n’appelle PAS les limites NAOqi (pour compat) ; on applique un clamp large et sûr.
#     Ajuste si besoin. Les signes sont “humains” : HeadYaw <0 -> gauche, >0 -> droite, etc.

import re, time, math

# Balises: %% Cmd(args) %%
MARKER_RE = re.compile(r"%%\s*([A-Za-z0-9_]+)\s*\((.*?)\)\s*%%")

def _to_f(v, default=None):
    try: return float(v)
    except: return default

def _deg_to_rad(d):
    return float(d) * math.pi / 180.0

# Clamps “safe” (larges). Ajustables si besoin.
# Mains: 0..1 ; Angles tête/bras: bornes prudentes
_CLAMP = {
    "Hand":      (0.0, 1.0),
    "HeadYaw":   (-120.0, 120.0),
    "HeadPitch": (-40.0,   30.0),
    "ShoulderPitch": (-120.0, 120.0),
    "ShoulderRoll_R": (-120.0,  30.0),  # R vers l’extérieur = négatif
    "ShoulderRoll_L": ( -30.0, 120.0),  # L vers l’extérieur = positif
    "ElbowYaw":  (-120.0, 120.0),
    "ElbowRoll_R": (0.0,   120.0),      # R se plie vers + (près du buste)
    "ElbowRoll_L": (-120.0, 0.0),       # L se plie vers - (près du buste)
    "WristYaw":  (-120.0, 120.0),
}

def _clamp(val, lo, hi):
    try:
        v = float(val)
        if v < lo: return lo
        if v > hi: return hi
        return v
    except:
        return lo





class PepperActions(object):
    """
    - Contient TOUTES les commandes moteur (_cmds).
    - Parsing unique des balises %%Cmd(args)%%.
    - Barrière de fin de mouvement après exécution (attend la fin des tâches moteur).

    API:
      - command_names() -> set([...])
      - is_motor_action(name) -> bool
      - parse_markers(text) -> iterator {name,args,span}
      - execute_markers(text) -> (texte_sans_balises, executed_list)
      - set_speed(f) -> vitesse par défaut 0.05..1.0
    """

    def _set_sync_speed(self, names, angles_deg, speed=None):
        """Déplacement simultané de plusieurs joints à vitesse relative (bloquant)."""
        self._ensure_ready()
        if isinstance(names, str): names = [names]
        if not isinstance(angles_deg, (list, tuple)): angles_deg = [angles_deg]
        sp = float(self._speed if speed is None else speed)
        targets = [_deg_to_rad(a) for a in angles_deg]
        # Un seul appel -> tous les joints bougent ensemble, NAOqi attend la fin
        self.motion.angleInterpolationWithSpeed(names, targets, sp)



    def __init__(self, session):
        self.session = session
        self.motion  = session.service("ALMotion")
        self.posture = session.service("ALRobotPosture")
        try: self.motion.setStiffnesses("Body", 0.8)
        except: pass

        self._speed = 0.25  # vitesse par défaut

        # ---- UNIQUE MAP des commandes (source de vérité) ----
        self._cmds = {
            # mains historiques
            "MoveRightHand": self.MoveRightHand,   # 0=fermer, 1=ouvrir
            "MoveLeftHand":  self.MoveLeftHand,    # 0=fermer, 1=ouvrir
            # gestes macro
            "RaiseRightArm": self.RaiseRightArm,
            "RaiseLeftArm":  self.RaiseLeftArm,
            "RestArm":       self.RestArm,         # arg: 'R' ou 'L'
            "Wave":          self.Wave,            # arg: 'R' ou 'L'
            # HEAD
            "HeadYaw":       self.HeadYaw,
            "HeadPitch":     self.HeadPitch,
            # LEFT ARM
            "LShoulderPitch": self.LShoulderPitch,
            "LShoulderRoll":  self.LShoulderRoll,
            "LElbowYaw":      self.LElbowYaw,
            "LElbowRoll":     self.LElbowRoll,
            "LWristYaw":      self.LWristYaw,
            "LHand":          self.MoveLeftHand,
            # RIGHT ARM
            "RShoulderPitch": self.RShoulderPitch,
            "RShoulderRoll":  self.RShoulderRoll,
            "RElbowYaw":      self.RElbowYaw,
            "RElbowRoll":     self.RElbowRoll,
            "RWristYaw":      self.RWristYaw,
            "RHand":          self.MoveRightHand,
        }

    # --- boot helpers ---
    def _ensure_ready(self):
        try:
            self.motion.wakeUp()
        except Exception:
            pass
        try:
            self.motion.setStiffnesses("Body", 1.0)
        except Exception:
            pass
        try:
            if self.posture:
                self.posture.goToPosture("StandInit", 0.5)
        except Exception:
            pass

    # ----------------- Vitesse -----------------
    def set_speed(self, fraction):
        try:
            f = max(0.05, min(1.0, float(fraction)))
            self._speed = f
        except:
            pass

    # ----------------- Parsing -----------------
    def command_names(self):
        return set(self._cmds.keys())

    def is_motor_action(self, name):
        return name in self._cmds

    def parse_markers(self, text):
        if not text: return
        for m in MARKER_RE.finditer(text):
            name = m.group(1)
            args = []
            if m.group(2):
                args = [a.strip() for a in m.group(2).split(",")]
            yield {"name": name, "args": args, "span": m.span()}

    def execute_markers(self, text):
        """
        Exécute les balises moteur et renvoie (texte_sans_balises, executed_list).
        -> Inclut une barrière de fin pour attendre la fin des mouvements.
        """
        executed = []
        if not text:
            return "", executed

        # Catégories explicites (évite les confusions d’arguments)
        ZERO_ARG = {"RaiseRightArm", "RaiseLeftArm"}
        SIDE_ARG = {"RestArm", "Wave"}
        HAND_ARG = {"MoveRightHand", "RHand", "MoveLeftHand", "LHand"}
        JOINT_ARG = {
            "HeadYaw","HeadPitch",
            "LShoulderPitch","LShoulderRoll","LElbowYaw","LElbowRoll","LWristYaw","LHand",
            "RShoulderPitch","RShoulderRoll","RElbowYaw","RElbowRoll","RWristYaw","RHand",
        }

        out = []
        last = 0
        did_motion = False

        for item in self.parse_markers(text):
            s, e = item["span"]
            out.append(text[last:s])
            name, args = item["name"], item["args"]
            fn = self._cmds.get(name)

            if not fn:
                executed.append(("UNKNOWN:"+name, args))
                last = e
                continue

            try:
                if name in ZERO_ARG:
                    fn()                             # <-- aucune valeur passée
                    did_motion = True
                    executed.append((name, []))

                elif name in SIDE_ARG:
                    side = (args[0] if args else "R")
                    fn(side)
                    did_motion = True
                    executed.append((name, [side]))

                elif name in HAND_ARG:
                    # mains : 0.0..1.0
                    val = _to_f(args[0], 0.0) if args else 0.0
                    fn(val)
                    did_motion = True
                    executed.append((name, [val]))

                elif name in JOINT_ARG:
                    # joints : angle en degrés (un seul)
                    ang = _to_f(args[0], 0.0) if args else 0.0
                    fn(ang)
                    did_motion = True
                    executed.append((name, [ang]))

                else:
                    # sécurité: si on arrive ici, on n’exécute pas
                    executed.append(("UNHANDLED:"+name, args))

            except Exception as e2:
                executed.append(("ERROR:"+name, [str(e2)]))

            last = e

        out.append(text[last:])
        final_text = "".join(out).strip()

        # Barrière de fin (attend la fin des mouvements)
        if did_motion and self.motion:
            try:
                self.motion.waitUntilMoveIsFinished()
            except Exception:
                pass
            self._wait_tasks_settle(timeout=2.0, settle_sleep=0.12)

        return final_text, executed


    def _wait_tasks_settle(self, timeout=2.0, settle_sleep=0.12):
        """Poll léger sur getTaskList pour s'assurer qu'aucune tâche motrice ne traîne."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                tasks = self.motion.getTaskList()
                if not tasks:
                    break
            except Exception:
                break
            time.sleep(0.05)
        time.sleep(settle_sleep)

    # ----------------- Helper bas niveau (bloquant) --------
    def _set(self, names, angles_deg, speed=None, min_dur=0.35, max_dur=2.0):
        """
        Déplacement BLOQUANT via angleInterpolation.
        - names: str ou liste
        - angles_deg: float ou liste (degrés)
        """
        self._ensure_ready()
        if isinstance(names, str): names = [names]
        if not isinstance(angles_deg, (list, tuple)): angles_deg = [angles_deg]

        targets = [_deg_to_rad(a) for a in angles_deg]

        # angles actuels (rad)
        try:
            cur = self.motion.getAngles(names, True)
        except Exception:
            cur = [0.0] * len(names)

        sp = float(self._speed if speed is None else speed)
        durations = []
        for c, t in zip(cur, targets):
            d = abs(t - c)
            dur = max(min_dur, min(max_dur, (d / max(0.05, sp)) * 0.7))
            durations.append(dur)

        angleLists = [[t] for t in targets]
        timeLists  = [[d] for d in durations]
        self.motion.angleInterpolation(names, angleLists, timeLists, True)

    # ----------------- Commandes “mains” --------------------
    def MoveRightHand(self, val=0):
        self._ensure_ready()
        v = _clamp(val, *_CLAMP["Hand"])
        self.motion.setAngles("RHand", v, self._speed)

    def MoveLeftHand(self, val=0):
        self._ensure_ready()
        v = _clamp(val, *_CLAMP["Hand"])
        self.motion.setAngles("LHand", v, self._speed)

    # ----------------- Tête --------------------
    def HeadYaw(self, deg=0):
        self._ensure_ready()
        a = _clamp(deg, *_CLAMP["HeadYaw"])
        self._set("HeadYaw", a)

    def HeadPitch(self, deg=0):
        self._ensure_ready()
        a = _clamp(deg, *_CLAMP["HeadPitch"])
        self._set("HeadPitch", a)

    # ----------------- Bras Gauche --------------------
    def LShoulderPitch(self, deg=0):
        self._ensure_ready()
        a = _clamp(deg, *_CLAMP["ShoulderPitch"])
        self._set("LShoulderPitch", a)

    def LShoulderRoll(self, deg=0):
        self._ensure_ready()
        lo,hi = _CLAMP["ShoulderRoll_L"]
        a = _clamp(deg, lo, hi)
        self._set("LShoulderRoll", a)

    def LElbowYaw(self, deg=0):
        self._ensure_ready()
        a = _clamp(deg, *_CLAMP["ElbowYaw"])
        self._set("LElbowYaw", a)

    def LElbowRoll(self, deg=0):
        self._ensure_ready()
        lo,hi = _CLAMP["ElbowRoll_L"]
        a = _clamp(deg, lo, hi)
        self._set("LElbowRoll", a)

    def LWristYaw(self, deg=0):
        self._ensure_ready()
        a = _clamp(deg, *_CLAMP["WristYaw"])
        self._set("LWristYaw", a)

    # ----------------- Bras Droit --------------------
    def RShoulderPitch(self, deg=0):
        self._ensure_ready()
        a = _clamp(deg, *_CLAMP["ShoulderPitch"])
        self._set("RShoulderPitch", a)

    def RShoulderRoll(self, deg=0):
        self._ensure_ready()
        lo,hi = _CLAMP["ShoulderRoll_R"]
        a = _clamp(deg, lo, hi)
        self._set("RShoulderRoll", a)

    def RElbowYaw(self, deg=0):
        self._ensure_ready()
        a = _clamp(deg, *_CLAMP["ElbowYaw"])
        self._set("RElbowYaw", a)

    def RElbowRoll(self, deg=0):
        self._ensure_ready()
        lo,hi = _CLAMP["ElbowRoll_R"]
        a = _clamp(deg, lo, hi)
        self._set("RElbowRoll", a)

    def RWristYaw(self, deg=0):
        self._ensure_ready()
        a = _clamp(deg, *_CLAMP["WristYaw"])
        self._set("RWristYaw", a)

    # ----------------- Gestes macro (déjà présents) --------
    def RaiseRightArm(self):
        self._ensure_ready()
        self._set_sync_speed(
            ["RShoulderPitch","RShoulderRoll","RElbowYaw","RElbowRoll","RWristYaw"],
            [-95,              -18,             80,          15,          0],
            speed=min(0.6, self._speed+0.2)
        )

    def RaiseLeftArm(self):
        self._ensure_ready()
        self._set_sync_speed(
            ["LShoulderPitch","LShoulderRoll","LElbowYaw","LElbowRoll","LWristYaw"],
            [-95,               18,            -80,        -15,          0],
            speed=min(0.6, self._speed+0.2)
        )

    def RestArm(self, side="R"):
        self._ensure_ready()
        side = (side or "R").upper()
        if side.startswith("R"):
            self._set(["RShoulderPitch","RShoulderRoll","RElbowYaw","RElbowRoll","RWristYaw"],
                      [ 80,                5,              60,          5,          0], speed=self._speed)
            self.MoveRightHand(0.0)
        else:
            self._set(["LShoulderPitch","LShoulderRoll","LElbowYaw","LElbowRoll","LWristYaw"],
                      [ 80,               -5,             -60,         -5,          0], speed=self._speed)
            self.MoveLeftHand(0.0)

    def Wave(self, side="R"):
        self._ensure_ready()
        side = (side or "R").upper()
        if side.startswith("R"):
            self.RaiseRightArm()
            for _ in range(3):
                self._set("RElbowYaw",  40, speed=min(0.7, self._speed+0.2))
                self._set("RElbowYaw", 110, speed=min(0.7, self._speed+0.2))
            self.RestArm("R")
        else:
            self.RaiseLeftArm()
            for _ in range(3):
                self._set("LElbowYaw", -40, speed=min(0.7, self._speed+0.2))
                self._set("LElbowYaw", -110, speed=min(0.7, self._speed+0.2))
            self.RestArm("L")
