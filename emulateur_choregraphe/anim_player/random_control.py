#!/usr/bin/env python
# -*- coding: ascii -*-

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
- ALMotion MoveArmsEnabled / WalkArmsEnabled (supports variants)
- ALMotion Breath on Body
- FULL Body stiffness snapshot -> force 1.0 -> restore
"""

from __future__ import print_function

_STATE = {
    "modules": {},       # serviceName -> {"enabled": bool, "paused": bool}
    "moveArms": None,    # (leftEnabled, rightEnabled) or (None,None)
    "walkArms": None,    # (leftEnabled, rightEnabled) or (None,None)
    "breath": None,      # bool for Body
    "stiff_Body": None   # (names, values) snapshot
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

def _get_move_arms_enabled(motion):
    try:
        lr = motion.getMoveArmsEnabled()
        try:
            return (bool(lr[0]), bool(lr[1]))
        except Exception:
            pass
    except TypeError:
        pass
    except Exception:
        pass
    try:
        l = bool(motion.getMoveArmsEnabled("LArm"))
        r = bool(motion.getMoveArmsEnabled("RArm"))
        return (l, r)
    except Exception:
        pass
    try:
        b = bool(motion.getMoveArmsEnabled("Arms"))
        return (b, b)
    except Exception:
        pass
    return (None, None)

def _set_move_arms_enabled(motion, left, right):
    try:
        motion.setMoveArmsEnabled(bool(left), bool(right))
        return True
    except TypeError:
        pass
    except Exception:
        pass
    ok = True
    try:
        motion.setMoveArmsEnabled("LArm", bool(left))
    except Exception:
        ok = False
    try:
        motion.setMoveArmsEnabled("RArm", bool(right))
    except Exception:
        ok = False
    return ok

def _get_walk_arms_enabled(motion):
    try:
        lr = motion.getWalkArmsEnabled()
        try:
            return (bool(lr[0]), bool(lr[1]))
        except Exception:
            pass
    except Exception:
        pass
    return (None, None)

def _set_walk_arms_enabled(motion, left, right):
    try:
        motion.setWalkArmsEnabled(bool(left), bool(right))
        return True
    except Exception:
        return False

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
        motion.wakeUp()
        print("[RC] WakeUp OK")
    except Exception as e:
        print("[RC] WakeUp KO: %s" % e)
    try:
        life = session.service("ALAutonomousLife")
        life.setState("interactive")
        print("[RC] AutonomousLife -> interactive")
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
        # MoveArms
        try:
            l, r = _get_move_arms_enabled(motion)
            _STATE["moveArms"] = (l, r)
            if l is not None and r is not None:
                _set_move_arms_enabled(motion, False, False)
                print("[RC] MoveArms (L,R) -> (False,False)")
            else:
                print("[RC] MoveArms: signature not found")
        except Exception as e:
            print("[RC] MoveArms set KO: %s" % e)

        # WalkArms
        try:
            wl, wr = _get_walk_arms_enabled(motion)
            _STATE["walkArms"] = (wl, wr)
            if wl is not None and wr is not None:
                _set_walk_arms_enabled(motion, False, False)
                print("[RC] WalkArms (L,R) -> (False,False)")
        except Exception:
            pass

        # Breath Body
        try:
            _STATE["breath"] = bool(motion.getBreathEnabled("Body"))
            motion.setBreathEnabled("Body", False)
            print("[RC] Breath Body -> False")
        except Exception:
            pass

        # FULL Body stiffness: snapshot + force 1.0
        try:
            _STATE["stiff_Body"] = _snapshot_body_stiffness(motion)
            _force_body_stiffness(motion, 1.0)
            print("[RC] Stiffness Body -> 1.0")
        except Exception:
            pass

def enable_random_modules(session):
    motion = None
    try:
        motion = session.service("ALMotion")
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
            if _STATE.get("breath") is not None:
                motion.setBreathEnabled("Body", bool(_STATE["breath"]))
                print("[RC] Breath Body restaure -> %s" % bool(_STATE["breath"]))
        except Exception:
            pass

        # Restore MoveArms
        try:
            if _STATE.get("moveArms") is not None:
                l, r = _STATE["moveArms"]
                if l is not None and r is not None:
                    _set_move_arms_enabled(motion, bool(l), bool(r))
                    print("[RC] MoveArms restaure -> (%s,%s)" % (l, r))
        except Exception as e:
            print("[RC] MoveArms restore KO: %s" % e)

        # Restore WalkArms
        try:
            if _STATE.get("walkArms") is not None:
                wl, wr = _STATE["walkArms"]
                if wl is not None and wr is not None:
                    _set_walk_arms_enabled(motion, bool(wl), bool(wr))
                    print("[RC] WalkArms restaure -> (%s,%s)" % (wl, wr))
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
