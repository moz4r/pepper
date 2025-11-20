# -*- coding: utf-8 -*- 
# classVision.py - Vision chat logic using OpenAI and camera management

import base64
import io
import time
import png
from openai import OpenAI
import threading
import os

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
        self.is_streaming = False
        self.streaming_thread = None
        self._current_camera_index = 0
        self.camera_users = 0
        self.lock = threading.Lock()
        self.ui_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "html")
        self.cam_png_path = os.path.join(self.ui_dir, "cam.png")
        self._stream_lock = threading.Lock()
        vision_cfg = (self.config.get('vision') or {})
        try:
            idle_value = float(vision_cfg.get('stream_idle_timeout', 15.0))
        except Exception:
            idle_value = 15.0
        self.stream_idle_timeout = idle_value if idle_value and idle_value > 0 else None
        self._last_consumer_ts = 0.0

    def _normalize_camera_index(self, camera_index):
        """Pepper 2.9 exige un Int32 strict : convertir les entrées texte ou booléennes."""
        if isinstance(camera_index, str):
            key = camera_index.strip().lower()
            if key in ("top", "0"):
                return 0
            if key in ("bottom", "1"):
                return 1
            try:
                return int(key)
            except ValueError:
                raise ValueError("Camera index must be an integer or 'top'/'bottom'")
        try:
            return int(camera_index)
        except (TypeError, ValueError):
            raise ValueError("Camera index must be an integer or 'top'/'bottom'")

    @property
    def current_camera_index(self):
        return self._current_camera_index

    @current_camera_index.setter
    def current_camera_index(self, value):
        self._current_camera_index = self._normalize_camera_index(value)

    def _stream_loop(self):
        try:
            while True:
                if not self.is_streaming:
                    break
                try:
                    png_data = self.get_png()
                    if png_data:
                        try:
                            temp_path = self.cam_png_path + ".tmp"
                            with open(temp_path, "wb") as f:
                                f.write(png_data)
                            os.rename(temp_path, self.cam_png_path)
                        except Exception as e:
                            self.log("[Vision] Error writing cam.png: %s" % e)
                except Exception as e:
                    self.log("[Vision] Unhandled error in stream loop: %s" % e, level='error')
                    time.sleep(1)
                    continue

                if self.stream_idle_timeout:
                    idle = time.time() - self._last_consumer_ts
                    if idle > self.stream_idle_timeout:
                        self.log("[Vision] No viewer detected for %.1fs, auto-stopping stream." % idle, level='info')
                        break

                time.sleep(1.0 / self.fps)
        finally:
            with self._stream_lock:
                self.is_streaming = False
                self.streaming_thread = None
            self.stop_camera()
            self.log("[Vision] Streaming loop terminated.")

    def start_streaming(self):
        with self._stream_lock:
            if self.is_streaming:
                self._last_consumer_ts = time.time()
                return True
            if not self.start_camera():
                self.log("[Vision] Cannot start streaming, camera subscription failed.")
                return False
            self.is_streaming = True
            self._last_consumer_ts = time.time()
            self.streaming_thread = threading.Thread(target=self._stream_loop)
            self.streaming_thread.daemon = True
            self.streaming_thread.start()
            self.log("[Vision] Started streaming to cam.png")
        return True

    def stop_streaming(self):
        thread = None
        with self._stream_lock:
            if not self.is_streaming:
                return True
            self.is_streaming = False
            thread = self.streaming_thread
        if thread:
            thread.join()
        with self._stream_lock:
            self.streaming_thread = None
        self.log("[Vision] Stopped streaming to cam.png")
        return True

    def touch_stream_consumer(self, auto_start=False):
        self._last_consumer_ts = time.time()
        if auto_start and not self.is_streaming:
            try:
                return self.start_streaming()
            except Exception as e:
                self.log("[Vision] Auto-start stream failed: %s" % e, level='warning')
                return False
        return True

    def switch_camera(self, camera_index):
        with self.lock:
            camera_index = self._normalize_camera_index(camera_index)
            was_streaming = self.is_streaming
            
            # Temporarily stop the stream to release the camera handle
            if was_streaming:
                self.is_streaming = False
                if self.streaming_thread:
                    self.streaming_thread.join()
                self.log("[Vision] Paused streaming for camera switch")

            # Unsubscribe from the current camera if it's active
            if self.sub:
                try:
                    self.cam.unsubscribe(self.sub)
                    self.log(f"[Cam] Unsubscribed from camera {self.current_camera_index}")
                    self.sub = None
                except Exception as e:
                    self.log(f"[Cam] Error unsubscribing during switch: {e}", level='warning')

            # Update index and resubscribe
            self.current_camera_index = camera_index
            try:
                self.cam = self.sess.service("ALVideoDevice")
                name = "PepperLifeCam_%d" % int(time.time())
                self.sub = self.cam.subscribeCamera(name, self.current_camera_index, self.res, self.color, self.fps)
                self.log(f"[Cam] Resubscribed to camera {self.current_camera_index}")
            except Exception as e:
                self.log(u"[Cam] Échec de la souscription à la caméra {}: {}".format(self.current_camera_index, e), level='error')
                self.sub = None
                return False

            # Restart the stream if it was running before
            if was_streaming:
                with self._stream_lock:
                    self.is_streaming = True
                    self._last_consumer_ts = time.time()
                    self.streaming_thread = threading.Thread(target=self._stream_loop)
                    self.streaming_thread.daemon = True
                    self.streaming_thread.start()
                self.log("[Vision] Resumed streaming after camera switch")

        return True

    def client(self):
        if self._client is None:
            api_key = None
            try:
                api_key = (self.config.get('openai', {}) or {}).get('api_key')
            except Exception:
                api_key = None
            if isinstance(api_key, str):
                api_key = api_key.strip()
            if not api_key:
                env_key = os.getenv("OPENAI_API_KEY")
                if isinstance(env_key, str) and env_key.strip():
                    api_key = env_key.strip()

            client_kwargs = {"timeout": 15.0}
            if api_key:
                client_kwargs["api_key"] = api_key
            else:
                self.log("[Vision] OPENAI_API_KEY manquant dans la config et l'environnement.", level='error')
            self._client = OpenAI(**client_kwargs)
        return self._client

    def start_camera(self):
        with self.lock:
            self.camera_users += 1
            self.log(f"[Cam] User added. Total users: {self.camera_users}")
            if self.camera_users == 1:
                cam_index = self.current_camera_index
                self.log(f"[Cam] First user, subscribing to camera index {cam_index}.")
                try:
                    self.cam = self.sess.service("ALVideoDevice")
                    name = "PepperLifeCam_%d" % int(time.time())
                    self.sub = self.cam.subscribeCamera(name, cam_index, self.res, self.color, self.fps)
                    self.log("[Cam] ALVideoDevice subscribed: %s" % self.sub)
                    return True
                except Exception as e:
                    self.log(f"[Cam] Abonnement caméra impossible: {e}", level='error')
                    self.sub = None
                    self.camera_users = 0 # Revert on failure
                    return False
        return True

    def stop_camera(self):
        with self.lock:
            if self.camera_users > 0:
                self.camera_users -= 1
            self.log(f"[Cam] User removed. Total users: {self.camera_users}")
            if self.camera_users == 0 and self.sub:
                self.log("[Cam] Last user, unsubscribing from camera.")
                try:
                    self.cam.unsubscribe(self.sub)
                    self.log("[Cam] Unsubscribed")
                except Exception as e:
                    self.log(f"[Cam] Error during unsubscribe: {e}", level='warning')
                self.sub = None
        return True

    def get_frame_rgb(self):
        # No lock here, as getImageRemote should be thread-safe
        # and locking here can cause deadlocks if switch_camera holds the lock for too long.
        if not self.cam or not self.sub:
            return (None, None, None)
        frame_acquired = False
        try:
            f = self.cam.getImageRemote(self.sub)
            frame_acquired = True
            w, h = int(f[0]), int(f[1])
            buf = bytes(f[6]) if f[6] is not None else None
            return (w, h, buf)
        except Exception as e:
            # This error can be spammy if the camera is switching, so log at debug level
            self.log("[Cam] get_frame_rgb error: %s" % e, level='debug')
            return (None, None, None)
        finally:
            if frame_acquired:
                try:
                    self.cam.releaseImage(self.sub)
                except Exception as release_err:
                    self.log("[Cam] releaseImage error: %s" % release_err, level='debug')

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
