# -*- coding: utf-8 -*-
# robot_comportement.py — gère l’enveloppe "contrôle moteur"
# - begin_control(): coupe random + breath + collision bras, stoppe tâches résiduelles
# - end_control():   restore proprement
# - apply_speed_markers(): %%SetSpeed(x)%% optionnel

import time, re

SETSPD_RE = re.compile(r"%%\s*SetSpeed\s*\(\s*([0-9]*\.?[0-9]+)\s*\)\s*%%")

class BehaviorManager(object):
    def __init__(self, session, logger, default_speed=0.5):
        self.s   = session
        self.m   = session.service("ALMotion")
        self.log = logger
        self.bm  = session.service("ALBehaviorManager") if self._has("ALBehaviorManager") else None
        self.mods = ["ALSpeakingMovement","ALListeningMovement","ALBackgroundMovement","ALAutonomousBlinking"]
        self._mods_snap = {}
        self._breath_snap = None
        self._collision_arms_snap = None
        self._acts = None
        self.default_speed = float(default_speed)

    def _has(self, name):
        try: 
            self.s.service(name)
            return True
        except Exception:
            return False

    def boot(self):
        """Prépare un état 'prêt' au démarrage (non intrusif)."""
        try:
            self.m.setExternalCollisionProtectionEnabled("Arms", True)
            self.log("[BC] boot: Collision Arms -> ON", level='info')
        except Exception as e:
            self.log("[BC] boot: Collision Arms set err: %s" % e, level='warning')

        try:
            self.m.setBreathEnabled("Body", True)
            self.log("[BC] boot: Breath Body -> ON", level='info')
        except Exception as e:
            self.log("[BC] boot: Breath set err: %s" % e, level='warning')

        for name in self.mods:
            try:
                proxy = self.s.service(name)
                if hasattr(proxy, "setEnabled"):
                    proxy.setEnabled(True)
                    self.log("[BC] boot: %s -> enabled" % name, level='info')
                elif hasattr(proxy, "pause"):
                    proxy.pause(False)
                    self.log("[BC] boot: %s -> unpaused" % name, level='info')
            except Exception as e:
                self.log("[BC] boot: %s err: %s" % (name, e), level='warning')

    def apply_speed_markers(self, text):
        if not text: return text, None
        m = SETSPD_RE.search(text)
        if not m: return text, None
        spd = float(m.group(1))
        
        start, end = m.span()
        text = (text[:start] + text[end:]).strip()
        return text, spd

    def begin_control(self):
        try: self.m.wakeUp()
        except Exception as e: self.log("[BC] wakeUp err: %s" % e, level='warning')
        try: self.m.stopMove()
        except Exception as e: self.log("[BC] stopMove err: %s" % e, level='warning')
        try: self.m.killAll()
        except Exception as e: self.log("[BC] killAll err: %s" % e, level='warning')
        time.sleep(0.05)

        for name in self.mods:
            st = {"enabled": None, "paused": None}
            try:
                proxy = self.s.service(name)
                if hasattr(proxy, "isEnabled"): st["enabled"] = bool(proxy.isEnabled())
                elif hasattr(proxy, "getEnabled"): st["enabled"] = bool(proxy.getEnabled())
                if hasattr(proxy, "isPaused"): st["paused"] = bool(proxy.isPaused())
            except Exception as e: self.log("[BC] snapshot %s err: %s" % (name, e), level='warning')
            self._mods_snap[name] = st
            try:
                proxy = self.s.service(name)
                if hasattr(proxy,"setEnabled"): proxy.setEnabled(False)
                elif hasattr(proxy,"pause"): proxy.pause(True)
            except Exception as e: self.log("[BC] disable %s err: %s" % (name, e), level='warning')

        try:
            self._breath_snap = bool(self.m.getBreathEnabled("Body"))
            self.m.setBreathEnabled("Body", False)
        except Exception as e: self.log("[BC] Breath Body OFF err: %s" % e, level='warning')

        try:
            self._collision_arms_snap = bool(self.m.getExternalCollisionProtectionEnabled("Arms"))
            self.m.setExternalCollisionProtectionEnabled("Arms", False)
        except Exception as e: self.log("[BC] Collision Arms OFF err: %s" % e, level='warning')

        try: self.m.setStiffnesses("Body", 1.0)
        except Exception as e: self.log("[BC] Stiffness Body err: %s" % e, level='warning')
        time.sleep(0.05)

    def end_control(self):
        try: self.m.waitUntilMoveIsFinished()
        except Exception as e: self.log("[BC] waitUntilMoveIsFinished err: %s" % e, level='warning')
        t0 = time.time()
        while time.time()-t0 < 1.5:
            try:
                if not self.m.getTaskList(): break
            except Exception: break
            time.sleep(0.05)

        try:
            if self._collision_arms_snap is not None: self.m.setExternalCollisionProtectionEnabled("Arms", bool(self._collision_arms_snap))
            else: self.m.setExternalCollisionProtectionEnabled("Arms", True)
        except Exception as e: self.log("[BC] restore Collision Arms err: %s" % e, level='warning')

        try:
            if self._breath_snap is not None: self.m.setBreathEnabled("Body", bool(self._breath_snap))
            else: self.m.setBreathEnabled("Body", True)
        except Exception as e: self.log("[BC] restore Breath Body err: %s" % e, level='warning')

        for name, st in (self._mods_snap or {}).items():
            try:
                proxy = self.s.service(name)
                if st.get("enabled") is not None and hasattr(proxy,"setEnabled"): proxy.setEnabled(bool(st["enabled"]))
                elif st.get("paused") is not None and hasattr(proxy,"pause"): proxy.pause(bool(st["paused"]))
            except Exception as e: self.log("[BC] restore module %s err: %s" % (name, e), level='warning')

        time.sleep(0.05)