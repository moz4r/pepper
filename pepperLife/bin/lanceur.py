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
import logging
import collections
import threading
import json
import time
import sys
import signal

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

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

    def launch(self):
        if self.is_running():
            self.logger.warning("Le processus principal est dÃ©jÃ  en cours d'exÃ©cution.")
            return True

        self.logs.clear()
        script_path = '/home/nao/.local/share/PackageManager/apps/pepperlife/pepperLife.py'
        
        # DÃ©finir le chemin par dÃ©faut du lanceur
        runner_path = '/home/nao/.local/share/PackageManager/apps/python3nao/bin/runpy3.sh'

        try:
            # RÃ©cupÃ©rer la version de NAOqi
            system_service = self.session.service("ALSystem")
            naoqi_version = system_service.systemVersion()
            self.logger.info("Version de NAOqi dÃ©tectÃ©e: {}".format(naoqi_version))

            # VÃ©rifier si la version est 2.5
            if "2.5" in naoqi_version:
                self.logger.info("NAOqi 2.5 dÃ©tectÃ©. Utilisation du lanceur local.")
                # Chemin vers le runpy3.sh local du projet
                local_runner_path = '/home/nao/.local/share/PackageManager/apps/pepperlife/bin/runpy3.sh'
                if os.path.exists(local_runner_path):
                    runner_path = local_runner_path
                else:
                    self.logger.warning("Le lanceur local pour NAOqi 2.5 est introuvable Ã : {}. Utilisation du lanceur par dÃ©faut.".format(local_runner_path))
            else:
                self.logger.info("Utilisation du lanceur par dÃ©faut pour NAOqi 2.9+.")

        except Exception as e:
            self.logger.error("Impossible de rÃ©cupÃ©rer la version de NAOqi: {}. Utilisation du lanceur par dÃ©faut.".format(e))

        if not os.path.exists(runner_path):
            err_msg = "Le lanceur python3 est introuvable Ã : {}".format(runner_path)
            self.logger.error(err_msg)
            self.logs.append("ERREUR: {}".format(err_msg))
            return False

        command = [runner_path, "-u", script_path]
        try:
            self.logger.info("Lancement de la commande: {}".format(' '.join(command)))
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, preexec_fn=os.setsid)
            thread = threading.Thread(target=self._read_pipe, args=(self.process.stdout,))
            thread.daemon = True
            thread.start()
            return True
        except Exception as e:
            self.logger.error("Erreur lors du lancement: {}".format(e))
            self.logs.append("ERREUR: {}".format(e))
            return False

    def is_running(self):
        if self.process and self.process.poll() is None:
            return True
        
        # Si le processus existe mais ne tourne plus, c'est qu'il vient de se terminer.
        if self.process:
            exit_code = self.process.poll()
            self.logger.info("Le processus s'est terminé avec le code: {}".format(exit_code))
            self.logs.append("--- Script terminé (code: {}) ---".format(exit_code))
            self.process = None # Nettoyage
            
        return False

    def get_logs(self):
        return list(self.logs)

    def stop(self):
        if not self.is_running():
            self.logger.warning("Le processus n'est pas en cours d'exécution.")
            return True
        try:
            pgid = os.getpgid(self.process.pid)
            self.logger.info("Arrêt du groupe de processus avec PGID: {}".format(pgid))
            os.killpg(pgid, signal.SIGTERM)
            # Attendre un peu pour laisser le temps au processus de se terminer proprement
            time.sleep(1) # Un court délai peut aider
            # Vérifier s'il est toujours en cours d'exécution
            if self.is_running():
                self.logger.warning("Le processus n'a pas répondu à SIGTERM, envoi de SIGKILL.")
                os.killpg(pgid, signal.SIGKILL)
            self.process = None
            self.logs.append("--- Processus arrêté par l'utilisateur ---")
            return True
        except Exception as e:
            self.logger.error("Erreur lors de l'arrêt du processus: {}".format(e))
            return False

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
        # super() ne fonctionne pas avec les old-style classes de Python 2
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
            status = {
                'is_running': self.launcher.is_running(),
                'python_runner_installed': self.launcher.is_python_runner_installed()
            }
            self._json_response(200, status)
        elif path == '/api/launcher/logs':
            raw_logs = self.launcher.get_logs()
            html_logs = [ansi_to_html(log) for log in raw_logs]
            self._json_response(200, {'logs': html_logs})
        else:
            # Servir les fichiers statiques
            SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/launcher/start':
            result = self.launcher.launch()
            self._json_response(200, {'success': result})
        elif path == '/api/launcher/stop':
            result = self.launcher.stop()
            self._json_response(200, {'success': result})
        else:
            self._json_response(404, {'error': 'Not Found'})

def start_web_server(logger, port, root_dir, launcher_service):
    """DÃ©marre le serveur HTTP multi-thread dans un thread sÃ©parÃ©."""

    # DÃ©finition d'un serveur qui gÃ¨re chaque requÃªte dans un thread distinct
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
            # os.chdir n'est pas thread-safe, mais on le garde pour minimiser les changements
            # par rapport Ã  la version originale.
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
    
    logger.info("--- DÃ©marrage du service PepperLifeLauncher ---")

    app = None
    while app is None:
        try:
            logger.info("Tentative de connexion Ã  NAOqi...")
            app = qi.Application(sys.argv)
            app.start()
        except Exception as e:
            logger.warning("Connexion Ã  NAOqi Ã©chouÃ©e: {}. Nouvelle tentative dans 5s...".format(e))
            time.sleep(5)

    logger.info("Connexion Ã  NAOqi rÃ©ussie.")

    # Le service NAOqi n'est plus nÃ©cessaire, mais on garde la logique de lancement
    # dans la classe LauncherService pour la clartÃ©.
    service_instance = LauncherService(app.session, logger)

    # DÃ©marrer le serveur web et lui passer l'instance du service
    web_root = os.path.abspath(os.path.join(script_dir, '..', 'html'))
    web_server_thread = start_web_server(logger, 8080, web_root, service_instance)

    # On n'enregistre plus de service NAOqi, on attend juste la fin du programme
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