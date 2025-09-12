# -*- coding: utf-8 -*-
# classWebServer.py — Un serveur web pour Pepper

import threading
import os
try:
    from http.server import SimpleHTTPRequestHandler
    from socketserver import TCPServer
except ImportError:
    from SimpleHTTPServer import SimpleHTTPRequestHandler
    from SocketServer import TCPServer

class WebServer(object):
    """
    Une classe pour gérer un serveur web simple sur le robot.
    """
    def __init__(self, logger, ui_dir, port=8090):
        """
        Initialise le serveur web.
        """
        self.logger = logger
        self.port = port
        self.ui_dir = ui_dir
        self.httpd = None
        self.http_thread = None
        self.logger("Initialisation du serveur web sur le port %d..." % self.port, level='info')

    def start(self, tablet_instance):
        """
        Démarre le serveur web.
        """
        parent = tablet_instance

        class _Handler(SimpleHTTPRequestHandler):
            def translate_path(self, path):
                import posixpath, urllib
                try:
                    from urllib.parse import unquote
                except Exception:
                    unquote = urllib.unquote
                path = posixpath.normpath(unquote(path.split('?',1)[0].split('#',1)[0]))
                words = filter(None, path.split('/'))
                root = self.server._root_dir
                p = root
                for word in words:
                    if os.path.dirname(word) or os.path.basename(word) != word:
                        continue
                    if word in (os.curdir, os.pardir):
                        continue
                    p = os.path.join(p, word)
                return p

            def log_message(self, fmt, *args):
                try:
                    self.server._logger("[HTTP] " + (fmt % args))
                except Exception:
                    pass

            def _send_503(self, msg):
                self.send_response(503)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                try:
                    self.wfile.write(msg.encode('utf-8'))
                except Exception:
                    pass

            def do_GET(self):
                if self.path.startswith("/last_capture.png"):
                    if not parent.last_capture:
                        return self._send_503("Pas de capture disponible.")
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(parent.last_capture)))
                    self.end_headers()
                    try:
                        self.wfile.write(parent.last_capture)
                    except Exception:
                        pass
                    return

                if self.path.startswith("/cam.png"):
                    if not parent.cam or not parent.cam.sub:
                        return self._send_503("Caméra indisponible (pas d'abonnement).")
                    png_bytes = parent.cam.get_png()
                    if not png_bytes:
                        return self._send_503("Capture échouée.")
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.send_header("Pragma", "no-cache")
                    self.send_header("Expires", "0")
                    self.send_header("Content-Length", str(len(png_bytes)))
                    self.end_headers()
                    try:
                        self.wfile.write(png_bytes)
                    except Exception:
                        pass
                    return

                return SimpleHTTPRequestHandler.do_GET(self)

        TCPServer.allow_reuse_address = True

        tried = [int(self.port), int(self.port)+1, 0]
        last_err = None
        for p in tried:
            try:
                self.httpd = TCPServer(("", p), _Handler)
                self.httpd._root_dir = self.ui_dir
                self.httpd._logger  = self.logger
                self.port = self.httpd.server_address[1]
                break
            except Exception as e:
                last_err = e
                self.logger("[WebServer] HTTP bind échec sur port %s: %s" % (p, e), level='warning')

        if not self.httpd:
            raise RuntimeError("Impossible de démarrer le HTTP server: %s" % last_err)

        self.http_thread = threading.Thread(target=self.httpd.serve_forever)
        self.http_thread.daemon = True
        self.http_thread.start()
        self.logger("[WebServer] Serveur HTTP démarré sur http://localhost:%d/" % self.port)


    def stop(self):
        """
        Arrête le serveur web.
        """
        if self.httpd:
            try:
                self.httpd.shutdown()
            except Exception:
                pass
            self.httpd = None
            self.logger("[WebServer] Serveur HTTP arrêté")