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
                 version_text=u"dev", version_file=None, version_provider=None, mic_toggle_callback=None, listener=None):
        self.session = session
        self._log = logger or (lambda msg, **k: print(msg))
        self.port = int(port)
        self.mic_toggle_callback = mic_toggle_callback
        self.listener = listener

        # Source de vérité pour la version
        self.version_provider = version_provider
        self.version_file = version_file
        self.version_text = self._resolve_version(version_text)

        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.ui_dir = os.path.join(os.path.dirname(self.script_dir), "gui")
        self.web_server = WebServer(logger=self._log, ui_dir=self.ui_dir, port=self.port, mic_toggle_callback=self.mic_toggle_callback, session=self.session, listener=self.listener)
        self.port = self.web_server.port
        self.tablet = None
        self.last_capture = None
        self._ensure_ui_files()

        self.al_memory = None
        self.heartbeat_key = "webview/alive"

        self.keep_showing = False
        self.show_thread = None

        # Suivi local (évite les refresh intempestifs si ALMemory mal typé)
        self._last_hb_local = 0.0  # epoch seconds
        self._last_show_ts = 0.0   # dernier show() effectif

        # Récupère ALTabletService si possible
        try:
            if self.session:
                self.tablet = self.session.service("ALTabletService")
                self.al_memory = self.session.service("ALMemory")
                self.al_memory.insertData(self.heartbeat_key, 0.0)
        except Exception as e:
            self._log("[Tablet] ALTabletService indisponible: %s" % e)

        # Clean à la sortie du process
        atexit.register(self.stop)

    # ---------- Public API ----------
    def start(self, show=True):
        # Rafraîchit la version
        self.version_text = self._resolve_version(self.version_text)
        self._log("[Tablet] Version UI = %s" % self.version_text)
        self.web_server.start(self)
        self.port = self.web_server.port
        if self.tablet:
            self.tablet.wakeUp()
            self.tablet.turnScreenOn(True)
        if show:
            self.keep_showing = True
            self.show_thread = threading.Thread(target=self._keep_showing_loop)
            self.show_thread.daemon = True
            self.show_thread.start()
        return self.get_url()


    def show(self, url=None):
        """Affiche l'URL sur la tablette (webview)."""
        if not self.tablet:
            self._log("[Tablet] Pas de tablette; UI visible sur %s" % self.get_url())
            return
        try:
            self.tablet.showWebview(url or self.get_url(from_tablet=True))
            self._log("[Tablet] Webview affichée: %s" % (url or self.get_url(from_tablet=True)))
        except Exception as e:
            self._log("[Tablet] Échec showWebview: %s" % e)

    def hide(self):
        """Cache la webview sur la tablette, si présente."""
        if not self.tablet:
            return
        try:
            self.tablet.hideWebview()
        except Exception:
            pass

    def stop(self):
        """Arrête proprement: cache la webview + coupe le serveur HTTP."""
        self.keep_showing = False
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
        return "http://%s:%d/index.html?t=%d" % (host, self.port, int(time.time()))

    def set_last_capture(self, image_bytes):
        self.last_capture = image_bytes

    def show_last_capture_on_tablet(self):
        if not self.tablet:
            return
        try:
            self.tablet.executeJS("show_last_capture()")
        except Exception as e:
            self._log("[Tablet] Échec executeJS(show_last_capture): %s" % e)

    def show_video_feed(self):
        if not self.tablet:
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
            time.sleep(10)  # Vérification toutes les 10s

    # ---------- Internes ----------
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
