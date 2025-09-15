# -*- coding: utf-8 -*-
# classWebServer.py — Un serveur web pour Pepper

import threading
import os
import json
import socket
import time
from .classAudioUtils import avgabs

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
    def __init__(self, logger, ui_dir, port=8090, mic_toggle_callback=None, session=None, listener=None):
        """
        Initialise le serveur web.
        """
        self.logger = logger
        self.port = port
        self.ui_dir = ui_dir
        self.mic_toggle_callback = mic_toggle_callback
        self.session = session
        self.listener = listener
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
                    self.server._logger("[HTTP] " + (fmt % args), level='debug')
                except Exception:
                    pass

            def _send_json_response(self, data):
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(data).encode("utf-8"))
                except BrokenPipeError:
                    self.server._logger("Broken pipe, client closed connection.", level='debug')
                except Exception as e:
                    self.server._logger("Error in _send_json_response: %s" % e, level='error')

            def _send_503(self, msg):
                try:
                    self.send_response(503)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(msg.encode('utf-8'))
                except BrokenPipeError:
                    self.server._logger("Broken pipe, client closed connection.", level='debug')
                except Exception as e:
                    self.server._logger("Error in _send_503: %s" % e, level='error')

            def do_GET(self):
                if self.path == "/api/heartbeat":
                    try:
                        if parent and hasattr(parent, 'update_heartbeat'):
                            parent.update_heartbeat()
                            self._send_json_response({"status": "ok"})
                        else:
                            self._send_503("Heartbeat callback not available.")
                    except Exception as e:
                        self.server._logger(f"Error processing heartbeat: {e}", level='error')
                        self._send_503("Error processing heartbeat: %s" % e)
                    return

                if self.path == '/' or self.path.startswith('/index.html'):
                    try:
                        with open(os.path.join(self.server._root_dir, 'index.html'), 'r') as f:
                            content = f.read()
                        content = content.replace('%VER%', parent.version_text)
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(content.encode('utf-8'))
                    except Exception as e:
                        self._send_503('Error reading index.html: %s' % e)
                    return

                if self.path == "/api/mic_toggle":
                    if self.server.mic_toggle_callback:
                        enabled = self.server.mic_toggle_callback()
                        self._send_json_response({"enabled": enabled})
                    else:
                        self._send_503("Mic toggle callback not configured.")
                    return

                if self.path == "/api/autonomous_life/state":
                    try:
                        life_service = self.server.session.service("ALAutonomousLife")
                        state = life_service.getState()
                        self._send_json_response({"state": state})
                    except Exception as e:
                        self._send_503("Error getting autonomous life state: %s" % e)
                    return

                if self.path == "/api/autonomous_life/toggle":
                    try:
                        life_service = self.server.session.service("ALAutonomousLife")
                        current_state = life_service.getState()
                        if current_state == "disabled":
                            new_state = "interactive"
                        else:
                            new_state = "disabled"
                        life_service.setState(new_state)
                        self._send_json_response({"state": new_state})
                    except Exception as e:
                        self._send_503("Error toggling autonomous life: %s" % e)
                    return

                if self.path == "/api/posture/state":
                    try:
                        motion_service = self.server.session.service("ALMotion")
                        is_awake = motion_service.robotIsWakeUp()
                        self._send_json_response({"is_awake": is_awake})
                    except Exception as e:
                        self.server._logger("Error getting posture state: %s" % e, level='error')
                        self._send_503("Error getting posture state: %s" % e)
                    return

                if self.path == "/api/posture/toggle":
                    try:
                        motion_service = self.server.session.service("ALMotion")
                        if motion_service.robotIsWakeUp():
                            motion_service.rest()
                            self._send_json_response({"is_awake": False})
                        else:
                            motion_service.wakeUp()
                            self._send_json_response({"is_awake": True})
                    except Exception as e:
                        self._send_503("Error toggling posture: %s" % e)
                    return
                
                if self.path == "/api/sound_level":
                    if self.server.listener:
                        level = avgabs(b"".join(self.server.listener.mon[-1:]))
                        self._send_json_response({"level": level})
                    else:
                        self._send_503("Listener not configured.")
                    return

                if self.path == "/api/volume/state":
                    try:
                        audio_service = self.server.session.service("ALAudioDevice")
                        volume = audio_service.getOutputVolume()
                        self._send_json_response({"volume": volume})
                    except Exception as e:
                        self._send_503("Error getting volume: %s" % e)
                    return

                if self.path == "/api/system/info":
                    # Toujours répondre 200 avec un JSON, même en cas d'erreur partielle
                    naoqi_version = "unknown"
                    ip_addresses = []
                    internet_connected = False

                    # 1) Version NAOqi
                    try:
                        system_service = self.server.session.service("ALSystem")
                        naoqi_version = system_service.systemVersion()
                    except Exception as e:
                        self.server._logger("ALSystem.systemVersion() failed: %s" % e, level='warning')

                    # 2) IPs via ALConnectionManager (si dispo)
                    try:
                        cm = self.server.session.service("ALConnectionManager")
                        # La structure diffère selon les builds NAOqi; on essaye plusieurs accès
                        for svc in cm.services():
                            try:
                                state = svc.get('State') or svc.get('state')
                                if state and state.lower() == 'online':
                                    ipv4 = svc.get('IPv4') or svc.get('ipv4') or {}
                                    # ipv4 peut être un dict ou une liste selon versions…
                                    if isinstance(ipv4, dict):
                                        addr = ipv4.get('Address') or ipv4.get('address')
                                        if addr:
                                            ip_addresses.append(addr)
                                    elif isinstance(ipv4, list):
                                        for item in ipv4:
                                            if isinstance(item, dict):
                                                addr = item.get('Address') or item.get('address')
                                                if addr:
                                                    ip_addresses.append(addr)
                                            elif isinstance(item, str):
                                                ip_addresses.append(item)
                            except Exception:
                                continue
                    except Exception as e:
                        self.server._logger("ALConnectionManager.services() failed: %s" % e, level='warning')

                    # 3) Fallback via ALSystem.systemIp()
                    if not ip_addresses:
                        try:
                            ip = system_service.systemIp()
                            if ip and ip != "127.0.0.1":
                                ip_addresses.append(ip)
                        except Exception:
                            pass

                    # 4) Fallback via socket (interfaces locales)
                    if not ip_addresses:
                        try:
                            hostname = socket.gethostname()
                            # getaddrinfo pour choper toutes les IPv4
                            infos = socket.getaddrinfo(hostname, None, family=socket.AF_INET)
                            dedup = {info[4][0] for info in infos if info[4] and info[4][0] != "127.0.0.1"}
                            ip_addresses.extend(sorted(dedup))
                        except Exception:
                            pass

                    # 5) Test connectivité internet (rapide)
                    try:
                        socket.create_connection(("8.8.8.8", 53), timeout=1)
                        internet_connected = True
                    except OSError:
                        internet_connected = False

                    data = {
                        "naoqi_version": naoqi_version or "unknown",
                        "ip_addresses": ip_addresses,
                        "internet_connected": internet_connected
                    }
                    self.server._logger("System info: %s" % data, level='debug')
                    self._send_json_response(data)
                    return


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

            def do_POST(self):
                if self.path == "/api/volume/set":
                    try:
                        content_length = int(self.headers['Content-Length'])
                        post_data = self.rfile.read(content_length)
                        data = json.loads(post_data)
                        volume = int(data['volume'])
                        audio_service = self.server.session.service("ALAudioDevice")
                        audio_service.setOutputVolume(volume)
                        self.send_response(200)
                        self.end_headers()
                    except Exception as e:
                        self._send_503("Error setting volume: %s" % e)
                    return

        TCPServer.allow_reuse_address = True

        tried = [int(self.port), int(self.port)+1, 0]
        last_err = None
        for p in tried:
            try:
                self.httpd = TCPServer(("", p), _Handler)
                self.httpd._root_dir = self.ui_dir
                self.httpd._logger  = self.logger
                self.httpd.mic_toggle_callback = self.mic_toggle_callback
                self.httpd.session = self.session
                self.httpd.listener = self.listener
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
