# -*- coding: utf-8 -*-
# classLEDs.py — gestion oreilles/yeux (listen=bleu, processing=violet, parler=blanc, idle=blanc)

class PepperLEDs(object):
    def __init__(self, session, logger):
        self.leds = session.service("ALLeds")
        self.log = logger

    def _set(self, group, rgb, dur=0.08):
        try: 
            self.leds.fadeRGB(group, int(rgb), float(dur))
        except Exception as e:
            self.log(u"[LEDs] Échec de la configuration de {}: {}".format(group, e), level='warning')

    # Oreilles (ON = il peut écouter)
    def ears_on(self):  self._set("LeftEarLeds", 0x0000FF); self._set("RightEarLeds", 0x0000FF)
    def ears_off(self): self._set("LeftEarLeds", 0x000000); self._set("RightEarLeds", 0x000000)

    # Yeux
    def eyes_white(self):   self._set("FaceLeds", 0xFFFFFF, 0.08)
    def eyes_blue(self):    self._set("FaceLeds", 0x0000FF, 0.05)
    def eyes_purple(self):  self._set("FaceLeds", 0x800080, 0.05)  # violet

    # États
    def idle(self):
        self.ears_on()
        self.eyes_white()          # BLANC: repos/idle

    def listening_recording(self):
        self.ears_on()
        self.eyes_blue()           # BLEU: [REC] en cours

    def processing(self):
        self.ears_off()
        self.eyes_purple()         # VIOLET: réflexion/traitement

    # Parole: **après réflexion** -> BLANC (tout en coupant les oreilles)
    def speaking_start(self):
        self.ears_off()
        self.eyes_white()          # BLANC: parle (mais n'écoute pas)

    def speaking_stop(self):
        self.idle()                # retour BLANC + oreilles ON

import time
import threading

def led_management_thread(stop_event, session, leds, listener):
    """
    Thread dédié à la gestion des LEDs en fonction de l'état réel du robot.
    """
    leds.log("Démarrage du thread de gestion des LEDs.", level='info')
    pls = None
    last_state = {}

    while not stop_event.is_set():
        try:
            if pls is None:
                pls = session.service("PepperLifeService")

            is_listening = listener.on  # 'on' est l'état d'enregistrement
            service_state = pls.get_state()
            
            current_state = {
                'listening': is_listening,
                'speaking': service_state.get('speaking', False),
                'thinking': service_state.get('thinking', False)
            }

            if current_state != last_state:
                if current_state['listening']:
                    leds.listening_recording()
                elif current_state['speaking']:
                    leds.speaking_start()
                elif current_state['thinking']:
                    leds.processing()
                else:
                    leds.idle()
                last_state = current_state

        except Exception as e:
            leds.log("Erreur dans le thread de gestion des LEDs: {}".format(e), level='error')
            pls = None  # Tenter de se reconnecter au service
        
        time.sleep(0.2)
    leds.log("Arrêt du thread de gestion des LEDs.", level='info')

