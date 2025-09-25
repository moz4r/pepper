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

Toutes les routes échouent en douceur si le service NAOqi demandé n'est pas disponible.

Intégration :
    server = WebServer(root_dir='./gui', session=qi.Session(), logger=print)
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
from io import BytesIO
from urllib.parse import urlparse, parse_qs

try:
    from http.server import SimpleHTTPRequestHandler
    from socketserver import TCPServer
except ImportError:  # Py2 fallback (au cas où)
    from SimpleHTTPServer import SimpleHTTPRequestHandler
    from SocketServer import TCPServer

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
    def __init__(self, root_dir='.', session=None, logger=None):
        self._root_dir = os.path.abspath(root_dir)
        self.session = session  # qi.Session ou objet mock
        self._logger = logger or (lambda *a, **k: None)

        self.heartbeat_callback = None

        # Callbacks optionnelles conservées pour compatibilité
        self.mic_toggle_callback = None
        self.listener = None  # Doit exposer .mon (buffers audio) si utilisé
        self.speaker = None
        self.version_text = 'dev'

        # Hooks internes
        self._last_heartbeat = 0
        self._httpd = None

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

    # —————— Serveur ——————
    def start(self, host='0.0.0.0', port=8080):
        os.chdir(self._root_dir)
        self._logger('Web root: %s' % self._root_dir)
        httpd = _TCPServer((host, port), self._make_handler())
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
        self._logger('WebServer started on %s:%s' % (host, port))
        return httpd

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    # —————— Handler factory ——————
    def _make_handler(self):
        parent = self

        class Handler(SimpleHTTPRequestHandler):
            server_version = 'PepperLifeHTTP/1.0'

            # Utilitaires HTTP
            def _json(self, code, payload, headers=None):
                try:
                    data = json.dumps(payload).encode('utf-8')
                except Exception as e:
                    data = json.dumps({'error': 'json', 'detail': str(e)}).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                if headers:
                    for k, v in headers.items():
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def _text(self, code, text, ctype='text/plain; charset=utf-8'):
                self.send_response(code)
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
                    self._text(200, content, 'text/html; charset=utf-8')
                except Exception as e:
                    self._send_503('Error reading index.html: %s' % e)

            # —————— DO_GET ——————
            def do_GET(self):
                parent._logger(f"GET {self.path}", level='debug')
                parsed = urlparse(self.path)
                path = parsed.path

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
                            level = avgabs(b''.join(listener.mon[-1:]))
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

                if path == '/api/logs/tail':
                    self._logs_tail(parsed)
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

                if path == '/api/speak':
                    self._speak(payload)
                    return

                self._send_503('Unknown POST %s' % path)

            # ————————————————————————————————
            # Implémentations API
            # ————————————————————————————————
            def _get_system_info(self):
                info = {
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
                    st = life.getState() if life else 'unknown'
                    self._json(200, {'state': st})
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
                        devices_data[name] = {
                            'Ack': vals[0], 'Nack': vals[1], 'Version': vals[2], 'Error': vals[3], 'Address': vals[4],
                            'Bootloader': vals[5], 'BoardId': vals[6], 'Available': vals[7], 'Bus': vals[8], 'Type': vals[9],
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
                apps = []
                error_msg = None
                try:
                    store = self.server.session.service('ALStore') if self.server.session else None
                    if store:
                        parent._logger("[apps] ALStore service found, using getPackagesInfo().", level='debug')
                        package_info = store.getPackagesInfo()
                        for p in package_info or []:
                            apps.append({
                                'name': p.get('name') or p.get('uuid'),
                                'status': p.get('status')
                            })
                    else:
                        parent._logger("[apps] ALStore not found, falling back to ALPackageManager.", level='debug')
                        pm = self.server.session.service('ALPackageManager') if self.server.session else None
                        if pm:
                            package_info = pm.packages()
                            for p in package_info or []:
                                apps.append({
                                    'name': p.get('name') or p.get('uuid'),
                                    'state': p.get('state')
                                })
                        else:
                            error_msg = "Neither ALStore nor ALPackageManager could be found."
                            parent._logger(f"[apps] {error_msg}", level='error')

                except Exception as e:
                    error_msg = f"Error listing applications: {e}"
                    parent._logger(f"[apps] {error_msg}", level='error')

                self._json(200, {'apps': apps, 'error': error_msg})

            def _apps_start(self, payload):
                name = payload.get('name')
                if not name:
                    self._send_503('missing app name')
                    return
                try:
                    # ALLauncher permet startApplication(uuid/name) sur certaines versions
                    launcher = self.server.session.service('ALLauncher') if self.server.session else None
                    if launcher:
                        try:
                            launcher.launchApp(name)
                            self._json(200, {'ok': True})
                            return
                        except Exception:
                            pass
                    # Fallback PackageManager
                    pm = self.server.session.service('ALPackageManager') if self.server.session else None
                    if pm and hasattr(pm, 'startApp'):  # certaines versions
                        pm.startApp(name)
                        self._json(200, {'ok': True})
                        return
                    self._send_503('No launcher available')
                except Exception as e:
                    self._send_503('apps/start error: %s' % e)

            def _apps_stop(self, payload):
                name = payload.get('name')
                if not name:
                    self._send_503('missing app name')
                    return
                try:
                    launcher = self.server.session.service('ALLauncher') if self.server.session else None
                    if launcher and hasattr(launcher, 'stopApp'):
                        launcher.stopApp(name)
                        self._json(200, {'ok': True})
                        return
                    pm = self.server.session.service('ALPackageManager') if self.server.session else None
                    if pm and hasattr(pm, 'stopApp'):
                        pm.stopApp(name)
                        self._json(200, {'ok': True})
                        return
                    self._send_503('No stop method available')
                except Exception as e:
                    self._send_503('apps/stop error: %s' % e)

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
                    self._json(200, {'text': '\n'.join(lines)})
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
# TCPServer custom : permet d'attacher des champs arbitraires
# ————————————————————————————————————————————————————————————
class _TCPServer(TCPServer):
    allow_reuse_address = True

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
