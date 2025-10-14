# -*- coding: utf-8 -*-
"""
class WebServer.py — Serveur web pour PepperLife (version étendue, v2)

• Conserve la compatibilité avec les routes existantes
  - /                 sert index.html (remplace %VER%)
  - /api/heartbeat
  - /api/mic_toggle
  - /api/sound_level
  - /api/volume/state
  - /api/volume/set
  - /api/autonomous_life/state
  - /api/autonomous_life/toggle
  - /api/posture/state
  - /api/posture/toggle
  - /cam.png, /last_capture.png (gérés en statique si présents dans root_dir)
...
  - POST /api/apps/stop  {name}
  - GET  /api/memory/search?pattern=...
  - GET  /api/memory/get?key=...
  - POST /api/memory/set {key, value}
  - GET  /api/settings/get
  - POST /api/settings/set {...}
  - GET  /api/logs/tail?n=200

• Ajoute la gestion du backend
  - GET  /api/system/status
  - POST /api/system/start
  - POST /api/system/stop
  - GET  /api/system/logs

• Nouveautés v2 (corrige 404 + crash log_message)
  - GET  /api/tts/languages        -> _get_tts_languages()
  - GET  /api/config/user          -> _config_get_user()
  - GET  /api/system_prompt        -> _get_system_prompt()
  - log_message() tolère les appels http.server (args[0] peut être HTTPStatus)

Toutes les routes échouent en douceur si le service NAOqi demandé n'est pas disponible.
"""
from __future__ import print_function

import os
import json
import time
import socket
import threading
import subprocess
import collections

try:
    # Python 3
    from urllib.parse import urlparse, parse_qs
except Exception:
    # Python 2 fallback
    from urlparse import urlparse, parse_qs

def ansi_to_html(text):
    # Conversion minimaliste ANSI → HTML (pour affichage des logs côté UI)
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text = text.replace('\033[95m', '<span style="color: magenta">')
    text = text.replace('\033[94m', '<span style="color: blue">')
    text = text.replace('\033[96m', '<span style="color: cyan">')
    text = text.replace('\033[92m', '<span style="color: green">')
    text = text.replace('\033[93m', '<span style="color: yellow">')
    text = text.replace('\033[91m', '<span style="color: red">')
    text = text.replace('\033[1m', '<span style="font-weight: bold">')
    text = text.replace('\033[4m', '<span style="text-decoration: underline">')
    text = text.replace('\033[0m', '</span>')
    return text

try:
    from http.server import SimpleHTTPRequestHandler
    from socketserver import TCPServer, ThreadingMixIn
except ImportError:
    from SimpleHTTPServer import SimpleHTTPRequestHandler
    from SocketServer import TCPServer, ThreadingMixIn

from .classSystem import version as SysVersion

try:
    from .classAudioUtils import avgabs
except Exception:
    def avgabs(_b):
        return 0

class _LockedServiceProxy(object):
    """Proxy qui sérialise tous les appels vers un service NAOqi via un RLock."""
    __slots__ = ("_lock", "_svc")
    def __init__(self, lock, svc):
        self._lock = lock
        self._svc = svc
    def __getattr__(self, name):
        target = getattr(self._svc, name)
        if callable(target):
            def _wrapped(*args, **kwargs):
                with self._lock:
                    return target(*args, **kwargs)
            return _wrapped
        # Attribut non-callable (ex: propriété)
        with self._lock:
            return target

class WebServer(object):
    def __init__(self, root_dir='.', session=None, logger=None, anim=None):
        self._root_dir = os.path.abspath(root_dir)
        self.session = session
        self._logger = logger or (lambda *a, **k: None)
        self.anim = anim
        self.heartbeat_callback = None
        self.mic_toggle_callback = None
        self.listener = None
        self.speaker = None
        self.version_text = 'dev'
        self.vision_service = None
        self.start_chat_callback = None
        self.stop_chat_callback = None
        self.get_chat_status_callback = None
        self.get_detailed_chat_status_callback = None
        self.config_changed_callback = None
        self._behavior_nature_cache = {}
        self._last_installed_behaviors = []
        self._running_behaviors = set()
        self._running_animation_futures = {}
        self._last_heartbeat = 0
        self._httpd = None
        self._backend_process = None
        self._backend_logs = collections.deque(maxlen=500)
        self._naoqi_lock = threading.RLock()
        self._svc_cache = {}

    def svc(self, name):
        """Récupère un service NAOqi sous verrou, renvoie un proxy verrouillé pour ses méthodes."""
        try:
            if not self.session:
                self._logger(f"[WebServer] svc({name}): session is None", level='error')
                return None
            with self._naoqi_lock:  # <-- important : sérialise l'appel C++ session.service
                if name in self._svc_cache:
                    return self._svc_cache[name]
                raw = self.session.service(name)
                if raw is None:
                    return None
                proxy = _LockedServiceProxy(self._naoqi_lock, raw)
                self._svc_cache[name] = proxy
                return proxy
        except Exception as e:
            self._logger(f"[WebServer] svc({name}): exception while getting service: {e}", level='error')
            return None

    def update_heartbeat(self):
        self._last_heartbeat = time.time()
        if self.heartbeat_callback:
            self.heartbeat_callback()

    def _read_output(self, pipe):
        try:
            while True:
                line = pipe.readline()
                if not line:
                    break
                try:
                    text = line.decode('utf-8', 'ignore').rstrip('\n')
                except Exception:
                    text = str(line).rstrip('\n')
                self._backend_logs.append(text)
        except Exception as e:
            self._logger(f"[WebServer] _read_output error: {e}", level='error')
        finally:
            try: pipe.close()
            except Exception: pass

    def start(self, host='0.0.0.0', port=8080):
        class ThreadingTCPServer(ThreadingMixIn, TCPServer):
            allow_reuse_address = True
            daemon_threads = True

        os.chdir(self._root_dir)
        self._logger('Web root: %s' % self._root_dir)
        httpd = ThreadingTCPServer((host, port), self._make_handler())
        httpd._root_dir = self._root_dir
        httpd._logger = self._logger
        httpd.session = self.session
        httpd.parent = self
        httpd.mic_toggle_callback = self.mic_toggle_callback
        httpd.listener = self.listener
        self._httpd = httpd
        th = threading.Thread(target=httpd.serve_forever)
        th.daemon = True
        th.start()
        self._logger('Serveur Web (multi-thread) démarré sur %s:%s' % (host, port))
        return httpd

    def stop(self):
        if self._backend_process:
            self._logger("[WebServer] Stopping managed backend process...")
            try:
                os.killpg(os.getpgid(self._backend_process.pid), subprocess.signal.SIGTERM)
                self._backend_process.wait(timeout=5)
            except Exception as e:
                self._logger(f"[WebServer] Error while stopping backend: {e}", level='error')
        if self._httpd:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass

    def _make_handler(self):
        parent = self

        class Handler(SimpleHTTPRequestHandler):
            server_version = "PepperLife-HTTP/1.0"

            # ---------- CORS helpers ----------
            def _apply_cors(self):
                origin = self.headers.get('Origin')
                if origin:
                    self.send_header('Access-Control-Allow-Origin', origin)
                    self.send_header('Vary', 'Origin')
                else:
                    self.send_header('Access-Control-Allow-Origin', '*')
                # allow credentials if frontend uses cookies/authorization
                self.send_header('Access-Control-Allow-Credentials', 'true')

            def do_OPTIONS(self):
                # CORS preflight
                try:
                    self.send_response(204)  # No Content
                    self._apply_cors()
                    acrh = self.headers.get('Access-Control-Request-Headers', 'Content-Type, Authorization, X-Requested-With, Accept')
                    self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                    self.send_header('Access-Control-Allow-Headers', acrh)
                    self.send_header('Access-Control-Max-Age', '600')
                    self.end_headers()
                except Exception:
                    try:
                        # last resort
                        self.send_response(204)
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, Accept')
                        self.end_headers()
                    except Exception:
                        pass

            def log_message(self, format, *args):
                # Ne plante pas si http.server passe un HTTPStatus
                try:
                    if args and isinstance(args[0], str) and args[0].startswith('GET /api/'):
                        return
                except Exception:
                    pass
                try:
                    parent._logger(format % args, level='debug')
                except Exception:
                    try:
                        parent._logger(str(format) + " " + " ".join(map(repr, args)), level='debug')
                    except Exception:
                        pass

            def _json(self, code, payload, headers=None):
                try:
                    data = json.dumps(payload).encode('utf-8')
                except Exception as e:
                    data = json.dumps({'error': 'json', 'detail': str(e)}).encode('utf-8')
                self.send_response(code)
                self._apply_cors()
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                if headers:
                    for k, v in headers.items():
                        self.send_header(k, v)
                self.end_headers()
                try:
                    self.wfile.write(data)
                except BrokenPipeError:
                    parent._logger("[WebServer] BrokenPipeError: client disconnected before response.", level='warning')
                except Exception as e:
                    parent._logger(f"[WebServer] Error writing response: {e}", level='error')

            def _text(self, code, text, ctype='text/plain; charset=utf-8'):
                self.send_response(code)
                self._apply_cors()
                self.send_header('Content-Type', ctype)
                self.end_headers()
                try:
                    if isinstance(text, str):
                        text = text.encode('utf-8')
                    self.wfile.write(text)
                except Exception:
                    pass

            def _send_503(self, msg):
                self._json(503, {'error': str(msg)})

            def _serve_index(self):
                try:
                    p = os.path.join(self.server._root_dir, 'index.html')
                    with open(p, 'r', encoding='utf-8') as f:
                        content = f.read()
                    content = content.replace('%VER%', getattr(parent, 'version_text', 'dev'))
                    self._text(200, content, 'text/html; charset=utf-8')
                except Exception as e:
                    self._send_503('Error reading index.html: %s' % e)

            # ---------- Routes ----------
            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path

                # backend/system
                if path == '/api/system/status': self._get_system_status(); return
                if path == '/api/system/logs': self._get_system_logs(); return

                # chat
                if path == '/api/chat/status': self._get_chat_status(); return
                if path == '/api/chat/detailed_status': self._get_detailed_chat_status(); return

                # misc
                if path == '/api/heartbeat':
                    try:
                        if parent and hasattr(parent, 'update_heartbeat'):
                            parent.update_heartbeat()
                            self._json(200, {'status': 'ok', 'ts': time.time()})
                        else:
                            self._send_503('Callback Heartbeat non disponible.')
                    except Exception as e:
                        self._send_503('Erreur lors du traitement du heartbeat: %s' % e)
                    return

                if path == '/' or path == '/index.html': self._serve_index(); return
                if path == '/tablet/index.html':
                    try:
                        p = os.path.join(self.server._root_dir, 'tablet', 'index.html')
                        with open(p, 'r', encoding='utf-8') as f:
                            content = f.read()
                        content = content.replace('%VER%', getattr(parent, 'version_text', 'dev'))
                        self._text(200, content, 'text/html; charset=utf-8')
                    except Exception as e:
                        self._send_503('Error reading tablet/index.html: %s' % e)
                    return

                if path == '/api/mic/status': self._get_mic_status(); return

                # controls
                if path == '/api/mic_toggle':
                    cb = getattr(self.server, 'mic_toggle_callback', None) or getattr(self.server.parent, 'mic_toggle_callback', None)
                    if cb:
                        try:
                            ok = cb()
                            self._json(200, {'enabled': bool(ok)})
                        except Exception as e:
                            self._send_503('mic_toggle error: %s' % e)
                    else:
                        self._send_503('Callback mic_toggle non disponible.')
                    return
                if path == '/api/sound_level':
                    listener = getattr(self.server, 'listener', None)
                    if listener and hasattr(listener, 'mon'):
                        try:
                            level = avgabs(listener.get_last_audio_chunk())
                            self._json(200, {'level': level})
                        except Exception as e:
                            self._send_503('sound_level error: %s' % e)
                    else:
                        self._send_503('Listener not configured.')
                    return

                # audio/volume
                if path == '/api/volume/state':
                    try:
                        ad = parent.svc('ALAudioDevice')
                        vol = ad.getOutputVolume() if ad else 0
                        self._json(200, {'volume': int(vol)})
                    except Exception as e:
                        self._send_503('volume/state error: %s' % e)
                    return

                if path == '/api/version': self._text(200, getattr(self.server.parent, 'version_text', 'dev')); return
                if path == '/api/system/info': self._get_system_info(); return
                if path == '/api/autonomous_life/state': self._get_life_state(); return
                if path == '/api/posture/state': self._get_posture_state(); return
                if path == '/api/hardware/info': self._get_hardware_info(); return
                if path == '/api/hardware/details': self._get_hardware_details(); return
                if path == '/api/wifi/scan': self._wifi_scan(); return
                if path == '/api/wifi/status': self._wifi_status(); return
                if path == '/api/apps/list': self._apps_list(); return
                if path == '/api/memory/search': self._memory_search(parsed); return
                if path == '/api/memory/get': self._memory_get(parsed); return
                if path == '/api/settings/get': self._settings_get(); return
                if path == '/api/config/default': self._config_get_default(); return
                if path == '/api/config/user': self._config_get_user(); return
                if path == '/api/logs/tail':
                    try:
                        n = int(parse_qs(parsed.query or '').get('n', ['200'])[0])
                    except Exception:
                        n = 200
                    p = os.path.join(self.server._root_dir, 'logs', 'pepperlife.log')
                    try:
                        lines = tail(p, n=n)
                        self._json(200, {'lines': lines})
                    except Exception as e:
                        self._send_503('tail logs error: %s' % e)
                    return
                if path == '/api/system_prompt': self._get_system_prompt(); return
                if path == '/api/tts/languages': self._get_tts_languages(); return
                if path == '/api/camera/status': self._camera_status(); return

                # Routes pour les logs
                if path == '/api/logs/launcher' or path == '/api/logs/service':
                    log_filename = 'lanceur.log' if path == '/api/logs/launcher' else 'pepper_life_service.log'
                    # Les logs sont dans le répertoire bin, qui est un niveau au-dessus de services/
                    log_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'bin', log_filename))
                    logs = []
                    try:
                        if os.path.exists(log_path):
                            with open(log_path, 'r') as f:
                                logs = [ansi_to_html(line.strip()) for line in f.readlines()]
                        else:
                            logs = ["Fichier log '{}' introuvable.".format(log_filename)]
                    except Exception as e:
                        logs = ["Erreur lors de la lecture de '{}': {}".format(log_filename, e)]
                    self._json(200, {'logs': logs})
                    return

                # Fichiers statiques
                if path in ('/cam.png', '/last_capture.png'):
                    p = os.path.join(self.server._root_dir, path.lstrip('/'))
                    if os.path.isfile(p):
                        try:
                            with open(p, 'rb') as f:
                                data = f.read()
                            self.send_response(200)
                            self._apply_cors()
                            self.send_header('Content-Type', 'image/png')
                            self.end_headers()
                            self.wfile.write(data)
                        except Exception:
                            pass
                        return

                # Sinon, laisser SimpleHTTPRequestHandler gérer
                return SimpleHTTPRequestHandler.do_GET(self)

            def do_POST(self):
                parsed = urlparse(self.path)
                path = parsed.path
                length = int(self.headers.get('Content-Length', '0') or '0')
                body = self.rfile.read(length) if length else b''
                try:
                    payload = json.loads(body.decode('utf-8')) if body else {}
                except Exception:
                    payload = {}

                if path == '/api/system/start': self._system_start(); return
                if path == '/api/system/stop': self._system_stop(); return
                if path == '/api/system/shutdown': self._system_shutdown(); return
                if path == '/api/system/restart': self._system_restart(); return
                if path == '/api/system/clear_logs': self._system_clear_logs(); return
                if path == '/api/camera/start_stream': self._camera_start_stream(); return
                if path == '/api/camera/stop_stream': self._camera_stop_stream(); return
                if path == '/api/camera/switch': self._camera_switch(payload); return
                if path == '/api/volume/set':
                    try:
                        v = int((payload or {}).get('volume', 0))
                        ad = parent.svc('ALAudioDevice')
                        if not ad: self._send_503('ALAudioDevice indisponible'); return
                        ad.setOutputVolume(max(0, min(100, v)))
                        self._json(200, {'ok': True})
                    except Exception as e:
                        self._send_503('volume/set error: %s' % e)
                    return
                if path == '/api/autonomous_life/toggle': self._life_toggle(); return
                if path == '/api/autonomous_life/set_state': self._life_set_state(payload); return
                if path == '/api/posture/toggle': self._posture_toggle(); return
                if path == '/api/posture/set_state': self._posture_set_state(payload); return
                if path == '/api/apps/start': self._apps_start(payload); return
                if path == '/api/apps/stop': self._apps_stop(payload); return
                if path == '/api/memory/set': self._memory_set(payload); return
                if path == '/api/settings/set': self._settings_set(payload); return
                if path == '/api/config/user': self._config_set_user(payload); return
                if path == '/api/speak': self._speak(payload); return
                if path == '/api/tts/set_language': self._set_tts_language(payload); return
                if path == '/api/chat/start': self._chat_start(payload); return
                if path == '/api/chat/stop': self._chat_stop(); return
                if path == '/api/system_prompt': self._set_system_prompt(payload); return
                self._send_503('Unknown POST %s' % path)

            def _get_mic_status(self):
                listener = getattr(self.server, 'listener', None)
                if listener and hasattr(listener, 'is_micro_enabled'):
                    try:
                        status = listener.is_micro_enabled()
                        self._json(200, {'enabled': status})
                    except Exception as e:
                        self._send_503('mic_status error: %s' % e)
                else:
                    self._send_503('Listener not configured for status.')

            # ----- Chat status -----
            def _get_detailed_chat_status(self):
                cb = getattr(self.server.parent, 'get_detailed_chat_status_callback', None)
                if cb:
                    try:
                        status = cb()
                        self._json(200, status)
                    except Exception as e:
                        self._send_503('get_detailed_chat_status failed: %s' % e)
                else:
                    self._send_503('Callback get_detailed_chat_status indisponible')

            def _get_chat_status(self):
                cb = getattr(self.server.parent, 'get_chat_status_callback', None)
                if cb:
                    try:
                        status = cb()
                        self._json(200, status)
                    except Exception as e:
                        self._send_503('get_chat_status failed: %s' % e)
                else:
                    self._send_503('Callback get_chat_status indisponible')

            # ----- Camera -----
            def _camera_status(self):
                try:
                    vision = self.server.parent.vision_service
                    if vision:
                        self._json(200, {'is_streaming': getattr(vision, 'is_streaming', False),
                                         'current_camera': 'top' if getattr(vision, 'current_camera_index', 0) == 0 else 'bottom'})
                    else:
                        self._send_503('Vision service not available.')
                except Exception as e:
                    self._send_503('Failed to get camera status: %s' % e)

            def _camera_switch(self, payload):
                try:
                    vision = self.server.parent.vision_service
                    camera = (payload or {}).get('camera')
                    if vision and camera in ('top', 'bottom'):
                        # Assume vision.switch_camera accepte 'top'/'bottom' (adapter si besoin)
                        ok = vision.switch_camera(camera)
                        self._json(200, {'status': 'ok' if ok else 'failed', 'camera': camera})
                    else:
                        self._send_503('Vision service not available or invalid camera.')
                except Exception as e:
                    self._send_503('Failed to switch camera: %s' % e)

            def _camera_start_stream(self):
                try:
                    vision = self.server.parent.vision_service
                    if vision:
                        if vision.start_streaming(): self._json(200, {'status': 'ok'})
                        else: self._send_503('Failed to start camera stream, check logs.')
                    else:
                        self._send_503('Vision service not available.')
                except Exception as e:
                    self._send_503('Failed to start stream: %s' % e)

            def _camera_stop_stream(self):
                try:
                    vision = self.server.parent.vision_service
                    if vision:
                        vision.stop_streaming()
                        self._json(200, {'status': 'ok'})
                    else:
                        self._send_503('Vision service not available.')
                except Exception as e:
                    self._send_503('Failed to stop stream: %s' % e)

            # ----- System management -----
            def _system_shutdown(self):
                try:
                    pls = parent.svc('ALSystem')
                    if not pls: self._send_503('ALSystem indisponible'); return
                    pls.shutdown()
                    self._json(200, {'status': 'ok'})
                except Exception as e:
                    self._send_503('shutdown error: %s' % e)

            def _system_restart(self):
                try:
                    pls = parent.svc('ALSystem')
                    if not pls: self._send_503('ALSystem indisponible'); return
                    pls.reboot()
                    self._json(200, {'status': 'ok'})
                except Exception as e:
                    self._send_503('reboot error: %s' % e)

            def _system_clear_logs(self):
                try:
                    logs_dir = os.path.join(self.server._root_dir, 'logs')
                    for fn in ('pepperlife.log',):
                        p = os.path.join(logs_dir, fn)
                        if os.path.isfile(p):
                            open(p, 'w').close()
                    self._json(200, {'status': 'ok'})
                except Exception as e:
                    self._send_503('clear_logs error: %s' % e)

            def _system_start(self):
                if parent._backend_process and parent._backend_process.poll() is None:
                    self._json(409, {'error': 'Backend already running.'}); return
                parent._backend_logs.clear()
                cmd = ['/home/nao/.local/share/PackageManager/apps/pepperlife/pepperLife.py']
                try:
                    parent._logger("Starting backend process with command: %s" % " ".join(cmd))
                    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, pre_exec_fn=os.setsid)
                    parent._backend_process = proc
                    th = threading.Thread(target=parent._read_output, args=(proc.stdout,))
                    th.daemon = True
                    th.start()
                    self._json(200, {'status': 'ok', 'pid': proc.pid})
                except Exception as e:
                    self._send_503('Failed to start backend: %s' % e)

            def _system_stop(self):
                try:
                    if parent._backend_process and parent._backend_process.poll() is None:
                        os.killpg(os.getpgid(parent._backend_process.pid), subprocess.signal.SIGTERM)
                        parent._backend_process.wait(timeout=5)
                        self._json(200, {'status': 'ok'})
                    else:
                        self._json(200, {'status': 'not_running'})
                except Exception as e:
                    self._send_503('Failed to stop backend: %s' % e)

            def _get_system_status(self):
                python3_exists = SysVersion.is_python3_nao_installed()
                backend_running = parent._backend_process and parent._backend_process.poll() is None
                self._json(200, {'python3_installed': python3_exists, 'backend_running': backend_running})

            def _get_system_logs(self):
                logs_html = [ansi_to_html(log) for log in parent._backend_logs]
                self._json(200, {'logs': logs_html})

            # ----- System prompt -----
            def _get_system_prompt(self):
                try:
                    prompt_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'prompts', 'system_prompt.txt'))
                    content = ''
                    if os.path.isfile(prompt_path):
                        with open(prompt_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                    self._json(200, {'content': content})
                except Exception as e:
                    self._send_503('Failed to read system prompt: %s' % e)

            def _set_system_prompt(self, payload):
                try:
                    content_value = payload.get('content')
                    text_to_write = None
                    if isinstance(content_value, str): text_to_write = content_value
                    elif isinstance(content_value, dict): text_to_write = content_value.get('content')
                    if not isinstance(text_to_write, str):
                        self._json(400, {'error': 'Invalid content format'}); return
                    prompt_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'prompts', 'system_prompt.txt'))
                    os.makedirs(os.path.dirname(prompt_path), exist_ok=True)
                    with open(prompt_path, 'w', encoding='utf-8') as f:
                        f.write(text_to_write)
                    self._json(200, {'success': True})
                except Exception as e:
                    self._send_503('Failed to write system prompt: %s' % e)

            # ====== NAOqi-backed endpoints ======
            def _get_system_info(self):
                """GET /api/system/info - Récupère les informations système générales."""
                info = {'version': getattr(self.server.parent, 'version_text', 'dev'),
                        'naoqi_version': None, 'ip_addresses': [], 'internet_connected': False,
                        'battery': {'charge': None, 'plugged': None}}
                try:
                    al_system = parent.svc('ALSystem')
                    if al_system: info['naoqi_version'] = al_system.systemVersion()
                except Exception: pass
                try: info['ip_addresses'] = self._ip_addresses()
                except Exception: pass
                try: info['internet_connected'] = self._check_internet()
                except Exception: pass
                try:
                    al_batt = parent.svc('ALBattery')
                    if al_batt:
                        try: info['battery']['charge'] = al_batt.getBatteryCharge()
                        except Exception: pass
                        try: info['battery']['plugged'] = al_batt.isBatteryFull()
                        except Exception: pass
                except Exception:
                    pass
                self._json(200, info)

            def _get_life_state(self):
                try:
                    life = parent.svc('ALAutonomousLife')
                    if not life:
                        self._send_503('ALAutonomousLife indisponible'); return
                    state = life.getState()
                    self._json(200, {'current_state': state,
                                     'all_states': ["solitary", "interactive", "disabled", "safeguard"]})
                except Exception as e:
                    self._send_503('life/state error: %s' % e)

            def _get_posture_state(self):
                try:
                    motion = parent.svc('ALMotion')
                    if not motion:
                        self._json(200, {'is_awake': False}); return
                    is_awake = bool(motion.robotIsWakeUp())
                    self._json(200, {'is_awake': is_awake})
                except Exception as e:
                    self._send_503('posture/state error: %s' % e)

            def _life_toggle(self):
                try:
                    life = parent.svc('ALAutonomousLife')
                    if not life: self._send_s03('ALAutonomousLife indisponible'); return
                    s = life.getState()
                    if s in ('interactive', 'solitary'):
                        life.setState('disabled')
                    else:
                        life.setState('interactive')
                    self._json(200, {'state': life.getState()})
                except Exception as e:
                    self._send_503('autonomous_life/toggle error: %s' % e)

            def _life_set_state(self, payload):
                try:
                    state = (payload or {}).get('state')
                    allowed_states = ["solitary", "interactive", "disabled", "safeguard"]
                    if not state in allowed_states:
                        self._json(400, {'error': 'Invalid state specified'}); return
                    
                    life = parent.svc('ALAutonomousLife')
                    if not life: self._send_503('ALAutonomousLife indisponible'); return

                    life.setState(state)
                    
                    self._json(200, {'state': life.getState()})
                except Exception as e:
                    self._send_503('autonomous_life/set_state error: %s' % e)

            def _posture_toggle(self):
                try:
                    motion = parent.svc('ALMotion')
                    if not motion: self._send_503('ALMotion indisponible'); return
                    if motion.robotIsWakeUp():
                        motion.rest()
                    else:
                        motion.wakeUp()
                    self._json(200, {'is_awake': bool(motion.robotIsWakeUp())})
                except Exception as e:
                    self._send_503('posture/toggle error: %s' % e)

            def _posture_set_state(self, payload):
                try:
                    state = (payload or {}).get('state')
                    if not state in ['wakeUp', 'rest']:
                        self._json(400, {'error': 'Invalid state specified'}); return
                    
                    motion = parent.svc('ALMotion')
                    if not motion: self._send_503('ALMotion indisponible'); return

                    if state == 'wakeUp':
                        motion.wakeUp()
                    else: # rest
                        motion.rest()
                    
                    self._json(200, {'is_awake': bool(motion.robotIsWakeUp())})
                except Exception as e:
                    self._send_503('posture/set_state error: %s' % e)

            def _get_hardware_info(self):
                """GET /api/hardware/info - Récupère un résumé de l'état matériel."""
                info = {
                    'system': {'version': 'N/A', 'robot': 'N/A'},
                    'battery': {'charge': 'N/A', 'plugged': 'N/A'},
                    'motion': {'awake': 'N/A', 'stiffness': 'N/A'},
                    'audio': {'language': 'N/A'}
                }
                try:
                    sys = parent.svc('ALSystem')
                    if sys:
                        info['system']['version'] = sys.systemVersion()
                        info['system']['robot'] = getattr(sys, 'robotName', lambda: 'N/A')()
                except Exception: pass
                try:
                    batt = parent.svc('ALBattery')
                    if batt:
                        info['battery']['charge'] = batt.getBatteryCharge()
                        info['battery']['plugged'] = batt.isBatteryFull()
                except Exception: pass
                try:
                    motion = parent.svc('ALMotion')
                    if motion:
                        info['motion']['awake'] = motion.robotIsWakeUp()
                        info['motion']['stiffness'] = motion.getStiffnesses('Body')
                except Exception: pass
                try:
                    tts = parent.svc('ALTextToSpeech')
                    if tts:
                        info['audio']['language'] = tts.getLanguage()
                except Exception: pass
                self._json(200, info)

            def _get_hardware_details(self):
                try:
                    almem = parent.svc('ALMemory')
                    if not almem: self._send_503('ALMemory indisponible'); return

                    def get_data_for_keys(key_list):
                        if not key_list:
                            return []
                        try:
                            return almem.getListData(key_list)
                        except Exception:
                            return [None] * len(key_list)

                    joints_data = {}
                    try:
                        all_joint_keys = almem.getDataList("Device/SubDeviceList")
                        hardness_keys = [k for k in all_joint_keys if "/Hardness/Actuator/Value" in k]
                        joint_key_stems = sorted(list(set([k.replace('/Hardness/Actuator/Value', '') for k in hardness_keys])))
                        for stem in joint_key_stems:
                            name = stem.split('/')[-1]
                            keys_to_fetch = [
                                f"{stem}/Temperature/Sensor/Value", f"{stem}/Position/Sensor/Value",
                                f"{stem}/Position/Actuator/Value", f"{stem}/Hardness/Actuator/Value",
                                f"{stem}/ElectricCurrent/Sensor/Value",
                            ]
                            vals = get_data_for_keys(keys_to_fetch)
                            joints_data[name] = {
                                'Temperature': vals[0], 'PositionSensor': vals[1], 'PositionActuator': vals[2],
                                'Stiffness': vals[3], 'ElectricCurrent': vals[4],
                            }
                    except Exception as e:
                        joints_data = {'error': 'Failed to get joints data: %s' % e}

                    devices_data = {}
                    try:
                        all_device_keys = almem.getDataList("Device/DeviceList")
                        ack_keys = [k for k in all_device_keys if k.endswith('/Ack') and '/Plugin/' not in k and '/Eeprom/' not in k]
                        device_key_stems = sorted(list(set([k.replace('/Ack', '') for k in ack_keys])))
                        for stem in device_key_stems:
                            name = stem.split('/')[-1]
                            keys_to_fetch = [
                                f"{stem}/Ack", f"{stem}/Nack", f"{stem}/ProgVersion", f"{stem}/Error",
                                f"{stem}/Address", f"{stem}/BootLoaderVersion", f"{stem}/BoardId",
                                f"{stem}/Available", f"{stem}/Bus", f"{stem}/Type",
                            ]
                            vals = get_data_for_keys(keys_to_fetch)

                            device_type = vals[9]
                            if isinstance(device_type, str) and device_type.lower() == 'plugin':
                                continue

                            devices_data[name] = {
                                'Ack': vals[0], 'Nack': vals[1], 'Version': vals[2], 'Error': vals[3], 'Address': vals[4],
                                'Bootloader': vals[5], 'BoardId': vals[6], 'Available': vals[7], 'Bus': vals[8], 'Type': device_type,
                            }
                    except Exception as e:
                        devices_data = {'error': 'Failed to get devices data: %s' % e}

                    config_data = {}
                    try:
                        config_keys = sorted(almem.getDataList("RobotConfig/"))
                        config_values = get_data_for_keys(config_keys)
                        for i, key in enumerate(config_keys):
                            config_data[key.replace('RobotConfig/', '')] = config_values[i]
                    except Exception as e:
                        config_data = {'error': 'Failed to get config data: %s' % e}

                    head_temp_data = {}
                    try:
                        temp_keys = almem.getDataList("Device/SubDeviceList/Head/Temperature/Sensor/Value")
                        temp_values = get_data_for_keys(temp_keys)
                        for i, key in enumerate(temp_keys):
                            head_temp_data[key] = temp_values[i]
                    except Exception as e:
                        head_temp_data = {'error': 'Failed to get head temp data: %s' % e}

                    self._json(200, {'joints': joints_data, 'devices': devices_data, 'config': config_data, 'head_temp': head_temp_data})
                except Exception as e:
                    self._send_503('hardware/details error: %s' % e)

            def _wifi_scan(self):
                """GET /api/wifi/scan - Scanne et retourne les réseaux WiFi disponibles."""
                try:
                    wifi = parent.svc('ALConnectionManager')
                    if not wifi: self._send_503('ALConnectionManager indisponible'); return
                    nets = []
                    try: nets = wifi.scan()
                    except Exception: pass
                    if not nets:
                        try: nets = wifi.services()
                        except Exception: pass
                    out = [{'ssid': n.get('Name') if isinstance(n, dict) else str(n), 'sec': n.get('Security', '') if isinstance(n, dict) else '', 'rssi': n.get('Strength', None) if isinstance(n, dict) else None} for n in nets or []]
                    self._json(200, {'list': out})
                except Exception as e:
                    self._send_503('wifi/scan error: %s' % e)

            def _wifi_status(self):
                """GET /api/wifi/status - Récupère l'état actuel de la connexion WiFi."""
                try:
                    wifi = parent.svc('ALConnectionManager')
                except Exception:
                    wifi = None
                if not wifi:
                    self._send_503('ALConnectionManager indisponible'); return
                try:
                    status = wifi.state()
                    self._json(200, {'status': status})
                except Exception as e:
                    self._send_503('wifi/status error: %s' % e)

            def _apps_list(self):
                """GET /api/apps/list - Liste les applications et animations installées."""
                try:
                    pls = parent.svc('PepperLifeService')
                    if not pls:
                        self._send_503('Service PepperLifeService indisponible')
                        return

                    # Le service a déjà fait tout le travail de scan et de tri par version
                    raw_applications = pls.getApplications()
                    raw_animations = pls.getInstalledAnimations()
                    running_behaviors = set(pls.getRunningAnimations())
                    naoqi_version_str = pls.getNaoqiVersion()

                    def process_list(raw_list, default_nature='unknown'):
                        processed = []
                        for item in raw_list:
                            name = item.get('name')
                            if not name: continue
                            processed.append({
                                'name': name,
                                'status': 'running' if name in running_behaviors else 'stopped',
                                'nature': item.get('nature', default_nature),
                                'runnable': True
                            })
                        return processed

                    applications = process_list(raw_applications, 'interactive')
                    animations = process_list(raw_animations, 'animation')

                    self._json(200, {
                        'applications': applications,
                        'animations': animations,
                        'naoqi_version': naoqi_version_str,
                        'running_behaviors': list(running_behaviors)
                    })

                except Exception as e:
                    parent._logger("Erreur in _apps_list: {}".format(e), level='error')
                    self._send_503('Erreur apps/list: {}'.format(e))

            def _apps_start(self, payload):
                """POST /api/apps/start - Démarre une application ou une animation."""
                name = payload.get('name')
                if not name:
                    self._send_503('Nom d\'application manquant')
                    return
                try:
                    pls = parent.svc('PepperLifeService')
                    if not pls:
                        self._send_503('Service PepperLifeService indisponible')
                        return
                    # On délègue entièrement au service, qui gère la logique de version
                    pls.playAnimation(name, False, True)
                    self._json(200, {'ok': True})
                except Exception as e:
                    self._send_503('Erreur apps/start pour {}: {}'.format(name, e))

            def _apps_stop(self, payload):
                """POST /api/apps/stop - Arrête une application ou une animation."""
                name = payload.get('name')
                if not name: self._send_503('Nom d\'application manquant'); return
                try:
                    pls = parent.svc('PepperLifeService')
                    if not pls:
                        self._send_503('Service PepperLifeService indisponible')
                        return
                    # On délègue entièrement au service
                    pls.stopAnimation(name)
                    self._json(200, {'ok': True})
                except Exception as e:
                    self._send_503('Erreur apps/stop pour {}: {}'.format(name, e))

            def _memory_search(self, parsed):
                try:
                    query = parse_qs(parsed.query or '').get('pattern', [''])[0]
                    almem = parent.svc('ALMemory')
                    if not almem: self._send_503('ALMemory indisponible'); return
                    keys = []
                    try: keys = almem.getDataList(query) if query else almem.getDataList('')
                    except Exception:
                        for ns in ('/Robot/', '/PepperLife/', '/ALAudio/', '/Device/', '/Tablet/'):
                            try: keys.extend(almem.getDataList(ns))
                            except Exception: pass
                    if query:
                        try:
                            import re
                            rx = re.compile(query)
                            keys = [k for k in keys if rx.search(k)]
                        except Exception: pass
                    keys = sorted(set(keys))[:1000]
                    self._json(200, keys)
                except Exception as e:
                    self._send_503('memory/search error: %s' % e)

            def _memory_get(self, parsed):
                try:
                    key = parse_qs(parsed.query or '').get('key', [''])[0]
                    if not key:
                        self._json(400, {'error': 'Missing key'}); return
                    almem = parent.svc('ALMemory')
                    if not almem:
                        self._send_503('ALMemory indisponible'); return
                    try:
                        value = almem.getData(key)
                    except Exception as e:
                        value = {'error': str(e)}
                    self._json(200, {'key': key, 'value': value})
                except Exception as e:
                    self._send_503('memory/get error: %s' % e)

            def _memory_set(self, payload):
                try:
                    key = (payload or {}).get('key')
                    value = (payload or {}).get('value')
                    if not key:
                        self._json(400, {'error': 'Missing key'}); return
                    almem = parent.svc('ALMemory')
                    if not almem:
                        self._send_503('ALMemory indisponible'); return
                    try:
                        almem.raiseMicroEvent(key, value)
                        self._json(200, {'ok': True})
                    except Exception as e:
                        self._send_503('memory/set error: %s' % e)
                except Exception as e:
                    self._send_503('memory/set error: %s' % e)

            def _settings_get(self):
                try:
                    config_path = os.path.expanduser('~/.config/pepperlife/config.json')
                    if not os.path.isfile(config_path):
                        self._json(200, {}); return
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    self._json(200, config)
                except Exception as e:
                    self._send_503('settings/get error: %s' % e)

            def _config_get_default(self):
                try:
                    p = os.path.join(self.server._root_dir, 'config', 'config.default.json')
                    with open(p, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    self._json(200, config)
                except Exception as e:
                    self._send_503('config/default error: %s' % e)

            def _config_get_user(self):
                try:
                    config_path = os.path.expanduser('~/.config/pepperlife/config.json')
                    if not os.path.isfile(config_path):
                        self._json(200, {}); return
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    self._json(200, config)
                except Exception as e:
                    self._send_503('config/user error: %s' % e)

            def _settings_set(self, payload):
                try:
                    config_path = os.path.expanduser('~/.config/pepperlife/config.json')
                    os.makedirs(os.path.dirname(config_path), exist_ok=True)
                    config = {}
                    if os.path.isfile(config_path):
                        try:
                            with open(config_path, 'r', encoding='utf-8') as f:
                                config = json.load(f)
                        except Exception:
                            config = {}
                    def deep_merge(src, destination):
                        for key, value in src.items():
                            if isinstance(value, dict):
                                node = destination.setdefault(key, {})
                                deep_merge(value, node)
                            else:
                                destination[key] = value
                        return destination
                    config = deep_merge(payload, config)
                    with open(config_path, 'w', encoding='utf-8') as f:
                        json.dump(config, f, indent=2, ensure_ascii=False)
                    
                    if parent.config_changed_callback:
                        try:
                            parent.config_changed_callback(payload)
                        except Exception as e:
                            parent._logger("config_changed_callback failed: %s" % e, level='error')

                    self._json(200, {'ok': True})
                except Exception as e:
                    self._send_503('settings/set error: %s' % e)

            def _config_set_user(self, payload):
                try:
                    return self._settings_set(payload)
                except Exception as e:
                    self._send_503('config/user set error: %s' % e)

            def _speak(self, payload):
                text = payload.get('text')
                if not text: self._send_503('missing text'); return
                speaker = getattr(self.server.parent, 'speaker', None)
                if speaker and hasattr(speaker, 'say_quick'):
                    try:
                        speaker.say_quick(text)
                        self._json(200, {'ok': True})
                    except Exception as e:
                        self._send_503('speak error: %s' % e)
                else:
                    self._send_503('Speaker not available')

            def _get_tts_languages(self):
                try:
                    tts = parent.svc('ALTextToSpeech')
                    if not tts: self._send_503('ALTextToSpeech indisponible'); return
                    self._json(200, {'available': tts.getAvailableLanguages(), 'current': tts.getLanguage()})
                except Exception as e:
                    self._send_503('tts/languages error: %s' % e)

            def _set_tts_language(self, payload):
                try:
                    lang = (payload or {}).get('lang')
                    if not lang:
                        self._json(400, {'error': 'Missing lang'}); return
                    tts = parent.svc('ALTextToSpeech')
                    if not tts: self._send_503('ALTextToSpeech indisponible'); return
                    tts.setLanguage(lang)
                    self._json(200, {'ok': True})
                except Exception as e:
                    self._send_503('tts/set_language error: %s' % e)

            def _chat_start(self, payload):
                try:
                    cb = getattr(self.server.parent, 'start_chat_callback', None)
                    if cb:
                        mode = (payload or {}).get('mode', 'gpt')
                        cb(mode)
                        self._json(200, {'ok': True})
                    else:
                        self._send_503('start_chat callback indisponible')
                except Exception as e:
                    self._send_503('chat/start error: %s' % e)

            def _chat_stop(self):
                try:
                    cb = getattr(self.server.parent, 'stop_chat_callback', None)
                    if cb:
                        cb()
                        self._json(200, {'ok': True})
                    else:
                        self._send_503('stop_chat callback indisponible')
                except Exception as e:
                    self._send_503('chat/stop error: %s' % e)

            # ----- Local utils -----
            def _ip_addresses(self):
                addrs = []
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(("8.8.8.8", 80))
                    ip = s.getsockname()[0]
                    s.close()
                    if ip not in addrs:
                        addrs.append(ip)
                except Exception:
                    pass
                return addrs

            def _check_internet(self, host='8.8.8.8', port=53, timeout=1.5):
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(timeout)
                    s.connect((host, port))
                    s.close()
                    return True
                except Exception:
                    return False
        return Handler

def tail(path, n=200):
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 4096
            data = b''
            while size > 0 and data.count(b'\n') <= n:
                delta = min(block, size)
                size -= delta
                f.seek(size)
                data = f.read(delta) + data
            lines = data.splitlines()[-n:]
            return [l.decode('utf-8', 'ignore') for l in lines]
    except Exception:
        return []
