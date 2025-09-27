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
            self.log(f"[LEDs] Failed to set {group}: {e}", level='warning')

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
