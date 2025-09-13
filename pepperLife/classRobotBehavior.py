# -*- coding: utf-8 -*-
# robot_comportement.py — gère l’enveloppe "contrôle moteur"
# - begin_control(): coupe random + breath + collision bras, stoppe tâches résiduelles
# - end_control():   restore proprement
# - apply_speed_markers(): %%SetSpeed(x)%% optionnel

import time, re

SETSPD_RE = re.compile(r"%%\s*SetSpeed\s*\(\s*([0-9]*\.?[0-9]+)\s*\)\s*%%")

class BehaviorManager(object):
    def __init__(self, session, default_speed=0.5):
        self.s   = session
        self.m   = session.service("ALMotion")
        self.bm  = session.service("ALBehaviorManager") if self._has("ALBehaviorManager") else None
        self.mods = ["ALSpeakingMovement","ALListeningMovement","ALBackgroundMovement","ALAutonomousBlinking"]
        self._mods_snap = {}
        self._breath_snap = None
        self._collision_arms_snap = None
        self._acts = None
        self.default_speed = float(default_speed)

    def _has(self, name):
        try: self.s.service(name); return True
        except: return False

    def set_actions(self, acts):
        self._acts = acts
        try: self._acts.set_speed(self.default_speed)
        except: pass

    def boot(self):
        """Prépare un état 'prêt' au démarrage (non intrusif)."""
        # Collision des bras ON (sécurité par défaut)
        try:
            self.m.setExternalCollisionProtectionEnabled("Arms", True)
            print("[BC] boot: Collision Arms -> ON")
        except Exception as e:
            print("[BC] boot: Collision Arms set err:", e)

        # Breath Body ON (posture 'vivante')
        try:
            self.m.setBreathEnabled("Body", True)
            print("[BC] boot: Breath Body -> ON")
        except Exception as e:
            print("[BC] boot: Breath set err:", e)

        # Réactive les modules 'random' (speaking/listening/background/blinking)
        for name in self.mods:
            try:
                proxy = self.s.service(name)
                if hasattr(proxy, "setEnabled"):
                    proxy.setEnabled(True)
                    print("[BC] boot: %s -> enabled" % name)
                elif hasattr(proxy, "pause"):
                    proxy.pause(False)
                    print("[BC] boot: %s -> unpaused" % name)
            except Exception as e:
                print("[BC] boot: %s err: %s" % (name, e))

        # Pousse la vitesse par défaut vers PepperActions (si liée)
        try:
            if self._acts:
                self._acts.set_speed(self.default_speed)
                print("[BC] boot: default speed ->", self.default_speed)
        except Exception as e:
            print("[BC] boot: set_speed err:", e)


    # --------- speed markers ---------
    def apply_speed_markers(self, text):
        if not text: return text, None
        m = SETSPD_RE.search(text)
        if not m: return text, None
        spd = float(m.group(1))
        try:
            if self._acts: self._acts.set_speed(spd)
        except: pass
        # retire la balise du texte
        start, end = m.span()
        text = (text[:start] + text[end:]).strip()
        return text, spd

    # --------- begin/end control ---------
    def begin_control(self):
        # Wake + léger nettoyage tâches
        try:
            self.m.wakeUp()
        except: pass
        try:
            self.m.stopMove()
        except: pass
        try:
            self.m.killAll()
        except: pass
        time.sleep(0.05)

        # Snapshot + OFF des modules “random”
        for name in self.mods:
            st = {"enabled": None, "paused": None}
            try:
                proxy = self.s.service(name)
                if hasattr(proxy, "isEnabled"):
                    st["enabled"] = bool(proxy.isEnabled())
                elif hasattr(proxy, "getEnabled"):
                    st["enabled"] = bool(proxy.getEnabled())
                if hasattr(proxy, "isPaused"):
                    st["paused"] = bool(proxy.isPaused())
            except: pass
            self._mods_snap[name] = st
            try:
                proxy = self.s.service(name)
                if hasattr(proxy,"setEnabled"):
                    proxy.setEnabled(False); print("[BC] %s -> disabled" % name)
                elif hasattr(proxy,"pause"):
                    proxy.pause(True);       print("[BC] %s -> paused" % name)
            except: pass

        # Snapshot + OFF du breath Body
        try:
            self._breath_snap = bool(self.m.getBreathEnabled("Body"))
        except:
            self._breath_snap = None
        try:
            self.m.setBreathEnabled("Body", False); print("[BC] Breath Body -> OFF")
        except: pass

        # Snapshot + OFF collision bras (clé POUR les grands mouvements)
        try:
            self._collision_arms_snap = bool(self.m.getExternalCollisionProtectionEnabled("Arms"))
        except:
            self._collision_arms_snap = None
        try:
            self.m.setExternalCollisionProtectionEnabled("Arms", False)
            print("[BC] Collision Arms -> OFF (temp)")
        except: pass

        # Stiffness Body 1.0 (garde le tonus)
        try:
            self.m.setStiffnesses("Body", 1.0)
            print("[BC] Stiffness Body -> 1.0")
        except: pass

        # mini temps pour laisser l’état se stabiliser
        time.sleep(0.05)

    def end_control(self):
        # Laisser retomber toute tâche résiduelle
        try:
            self.m.waitUntilMoveIsFinished()
        except: pass
        t0 = time.time()
        while time.time()-t0 < 1.5:
            try:
                tl = self.m.getTaskList()
                if not tl: break
            except: break
            time.sleep(0.05)

        # Restore collision bras
        try:
            if self._collision_arms_snap is not None:
                self.m.setExternalCollisionProtectionEnabled("Arms", bool(self._collision_arms_snap))
            else:
                self.m.setExternalCollisionProtectionEnabled("Arms", True)
            print("[BC] Collision Arms -> restored")
        except: pass

        # Restore breath
        try:
            if self._breath_snap is not None:
                self.m.setBreathEnabled("Body", bool(self._breath_snap))
            else:
                self.m.setBreathEnabled("Body", True)
            print("[BC] Breath Body -> restored")
        except: pass

        # Restore modules
        for name, st in (self._mods_snap or {}).items():
            try:
                proxy = self.s.service(name)
                if st.get("enabled") is not None and hasattr(proxy,"setEnabled"):
                    proxy.setEnabled(bool(st["enabled"]))
                    print("[BC] %s restored (%s)" % (name, "enabled" if st["enabled"] else "disabled"))
                elif st.get("paused") is not None and hasattr(proxy,"pause"):
                    proxy.pause(bool(st["paused"]))
                    print("[BC] %s restored (paused=%s)" % (name, st["paused"]))
            except: pass

        # petit settle
        time.sleep(0.05)
