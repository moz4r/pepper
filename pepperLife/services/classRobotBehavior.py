# -*- coding: utf-8 -*-
# robot_comportement.py — gère l’enveloppe "contrôle moteur"

class BehaviorManager(object):
    def __init__(self, session, logger, **kwargs):
        self.m   = session.service("ALMotion")
        self.log = logger

    def boot(self):
        """Prépare un état 'prêt' au démarrage (non intrusif)."""
        try:
            self.m.setExternalCollisionProtectionEnabled("Arms", True)
        except Exception as e:
            self.log("[BC] boot: Collision Arms set err: %s" % e, level='warning')