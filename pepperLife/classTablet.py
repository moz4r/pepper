# -*- coding: utf-8 -*-
# classTablet.py — gestion UI tablette (ALTabletService) + mini serveur HTTP
from __future__ import print_function
import os, io, atexit, threading
import time
import struct

from classWebServer import WebServer
from classCamera import classCamera

class classTablet(object):
    """
    Démarre un mini serveur HTTP qui sert une page noire avec un titre bleu,
    et l'affiche sur la tablette via ALTabletService si disponible.
    Permet de fournir la version via un provider (callable) ou un fichier.
    """
    def __init__(self, session=None, logger=None, port=8088,
                 version_text=u"dev", version_file=None, version_provider=None):
        self.session = session
        self._log = logger or (lambda msg, **k: print(msg))
        self.port = int(port)

        # Source de vérité pour la version
        self.version_provider = version_provider
        self.version_file = version_file
        self.version_text = self._resolve_version(version_text)

        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.ui_dir = os.path.join(self.script_dir, "ui_pepperlife")
        self.web_server = WebServer(logger=self._log, ui_dir=self.ui_dir, port=self.port)
        self.port = self.web_server.port
        self.tablet = None
        self.last_capture = None
        self._ensure_ui_files()

        # Récupère ALTabletService si possible
        try:
            if self.session:
                self.tablet = self.session.service("ALTabletService")
        except Exception as e:
            self._log("[Tablet] ALTabletService indisponible: %s" % e)

        self.cam = classCamera(session, self._log, res=1, color=13, fps=5)  # QVGA 320x240, BGR, ~5 FPS



        # Clean à la sortie du process
        atexit.register(self.stop)

    # ---------- Public API ----------
    def start(self, show=True):
        # Rafraîchit la version et régénère l'HTML
        self.version_text = self._resolve_version(self.version_text)
        self._ensure_ui_files()
        self._log("[Tablet] Version UI = %s" % self.version_text)
        try:
            self.cam.start()
        except Exception:
            pass
        self.web_server.start(self)
        self.port = self.web_server.port
        if show:
            self.show()
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
        self.hide()
        try:
            self.cam.stop()
        except Exception:
            pass
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
        html = u"""<!doctype html>
    <html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>PepperLife</title>
    <style>
    :root{--fg:#8EC8FF;--bg:#000;--btn:#111;--btnb:#1c1c1c;--white:#fff;--red:#e02727;--border:#2a2a2a}
    *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
    html,body{height:100%;margin:0}
    body{background:var(--bg);color:#cfe6ff;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Ubuntu,"Helvetica Neue",Arial,sans-serif}
    .wrap{display:flex;flex-direction:column;min-height:100%}

    .topbar{display:flex;align-items:center;justify-content:space-between;padding:12px 16px}
    .title{font-size:24px;color:var(--fg);font-weight:800;letter-spacing:.4px}
    .actions{display:flex;gap:12px}
    .btn{border:1px solid var(--btnb);background:var(--btn);color:#d6e8ff;padding:12px 14px;
        min-width:100px;min-height:48px;display:inline-flex;align-items:center;justify-content:center;
        font-weight:800;letter-spacing:.6px;border-radius:10px;cursor:pointer;user-select:none}
    .btn:active{transform:scale(.98)}
    .btn.on{border-color:#1e6b2d}
    .btn.sleep{border-color:#6b4c1e}

    .content{flex:1;display:grid;grid-template-columns:1fr 1.1fr;gap:20px;padding:16px}
    .panel{border:1px solid var(--border);border-radius:14px;padding:18px;background:rgba(255,255,255,.02)}

    .badgewrap{height:100%;display:flex;align-items:center;justify-content:center}
    .badge{width:220px;height:220px;border-radius:50%;background:var(--white);box-shadow:0 10px 40px rgba(0,0,0,.45);
            display:flex;align-items:center;justify-content:center}
    .dot{width:90px;height:90px;border-radius:50%;background:var(--red);box-shadow:inset 0 0 20px rgba(0,0,0,.25)}

    .camhead{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
    .camtitle{font-weight:700;opacity:.9}
    .camframe{position:relative;width:100%;aspect-ratio:4/3;background:#0e0e0e;border:1px solid var(--border);border-radius:12px;
                overflow:hidden;display:flex;align-items:center;justify-content:center}
    .camplaceholder{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
                    color:#7aa7cc;opacity:.7;font-weight:600;letter-spacing:.3px}
    video, img#cam{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:none}

    @media (max-width: 920px) {
        .content{grid-template-columns:1fr;gap:16px}
    }
    @media (max-width: 640px) {
        .title{font-size:20px}
        .btn{min-width:92px;min-height:44px;padding:10px 12px}
        .badge{width:200px;height:200px}
        .dot{width:80px;height:80px}
    }
    </style>
    <body>
    <div class="wrap">
        <div class="topbar">
        <div class="title">PepperLife – %VER%</div>
        <div class="actions">
            <div class="btn on"    id="btn-on">LIFE&nbsp;ON</div>
            <div class="btn sleep" id="btn-sleep">SLEEP</div>
        </div>
        </div>

        <div class="content">
        <div class="panel badgewrap">
            <div class="badge"><div class="dot" id="status-dot"></div></div>
        </div>

        <div class="panel">
            <div class="camhead">
            <div class="camtitle">Retour caméra</div>
            <div style="opacity:.6;font-size:12px" id="cam-status">en attente…</div>
            </div>
            <div class="camframe">
            <video id="camvid" autoplay muted playsinline></video>
            <img id="cam" alt="cam feed"/>
            <div class="camplaceholder" id="cam-ph">Aucune source vidéo</div>
            </div>
        </div>
        </div>
    </div>

    <script>
        function log(msg){ try { console.log(msg); } catch(e){} }
        function show_last_capture(){
            if (_poll) clearInterval(_poll);
            var img = document.getElementById('cam');
            img.src = "/last_capture.png?ts=" + Date.now();
            document.getElementById('cam-status').textContent = 'Capture';
        }
        document.getElementById('btn-on').addEventListener('click',  function(){ log('[UI] LIFE ON');  });
        document.getElementById('btn-sleep').addEventListener('click',function(){ log('[UI] SLEEP');    });

        var _poll = null;
        function startPngPolling(){
        var img = document.getElementById('cam');
        var vid = document.getElementById('camvid');
        var ph  = document.getElementById('cam-ph');
        var st  = document.getElementById('cam-status');

        vid.style.display='none'; vid.removeAttribute('src');
        img.style.display='block';
        ph.style.display='none';
        st.textContent = 'PNG';

        function tick(){
            img.src = "http://198.18.0.1:8088/cam.png?ts=" + Date.now();
        }
        if (_poll) clearInterval(_poll);
        tick();
        _poll = setInterval(tick, 200); // ~5 fps
        }
    </script>
    </body>
    </html>"""
        html = html.replace("%VER%", self.version_text)  # <-- simple et robuste
        with io.open(index_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Favicon stub pour éviter le 404
        fav = os.path.join(self.ui_dir, "favicon.ico")
        if not os.path.exists(fav):
            with io.open(fav, "wb") as f:
                f.write(b"")




    
