#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
random_control.py (Body stiffness)
----------------------------------
Disable/restore "random" micro-movements during an animation, plus
set FULL BODY stiffness to 1.0 while playing, then restore everything after.

Exposed functions:
- disable_random_modules(session)
- enable_random_modules(session)

Saved/restored:
- ALSpeakingMovement, ALListeningMovement, ALBackgroundMovement, ALAutonomousBlinking
- (simplified) we no longer touch MoveArmsEnabled / WalkArmsEnabled
- ALMotion Breath on Body
- FULL Body stiffness snapshot -> force 1.0 -> restore
"""
from __future__ import print_function
import time

def _hard_stop_motion(motion):
    """Stoppe immédiatement toute tâche de mouvement résiduelle."""
    if not motion:
        return
    try:
        motion.stopMove()
    except Exception:
        pass
    try:
        motion.killAll()
    except Exception:
        pass

def _go_to_standinit(session, speed=0.8):
    """Tente de passer en posture StandInit. Retourne True si OK."""
    try:
        posture = session.service("ALRobotPosture")
    except Exception:
        posture = None
    if not posture:
        return False
    try:
        posture.goToPosture("StandInit", float(speed))
        return True
    except Exception:
        return False

def _zero_upper_body(session, speed=1.0):
    """Remet les articulateurs du haut du corps à 0.0 rapidement (avec clamp léger).
    Fait un second passage plus lent si l'écart résiduel dépasse 0.05 rad sur des joints clés.
    """
    try:
        motion = session.service("ALMotion")
    except Exception:
        motion = None
    if not motion:
        return
    names = [
        "HeadYaw","HeadPitch",
        "LShoulderPitch","LShoulderRoll","LElbowYaw","LElbowRoll","LWristYaw","LHand",
        "RShoulderPitch","RShoulderRoll","RElbowYaw","RElbowRoll","RWristYaw","RHand",
    ]
    zeros = []
    for n in names:
        z = 0.0
        lo = None; hi = None
        try:
            lim = motion.getLimits([n])
            if isinstance(lim, (list, tuple)) and lim and isinstance(lim[0], (list, tuple)) and len(lim[0]) >= 2:
                lo, hi = float(lim[0][0]), float(lim[0][1])
        except Exception:
            lo = None; hi = None
        if lo is not None and hi is not None:
            eps = 1e-6
            low, high = lo + eps, hi - eps
            if z < low:  z = low
            if z > high: z = high
        zeros.append(z)

    try:
        motion.angleInterpolationWithSpeed(names, zeros, float(speed))
        check_joints = ["LShoulderPitch","RShoulderPitch","LShoulderRoll","RElbowRoll"]
        cur = motion.getAngles(check_joints, True)
        resid = [abs(v) for v in cur]
        if any(v > 0.05 for v in resid):
            # second passage un peu plus lent pour se poser
            motion.angleInterpolationWithSpeed(names, zeros, 0.5)
    except Exception:
        pass

_STATE = {
    "modules": {},       # serviceName -> {"enabled": bool, "paused": bool}
    "breath": None,      # bool for Body
    "stiff_Body": None,   # (names, values) snapshot,
    "life_state": None,
    "breath_parts": {},
}


def _set_service_enabled(session, name, enabled):
    try:
        proxy = session.service(name)
    except Exception:
        return
    try:
        if hasattr(proxy, "setEnabled"):
            proxy.setEnabled(bool(enabled))
        elif hasattr(proxy, "pause"):
            proxy.pause(not enabled)
    except Exception as e:
        print("[RC] %s setEnabled(%s) -> %s" % (name, enabled, e))

def _snapshot_service_state(session, name):
    st = {"enabled": None, "paused": None}
    try:
        proxy = session.service(name)
    except Exception:
        return st
    for getter in ("isEnabled", "getEnabled"):
        if hasattr(proxy, getter):
            try:
                st["enabled"] = bool(getattr(proxy, getter)())
                break
            except Exception:
                pass
    if hasattr(proxy, "isPaused"):
        try:
            st["paused"] = bool(proxy.isPaused())
        except Exception:
            pass
    return st

# -- Body stiffness helpers --
def _snapshot_body_stiffness(motion):
    try:
        names = motion.getBodyNames("Body")  # list of all joint names
        vals = motion.getStiffnesses(names)
        return (names, vals)
    except Exception:
        return (None, None)

def _force_body_stiffness(motion, value):
    try:
        motion.setStiffnesses("Body", float(value))
        return True
    except Exception:
        return False

def _restore_body_stiffness(motion, snapshot):
    try:
        names, vals = snapshot
        if names and vals and len(names) == len(vals):
            motion.setStiffnesses(names, vals)
            return True
    except Exception:
        pass
    return False

def disable_random_modules(session):
    motion = None
    try:
        motion = session.service("ALMotion")
        try:
            if motion:
                motion.waitUntilMoveIsFinished()
        except Exception:
            pass
        time.sleep(0.3)  # settle after rest before re-enabling random
        motion.wakeUp()
        print("[RC] WakeUp OK")
        _hard_stop_motion(motion)
    except Exception as e:
        print("[RC] WakeUp KO: %s" % e)
    try:
        life = session.service("ALAutonomousLife")
        try:
            _STATE["life_state"] = life.getState()
        except Exception:
            _STATE["life_state"] = None
        #life.setState("disabled")
        print("[RC] AutonomousLife -> disabled (snapshot: %s)" % _STATE["life_state"])
    except Exception:
        pass

    modules = [
        "ALSpeakingMovement",
        "ALListeningMovement",
        "ALBackgroundMovement",
        "ALAutonomousBlinking",
    ]
    for name in modules:
        st = _snapshot_service_state(session, name)
        _STATE["modules"][name] = st
        _set_service_enabled(session, name, False)
        if st["enabled"] is not None:
            print("[RC] %s desactive" % name)

    if motion:
        # Breath Body/Arms/Head
        try:
            _STATE["breath"] = bool(motion.getBreathEnabled("Body"))
            _STATE["breath_parts"] = {
                "Body": _STATE["breath"],
                "Arms": (bool(motion.getBreathEnabled("Arms")) if hasattr(motion, "getBreathEnabled") else None),
                "Head": (bool(motion.getBreathEnabled("Head")) if hasattr(motion, "getBreathEnabled") else None),
            }
            motion.setBreathEnabled("Body", False)
            try:
                motion.setBreathEnabled("Arms", False)
            except Exception:
                pass
            try:
                motion.setBreathEnabled("Head", False)
            except Exception:
                pass
            print("[RC] Breath Body/Arms/Head -> False")
        except Exception:
            pass

        # FULL Body stiffness: snapshot + force 1.0
        try:
            _STATE["stiff_Body"] = _snapshot_body_stiffness(motion)
            _force_body_stiffness(motion, 1.0)
            print("[RC] Stiffness Body -> 1.0")
            try:
                if motion:
                    motion.waitUntilMoveIsFinished()
            except Exception:
                pass
            time.sleep(0.3)  # settle after stop-random + stiffen
            # -- Safe reset: StandInit then gentle zero as fallback
            ok = _go_to_standinit(session, 0.8)
            if not ok:
                _zero_upper_body(session, speed=0.8)
            try:
                if motion:
                    motion.waitUntilMoveIsFinished()
            except Exception:
                pass

        except Exception:
            pass

def enable_random_modules(session):
    motion = None
    try:
        motion = session.service("ALMotion")
        try:
            if motion:
                motion.waitUntilMoveIsFinished()
        except Exception:
            pass
        time.sleep(0.3)  # settle after rest before re-enabling random
    except Exception:
        pass

    if motion:
        # Restore Body stiffness first (ensures no limp joints)
        try:
            if _STATE.get("stiff_Body") is not None:
                _restore_body_stiffness(motion, _STATE["stiff_Body"])
                print("[RC] Stiffness Body restored")
        except Exception:
            pass

        # Restore Breath
        try:
            bp = _STATE.get("breath_parts") or {}
            if "Body" in bp and bp["Body"] is not None:
                motion.setBreathEnabled("Body", bool(bp["Body"]))
            if "Arms" in bp and bp["Arms"] is not None:
                try:
                    motion.setBreathEnabled("Arms", bool(bp["Arms"]))
                except Exception:
                    pass
            if "Head" in bp and bp["Head"] is not None:
                try:
                    motion.setBreathEnabled("Head", bool(bp["Head"]))
                except Exception:
                    pass
            print("[RC] Breath Body/Arms/Head restored")
        except Exception:
            pass

    # Restore random modules
    for name, st in _STATE.get("modules", {}).items():
        try:
            proxy = session.service(name)
        except Exception:
            continue
        try:
            if st["enabled"] is not None:
                _set_service_enabled(session, name, st["enabled"])
                print("[RC] %s restaure (%s)" % (name, "enabled" if st["enabled"] else "disabled"))
            elif st["paused"] is not None:
                proxy.pause(st["paused"])
                print("[RC] %s pause restaure (%s)" % (name, st["paused"]))
        except Exception as e:
            print("[RC] Enable %s: %s" % (name, e))

    # ensure Life interactive
    try:
        life = session.service("ALAutonomousLife")
        life.setState("interactive")
        print("[RC] AutonomousLife -> interactive")
    except Exception:
        pass

    # Restore ALAutonomousLife state
    try:
        life = session.service("ALAutonomousLife")
        st = _STATE.get("life_state")
        if st:
            life.setState(st)
            print("[RC] AutonomousLife restored -> %s" % st)
        else:
            life.setState("interactive")
            print("[RC] AutonomousLife -> interactive (default)")
    except Exception:
        pass

# Final safety: stop any residual navigation move (non-destructive)
    try:
        if motion:
            motion.stopMove()
            print("[RC] stopMove() at end")
    except Exception:
        pass
