#!/usr/bin/env python
# -*- coding: utf-8 -*-
""" 
PepperLife Launcher Service and Web Server

Ce script a un double rôle :
1.  En tant que service NAOqi ("PepperLifeLauncher"), il permet de dÃ©marrer/arrÃªter 
    le script principal de l'application (`pepperLife.py`).
2.  En tant que serveur web REST, il sert l'interface utilisateur (le dossier `html/`) 
    sur le port 8080 et expose une API pour contrÃ´ler le lanceur.
"""
import qi
import subprocess
import os
import stat
import logging
import collections
import threading
import json
import time
import sys
import signal
import io
import re


BIN_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_DIR = os.path.dirname(BIN_DIR)
REPO_ROOT = os.path.dirname(PACKAGE_DIR)
if REPO_ROOT and REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    from pepperLife.services.classSystem import RobotIdentityManager
except Exception:
    RobotIdentityManager = None

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

try:
    text_type = unicode
except NameError:
    text_type = str

try:
    from http.server import SimpleHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn
except ImportError:
    from SimpleHTTPServer import SimpleHTTPRequestHandler
    from BaseHTTPServer import HTTPServer
    from SocketServer import ThreadingMixIn

# ==============================================================================
# 1. SERVICE NAOqi : LANCEUR DE PROCESSUS
# ==============================================================================

class LauncherService:
    """
    Contient la logique de gestion du processus pepperLife.py.
    """
    def __init__(self, session, logger=None):
        self.session = session
        self.logger = logger or logging.getLogger(__name__)
        self.process = None
        self.logs = collections.deque(maxlen=200)
        self.service_status = "Checking..."
        self.autostart_enabled = False
        self.autostart_has_run = False
        self._config_paths = self._compute_config_paths()
        self._svc_lock = threading.RLock()
        self.identity_manager = RobotIdentityManager(self._svc, self._identity_log) if RobotIdentityManager else None
        self.refresh_autostart_flag()
        self.robot_identity = self.identity_manager.get_identity() if self.identity_manager else {'type': 'pepper'}
        self._naoqi_version = None
        self._naoqi_version_tuple = None
        self._autostart_stop = threading.Event()
        self._autostart_thread = threading.Thread(target=self._autostart_worker, name="PepperLifeAutostart")
        self._autostart_thread.daemon = True
        self._autostart_thread.start()

    def _read_pipe(self, pipe):
        try:
            for line in iter(pipe.readline, b''):
                decoded_line = line.decode('utf-8', 'ignore').strip()
                self.logs.append(decoded_line)
                self.logger.info("[pepperLife.py] %s", decoded_line)
        finally:
            pipe.close()

    def is_python_runner_installed(self):
        runner_path = '/home/nao/.local/share/PackageManager/apps/python3nao/bin/runpy3.sh'
        return os.path.exists(runner_path)

    def _parse_version_tuple(self, version):
        if not version:
            return None
        parts = []
        for token in str(version).split('.'):
            match = re.match(r'(\d+)', token)
            if not match:
                continue
            parts.append(int(match.group(1)))
            if len(parts) >= 3:
                break
        return tuple(parts) if parts else None

    def _get_naoqi_version(self, refresh=False):
        if not refresh and self._naoqi_version:
            return self._naoqi_version
        if not self.session:
            return None
        try:
            system_service = self.session.service("ALSystem")
            if not system_service:
                return None
            version = system_service.systemVersion()
            if version:
                self._naoqi_version = version
                self._naoqi_version_tuple = self._parse_version_tuple(version)
            return self._naoqi_version
        except Exception as e:
            self.logger.debug("Impossible de récupérer la version de NAOqi: %s", e)
            return None

    def _is_naoqi_29_or_newer(self):
        version_tuple = self._naoqi_version_tuple
        if not version_tuple:
            version = self._get_naoqi_version()
            version_tuple = self._naoqi_version_tuple if version else None
        if not version_tuple:
            return False
        major = version_tuple[0] if len(version_tuple) > 0 else 0
        minor = version_tuple[1] if len(version_tuple) > 1 else 0
        if major > 2:
            return True
        if major == 2 and minor >= 9:
            return True
        return False

    def _get_runner_path(self):
        """Retourne le chemin correct du runpy3.sh en fonction de la version de NAOqi."""
        default_runner_path = '/home/nao/.local/share/PackageManager/apps/python3nao/bin/runpy3.sh'
        naoqi_version = self._get_naoqi_version()
        if naoqi_version:
            self.logger.info("Version de NAOqi détectée: {}".format(naoqi_version))
            if naoqi_version.startswith("2.5"):
                self.logger.info("NAOqi 2.5 détecté. Utilisation du lanceur local.")
                local_runner_path = '/home/nao/.local/share/PackageManager/apps/pepperlife/bin/runpy3.sh'
                if os.path.exists(local_runner_path):
                    return local_runner_path
                else:
                    self.logger.warning("Le lanceur local pour NAOqi 2.5 est introuvable. Utilisation du lanceur par défaut.")
            else:
                self.logger.info("Utilisation du lanceur par défaut pour NAOqi 2.9+.")
        else:
            self.logger.error("Impossible de récupérer la version de NAOqi. Utilisation du lanceur par défaut.")

        return default_runner_path

    def _ensure_runner_executable(self, path):
        if not path or not os.path.exists(path):
            return
        try:
            st = os.stat(path)
            if not (st.st_mode & stat.S_IXUSR):
                new_mode = st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                os.chmod(path, new_mode)
                self.logger.info("Droits d'exécution ajoutés à %s", path)
        except Exception as e:
            self.logger.warning("Impossible d'ajuster les droits de %s: %s", path, e)

    def launch(self):
        if self.is_running():
            self.logger.warning("Le processus principal est déjà en cours d'exécution.")
            return True

        self.logs.clear()
        script_path = '/home/nao/.local/share/PackageManager/apps/pepperlife/pepperLife.py'
        runner_path = self._get_runner_path()

        if not os.path.exists(runner_path):
            err_msg = "Le lanceur python3 est introuvable à: {}".format(runner_path)
            self.logger.error(err_msg)
            self.logs.append("ERREUR: {}".format(err_msg))
            return False

        self._ensure_runner_executable(runner_path)

        command = [runner_path, "-u", script_path]
        try:
            self.logger.info("Lancement de la commande: {}".format(' '.join(command)))
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, preexec_fn=os.setsid)
            thread = threading.Thread(target=self._read_pipe, args=(self.process.stdout,))
            thread.daemon = True
            thread.start()
            self.autostart_has_run = True
            return True
        except Exception as e:
            self.logger.error("Erreur lors du lancement: {}".format(e))
            self.logs.append("ERREUR: {}".format(e))
            return False

    def is_running(self):
        if self.process and self.process.poll() is None:
            self.autostart_has_run = True
            return True
        
        if self.process:
            exit_code = self.process.poll()
            self.logger.info("Le processus s'est terminé avec le code: {}".format(exit_code))
            self.logs.append("--- Script terminé (code: {}) ---".format(exit_code))
            self.process = None # Nettoyage
            
        return False

    def get_logs(self):
        return list(self.logs)

    def _compute_config_paths(self):
        bin_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(bin_dir)
        default_path = os.path.join(root_dir, 'config.json.default')
        user_path = os.path.expanduser('~/.config/pepperlife/config.json')
        return default_path, user_path

    def _read_config_file(self, path):
        if not path or not os.path.exists(path):
            return {}
        try:
            with io.open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
            self.logger.warning("Config JSON inattendu (%s): type %s", path, type(data))
        except ValueError as exc:
            self.logger.warning("Config JSON invalide (%s): %s", path, exc)
        except Exception as exc:
            self.logger.debug("Lecture du fichier de config impossible (%s): %s", path, exc)
        return {}

    def _load_autostart_flag(self):
        default_path, user_path = self._config_paths
        autostart = False
        for source, path in (("default", default_path), ("user", user_path)):
            data = self._read_config_file(path)
            if not data:
                continue
            boot_section = data.get('boot') if isinstance(data, dict) else {}
            if isinstance(boot_section, dict) and 'autostart_pepperlife' in boot_section:
                autostart = bool(boot_section.get('autostart_pepperlife'))
                if source == "user":
                    break
        self.autostart_enabled = autostart
        return self.autostart_enabled

    def refresh_autostart_flag(self):
        return self._load_autostart_flag()

    def refresh_robot_identity(self):
        if not self.identity_manager:
            return self.robot_identity
        self.robot_identity = self.identity_manager.refresh_identity()
        return self.robot_identity

    def get_robot_type(self):
        if self.identity_manager:
            return self.identity_manager.get_robot_type()
        if isinstance(self.robot_identity, dict):
            value = self.robot_identity.get('type')
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
        return 'pepper'

    # ------------------------------------------------------------------ Helpers
    def _svc(self, name):
        if not self.session:
            return None
        try:
            with self._svc_lock:
                return self.session.service(name)
        except Exception as exc:
            self.logger.debug("Launcher svc(%s) failed: %s", name, exc)
            return None

    def _identity_log(self, message, level='info', **_):
        log_fn = getattr(self.logger, level, None)
        if callable(log_fn):
            log_fn(message)
        else:
            self.logger.info(message)

    def get_wakeup_boot_status(self):
        if self._is_naoqi_29_or_newer():
            try:
                life_starter = self.session.service("LifeStarter")
                if not life_starter:
                    raise RuntimeError("LifeStarter non disponible")
                allow = life_starter.getAllowToStartLife()
                if allow is None:
                    return "RUN"
                return "OK" if bool(allow) else "RUN"
            except Exception as exc:
                self.logger.debug("LifeStarter.getAllowToStartLife indisponible: %s", exc)
                # Fallback ALMotion ci-dessous
        try:
            motion = self.session.service("ALMotion")
            if not motion:
                raise RuntimeError("ALMotion non disponible")
            is_awake = motion.robotIsWakeUp()
        except Exception as exc:
            self.logger.debug("WakeUp status unavailable: %s", exc)
            return "UNKNOWN"
        if is_awake is None:
            return "RUN"
        return "OK" if bool(is_awake) else "RUN"

    def _autostart_worker(self):
        """Surveille l'état du robot pour déclencher le lancement sans interface."""
        interval = 5.0
        wait = self._autostart_stop.wait
        while not self._autostart_stop.is_set():
            try:
                self.refresh_autostart_flag()
                if not self.autostart_enabled:
                    pass
                elif self.is_running() or self.autostart_has_run:
                    pass
                elif self.service_status != 'OK':
                    pass
                else:
                    wakeup_state = self.get_wakeup_boot_status()
                    if wakeup_state == 'OK':
                        self.logger.info("[Autostart] Conditions remplies (service OK, wakeup OK). Lancement de pepperLife.py")
                        result = self.launch()
                        if result:
                            self.logger.info("[Autostart] Lancement automatique déclenché.")
                        else:
                            self.logger.warning("[Autostart] Lancement automatique échoué, nouvel essai ultérieur.")
                    else:
                        self.logger.debug("[Autostart] WakeUp non prêt (%s).", wakeup_state)
            except Exception as exc:
                self.logger.debug("[Autostart] Boucle interrompue: %s", exc)
            finally:
                wait(interval)

    def restart_robot(self):
        try:
            al_system = self.session.service("ALSystem")
            if not al_system:
                raise RuntimeError("ALSystem indisponible")
            al_system.reboot()
            self.logger.info("Commande de redémarrage robot envoyée")
            return True
        except Exception as exc:
            self.logger.error("Impossible de redémarrer le robot: %s", exc)
            return False

    def shutdown_robot(self):
        try:
            al_system = self.session.service("ALSystem")
            if not al_system:
                raise RuntimeError("ALSystem indisponible")
            al_system.shutdown()
            self.logger.info("Commande d'arrêt robot envoyée")
            return True
        except Exception as exc:
            self.logger.error("Impossible d'éteindre le robot: %s", exc)
            return False

    def stop(self):
        if not self.is_running():
            self.logger.warning("Le processus n'est pas en cours d'exécution.")
            return True
        try:
            pgid = os.getpgid(self.process.pid)
            self.logger.info("Arrêt du groupe de processus avec PGID: {}".format(pgid))
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(1)
            if self.is_running():
                self.logger.warning("Le processus n'a pas répondu à SIGTERM, envoi de SIGKILL.")
                os.killpg(pgid, signal.SIGKILL)
            self.process = None
            self.logs.append("--- Processus arrêté par l'utilisateur ---")
            return True
        except Exception as e:
            self.logger.error("Erreur lors de l'arrêt du processus: {}".format(e))
            return False

    def start_pepper_life_service(self):
        self.logger.info("Tentative de démarrage du service PepperLife NaoQI...")
        runner_path = self._get_runner_path()

        if not os.path.exists(runner_path):
            self.logger.error("  -> Le lanceur Python 3 est introuvable. Impossible de démarrer le service.")
            self.service_status = "FAILED"
            return False

        self._ensure_runner_executable(runner_path)

        service_script_path = '/home/nao/.local/share/PackageManager/apps/pepperlife/bin/pepper_life_service.py'
        command = [runner_path, service_script_path]

        try:
            subprocess.Popen(command, preexec_fn=os.setsid)
            self.logger.info("  -> Commande de lancement envoyée. Attente de 3 secondes pour la vérification...")
            time.sleep(3)

            self.session.service("PepperLifeService")
            self.service_status = "OK"
            self.logger.info("  -> VÃ©rification rÃ©ussie. Service PepperLife NaoQI : OK")
            self.logs.append("Service PepperLife NaoQI : OK")
            return True
        except Exception as e:
            self.service_status = "FAILED"
            self.logger.error("  -> Ã‰chec du dÃ©marrage ou de la vÃ©rification du service PepperLife: {}".format(e))
            self.logs.append("Service PepperLife NaoQI : FAILED ({})".format(e))
            return False

    def restart_pepper_life_service(self):
        self.logger.info("Tentative de redémarrage du service PepperLife NaoQI...")
        try:
            # Tenter d'arrêter proprement le service existant
            self.logger.info("  -> Arrêt de l'ancien processus de service (si existant)...")
            subprocess.call(['pkill', '-f', 'pepper_life_service.py'])
            time.sleep(1) # Laisser le temps au processus de se terminer
        except Exception as e:
            self.logger.warning("  -> N'a pas pu arrêter l'ancien service (ce n'est peut-être pas un problème): {}".format(e))
        
        # Démarrer le nouveau service
        return self.start_pepper_life_service()

# ==============================================================================
# 2. SERVEUR WEB : SERT L'UI ET L'API REST
# ==============================================================================

def ansi_to_html(text):
    """Convertit les codes de couleur ANSI (standard et non-standard) en HTML."""
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    replacements = {
        # Standard ANSI avec ESC
        "\033[95m": '<span style="color: magenta">',
        "\033[94m": '<span style="color: blue">',
        "\033[96m": '<span style="color: cyan">',
        "\033[92m": '<span style="color: green">',
        "\033[93m": '<span style="color: yellow">',
        "\033[91m": '<span style="color: red">',
        "\033[1m": '<span style="font-weight: bold">',
        "\033[4m": '<span style="text-decoration: underline">',
        "\033[0m": '</span>',
        # Non-standard sans ESC
        "[95m": '<span style="color: magenta">',
        "[94m": '<span style="color: blue">',
        "[96m": '<span style="color: cyan">',
        "[92m": '<span style="color: green">',
        "[93m": '<span style="color: yellow">',
        "[91m": '<span style="color: red">',
        "[1m": '<span style="font-weight: bold">',
        "[4m": '<span style="text-decoration: underline">',
        "[0m": '</span>',
    }
    for code, tag in replacements.items():
        text = text.replace(code, tag)
    return text

class WebHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.launcher = kwargs.pop('launcher', None)
        SimpleHTTPRequestHandler.__init__(self, *args, **kwargs)

    def _json_response(self, code, payload):
        data = json.dumps(payload).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/launcher/status':
            autostart_flag = self.launcher.refresh_autostart_flag()
            wakeup_state = self.launcher.get_wakeup_boot_status()
            if hasattr(self.launcher, 'refresh_robot_identity'):
                try:
                    self.launcher.refresh_robot_identity()
                except Exception:
                    pass
            status = {
                'is_running': self.launcher.is_running(),
                'python_runner_installed': self.launcher.is_python_runner_installed(),
                'service_status': self.launcher.service_status,
                'wakeup_boot': wakeup_state,
                'autostart_pepperlife': autostart_flag,
                'autostart_has_run': getattr(self.launcher, 'autostart_has_run', False),
                'robot_type': self.launcher.get_robot_type() if hasattr(self.launcher, 'get_robot_type') else 'pepper',
            }
            self._json_response(200, status)
        elif path == '/api/launcher/logs':
            raw_logs = self.launcher.get_logs()
            html_logs = [ansi_to_html(log) for log in raw_logs]
            self._json_response(200, {'logs': html_logs})
        else:
            SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/launcher/start':
            result = self.launcher.launch()
            self._json_response(200, {'success': result})
        elif path == '/api/launcher/stop':
            result = self.launcher.stop()
            self._json_response(200, {'success': result})
        elif path == '/api/service/restart':
            result = self.launcher.restart_pepper_life_service()
            self._json_response(200, {'success': result})
        elif path == '/api/robot/restart':
            result = self.launcher.restart_robot()
            self._json_response(200, {'success': result})
        elif path == '/api/robot/shutdown':
            result = self.launcher.shutdown_robot()
            self._json_response(200, {'success': result})
        else:
            self._json_response(404, {'error': 'Not Found'})

def start_web_server(logger, port, root_dir, launcher_service):
    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

    def handler_factory(*args, **kwargs):
        return WebHandler(*args, launcher=launcher_service, **kwargs)

    class WebServerThread(threading.Thread):
        def __init__(self, host, port, root_dir, factory):
            super(WebServerThread, self).__init__()
            self.daemon = True
            self.server = ThreadingHTTPServer((host, port), factory)
            logger.info("[WebServer] DÃ©marrage du serveur multi-thread sur {}:{}, racine: {}".format(host, port, root_dir))

        def run(self):
            os.chdir(root_dir)
            self.server.serve_forever()

        def stop(self):
            if self.server:
                self.server.shutdown()
                self.server.server_close()

    server_thread = WebServerThread('0.0.0.0', port, root_dir, handler_factory)
    server_thread.start()
    return server_thread

# ==============================================================================
# 3. POINT D'ENTRÃ‰E PRINCIPAL
# ==============================================================================

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(script_dir, 'lanceur.log')
    logger = logging.getLogger("pepperlife_lanceur")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    try:
        fh = logging.FileHandler(log_file, mode='w')
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception as e:
        print("Erreur de configuration du FileHandler: {}".format(e))

    if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
        sh = logging.StreamHandler()
        sh.setFormatter(formatter)
        logger.addHandler(sh)
    
    logger.info("--- Démarrage du service PepperLifeLauncher ---")

    try:
        app = qi.Application(sys.argv)
    except Exception as e:
        logger.error("Impossible de créer l'instance qi.Application: {}".format(e))
        sys.exit(1)

    is_connected = False
    while not is_connected:
        try:
            logger.info("Tentative de connexion Ã  NAOqi...")
            app.start()
            app.session.service("ALSystem")
            logger.info("Connexion Ã  NAOqi et ALSystem rÃ©ussie.")
            is_connected = True
        except Exception as e:
            logger.warning("Connexion Ã  NAOqi Ã©chouÃ©e: {}. Nouvelle tentative dans 5s...".format(e))
            time.sleep(5)

    # dans la classe LauncherService pour la clartÃ©.
    service_instance = LauncherService(app.session, logger)

    logger.info("Lancement du service NaoQI...")
    service_instance.start_pepper_life_service()

    web_root = os.path.abspath(os.path.join(script_dir, '..', 'html'))
    web_server_thread = start_web_server(logger, 8080, web_root, service_instance)

    logger.info("Serveur web dÃ©marrÃ©. Attente de la fin du programme (Ctrl+C).")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("ArrÃªt demandÃ©.")
    finally:
        logger.info("ArrÃªt du serveur web.")
        web_server_thread.stop()

if __name__ == "__main__":
    main()
