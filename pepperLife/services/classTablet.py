# -*- coding: utf-8 -*-
# classTablet.py — gestion UI tablette (ALTabletService) + mini serveur HTTP
from __future__ import print_function
import os, io, atexit, threading
import time

from .classWebServer import WebServer

class classTablet(object):
    """
    Démarre un mini serveur HTTP qui sert une page noire avec un titre bleu,
    et l'affiche sur la tablette via ALTabletService si disponible.
    Permet de fournir la version via un provider (callable) ou un fichier.
    """
    def __init__(self, session=None, logger=None, port=8088,
                 version_text="dev", version_file=None, version_provider=None, mic_toggle_callback=None, listener=None, speaker=None, vision_service=None,
                 start_chat_callback=None, stop_chat_callback=None, get_chat_status_callback=None, get_detailed_chat_status_callback=None, anim=None, config_changed_callback=None,
                 chat_send_callback=None):
        self.session = session
        self._log = logger or (lambda msg, **k: print(msg))
        self.port = int(port)
        self.mic_toggle_callback = mic_toggle_callback
        self.listener = listener
        self.speaker = speaker

        # Source de vérité pour la version
        self.version_provider = version_provider
        self.version_file = version_file
        self.version_text = self._resolve_version(version_text)

        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.ui_dir = os.path.join(os.path.dirname(self.script_dir), "html")
        
        self.web_server = WebServer(root_dir=self.ui_dir, session=self.session, logger=self._log)
        self.web_server.mic_toggle_callback = self.mic_toggle_callback
        self.web_server.listener = self.listener
        self.web_server.speaker = self.speaker
        self.web_server.heartbeat_callback = self.update_heartbeat
        self.web_server.vision_service = vision_service
        self.web_server.start_chat_callback = start_chat_callback
        self.web_server.stop_chat_callback = stop_chat_callback
        self.web_server.get_chat_status_callback = get_chat_status_callback
        self.web_server.get_detailed_chat_status_callback = get_detailed_chat_status_callback
        self.web_server.chat_send_callback = chat_send_callback
        self.web_server.config_changed_callback = config_changed_callback

        self.tablet = None
        self.last_capture = None
        self._ensure_ui_files()

        self.al_memory = None
        self.heartbeat_key = "webview/alive"
        self._tablet_ready_logged = False
        self._tablet_warned_once = False

        # Le WebServer gère son propre thread, on n'a plus besoin de http_thread ici

        self.keep_showing = False
        self.show_thread = None
        self.stop_event = threading.Event()

        # Suivi local (évite les refresh intempestifs si ALMemory mal typé)
        self._last_hb_local = 0.0  # epoch seconds
        self._last_show_ts = 0.0   # dernier show() effectif

        # Récupère ALTabletService si possible (log uniquement si trouvé)
        if not self._ensure_tablet_service() and not self._tablet_warned_once:
            self._log("[Tablet] ALTabletService indisponible; tentative de reconnexion périodique.", level='warning')
            self._tablet_warned_once = True

        # Clean à la sortie du process
        atexit.register(self.stop)

    # ---------- Public API ----------
    def start(self, show=True):
        # Rafraîchit la version
        self.version_text = self._resolve_version(self.version_text)
        self._log("[Tablet] Version UI = %s" % self.version_text)
        
        self.web_server.version_text = self.version_text
        httpd = self.web_server.start(host='0.0.0.0', port=self.port)
        self.port = httpd.server_address[1]

        if not self._ensure_tablet_service() and not self._tablet_warned_once:
            self._log("[Tablet] ALTabletService indisponible; tentative de reconnexion périodique.", level='warning')
            self._tablet_warned_once = True
        if show:
            self.keep_showing = True
            self.show_thread = threading.Thread(target=self._keep_showing_loop)
            self.show_thread.daemon = True
            self.show_thread.start()
        return self.get_url()


    def show(self, url=None, _skip_resolve=False):
        """Affiche l'URL sur la tablette (webview)."""
        if not _skip_resolve and not self._ensure_tablet_service():
            return
        if not self.tablet:
            return
        try:
            resolved_url = url or self.get_url(from_tablet=True)
            self.tablet.showWebview(resolved_url)
            self._log("[Tablet] Webview affichée: %s" % resolved_url, level='debug')
        except Exception as e:
            self._log("[Tablet] Échec showWebview: %s" % e)

    def hide(self):
        """Cache la webview sur la tablette, si présente."""
        if not self._ensure_tablet_service():
            return
        try:
            self.tablet.hideWebview()
        except Exception:
            pass

    def stop(self):
        """Arrête proprement: cache la webview + coupe le serveur HTTP."""
        self.keep_showing = False
        self.stop_event.set()
        if self.show_thread:
            self.show_thread.join()
        self.hide()
        if self.web_server:
            self.web_server.stop()

    def get_url(self, from_tablet=False):
        """
        Retourne l'URL de la page index.
        - from_tablet=True : utilise l'IP spéciale vue depuis la tablette (198.18.0.1).
        """
        host = "198.18.0.1" if from_tablet else "localhost"
        return "http://%s:%d/tablet/index.html?t=%d" % (host, self.port, int(time.time()))

    def set_last_capture(self, image_bytes):
        self.last_capture = image_bytes
        if image_bytes:
            try:
                capture_path = os.path.join(self.ui_dir, "last_capture.png")
                with open(capture_path, "wb") as f:
                    f.write(image_bytes)
                self._log("[Tablet] Saved last_capture.png", level='debug')
            except Exception as e:
                self._log("[Tablet] Failed to write last_capture.png: %s" % e, level='error')

    def show_last_capture_on_tablet(self):
        if not self._ensure_tablet_service():
            return
        try:
            self.tablet.executeJS("show_last_capture()")
        except Exception as e:
            self._log("[Tablet] Échec executeJS(show_last_capture): %s" % e)

    def show_video_feed(self):
        if not self._ensure_tablet_service():
            return
        try:
            self.tablet.executeJS("startPngPolling()")
        except Exception as e:
            self._log("[Tablet] Échec executeJS(startPngPolling): %s" % e)

    def update_heartbeat(self, ts=None):
        """Mise à jour du heartbeat depuis la page web (WebServer).
        - ts: epoch seconds (float/int). Si None, on utilise time.time().
        Met à jour ALMemory *et* un cache local fiable pour éviter les problèmes de type (str/bool).
        """
        try:
            now = float(ts) if ts is not None else time.time()
        except Exception:
            now = time.time()
        self._last_hb_local = now
        if self.al_memory:
            try:
                # Enregistre un float epoch; compatible avec la comparaison time.time() - value
                self.al_memory.insertData(self.heartbeat_key, float(now))
                self._log("Updating heartbeat key '%s'" % self.heartbeat_key, level='debug')
            except Exception as e:
                self._log("[Tablet] insertData heartbeat KO: %s" % e, level='warning')
        self._log("Heartbeat received. Parent is: %r" % self, level='debug')

    def _keep_showing_loop(self):
        # Paramètres anti-refresh
        heartbeat_timeout = 45.0   # avant: 25s (trop court si tablette en veille légère)
        min_show_interval = 90.0   # ne jamais réafficher plus souvent que toutes les 90s
        while self.keep_showing:
            try:
                self._ensure_tablet_service()
                if not self.tablet:
                    self.stop_event.wait(10)
                    continue
                now = time.time()
                last_hb_mem = None
                if self.al_memory:
                    try:
                        val = self.al_memory.getData(self.heartbeat_key)
                        # Convertit proprement en float epoch si possible
                        if isinstance(val, (int, float)):
                            last_hb_mem = float(val)
                        elif isinstance(val, (str, bytes)):
                            try:
                                last_hb_mem = float(val)
                            except Exception:
                                last_hb_mem = None
                    except Exception:
                        last_hb_mem = None
                # Utilise le meilleur des deux (ALMemory ou cache local)
                last_hb = last_hb_mem if (last_hb_mem is not None) else self._last_hb_local
                age = (now - last_hb) if (last_hb > 0) else 1e9
                since_last_show = now - self._last_show_ts
                if age > heartbeat_timeout and since_last_show > min_show_interval:
                    self._log("[Tablet] Heartbeat trop vieux (%.1fs), réaffichage webview." % age, level='debug')
                    self.show()
                    self._last_show_ts = now
            except Exception as e:
                self._log("[Tablet] Erreur dans _keep_showing_loop: %s" % e, level='error')
            self.stop_event.wait(10)  # Vérification toutes les 10s

    # ---------- Internes ----------
    def _ensure_tablet_service(self):
        if self.tablet:
            return True
        if not self.session:
            return False
        try:
            tablet = self.session.service("ALTabletService")
        except Exception:
            return False
        self.tablet = tablet
        try:
            self.al_memory = self.session.service("ALMemory")
            if self.al_memory:
                self.al_memory.insertData(self.heartbeat_key, float(self._last_hb_local or 0.0))
        except Exception:
            self.al_memory = None
        self._handle_tablet_ready()
        return True

    def _handle_tablet_ready(self):
        if not self.tablet:
            return
        if not self._tablet_ready_logged:
            self._log("[Tablet] ALTabletService détecté, activation de la webview.")
            self._tablet_ready_logged = True
        self._tablet_warned_once = False
        try:
            self.tablet.wakeUp()
            self.tablet.turnScreenOn(True)
        except Exception as e:
            self._log("[Tablet] Impossible d'initialiser la tablette: %s" % e, level='warning')
        if self.keep_showing:
            try:
                self.show(_skip_resolve=True)
                self._last_show_ts = time.time()
            except Exception as e:
                self._log("[Tablet] Impossible d'afficher la webview après connexion: %s" % e, level='warning')

    def _resolve_version(self, default_text):
        """Ordre: provider() -> fichier -> texte fourni -> 'dev'."""
        v = self._get_version_from_provider()
        if v:
            return v
        v = self._read_version_file()
        if v:
            return v
        return default_text or u"dev"

    def _get_version_from_provider(self):
        try:
            if callable(self.version_provider):
                return (self.version_provider() or u"").strip()
        except Exception as e:
            self._log("[Tablet] version_provider a échoué: %s" % e)
        return None

    def _read_version_file(self):
        # Si un chemin explicite est donné, on l’utilise
        path = self.version_file
        if path and os.path.isfile(path):
            try:
                with io.open(path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as e:
                self._log("[Tablet] Lecture version_file échouée: %s" % e)
                return None
        # Sinon on ne force rien ici — on laisse la logique de classSystem être la source de vérité
        return None

    def _ensure_ui_files(self):
        if not os.path.exists(self.ui_dir):
            os.makedirs(self.ui_dir)
        index_path = os.path.join(self.ui_dir, "index.html")
        if not os.path.exists(index_path):
            self._log("[Tablet] Fichier index.html manquant dans %s" % self.ui_dir, level='error')

        # Favicon stub pour éviter le 404
        fav = os.path.join(self.ui_dir, "favicon.ico")
        if not os.path.exists(fav):
            with io.open(fav, "wb") as f:
                f.write(b"")
