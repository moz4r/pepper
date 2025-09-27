# -*- coding: utf-8 -*-
# Main application entrypoint.
# This script starts a stateful web server to manage the pepperLife.py subprocess.
# It is designed to be Python 2.7 compatible for boot reliability.

try:
    # Python 3
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import socketserver
    from socketserver import ThreadingMixIn
    import threading
except ImportError:
    # Python 2
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
    from SocketServer import ThreadingMixIn
    import threading

import os
import sys
import subprocess
import json
from collections import deque
import time

# --- Global State --- (simple, for a single-user app)
PORT = 8088
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(PROJECT_ROOT, 'html', 'index.html') # Serve the original index

process_handle = None
logs = deque(maxlen=500) # Store last 500 log lines
process_lock = threading.Lock()

# --- Log Reader Thread ---
def log_reader_thread(process):
    """Reads a process's stdout and appends lines to the global logs deque."""
    for line in iter(process.stdout.readline, b''):
        with process_lock:
            logs.append(line.decode('utf-8', 'ignore').strip())
    process.stdout.close()

# --- HTTP Request Handler ---
class RequestHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests by dispatching to different endpoints."""

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.serve_static(HTML_FILE, 'text/html')
        elif self.path.startswith('/js/') or self.path.startswith('/css/') or self.path.startswith('/img/'):
            self.serve_static(os.path.join(PROJECT_ROOT, 'html', self.path.lstrip('/')), None)
        elif self.path == '/launch':
            self.handle_launch()
        elif self.path == '/stop':
            self.handle_stop()
        elif self.path == '/status':
            self.handle_status()
        elif self.path == '/get_logs':
            self.handle_get_logs()
        else:
            self.send_error(404, "Not Found")

    def serve_static(self, file_path, content_type):
        """Serves a static file."""
        try:
            with open(file_path, 'rb') as f:
                self.send_response(200)
                if content_type:
                    self.send_header('Content-type', content_type)
                self.end_headers()
                self.wfile.write(f.read())
        except IOError:
            self.send_error(404, "File Not Found")

    def handle_launch(self):
        global process_handle
        with process_lock:
            if process_handle and process_handle.poll() is None:
                self.send_response(409, "Conflict") # 409 Conflict - already running
                self.end_headers()
                self.wfile.write(b"Service is already running.")
                return

            logs.clear()
            logs.append("--- Launch request received. Detecting Python 3... ---")

            python3_runner = '/home/nao/.local/share/PackageManager/apps/python3nao/bin/runpy3.sh'
            target_script = os.path.join(PROJECT_ROOT, 'pepperLife.py')
            command = None

            if os.path.exists(python3_runner):
                command = [python3_runner, target_script]
            elif self._command_exists('python3'):
                command = ['python3', target_script]
            else:
                logs.append("FATAL: No Python 3 environment found.")
                self.send_response(500)
                self.end_headers()
                return

            try:
                process_handle = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                thread = threading.Thread(target=log_reader_thread, args=(process_handle,))
                thread.daemon = True
                thread.start()
                logs.append("--- Service process started. ---")
                self.send_response(200)
                self.end_headers()
            except Exception as e:
                logs.append("--- FAILED TO LAUNCH SUBPROCESS: %s ---" % str(e))
                self.send_response(500)
                self.end_headers()

    def handle_stop(self):
        global process_handle
        with process_lock:
            if process_handle and process_handle.poll() is None:
                logs.append("--- Stop request received. Terminating process... ---")
                process_handle.terminate()
                try:
                    process_handle.wait(timeout=5) # Python 3 only
                except:
                    pass # wait() has no timeout in python 2
                process_handle = None
                logs.append("--- Process stopped. ---")
            self.send_response(200)
            self.end_headers()

    def handle_status(self):
        with process_lock:
            is_running = process_handle and process_handle.poll() is None
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'isRunning': is_running}).encode('utf-8'))

    def handle_get_logs(self):
        with process_lock:
            log_list = list(logs)
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(log_list).encode('utf-8'))

    def _command_exists(self, cmd):
        return subprocess.call("type " + cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""

def run_server():
    """Starts the web server."""
    try:
        server_address = ('', PORT)
        httpd = ThreadingHTTPServer(server_address, RequestHandler)
        print("Stateful server starting on port %d..." % PORT)
        # Create a startup log for definitive proof of execution
        with open("/tmp/server_started.log", "w") as f:
            f.write("Server started successfully on port %d at %s." % (PORT, time.strftime("%Y-%m-%d %H:%M:%S")))
        httpd.serve_forever()
    except Exception as e:
        # If startup fails, log to a different file
        with open("/tmp/server_boot_error.log", "w") as f:
            f.write("Failed to start server: %s" % str(e))

if __name__ == '__main__':
    run_server()