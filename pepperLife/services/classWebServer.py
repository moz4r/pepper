# -*- coding: utf-8 -*-
"""
classWebServer.py — Serveur web pour PepperLife (version étendue)

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

• Ajoute des routes "admin" inspirées de robots_advanced
  - GET  /api/system/info
  - GET  /api/hardware/info
  - GET  /api/wifi/scan
  - POST /api/wifi/connect {ssid, psk}
  - GET  /api/wifi/status
  - GET  /api/apps/list
  - POST /api/apps/start {name}
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

Toutes les routes échouent en douceur si le service NAOqi demandé n'est pas disponible.

Intégration :
    server = WebServer(root_dir='./html', session=qi.Session(), logger=print)
    server.version_text = '1.0.0'
    server.start(host='0.0.0.0', port=8080)

"""
from __future__ import print_function

import os
import json
import time
import socket
import threading
import traceback
import traceback
import subprocess
import collections
from io import BytesIO
from urllib.parse import urlparse, parse_qs

def ansi_to_html(text):
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
except ImportError:  # Py2 fallback (au cas où)
    from SimpleHTTPServer import SimpleHTTPRequestHandler
    from SocketServer import TCPServer, ThreadingMixIn

from .classSystem import version as SysVersion

# Optionnel : pour wifi fallback

# Audio utils facultatif (vumètre)
try:
    from .classAudioUtils import avgabs
except Exception:
    def avgabs(_b):
        return 0

# ————————————————————————————————————————————————————————————
# WebServer
# ————————————————————————————————————————————————————————————
class WebServer(object):
    def __init__(self, root_dir='.', session=None, logger=None, anim=None):
        self._root_dir = os.path.abspath(root_dir)
        self.session = session  # qi.Session ou objet mock
        self._logger = logger or (lambda *a, **k: None)
        self.anim = anim

        self.heartbeat_callback = None

        # Callbacks optionnelles conservées pour compatibilité
        self.mic_toggle_callback = None
        self.listener = None  # Doit exposer .mon (buffers audio) si utilisé
        self.speaker = None
        self.version_text = 'dev'
        self.vision_service = None
        self.start_chat_callback = None
        self.stop_chat_callback = None
        self.get_chat_status_callback = None

        # Cache pour les natures de comportements
        self._behavior_nature_cache = {}
        self._last_installed_behaviors = []
        self._running_behaviors = set()

        # Hooks internes
        self._last_heartbeat = 0
        self._httpd = None

        # Pour la gestion du processus backend
        self._backend_process = None
        self._backend_logs = collections.deque(maxlen=500)

    # —————— Helpers NAOqi ——————
    def svc(self, name):
        try:
            if not self.session:
                return None
            return self.session.service(name)
        except Exception:
            return None

    def update_heartbeat(self):
        self._last_heartbeat = time.time()
        if self.heartbeat_callback:
            self.heartbeat_callback()

    def _read_output(self, pipe):
        """Lit la sortie d'un pipe et l'ajoute aux logs."""
        try:
            for line in iter(pipe.readline, b''):
                self._backend_logs.append(line.decode('utf-8', 'ignore').strip())
        finally:
            pipe.close()

    # —————— Serveur ——————
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
        self._logger('WebServer (multi-threaded) started on %s:%s' % (host, port))
        return httpd

    def stop(self):
        if self._backend_process:
            self._logger("[WebServer] Stopping managed backend process...")
            try:
                os.killpg(os.getpgid(self._backend_process.pid), subprocess.signal.SIGTERM)
                self._backend_process.wait(timeout=5)
            except Exception as e:
                self._logger(f"[WebServer] Error terminating backend process, trying to kill: {e}")
                try:
                    os.killpg(os.getpgid(self._backend_process.pid), subprocess.signal.SIGKILL)
                except Exception as e2:
                    self._logger(f"Error killing backend process: {e2}", level='error')
            self._backend_process = None

        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    # —————— Handler factory ——————
    def _make_handler(self):
        parent = self

        class Handler(SimpleHTTPRequestHandler):
            server_version = 'PepperLifeHTTP/1.0'

            def do_OPTIONS(self):
                self.send_response(200, "ok")
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type")
                self.end_headers()

            def log_message(self, format, *args):
                # Redirige les logs d'accès HTTP vers le niveau debug
                parent._logger(format % args, level='debug')

            # Utilitaires HTTP
            def _json(self, code, payload, headers=None):
                try:
                    data = json.dumps(payload).encode('utf-8')
                except Exception as e:
                    data = json.dumps({'error': 'json', 'detail': str(e)}).encode('utf-8')
                self.send_response(code)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                if headers:
                    for k, v in headers.items():
                        self.send_header(k, v)
                self.end_headers()
                try:
                    self.wfile.write(data)
                except BrokenPipeError:
                    parent._logger("[WebServer] BrokenPipeError: Client disconnected before response could be sent.", level='warning')
                except Exception as e:
                    parent._logger(f"[WebServer] Error writing response: {e}", level='error')

            def _text(self, code, text, ctype='text/plain; charset=utf-8'):
                self.send_response(code)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', ctype)
                self.end_headers()
                if isinstance(text, str):
                    text = text.encode('utf-8')
                self.wfile.write(text)

            def _send_503(self, msg='Service unavailable'):
                parent._logger('[503] %s' % msg)
                self._text(503, msg)

            def _serve_index(self):
                try:
                    p = os.path.join(self.server._root_dir, 'index.html')
                    with open(p, 'r', encoding='utf-8') as f:
                        content = f.read()
                    content = content.replace('%VER%', getattr(parent, 'version_text', 'dev'))
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self._text(200, content, 'text/html; charset=utf-8')
                except Exception as e:
                    self._send_503('Error reading index.html: %s' % e)

            # —————— DO_GET ——————
            def do_GET(self):
                parent._logger(f"GET {self.path}", level='debug')
                parsed = urlparse(self.path)
                path = parsed.path

                if path == '/api/system/status':
                    self._get_system_status()
                    return
                
                if path == '/api/system/logs':
                    self._get_system_logs()
                    return

                if path == '/api/chat/status':
                    self._get_chat_status()
                    return

                # 1) Heartbeat
                if path == '/api/heartbeat':
                    try:
                        if parent and hasattr(parent, 'update_heartbeat'):
                            parent.update_heartbeat()
                            self._json(200, {'status': 'ok', 'ts': time.time()})
                        else:
                            self._send_503('Heartbeat callback not available.')
                    except Exception as e:
                        self._send_503('Error processing heartbeat: %s' % e)
                    return

                # 2) Index intact pour la tablette
                if path == '/' or path == '/index.html':
                    self._serve_index()
                    return

                # 3) API existantes — audio/volume/vu-mètre
                if path == '/api/mic_toggle':
                    cb = getattr(self.server, 'mic_toggle_callback', None)
                    if cb:
                        try:
                            enabled = cb()  # doit retourner True/False
                            self._json(200, {'enabled': bool(enabled)})
                        except Exception as e:
                            self._send_503('mic_toggle failed: %s' % e)
                    else:
                        self._send_503('mic_toggle callback unavailable')
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

                if path == '/api/volume/state':
                    try:
                        ad = self.server.session.service('ALAudioDevice') if self.server.session else None
                        vol = ad.getOutputVolume() if ad else 0
                        self._json(200, {'volume': int(vol)})
                    except Exception as e:
                        self._send_503('volume/state error: %s' % e)
                    return

                if path == '/api/version':
                    self._text(200, getattr(self.server.parent, 'version_text', 'dev'))
                    return

                # 4) Autres GET API (nouvelles)
                if path == '/api/system/info':
                    self._get_system_info()
                    return

                if path == '/api/autonomous_life/state':
                    self._get_life_state()
                    return

                if path == '/api/posture/state':
                    self._get_posture_state()
                    return

                if path == '/api/hardware/info':
                    self._get_hardware_info()
                    return

                if path == '/api/hardware/details':
                    self._get_hardware_details()
                    return

                if path == '/api/wifi/scan':
                    self._wifi_scan()
                    return

                if path == '/api/wifi/status':
                    self._wifi_status()
                    return

                if path == '/api/apps/list':
                    self._apps_list()
                    return

                if path == '/api/memory/search':
                    self._memory_search(parsed)
                    return

                if path == '/api/memory/get':
                    self._memory_get(parsed)
                    return

                if path == '/api/settings/get':
                    self._settings_get()
                    return

                if path == '/api/config/default':
                    self._config_get_default()
                    return

                if path == '/api/config/user':
                    self._config_get_user()
                    return

                if path == '/api/logs/tail':
                    self._logs_tail(parsed)
                    return

                if path == '/api/tts/languages':
                    self._get_tts_languages()
                    return

                if path == '/api/camera/status':
                    self._camera_status()
                    return

                # 5) Fichiers statiques (cam.png, last_capture.png, admin/…)
                return SimpleHTTPRequestHandler.do_GET(self)

            # —————— DO_POST ——————
            def do_POST(self):
                parsed = urlparse(self.path)
                path = parsed.path

                length = int(self.headers.get('Content-Length', '0') or '0')
                body = self.rfile.read(length) if length else b''
                try:
                    payload = json.loads(body.decode('utf-8')) if body else {}
                except Exception:
                    payload = {}

                if path == '/api/system/start':
                    self._system_start()
                    return

                if path == '/api/system/stop':
                    self._system_stop()
                    return

                if path == '/api/system/shutdown':
                    self._system_shutdown()
                    return

                if path == '/api/system/restart':
                    self._system_restart()
                    return

                if path == '/api/camera/start_stream':
                    self._camera_start_stream()
                    return

                if path == '/api/camera/stop_stream':
                    self._camera_stop_stream()
                    return

                if path == '/api/camera/switch':
                    self._camera_switch(payload)
                    return

                if path == '/api/volume/set':
                    try:
                        v = int(payload.get('volume', 0))
                        ad = self.server.session.service('ALAudioDevice') if self.server.session else None
                        if not ad:
                            self._send_503('ALAudioDevice unavailable')
                            return
                        ad.setOutputVolume(max(0, min(100, v)))
                        self._json(200, {'ok': True})
                    except Exception as e:
                        self._send_503('volume/set error: %s' % e)
                    return

                if path == '/api/autonomous_life/toggle':
                    self._life_toggle()
                    return

                if path == '/api/posture/toggle':
                    self._posture_toggle()
                    return

                if path == '/api/autonomous_life/set_state':
                    self._life_set_state(payload)
                    return

                if path == '/api/posture/set_state':
                    self._posture_set_state(payload)
                    return

                if path == '/api/wifi/connect':
                    self._wifi_connect(payload)
                    return

                if path == '/api/apps/start':
                    self._apps_start(payload)
                    return

                if path == '/api/apps/stop':
                    self._apps_stop(payload)
                    return

                if path == '/api/memory/set':
                    self._memory_set(payload)
                    return

                if path == '/api/settings/set':
                    self._settings_set(payload)
                    return

                if path == '/api/config/user':
                    self._config_set_user(payload)
                    return

                if path == '/api/speak':
                    self._speak(payload)
                    return

                if path == '/api/tts/set_language':
                    self._set_tts_language(payload)
                    return

                if path == '/api/chat/start':
                    self._chat_start(payload)
                    return

                if path == '/api/chat/stop':
                    self._chat_stop()
                    return

                self._send_503('Unknown POST %s' % path)

            # ————————————————————————————————
            # Implémentations API
            # ————————————————————————————————

            def _get_chat_status(self):
                cb = getattr(self.server.parent, 'get_chat_status_callback', None)
                if cb:
                    try:
                        status = cb()
                        self._json(200, status)
                    except Exception as e:
                        self._send_503('get_chat_status failed: %s' % e)
                else:
                    self._send_503('get_chat_status callback unavailable')

            def _chat_start(self, payload):
                cb = getattr(self.server.parent, 'start_chat_callback', None)
                if cb:
                    try:
                        mode = payload.get('mode', 'gpt') # Default to gpt
                        cb(mode)
                        self._json(200, {'status': 'ok', 'message': f'Chat start requested in {mode} mode.'})
                    except Exception as e:
                        self._send_503('chat_start failed: %s' % e)
                else:
                    self._send_503('chat_start callback unavailable')

            def _chat_stop(self):
                cb = getattr(self.server.parent, 'stop_chat_callback', None)
                if cb:
                    try:
                        cb()
                        self._json(200, {'status': 'ok', 'message': 'Chat stop requested.'})
                    except Exception as e:
                        self._send_503('chat_stop failed: %s' % e)
                else:
                    self._send_503('chat_stop callback unavailable')

            def _system_shutdown(self):
                try:
                    al_system = self.server.session.service('ALSystem') if self.server.session else None
                    if al_system:
                        al_system.shutdown()
                        self._json(200, {'status': 'ok', 'message': 'Shutdown initiated.'})
                    else:
                        self._send_503('ALSystem service not available.')
                except Exception as e:
                    self._send_503('Shutdown failed: %s' % e)

            def _system_restart(self):
                try:
                    al_system = self.server.session.service('ALSystem') if self.server.session else None
                    if al_system:
                        al_system.reboot()
                        self._json(200, {'status': 'ok', 'message': 'Restart initiated.'})
                    else:
                        self._send_503('ALSystem service not available.')
                except Exception as e:
                    self._send_503('Restart failed: %s' % e)

            def _camera_start_stream(self):
                try:
                    vision = self.server.parent.vision_service
                    if vision:
                        success = vision.start_streaming()
                        if success:
                            self._json(200, {'status': 'ok'})
                        else:
                            self._send_503('Failed to start camera stream, check logs.')
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

            def _camera_status(self):
                try:
                    vision = self.server.parent.vision_service
                    if vision:
                        status = {
                            'is_streaming': vision.is_streaming,
                            'current_camera': 'top' if vision.current_camera_index == 0 else 'bottom'
                        }
                        self._json(200, status)
                    else:
                        self._send_503('Vision service not available.')
                except Exception as e:
                    self._send_503('Failed to get camera status: %s' % e)
        
            def _camera_switch(self, payload):
                try:
                    vision = self.server.parent.vision_service
                    cam_name = payload.get('camera') # 'top' or 'bottom'
                    if cam_name not in ['top', 'bottom']:
                        self._json(400, {'error': 'Invalid camera name'})
                        return
                    
                    camera_index = 0 if cam_name == 'top' else 1
                    
                    if vision:
                        success = vision.switch_camera(camera_index)
                        if success:
                            self._json(200, {'status': 'ok'})
                        else:
                            self._send_503('Failed to switch camera.')
                    else:
                        self._send_503('Vision service not available.')
                except Exception as e:
                    self._send_503('Failed to switch camera: %s' % e)

            def _config_get_default(self):
                try:
                    app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
                    config_path = os.path.join(app_dir, 'config.json.default')
                    with open(config_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self._text(200, content, ctype='text/plain; charset=utf-8')
                except Exception as e:
                    self._send_503('Failed to read default config: %s' % e)

            def _config_get_user(self):
                try:
                    app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
                    config_path = os.path.join(app_dir, 'config.json')
                    with open(config_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self._json(200, data)
                except Exception as e:
                    self._send_503('Failed to read user config: %s' % e)

            def _config_set_user(self, payload):
                try:
                    app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
                    config_path = os.path.join(app_dir, 'config.json')
                    with open(config_path, 'w', encoding='utf-8') as f:
                        json.dump(payload, f, indent=2, ensure_ascii=False)
                    self._json(200, {'success': True})
                except Exception as e:
                    self._send_503('Failed to write user config: %s' % e)

            def _get_system_status(self):
                python3_exists = SysVersion.is_python3_nao_installed()
                
                backend_running = False
                if parent._backend_process:
                    backend_running = parent._backend_process.poll() is None

                self._json(200, {
                    'python3_installed': python3_exists,
                    'backend_running': backend_running,
                })

            def _get_system_logs(self):
                logs_html = [ansi_to_html(log) for log in parent._backend_logs]
                self._json(200, {'logs': logs_html})

            def _system_start(self):
                if parent._backend_process and parent._backend_process.poll() is None:
                    self._json(409, {'error': 'Backend already running.'})
                    return

                parent._backend_logs.clear()
                
                cmd = [
                    '/home/nao/.local/share/PackageManager/apps/python3nao/bin/runpy3.sh',
                    '/home/nao/.local/share/PackageManager/apps/pepperlife/pepperLife.py'
                ]
                
                try:
                    parent._logger(f"Starting backend process with command: {' '.join(cmd)}")
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        pre_exec_fn=os.setsid
                    )
                    parent._backend_process = proc
                    
                    th = threading.Thread(target=parent._read_output, args=(proc.stdout,))
                    th.daemon = True
                    th.start()

                    self._json(200, {'status': 'ok', 'pid': proc.pid})
                except Exception as e:
                    parent._logger(f"Failed to start backend process: {e}", level='error')
                    self._send_503(f"Failed to start backend: {e}")

            def _system_stop(self):
                if not parent._backend_process or parent._backend_process.poll() is not None:
                    self._json(409, {'error': 'Backend not running.'})
                    return
                
                try:
                    parent._logger(f"Stopping backend process with PID: {parent._backend_process.pid}")
                    os.killpg(os.getpgid(parent._backend_process.pid), subprocess.signal.SIGTERM)
                    parent._backend_process.wait(timeout=5)
                except Exception as e:
                    parent._logger(f"Error stopping backend process, trying to kill: {e}", level='warning')
                    try:
                        os.killpg(os.getpgid(parent._backend_process.pid), subprocess.signal.SIGKILL)
                    except Exception as e2:
                         parent._logger(f"Error killing backend process: {e2}", level='error')

                parent._backend_process = None
                self._json(200, {'status': 'ok'})

            def _get_system_info(self):
                info = {
                    'version': getattr(self.server.parent, 'version_text', 'dev'),
                    'naoqi_version': None,
                    'ip_addresses': [],
                    'internet_connected': False,
                    'battery': {
                        'charge': None,
                        'plugged': None,
                    },
                }

                # NAOqi version
                try:
                    al_system = self.server.session.service('ALSystem') if self.server.session else None
                    if al_system:
                        info['naoqi_version'] = al_system.systemVersion()
                except Exception:
                    pass

                # IP addresses
                try:
                    info['ip_addresses'] = self._ip_addresses()
                except Exception:
                    pass

                # Internet status
                try:
                    info['internet_connected'] = self._check_internet()
                except Exception:
                    pass

                # Battery info
                try:
                    al_batt = self.server.session.service('ALBattery') if self.server.session else None
                    if al_batt:
                        try:
                            info['battery']['charge'] = al_batt.getBatteryCharge()
                        except Exception:
                            pass
                        try:
                            info['battery']['plugged'] = al_batt.isBatteryFull()
                        except Exception:
                            pass
                except Exception:
                    pass
                
                self._json(200, info)

            def _get_life_state(self):
                try:
                    life = self.server.session.service('ALAutonomousLife') if self.server.session else None
                    if not life:
                        self._send_503('ALAutonomousLife unavailable')
                        return
                    current_state = life.getState()
                    all_states = ["solitary", "interactive", "disabled", "safeguard"]
                    self._json(200, {'current_state': current_state, 'all_states': all_states})
                except Exception as e:
                    self._send_503('life/state error: %s' % e)

            def _life_toggle(self):
                try:
                    life = self.server.session.service('ALAutonomousLife') if self.server.session else None
                    if not life:
                        self._send_503('ALAutonomousLife unavailable')
                        return
                    st = life.getState()
                    if st in ('solitary', 'interactive', 'safeguard'):
                        life.setState('disabled')
                    else:
                        life.setState('solitary')
                    self._json(200, {'state': life.getState()})
                except Exception as e:
                    self._send_503('life/toggle error: %s' % e)

            def _get_posture_state(self):
                try:
                    motion = self.server.session.service('ALMotion') if self.server.session else None
                    awake = bool(motion.robotIsWakeUp()) if motion else False
                    self._json(200, {'is_awake': awake})
                except Exception as e:
                    self._send_503('posture/state error: %s' % e)

            def _posture_toggle(self):
                try:
                    motion = self.server.session.service('ALMotion') if self.server.session else None
                    if not motion:
                        self._send_503('ALMotion unavailable')
                        return
                    if motion.robotIsWakeUp():
                        motion.rest()
                    else:
                        motion.wakeUp()
                    self._json(200, {'is_awake': bool(motion.robotIsWakeUp())})
                except Exception as e:
                    self._send_503('posture/toggle error: %s' % e)

            def _life_set_state(self, payload):
                try:
                    life = self.server.session.service('ALAutonomousLife') if self.server.session else None
                    if not life:
                        self._send_503('ALAutonomousLife unavailable')
                        return
                    state = payload.get('state')
                    if state and state in ["solitary", "interactive", "disabled", "safeguard"]:
                        life.setState(state)
                        self._json(200, {'ok': True, 'state': life.getState()})
                    else:
                        self._json(400, {'error': 'Invalid or missing state parameter'})
                except Exception as e:
                    self._send_503('life/set_state error: %s' % e)

            def _posture_set_state(self, payload):
                try:
                    motion = self.server.session.service('ALMotion') if self.server.session else None
                    if not motion:
                        self._send_503('ALMotion unavailable')
                        return
                    state = payload.get('state')
                    if state == 'awake':
                        motion.wakeUp()
                    elif state == 'rest':
                        motion.rest()
                    else:
                        self._json(400, {'error': 'Invalid or missing state parameter'})
                        return
                    self._json(200, {'ok': True, 'is_awake': motion.robotIsWakeUp()})
                except Exception as e:
                    self._send_503('posture/set_state error: %s' % e)

            def _get_hardware_info(self):
                try:
                    sys = self.server.session.service('ALSystem') if self.server.session else None
                    batt = self.server.session.service('ALBattery') if self.server.session else None
                    motion = self.server.session.service('ALMotion') if self.server.session else None
                    tts = self.server.session.service('ALTextToSpeech') if self.server.session else None
                    info = {
                        'system': {
                            'version': sys.systemVersion() if sys else None,
                            'robot': getattr(sys, 'robotName', lambda: None)() if sys else None,
                        },
                        'battery': {
                            'charge': batt.getBatteryCharge() if batt else None,
                        },
                        'motion': {
                            'awake': motion.robotIsWakeUp() if motion else None,
                            'stiffness': (motion.getStiffnesses('Body') if motion else None),
                        },
                        'audio': {
                            'language': tts.getLanguage() if tts else None,
                        }
                    }
                    self._json(200, info)
                except Exception as e:
                    self._send_503('hardware/info error: %s' % e)

            def _get_hardware_details(self):
                parent._logger("Fetching hardware details...", level='debug')
                import re
                almem = self.server.session.service('ALMemory') if self.server.session else None
                if not almem:
                    parent._logger("ALMemory service not found", level='error')
                    self._send_503('ALMemory unavailable')
                    return

                # --- Helper for batch-fetching data ---
                def get_data_for_keys(key_list):
                    if not key_list:
                        return []
                    try:
                        return almem.getListData(key_list)
                    except Exception:
                        return [None] * len(key_list)

                # --- Joints Data ---
                joints_data = {}
                try:
                    all_joint_keys = almem.getDataList("Device/SubDeviceList")
                    parent._logger(f"[hardware] Found {len(all_joint_keys)} total SubDevice keys", level='debug')
                    hardness_keys = [k for k in all_joint_keys if "/Hardness/Actuator/Value" in k]
                    joint_key_stems = sorted(list(set([k.replace('/Hardness/Actuator/Value', '') for k in hardness_keys])))
                    parent._logger(f"[hardware] Found {len(joint_key_stems)} joint stems", level='debug')
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
                    joints_data = {'error': f'Failed to get joints data: {e}'}
                    parent._logger(f"[hardware] Joints error: {e}", level='error')

                # --- Devices Data ---
                devices_data = {}
                try:
                    all_device_keys = almem.getDataList("Device/DeviceList")
                    parent._logger(f"[hardware] Found {len(all_device_keys)} total Device keys", level='debug')
                    ack_keys = [k for k in all_device_keys if k.endswith('/Ack') and '/Plugin/' not in k and '/Eeprom/' not in k]
                    device_key_stems = sorted(list(set([k.replace('/Ack', '') for k in ack_keys])))
                    parent._logger(f"[hardware] Found {len(device_key_stems)} device stems", level='debug')
                    for stem in device_key_stems:
                        name = stem.split('/')[-1]
                        keys_to_fetch = [
                            f"{stem}/Ack", f"{stem}/Nack", f"{stem}/ProgVersion", f"{stem}/Error",
                            f"{stem}/Address", f"{stem}/BootLoaderVersion", f"{stem}/BoardId",
                            f"{stem}/Available", f"{stem}/Bus", f"{stem}/Type",
                        ]
                        vals = get_data_for_keys(keys_to_fetch)

                        # Exclure si le type est 'plugin'
                        device_type = vals[9]
                        if isinstance(device_type, str) and device_type.lower() == 'plugin':
                            continue

                        devices_data[name] = {
                            'Ack': vals[0], 'Nack': vals[1], 'Version': vals[2], 'Error': vals[3], 'Address': vals[4],
                            'Bootloader': vals[5], 'BoardId': vals[6], 'Available': vals[7], 'Bus': vals[8], 'Type': device_type,
                        }
                except Exception as e:
                    devices_data = {'error': f'Failed to get devices data: {e}'}
                    parent._logger(f"[hardware] Devices error: {e}", level='error')

                # --- Config Data ---
                config_data = {}
                try:
                    config_keys = sorted(almem.getDataList("RobotConfig/"))
                    parent._logger(f"[hardware] Found {len(config_keys)} config keys", level='debug')
                    config_values = get_data_for_keys(config_keys)
                    for i, key in enumerate(config_keys):
                        config_data[key.replace('RobotConfig/', '')] = config_values[i]
                except Exception as e:
                    config_data = {'error': f'Failed to get config data: {e}'}
                    parent._logger(f"[hardware] Config error: {e}", level='error')

                # --- Head Temp ---
                head_temp_data = {}
                try:
                    temp_keys = almem.getDataList("Device/SubDeviceList/Head/Temperature/Sensor/Value")
                    parent._logger(f"[hardware] Found {len(temp_keys)} head temp keys", level='debug')
                    temp_values = get_data_for_keys(temp_keys)
                    for i, key in enumerate(temp_keys):
                        head_temp_data[key] = temp_values[i]
                except Exception as e:
                    head_temp_data = {'error': f'Failed to get head temp data: {e}'}
                    parent._logger(f"[hardware] Head temp error: {e}", level='error')

                self._json(200, {
                    'joints': joints_data,
                    'devices': devices_data,
                    'config': config_data,
                    'head_temp': head_temp_data,
                })

            # ——— Wi‑Fi / Tethering ———
            def _wifi_scan(self):
                """Scan Wi‑Fi via ALConnectionManager uniquement."""
                try:
                    cm = self.server.session.service('ALConnectionManager') if self.server.session else None
                    if not cm:
                        self._send_503('ALConnectionManager unavailable')
                        return
                    nets = []
                    try:
                        nets = cm.scan()
                    except Exception:
                        pass
                    try:
                        if not nets:
                            nets = cm.services()
                    except Exception:
                        pass
                    out = []
                    for n in nets or []:
                        ssid = n.get('Name') if isinstance(n, dict) else str(n)
                        sec = n.get('Security', '') if isinstance(n, dict) else ''
                        rssi = n.get('Strength', None) if isinstance(n, dict) else None
                        out.append({'ssid': ssid, 'sec': sec, 'rssi': rssi})
                    self._json(200, {'list': out})
                except Exception as e:
                    self._send_503('wifi scan error: %s' % e)

            def _wifi_connect(self, payload):
                """Connexion Wi‑Fi via ALConnectionManager uniquement."""
                ssid = payload.get('ssid')
                psk = payload.get('psk')
                if not ssid:
                    self._send_503('missing ssid')
                    return
                try:
                    cm = self.server.session.service('ALConnectionManager') if self.server.session else None
                    if not cm:
                        self._send_503('ALConnectionManager unavailable')
                        return
                    try:
                        cm.connect(ssid, psk or '')
                    except Exception:
                        try:
                            cm.setServiceInput(ssid, {'passphrase': psk or ''})
                            cm.connect(ssid)
                        except Exception:
                            raise
                    self._json(200, {'ok': True})
                except Exception as e:
                    self._send_503('wifi connect error: %s' % e)

            def _wifi_status(self):
                """Statut Wi‑Fi via ALConnectionManager uniquement."""
                try:
                    cm = self.server.session.service('ALConnectionManager') if self.server.session else None
                    if not cm:
                        self._send_503('ALConnectionManager unavailable')
                        return
                    st = None
                    try:
                        st = cm.state()
                    except Exception:
                        try:
                            st = cm.status()
                        except Exception:
                            st = None
                    self._json(200, {'status': st})
                except Exception as e:
                    self._send_503('wifi status error: %s' % e)

            # ——— Apps ———
            def _apps_list(self):
                t_start_total = time.time()
                applications = []
                animations = []
                error_msg = None
                naoqi_version_str = "0.0"
                
                parent._logger("[apps] Starting _apps_list processing...", level='debug')

                try:
                    # --- Version Detection ---
                    t_start_version = time.time()
                    try:
                        al_system = self.server.session.service('ALSystem')
                        naoqi_version_str = al_system.systemVersion()
                    except Exception:
                        pass # Keep default version
                    parent._logger(f"[apps] Version detection took: {time.time() - t_start_version:.4f}s", level='debug')

                    major_version, minor_version = (0,0)
                    try:
                        version_parts = naoqi_version_str.split('.')
                        major_version = int(version_parts[0]) if len(version_parts) > 0 else 0
                        minor_version = int(version_parts[1]) if len(version_parts) > 1 else 0
                    except Exception:
                        pass # Keep default 0.0

                    # --- Logic Branch ---
                    if major_version < 2 or (major_version == 2 and minor_version < 9):
                        # --- NAOqi < 2.9 Logic (using ALBehaviorManager) ---
                        parent._logger("[apps] Using NAOqi < 2.9 logic (ALBehaviorManager)", level='info')
                        bm = self.server.session.service('ALBehaviorManager')
                        if bm:
                            current_installed_behaviors = bm.getInstalledBehaviors()
                            running_behaviors = set(bm.getRunningBehaviors()) # Use a set for faster lookups
                            
                            # Cache invalidation logic for natures
                            if sorted(current_installed_behaviors) != sorted(parent._last_installed_behaviors):
                                parent._logger("[apps] Installed behaviors changed. Clearing nature cache.", level='info')
                                parent._behavior_nature_cache = {}
                                parent._last_installed_behaviors = current_installed_behaviors[:]

                            for name in sorted(current_installed_behaviors):
                                nature = parent._behavior_nature_cache.get(name)
                                if nature is None:
                                    nature = bm.getBehaviorNature(name)
                                    parent._behavior_nature_cache[name] = nature

                                behavior_info = {
                                    'name': name,
                                    'status': 'running' if name in running_behaviors else 'stopped',
                                    'runnable': True, # Assumed runnable on older systems
                                    'nature': nature
                                }
                                if nature in ['interactive', 'solitary']:
                                    applications.append(behavior_info)
                                else:
                                    animations.append(behavior_info)
                        else:
                            error_msg = "ALBehaviorManager service not found."
                    else:
                        # --- NAOqi >= 2.9 Logic (using pm.db and classAnimation) ---
                        parent._logger("[apps] Using NAOqi 2.9+ logic (pm.db and classAnimation)", level='info')
                        
                        # Get applications from pm.db
                        db_path = '/home/nao/.local/share/PackageManager/pm.db'
                        # For local testing, use the example file at the root
                        if not os.path.exists(db_path):
                            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'pm.db')

                        if os.path.exists(db_path):
                            try:
                                import sqlite3
                                conn = sqlite3.connect(db_path)
                                cursor = conn.cursor()
                                cursor.execute("SELECT uuid FROM packages")
                                packages = cursor.fetchall()
                                conn.close()

                                running_behaviors = parent._running_behaviors

                                for pkg in packages:
                                    name = pkg[0]
                                    if not name: continue

                                    behavior_info = {
                                        'name': name,
                                        'status': 'running' if name in running_behaviors else 'stopped',
                                        'runnable': False, # Per user request for 2.9
                                        'nature': 'interactive'
                                    }
                                    applications.append(behavior_info)

                            except Exception as e:
                                error_msg = f"Error reading pm.db: {e}"
                                parent._logger(f"[apps] {error_msg}", level='error')
                        else:
                            error_msg = "pm.db not found."

                        # Get animations from classAnimation
                        if parent.anim:
                            try:
                                anim_list = parent.anim.get_installed_animations()
                                bm = parent.svc('ALBehaviorManager')
                                running_behaviors = set(bm.getRunningBehaviors()) if bm else set()
                                for anim_name in anim_list:
                                    behavior_info = {
                                        'name': anim_name,
                                        'status': 'running' if anim_name in running_behaviors else 'stopped',
                                        'runnable': True,
                                        'nature': 'animation'
                                    }
                                    animations.append(behavior_info)
                            except Exception as e:
                                error_msg_anim = f"Error getting animations: {e}"
                                if error_msg:
                                    error_msg += f"; {error_msg_anim}"
                                else:
                                    error_msg = error_msg_anim
                                parent._logger(f"[apps] {error_msg_anim}", level='error')

                except Exception as e:
                    error_msg = f"Error listing applications: {e}"
                    parent._logger(f"[apps] {error_msg} {traceback.format_exc()}", level='error')

                parent._logger(f"[apps] _apps_list total processing took: {time.time() - t_start_total:.4f}s", level='info')
                self._json(200, {
                    'applications': applications, 
                    'animations': animations, 
                    'error': error_msg, 
                    'naoqi_version': naoqi_version_str,
                    'running_behaviors': list(running_behaviors)
                })

            def _apps_start(self, payload):
                name = payload.get('name')
                if not name:
                    self._send_503('missing app name')
                    return
                try:
                    # Check if it's an animation for 2.9
                    is_animation = parent.anim and parent.anim.is_29 and name in parent.anim.get_installed_animations()

                    if is_animation:
                        player = self.server.session.service('ALAnimationPlayer')
                        animation_name = "animations/" + name
                        parent._logger(f"Running animation '{animation_name}' with ALAnimationPlayer.", level='info')
                        player.run(animation_name)
                        self._json(200, {'ok': True})
                    else:
                        bm = self.server.session.service('ALBehaviorManager')
                        if not bm.isBehaviorRunning(name):
                            parent._logger(f"Starting behavior '{name}' non-blockingly.", level='debug')
                            bm.startBehavior(name)
                            parent._running_behaviors.add(name)
                        self._json(200, {'ok': True})
                except Exception as e:
                    self._send_503(f'apps/start error for {name}: {e}')

            def _apps_stop(self, payload):
                name = payload.get('name')
                if not name:
                    self._send_503('missing app name')
                    return
                try:
                    bm = self.server.session.service('ALBehaviorManager')
                    if bm.isBehaviorRunning(name):
                        bm.stopBehavior(name)
                        parent._running_behaviors.discard(name)
                    self._json(200, {'ok': True})
                except Exception as e:
                    self._send_503(f'apps/stop error for {name}: {e}')

            # ——— ALMemory ———
            def _memory_search(self, parsed):
                try:
                    query = parse_qs(parsed.query or '').get('pattern', [''])[0]
                    almem = self.server.session.service('ALMemory') if self.server.session else None
                    if not almem:
                        self._send_503('ALMemory unavailable')
                        return
                    # Selon la taille, on peut lister via getDataList
                    keys = []
                    try:
                        keys = almem.getDataList(query) if query else almem.getDataList('')
                    except Exception:
                        # Fallback: récupère quelques namespaces connus
                        for ns in ('/Robot/', '/PepperLife/', '/ALAudio/', '/Device/', '/Tablet/'):
                            try:
                                keys.extend(almem.getDataList(ns))
                            except Exception:
                                pass
                    # Filtre par motif simple si fourni
                    if query:
                        try:
                            import re
                            rx = re.compile(query)
                            keys = [k for k in keys if rx.search(k)]
                        except Exception:
                            pass
                    keys = sorted(set(keys))[:1000]
                    self._json(200, keys)
                except Exception as e:
                    self._send_503('memory/search error: %s' % e)

            def _memory_get(self, parsed):
                try:
                    key = parse_qs(parsed.query or '').get('key', [''])[0]
                    almem = self.server.session.service('ALMemory') if self.server.session else None
                    if not almem:
                        self._send_503('ALMemory unavailable')
                        return
                    val = almem.getData(key)
                    # sérialisation sûre
                    try:
                        json.dumps(val)
                    except Exception:
                        val = str(val)
                    self._json(200, val)
                except Exception as e:
                    self._send_503('memory/get error: %s' % e)

            def _memory_set(self, payload):
                try:
                    key = payload.get('key')
                    value = payload.get('value')
                    if key is None:
                        self._send_503('missing key')
                        return
                    almem = self.server.session.service('ALMemory') if self.server.session else None
                    if not almem:
                        self._send_503('ALMemory unavailable')
                        return
                    # insertData accepte types simples ; sinon stringifier
                    try:
                        almem.insertData(key, value)
                    except Exception:
                        almem.insertData(key, json.dumps(value))
                    self._json(200, {'ok': True})
                except Exception as e:
                    self._send_503('memory/set error: %s' % e)

            # ——— Settings ———
            def _settings_get(self):
                try:
                    tts = self.server.session.service('ALTextToSpeech') if self.server.session else None
                    lang = tts.getLanguage() if tts else None
                    self._json(200, {'language': lang})
                except Exception as e:
                    self._send_503('settings/get error: %s' % e)

            def _settings_set(self, payload):
                try:
                    tts = self.server.session.service('ALTextToSpeech') if self.server.session else None
                    if not tts:
                        self._send_503('ALTextToSpeech unavailable')
                        return
                    lang = payload.get('language')
                    if lang:
                        tts.setLanguage(lang)
                    self._json(200, {'ok': True})
                except Exception as e:
                    self._send_503('settings/set error: %s' % e)

            def _speak(self, payload):
                text = payload.get('text')
                if not text:
                    self._send_503('missing text')
                    return
                
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
                    tts = self.server.session.service('ALTextToSpeech') if self.server.session else None
                    if not tts:
                        parent._logger('[tts] ALTextToSpeech service unavailable', level='error')
                        self._send_503('ALTextToSpeech unavailable')
                        return
                    
                    parent._logger('[tts] Fetching available languages...', level='debug')
                    available_langs = tts.getAvailableLanguages()
                    parent._logger(f'[tts] Available languages found: {available_langs}', level='debug')

                    current_lang = tts.getLanguage()
                    parent._logger(f'[tts] Current language is: {current_lang}', level='info')
                    
                    self._json(200, {
                        'available': available_langs,
                        'current': current_lang
                    })
                except Exception as e:
                    parent._logger(f'[tts] Error fetching languages: {e}', level='error')
                    self._send_503('tts/languages error: %s' % e)

            def _set_tts_language(self, payload):
                try:
                    tts = self.server.session.service('ALTextToSpeech') if self.server.session else None
                    if not tts:
                        self._send_503('ALTextToSpeech unavailable')
                        return
                    
                    lang = payload.get('language')
                    if lang:
                        tts.setLanguage(lang)
                        self._json(200, {'ok': True, 'language': lang})
                    else:
                        self._json(400, {'error': 'missing language parameter'})
                except Exception as e:
                    self._send_503('tts/set_language error: %s' % e)

            # ——— Logs ———
            def _logs_tail(self, parsed):
                try:
                    qs = parse_qs(parsed.query or '')
                    n = int(qs.get('n', ['200'])[0])
                    log_file = os.path.join(self.server._root_dir, 'pepperlife.log')
                    if not os.path.exists(log_file):
                        self._json(200, {'text': ''})
                        return
                    lines = tail(log_file, n)
                    # Convertir les codes ANSI en HTML pour un affichage correct
                    html_lines = [ansi_to_html(line) for line in lines]
                    self._json(200, {'text': '\n'.join(html_lines)})
                except Exception as e:
                    self._send_503('logs/tail error: %s' % e)

            # ——— Utils internes ———
            def _ip_addresses(self):
                addrs = []
                try:
                    hostname = socket.gethostname()
                    addrs.append(socket.gethostbyname(hostname))
                except Exception:
                    pass
                # On peut lister /sys/class/net/*/address si besoin
                try:
                    for ifn in os.listdir('/sys/class/net'):
                        try:
                            import fcntl, struct
                            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            ifreq = struct.pack('256s', ifn[:15].encode('utf-8'))
                            ip = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, ifreq)[20:24])  # SIOCGIFADDR
                            if ip not in addrs:
                                addrs.append(ip)
                        except Exception:
                            pass
                except Exception:
                    pass
                return addrs

            def _check_internet(self):
                try:
                    socket.create_connection(('8.8.8.8', 53), 0.5).close()
                    return True
                except Exception:
                    return False

        return Handler



# ————————————————————————————————————————————————————————————
# Utilitaires
# ————————————————————————————————————————————————————————————
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
