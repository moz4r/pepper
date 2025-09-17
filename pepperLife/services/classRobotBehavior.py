# -*- coding: utf-8 -*-
# robot_comportement.py — gère l’enveloppe "contrôle moteur"
# - begin_control(): coupe random + breath + collision bras, stoppe tâches résiduelles
# - end_control():   restore proprement
# - apply_speed_markers(): %%SetSpeed(x)%% optionnel

import time, re



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
