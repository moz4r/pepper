# -*- coding: utf-8 -*-
# classCamera.py — gestion de la caméra de Pepper (ALVideoDevice)
from __future__ import print_function
import io, time, threading
import png  # PyPNG (pur Python)

class classCamera(object):
    """
    Abonnement simple à ALVideoDevice et conversion PNG.
    - Résolution par défaut: kVGA (640x480) pour une image lisible.
    - Couleur: kBGRColorSpace (13), simple à convertir en RGB.
    """

    def __init__(self, session, logger, res=2, color=13, fps=10):
        self.sess = session
        self.log = logger
        self.res = res   # 1=QVGA, 2=VGA
        self.color = color
        self.fps = max(1, min(20, int(fps)))
        self.cam = None
        self.sub = None
        self.lock = threading.Lock()

    def start(self):
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

    def stop(self):
        try:
            if self.cam and self.sub:
                self.cam.unsubscribe(self.sub)
                self.log("[Cam] Unsubscribed")
        except Exception:
            pass
        self.sub = None

    def get_frame_bgr(self):
        if not self.cam or not self.sub:
            return (None, None, None)
        try:
            f = self.cam.getImageRemote(self.sub)
            w, h = int(f[0]), int(f[1])
            buf = f[6]  # BGR bytes
            return (w, h, buf)
        except Exception as e:
            self.log("[Cam] get_frame_bgr error: %s" % e)
            return (None, None, None)

    def get_png(self):
        """
        Retourne un PNG (bytes) encodé en pur Python via PyPNG à partir d'un buffer BGR.
        """
        w, h, bgr = self.get_frame_bgr()
        if not w:
            return None
        out = io.BytesIO()
        wr = png.Writer(width=w, height=h, greyscale=False, alpha=False, compression=5)
        # Convertit BGR -> RGB ligne par ligne (pur Python)
        rowlen = w * 3
        rows = []
        for y in range(h):
            row_bgr = bgr[y*rowlen : (y+1)*rowlen]
            # BGR->RGB: swap par pixel
            row_rgb = bytearray(rowlen)
            for i in range(0, rowlen, 3):
                row_rgb[i]   = row_bgr[i+2]  # R
                row_rgb[i+1] = row_bgr[i+1]  # G
                row_rgb[i+2] = row_bgr[i]    # B
            rows.append(bytes(row_rgb))
        wr.write(out, rows)
        return out.getvalue()
