# -*- coding: utf-8 -*- 
# classVision.py - Vision chat logic using OpenAI and camera management

import base64
import io
import time
import png
from openai import OpenAI

class Vision(object):
    def __init__(self, config, session, logger):
        self.config = config
        self.sess = session
        self.log = logger
        self._client = None
        self.res = 2   # 1=QVGA, 2=VGA
        self.color = 11  # kRGBColorSpace
        self.fps = 5
        self.cam = None
        self.sub = None

    def client(self):
        if self._client is None:
            self._client = OpenAI(timeout=15.0)
        return self._client

    def start_camera(self):
        try:
            self.cam = self.sess.service("ALVideoDevice")
            name = "PepperLifeCam_%d" % int(time.time())
            self.sub = self.cam.subscribeCamera(name, 0, self.res, self.color, self.fps)
            self.log("[Cam] ALVideoDevice subscribed: %s" % self.sub)
            return True
        except Exception as e:
            self.log("[Cam] Abonnement caméra impossible: %s" % e)
            self.sub = None
            return False

    def stop_camera(self):
        try:
            if self.cam and self.sub:
                self.cam.unsubscribe(self.sub)
                self.log("[Cam] Unsubscribed")
        except Exception:
            pass
        self.sub = None

    def get_frame_rgb(self):
        if not self.cam or not self.sub:
            return (None, None, None)
        try:
            f = self.cam.getImageRemote(self.sub)
            w, h = int(f[0]), int(f[1])
            buf = f[6]  # RGB bytes
            return (w, h, buf)
        except Exception as e:
            self.log("[Cam] get_frame_rgb error: %s" % e)
            return (None, None, None)

    def get_png(self):
        """
        Retourne un PNG (bytes) encodé en pur Python via PyPNG à partir d'un buffer RGB.
        """
        w, h, rgb_bytes = self.get_frame_rgb()
        if not w:
            return None
        out = io.BytesIO()
        wr = png.Writer(width=w, height=h, greyscale=False, alpha=False, compression=5)
        # Convertit le buffer plat en une liste de lignes
        row_len = w * 3
        rows = [rgb_bytes[i:i+row_len] for i in range(0, len(rgb_bytes), row_len)]
        wr.write(out, rows)
        return out.getvalue()

    def vision_chat(self, user_text, image_bytes, hist):
        """
        Chat vision unifié :
        - Prompt système configurable via CONFIG['vision']['system_prompt']
        - Modèle configurable via CONFIG['vision']['model']
        - Historique vision optionnel (passé via hist)
        - Le texte utilisateur est passé tel quel, le modèle décide quoi faire (décrire, compter, etc.)
        """
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

        msgs = [{"role": "system", "content": self.config['vision']['system_prompt'] }]

        # Historique dédié à la vision (si on veut conserver du contexte multi-tours)
        for role, content in hist:
            msgs.append({"role": role, "content": content})

        msgs.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {
                    "type": "image_url",
                    "image_url": { "url": f"data:image/png;base64,{image_base64}" }
                }
            ]
        })

        try:
            resp = self.client().chat.completions.create(
                model=self.config['vision'].get('model', 'gpt-4o-mini'),
                messages=msgs,
                temperature=0.2,
                max_tokens=120
            )
            return resp.choices[0].message.content.replace("\n"," ").strip()
        except Exception as e:
            self.log(f"[Vision] OpenAI API error: {e}", level='error')
            return "Désolé, je n'ai pas pu analyser l'image."

    def _utterance_triggers_vision(self, txt_lower):
        """Retourne True si l'énoncé déclenche une analyse vision.
        Utilise CONFIG['vision']['triggers'] (liste) pour rester configurable.
        """
        try:
            triggers = [t.lower() for t in self.config['vision'].get('triggers', [])]
        except Exception:
            triggers = []
        return any(t in txt_lower for t in triggers)