# -*- coding: utf-8 -*-
"""
classChoreography.py — coordination multi-robots via MQTT.
"""
from __future__ import print_function

import json
import os
import ssl
import threading
import time
import uuid

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover
    mqtt = None


class ChoreographyCoordinator(object):
    """Agrège l'état et gère la synchronisation MQTT."""

    def __init__(self, logger=None):
        self._logger = logger or (lambda *a, **k: None)
        self._lock = threading.RLock()
        self._program_queue = []
        self._robots = {}
        self._selected_robot_ids = set()
        self._status = 'idle'
        self._last_action = None
        self._mqtt_config = {}
        self._self_robot_id = None
        self._self_identity = {}
        self._mqtt_client = None
        self._mqtt_client_id = None
        self._mqtt_connected = False
        self._mqtt_last_error = None
        self._mqtt_topics = {'presence_pub': None, 'presence_sub': None, 'commands': None}
        self._mqtt_presence_thread = None
        self._mqtt_presence_stop = threading.Event()
        self._command_executor = None
        self._service_provider = None
        self._mqtt_should_run = False
        self._room_code = None
        self._mqtt_connect_logged = False
        self._mqtt_keepalive = 60

    # ------------------------------------------------------------------ Robots
    def ensure_self_robot(self, identity):
        """Enregistre/actualise le robot local et relance MQTT uniquement si besoin."""
        if not identity:
            return
        robot_id = identity.get('serial') or identity.get('name') or identity.get('type')
        if not robot_id:
            robot_id = 'local'
        robot_name = identity.get('name') or identity.get('type') or robot_id
        meta = {
            'type': identity.get('type', 'pepper'),
            'raw': identity.get('raw'),
            'source': identity.get('source')
        }
        new_identity = dict(identity)
        prev_robot_id = self._self_robot_id
        prev_identity = self._self_identity
        identity_changed = (prev_robot_id != robot_id) or (prev_identity != new_identity)

        self._self_identity = new_identity
        self._self_robot_id = robot_id
        self.upsert_robot(robot_id, robot_name, status='ready', meta=meta, is_self=True)
        # Ne relance MQTT que si l'identité a véritablement changé.
        if identity_changed:
            self._apply_mqtt_config(async_restart=True)

    def upsert_robot(self, robot_id, name, status='ready', meta=None, is_self=False):
        if not robot_id:
            return
        now = time.time()
        with self._lock:
            info = self._robots.get(robot_id, {}).copy()
            info.update({
                'id': robot_id,
                'name': name or info.get('name') or robot_id,
                'status': status or info.get('status', 'unknown'),
                'last_seen': now,
                'is_self': bool(is_self) or info.get('is_self', False),
                'meta': meta or info.get('meta', {}),
                'serial': (meta or {}).get('serial') or info.get('serial')
            })
            info['display_name'] = info.get('name') or robot_id
            self._robots[robot_id] = info
            if info.get('is_self'):
                self._selected_robot_ids.add(robot_id)

    def mark_robot_offline(self, robot_id):
        if not robot_id:
            return
        with self._lock:
            if robot_id in self._robots:
                self._robots[robot_id]['status'] = 'offline'

    def select_robots(self, robot_ids):
        with self._lock:
            valid_ids = {r_id for r_id in (robot_ids or []) if r_id in self._robots}
            if self._self_robot_id and self._self_robot_id in self._robots:
                valid_ids.add(self._self_robot_id)  # Toujours inclure le robot local
            self._selected_robot_ids = valid_ids

    # ------------------------------------------------------------- Programmes
    def add_program(self, name, nature='animation', source='apps'):
        if not name:
            raise ValueError("Le nom du programme est obligatoire.")
        program = {
            'id': str(uuid.uuid4()),
            'name': name,
            'nature': nature or 'animation',
            'source': source or 'apps',
            'added_at': time.time()
        }
        with self._lock:
            self._program_queue.append(program)
        return program

    def remove_program(self, program_id):
        if not program_id:
            return False
        with self._lock:
            before = len(self._program_queue)
            self._program_queue = [p for p in self._program_queue if p.get('id') != program_id]
            return len(self._program_queue) < before

    def reset_programs(self):
        with self._lock:
            self._program_queue = []

    def reset_remote_robots(self):
        with self._lock:
            remote_ids = [robot_id for robot_id, info in self._robots.items() if not info.get('is_self')]
            to_keep = {robot_id: info for robot_id, info in self._robots.items() if info.get('is_self')}
            self._robots = to_keep
            selected = {robot_id for robot_id in self._selected_robot_ids if robot_id in to_keep}
            if not selected and self._self_robot_id and self._self_robot_id in to_keep:
                selected.add(self._self_robot_id)
            self._selected_robot_ids = selected
        try:
            self._clear_remote_presence(remote_ids)
        except Exception:
            pass

    def set_command_executor(self, executor):
        if executor and not callable(executor):
            raise ValueError("Command executor must be callable.")
        self._command_executor = executor

    def set_service_provider(self, provider):
        if provider and not callable(provider):
            raise ValueError("Service provider must be callable.")
        self._service_provider = provider

    # -------------------------------------------------------------------- MQTT
    def update_from_config(self, mqtt_config):
        with self._lock:
            self._mqtt_config = dict(mqtt_config or {})
            room = (self._mqtt_config.get('room_code') or '').strip()
            generated = False
        if not room:
            room = "pepperparty_" + uuid.uuid4().hex[:5]
            self._mqtt_config['room_code'] = room
            generated = True
        self._room_code = room
        if self._mqtt_should_run:
            self._apply_mqtt_config(async_restart=True)

    def connect_mqtt(self):
        self._mqtt_should_run = True
        try:
            self._apply_mqtt_config()
        except Exception as exc:
            self._mqtt_should_run = False
            self._stop_mqtt_client()
            raise exc

    def disconnect_mqtt(self):
        self._mqtt_should_run = False
        self._stop_mqtt_client()
        self.reset_remote_robots()

    def _apply_mqtt_config(self, async_restart=False):
        if not self._mqtt_should_run:
            return
        enabled = bool(self._mqtt_config.get('enabled', True))
        if not enabled:
            raise ValueError("La configuration MQTT est désactivée.")
        if mqtt is None:
            self._mqtt_last_error = "paho-mqtt non installé"
            self._logger("[Choreo] MQTT activé mais paho-mqtt manquant.", level='warning')
            return
        # Redémarre le client pour appliquer les nouveaux paramètres / identité
        if async_restart:
            threading.Thread(target=self._restart_mqtt_client, daemon=True).start()
        else:
            self._restart_mqtt_client()

    def _restart_mqtt_client(self):
        self._stop_mqtt_client()
        try:
            self._start_mqtt_client()
        except Exception as e:
            self._mqtt_last_error = str(e)
            self._logger("[Choreo] Échec démarrage MQTT: %s" % e, level='error')

    def _start_mqtt_client(self):
        url = (self._mqtt_config.get('broker_url') or '').strip()
        if not url:
            raise ValueError("broker_url MQTT manquant.")
        parsed = urlparse(url if '://' in url else 'mqtt://' + url)
        scheme = (parsed.scheme or 'mqtt').lower()
        host = parsed.hostname or parsed.path
        if not host:
            raise ValueError("broker_url MQTT invalide (%s)." % url)
        port = parsed.port or (8883 if scheme in ('mqtts', 'ssl', 'tls') else 1883)
        keepalive = int(self._mqtt_config.get('keepalive') or 60)
        self._mqtt_keepalive = keepalive
        topic_prefix = (self._mqtt_config.get('topic_prefix') or 'pepperlife/choreo').strip('/ ')
        room_code = (self._room_code or '').strip('_ ')
        room_suffix = room_code if room_code else uuid.uuid4().hex[:5]
        topic_prefix_room = "{}/{}".format(topic_prefix, room_suffix)
        presence_suffix = (self._mqtt_config.get('presence_topic') or 'presence').strip('/ ')
        if presence_suffix.startswith(topic_prefix):
            presence_suffix = presence_suffix[len(topic_prefix):].lstrip('/')
        presence_root = "{}/{}".format(topic_prefix_room, presence_suffix)
        command_suffix = (self._mqtt_config.get('command_topic') or 'commands').strip('/ ')
        if command_suffix.startswith(topic_prefix):
            command_suffix = command_suffix[len(topic_prefix):].lstrip('/')
        command_topic = "{}/{}".format(topic_prefix_room, command_suffix)
        publish_suffix = self._self_robot_id or 'local'
        presence_pub = "%s/%s" % (presence_root, publish_suffix)
        presence_sub = presence_root + "/+"
        client_id = self._mqtt_config.get('client_id') or ("pepperlife-%s" % uuid.uuid4().hex[:10])

        client = mqtt.Client(client_id=client_id, clean_session=True)
        username = self._mqtt_config.get('username') or os.environ.get('PEPPER_MQTT_USER')
        password = self._mqtt_config.get('password') or os.environ.get('PEPPER_MQTT_PASS')
        if username:
            client.username_pw_set(username, password or '')
        if scheme in ('mqtts', 'ssl', 'tls'):
            context = ssl.create_default_context()
            if self._mqtt_config.get('allow_insecure_tls'):
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            client.tls_set_context(context)

        client.on_connect = self._on_mqtt_connect
        client.on_disconnect = self._on_mqtt_disconnect
        client.on_message = self._on_mqtt_message
        client.enable_logger() if self._mqtt_config.get('debug') else None

        self._mqtt_client = client
        self._mqtt_client_id = client_id
        self._mqtt_connected = False
        self._mqtt_last_error = None
        self._mqtt_topics = {
            'presence_pub': presence_pub,
            'presence_sub': presence_sub,
            'presence_root': presence_root,
            'commands': command_topic
        }
        client.connect(host, port, keepalive)
        client.loop_start()
        self._start_presence_loop()

    def _stop_mqtt_client(self):
        self._stop_presence_loop()
        if self._mqtt_client:
            try:
                self._publish_presence(status='offline', disconnecting=True)
            except Exception:
                pass
            try:
                self._mqtt_client.loop_stop()
            except Exception:
                pass
            try:
                self._mqtt_client.disconnect()
            except Exception:
                pass
        self._mqtt_client = None
        self._mqtt_connected = False
        self._mqtt_client_id = None
        if not self._mqtt_should_run:
            self._mqtt_last_error = None

    def _start_presence_loop(self):
        if self._mqtt_presence_thread and self._mqtt_presence_thread.is_alive():
            return
        self._mqtt_presence_stop = threading.Event()
        self._mqtt_presence_thread = threading.Thread(target=self._presence_loop)
        self._mqtt_presence_thread.daemon = True
        self._mqtt_presence_thread.start()

    def _stop_presence_loop(self):
        if self._mqtt_presence_thread and self._mqtt_presence_thread.is_alive():
            self._mqtt_presence_stop.set()
            self._mqtt_presence_thread.join(timeout=2)
        self._mqtt_presence_thread = None

    def _presence_loop(self):
        interval = int(self._mqtt_config.get('presence_interval') or 30)
        interval = max(10, min(300, interval))
        while not self._mqtt_presence_stop.wait(interval):
            try:
                self._publish_presence()
            except Exception as exc:
                self._logger("[Choreo] Presence loop error: %s" % exc, level='warning')

    def _publish_presence(self, status='ready', disconnecting=False):
        client = self._mqtt_client
        if not client or not self._mqtt_topics.get('presence_pub'):
            return
        if disconnecting:
            payload = ''
        else:
            identity = dict(self._self_identity or {})
            payload = {
                'id': self._self_robot_id or 'local',
                'name': identity.get('name') or identity.get('type') or self._self_robot_id or 'local',
                'status': status,
                'type': identity.get('type') or 'pepper',
                'serial': identity.get('serial'),
                'timestamp': time.time(),
                'meta': identity
            }
            payload = json.dumps(payload)
        client.publish(
            self._mqtt_topics['presence_pub'],
            payload,
            qos=int(self._mqtt_config.get('presence_qos') or 0),
            retain=True
        )

    def _clear_remote_presence(self, robot_ids):
        client = self._mqtt_client
        root = self._mqtt_topics.get('presence_root')
        if not client or not root:
            return
        for robot_id in robot_ids or []:
            if not robot_id or robot_id == self._self_robot_id:
                continue
            topic = "{}/{}".format(root, robot_id)
            try:
                client.publish(topic, '', qos=0, retain=True)
            except Exception as exc:
                self._logger("[Choreo] Effacement présence MQTT (%s) impossible: %s" % (topic, exc), level='warning')

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        self._mqtt_connected = (rc == 0)
        if rc != 0:
            self._mqtt_last_error = "Connexion MQTT rc=%s" % rc
            self._logger("[Choreo] Connexion MQTT échouée (rc=%s)" % rc, level='error')
            return
        self._mqtt_last_error = None
        presence_sub = self._mqtt_topics.get('presence_sub')
        commands = self._mqtt_topics.get('commands')
        if not self._mqtt_connect_logged:
            self._logger("[Choreo] MQTT connecté (room=%s). Souscription à %s et %s" % (
                self._room_code or 'default', presence_sub, commands
            ), level='info')
            self._mqtt_connect_logged = True
        if presence_sub:
            client.subscribe(presence_sub, qos=0)
        if commands:
            client.subscribe(commands, qos=1)
        self._publish_presence(status='ready')

    def _on_mqtt_disconnect(self, client, userdata, rc):
        self._mqtt_connected = False
        self._mqtt_connect_logged = False
        if rc != 0:
            self._mqtt_last_error = "Déconnexion inattendue rc=%s" % rc
            self._logger("[Choreo] MQTT déconnecté (rc=%s)" % rc, level='warning')

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8') if msg.payload else ''
            if topic == self._mqtt_topics.get('commands'):
                self._handle_command_message(payload)
            elif self._mqtt_topics.get('presence_sub') and topic.startswith(self._mqtt_topics['presence_sub'].rstrip('+')):
                self._handle_presence_message(payload)
        except Exception as exc:
            self._logger("[Choreo] MQTT message error: %s" % exc, level='warning')

    def _handle_presence_message(self, payload):
        if not payload:
            return
        try:
            data = json.loads(payload)
        except Exception:
            return
        robot_id = data.get('id')
        if not robot_id or robot_id == self._self_robot_id:
            return
        name = data.get('name') or robot_id
        status = data.get('status') or 'ready'
        meta = data.get('meta') or {'type': data.get('type')}
        if data.get('serial'):
            meta = dict(meta or {})
            meta['serial'] = data.get('serial')
        self.upsert_robot(robot_id, name, status=status, meta=meta, is_self=False)

    def _handle_command_message(self, payload):
        if not payload:
            return
        try:
            data = json.loads(payload)
        except Exception:
            return
        event = data.get('event')
        if event != 'start':
            return
        with self._lock:
            self._status = 'running'
            self._last_action = {
                'type': 'start',
                'payload': data,
                'at': data.get('timestamp') or time.time(),
                'origin': data.get('origin')
            }
        self._execute_command(data)

    # ------------------------------------------------------------------- State
    def get_state(self):
        with self._lock:
            now = time.time()
            robots = []
            for robot in self._robots.values():
                entry = robot.copy()
                last_seen = entry.get('last_seen', 0) or 0
                stale_threshold = max(35, (self._mqtt_keepalive or 60) * 2)
                entry['alive'] = bool(now - last_seen < stale_threshold)
                entry['last_seen_ts'] = last_seen
                robots.append(entry)
            mqtt_state = {
                'enabled': bool(self._mqtt_config.get('enabled')),
                'broker_url': self._mqtt_config.get('broker_url') or '',
                'topic_prefix': self._mqtt_config.get('topic_prefix') or 'pepperlife/choreo',
                'status': 'connected' if self._mqtt_connected else 'disconnected',
                'client_id': self._mqtt_client_id,
                'last_error': self._mqtt_last_error,
                'should_run': self._mqtt_should_run,
                'connected': self._mqtt_connected,
                'config': {
                    'broker_url': self._mqtt_config.get('broker_url') or '',
                    'username': self._mqtt_config.get('username') or '',
                    'allow_insecure_tls': bool(self._mqtt_config.get('allow_insecure_tls')),
                    'room_code': self._room_code,
                    'keepalive': self._mqtt_keepalive
                }
            }
            state = {
                'available': True,
                'status': self._status,
                'program_queue': list(self._program_queue),
                'robots': robots,
                'selected_robot_ids': list(self._selected_robot_ids),
                'mqtt': mqtt_state,
                'last_action': self._last_action
            }
        return state

    # ------------------------------------------------------------ Coordination
    def start(self, metadata=None):
        with self._lock:
            if not self._program_queue:
                raise ValueError("Aucun programme dans la file.")
            if not self._selected_robot_ids:
                raise ValueError("Aucun robot sélectionné.")
            payload = {
                'programs': list(self._program_queue),
                'robot_ids': list(self._selected_robot_ids),
                'timestamp': time.time(),
                'metadata': metadata or {}
            }
            self._status = 'running'
            self._last_action = {
                'type': 'start',
                'payload': payload,
                'at': payload['timestamp'],
                'origin': self._self_robot_id
            }
        self._logger("[Choreo] Déclenchement multi-robots: %s" % payload, level='info')
        self._broadcast_command(payload)
        self._execute_command(payload)
        return payload

    def _broadcast_command(self, payload):
        client = self._mqtt_client
        topic = self._mqtt_topics.get('commands')
        if not client or not topic or not self._mqtt_connected:
            return
        message = dict(payload)
        message['event'] = 'start'
        message['origin'] = self._self_robot_id or 'local'
        try:
            client.publish(topic, json.dumps(message), qos=1, retain=False)
            self._logger("[Choreo] Commande publiée sur %s" % topic, level='info')
        except Exception as exc:
            self._logger("[Choreo] Publication commande échouée: %s" % exc, level='warning')

    def _execute_command(self, command):
        if not command:
            return
        robot_ids = command.get('robot_ids') or []
        if self._self_robot_id and robot_ids and self._self_robot_id not in robot_ids:
            self.notify_command_complete({'status': 'skipped', 'command': command})
            return
        executor = self._command_executor
        if callable(executor):
            try:
                executor(command)
            except Exception as exc:
                self._logger("[Choreo] Command executor failed: %s" % exc, level='error')
            return

        if self._service_provider:
            self._spawn_default_runner(command)

    def notify_command_complete(self, result=None):
        with self._lock:
            self._status = 'idle'
            if result:
                self._last_action = {
                    'type': 'complete',
                    'payload': result,
                    'at': time.time(),
                    'origin': self._self_robot_id
                }

    def _spawn_default_runner(self, command):
        programs = command.get('programs') or []
        def _runner():
            try:
                pls = None
                try:
                    pls = self._service_provider('PepperLifeService')
                except Exception as exc:
                    self._logger("[Choreo] Service provider failure: %s" % exc, level='error')
                if not pls:
                    self._logger("[Choreo] PepperLifeService indisponible pour exécuter la commande.", level='error')
                    return
                for entry in programs:
                    name = (entry or {}).get('name')
                    if not name:
                        continue
                    try:
                        self._logger("[Choreo] Lancement local de %s" % name, level='info')
                        pls.playAnimation(name, False, True)
                        time.sleep(1.0)
                    except Exception as exc:
                        self._logger("[Choreo] Échec playAnimation(%s): %s" % (name, exc), level='error')
            finally:
                self.notify_command_complete({'programs': programs})
        th = threading.Thread(target=_runner, name="ChoreoRunner")
        th.daemon = True
        th.start()

    # ----------------------------------------------------------------- Cleanup
    def shutdown(self):
        self._stop_mqtt_client()
