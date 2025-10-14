# -*- coding: utf-8 -*-
# robot_comportement.py — gère l’enveloppe "contrôle moteur"
import threading

class BehaviorManager(object):
    def __init__(self, session, logger, **kwargs):
        self.s = session
        self.log = logger

    def get_running_behaviors(self):
        """Retourne la liste des comportements en cours."""
        try:
            bm = self.s.service("ALBehaviorManager")
            return bm.getRunningBehaviors()
        except Exception as e:
            self.log(f"Impossible de récupérer les comportements en cours: {e}", level='error')
            return []

    def start_behavior(self, name):
        """Démarre un comportement dans un thread séparé pour être non bloquant."""
        def target():
            try:
                bm = self.s.service("ALBehaviorManager")
                if bm.isBehaviorInstalled(name):
                    bm.runBehavior(name)
                else:
                    self.log(f"Comportement '{name}' non trouvé.", level='warning')
            except Exception as e:
                if "interrupted" not in str(e).lower():
                    self.log(f"Erreur lors de l'exécution du comportement '{name}': {e}", level='error')

        try:
            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
        except Exception as e:
            self.log(f"Impossible de démarrer le thread pour le comportement '{name}': {e}", level='error')

    def stop_behavior(self, name):
        """Arrête un comportement s'il est en cours."""
        try:
            bm = self.s.service("ALBehaviorManager")
            if bm.isBehaviorRunning(name):
                bm.stopBehavior(name)
        except Exception as e:
            self.log(f"Impossible d'arrêter le comportement '{name}': {e}", level='error')

    def boot(self):
        """Prépare un état 'prêt' au démarrage (non intrusif)."""
        try:
            motion = self.s.service("ALMotion")
            motion.setExternalCollisionProtectionEnabled("Arms", True)
        except Exception as e:
            self.log("Erreur lors de l'activation de la protection anti-collision: %s" % e, level='warning')
