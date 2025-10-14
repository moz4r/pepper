// API pour le lanceur lui-même (servi sur le même port que la page, 8080)
const launcherApi = {
  getStatus: () => fetch('/api/launcher/status').then(r => r.json()),
  start: () => fetch('/api/launcher/start', { method: 'POST' }).then(r => r.json()),
  stop: () => fetch('/api/launcher/stop', { method: 'POST' }).then(r => r.json()),
  restartService: () => fetch('/api/service/restart', { method: 'POST' }).then(r => r.json()),
  getLogs: () => fetch('/api/launcher/logs').then(r => r.json()),
};

const template = `
  <style>
    /* --- Layout --- */
    .home-grid { display: grid; grid-template-columns: 50% 50%; gap: 16px; }
    @media (max-width: 980px) { .home-grid { grid-template-columns: 1fr; } }

    /* --- Cards --- */
    .card {
      background: #fbfbfd;
      border-radius: 16px;
      border: 1px solid rgba(2,6,23,0.08);
      box-shadow: 0 10px 30px rgba(2,6,23,0.06);
      padding: 16px;
      color: #0b1220;
    }
    .title {
      font-weight: 700;
      font-size: 1.05rem;
      letter-spacing: .2px;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
      color:#0b1220;
    }
    .title::before{
      content:"";
      width: 8px;height: 8px;border-radius: 50%;
      background: linear-gradient(135deg, #7c3aed, #06b6d4);
      box-shadow: 0 0 0 4px rgba(124,58,237,0.10);
    }

    /* --- Backend manager --- */
    .backend-manager .status-line { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; font-size: 0.9em; font-weight: 500; }
    .backend-manager .status-dot { width: 12px; height: 12px; border-radius: 50%; background: #9aa4b2; box-shadow: 0 0 0 4px rgba(2,6,23,0.06); }
    .backend-manager .status-dot.running { background: #22c55e; }
    .backend-manager .status-dot.stopped { background: #ef4444; }
    .backend-manager .actions { display: flex; gap: 10px; }

    .btn {
      display: inline-flex; align-items: center; gap: 8px;
      border: 1px solid rgba(2,6,23,0.10);
      background: #0ea5e9;
      color: #fff;
      padding: 8px 12px;
      border-radius: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: transform .06s ease, box-shadow .2s ease, opacity .2s ease, background .2s ease;
      box-shadow: 0 6px 16px rgba(14,165,233,.25);
    }
    .btn:hover { transform: translateY(-1px); }
    .btn:disabled { opacity: .6; cursor: not-allowed; }
    .btn.btn-warning { background: #f59e0b; box-shadow: 0 6px 16px rgba(245,158,11,.25); }
    .btn.btn-danger  { background: #ef4444; box-shadow: 0 6px 16px rgba(239,68,68,.25); }
    .btn.btn-ghost  { background: rgba(2,6,23,0.06); color: #0b1220; box-shadow: none; border-color: rgba(2,6,23,0.10); }

    .hidden { display: none; }
    .python-status { font-size: 0.9em; opacity: 0.9; color:#0b1220; }

    /* --- Robot info card (refonte) --- */
    .robot-info-card {
      background: linear-gradient(180deg,#ffffff, #f6f8fb);
    }
    .robot-info-card .content-grid {
      display: grid;
      grid-template-columns: 1fr auto 140px;
      align-items: center;
      gap: 1rem;
    }
    .robot-info-card .status-params { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; }
    .robot-info-card .status-item {
      display: flex; justify-content: space-between; align-items: center;
      padding: .5rem .65rem;
      background: #fff;
      border-radius: 12px;
      border: 1px solid #e8edf5;
      color:#0b1220;
    }
    .robot-info-card .status-item .label { font-weight: 700; color: #334155; font-size: .9em; }
    .robot-info-card .status-item .value { color: #0b1220; text-align: right; font-size: .92em; }
    .robot-info-card .status-item .version-status { font-size: .8em; opacity: .8; }
    .robot-info-card .status-image {
      padding-left: 1rem; border-left: 1px dashed #e5e9f2;
      display:flex; align-items:center; justify-content:center;
    }
    .robot-info-card .status-image img {
      max-height: 180px; filter: drop-shadow(0 10px 22px rgba(2,6,23,.15));
    }
    .power-control { position: relative; display: flex; align-items: center; justify-content: center; }
    #power-icon { font-size: 2rem; cursor: pointer; padding: 10px; color:#0b1220; border-radius:12px; }
    #power-icon:hover{ background:#eef2f7; }
    .power-menu {
      display: none; position: absolute; top: 100%; right: 0;
      background: #111827; color:#e5e7eb;
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 12px; padding: 8px; z-index: 100;
      box-shadow: 0 20px 40px rgba(2,6,23,.28);
    }
    .power-menu .btn{ background:#374151; border-color:#4b5563; box-shadow:none; }
    .power-menu .btn:hover{ background:#4b5563; }

    /* --- Console dock: DARK, 90vh --- */
    .console-dock {
      position: fixed; left: 24px; right: 24px; bottom: 24px;
      border-radius: 18px;
      overflow: hidden;
      background: radial-gradient(900px 900px at 85% 120%, rgba(59,130,246,.15), transparent 40%),
                  linear-gradient( 180deg, #0b1220, #0a0f1a );
      border: 1px solid rgba(255,255,255,.06);
      box-shadow: 0 40px 80px rgba(2,6,23,.45);
      transition: transform .35s cubic-bezier(.2,.8,.2,1), box-shadow .35s ease, height .35s ease;
      height: 45vh; /* Default smaller height */
      display: grid;
      grid-template-rows: auto 1fr;
      z-index: 60;
      color:#e5e7eb;
    }
    .console-dock.is-fullscreen {
      height: 90vh;
    }
    .console-dock.is-collapsed {
      height: 64px;
      transform: translateY(0);
      box-shadow: 0 14px 40px rgba(2,6,23,.35);
    }

    .console-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 10px 14px;
      border-bottom: 1px solid rgba(255,255,255,.06);
      font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto;
      color:#f8fafc;
    }
    .console-title {
      display: flex; align-items: center; gap: 10px;
      font-weight: 800;
    }
    .console-title .dot {
      width: 10px;height: 10px;border-radius: 50%;
      background: #16a34a; box-shadow: 0 0 0 4px rgba(22,163,74,.18);
    }
    .console-actions { display: flex; align-items: center; gap: 8px; }
    .console-actions .btn {
      padding: 6px 10px; border-radius: 10px; font-size: .9rem;
      background: rgba(255,255,255,.06);
      color:#e5e7eb; border-color: rgba(255,255,255,.10);
      box-shadow:none;
    }
    .console-actions .btn:hover{ background: rgba(255,255,255,.12); }

    .console-body {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      color: #e5e7eb;
      background: linear-gradient(0deg, rgba(255,255,255,.02), transparent 35%);
      overflow: hidden;
      display: grid;
      grid-template-rows: auto 1fr;
    }

    .console-toolbar {
      display:flex; gap:8px; align-items:center;
      padding:8px 12px; border-bottom: 1px dashed rgba(255,255,255,.08);
    }
    .console-toolbar input[type="text"]{
      flex:1; border:1px solid rgba(255,255,255,.12); border-radius: 10px; padding:8px 10px;
      outline:none; background:#0f172a; color:#e5e7eb;
    }

    .logs {
      margin: 0; padding: 12px; overflow: auto;
      white-space: pre-wrap; /* conserver retours + interpréter HTML */
      word-break: break-word;
      line-height: 1.45; font-size: 13.5px;
      tab-size: 2;
    }

    .badge {
      display:inline-flex; align-items:center; gap:6px;
      background: rgba(59,130,246,.18); color:#dbeafe; border:1px solid rgba(59,130,246,.35);
      padding:4px 8px; border-radius: 999px; font-weight:700; font-size:.78rem;
    }

    /* Log highlighting */
    .log-ts { opacity:.75; }
    .log-lvl { font-weight:800; padding:0 .25em; border-radius:.35rem; }
    .lvl-info{ color:#93c5fd; }
    .lvl-warn{ color:#fde68a; }
    .lvl-error{ color:#fecaca; }
    .lvl-debug{ color:#a7f3d0; }

    /* Responsive */
    @media (max-width: 980px) {
      .console-dock { left: 16px; right: 16px; bottom: 16px; }
    }
  </style>

  <div class="home-grid">
    <div class="card backend-manager">
      <div class="title">Système</div>
      <div id="python-runner-status" class="status-line python-status" style="margin-bottom: 8px; margin-top: -8px;"></div>
      <div class="status-line">
        <div id="service-status-dot" class="status-dot"></div>
        <div id="service-status-text" style="flex-grow: 1;">Service PepperLife NaoQI : Vérification...</div>
        <button id="restart-service-btn" class="btn btn-ghost" style="padding: 4px 8px; font-size: .8rem;"><i class="bi bi-arrow-clockwise"></i> Relancer</button>
      </div>
  <div class="status-line">
    <div id="status-dot" class="status-dot"></div>
    <div id="status-text" style="flex-grow: 1;">Backend : Vérification...</div>
    <div class="actions">
      <button id="start-btn" class="btn hidden"><span style="font-size: 1.2em;">🧠</span> Démarrer</button>
      <button id="stop-btn" class="btn hidden"><i class="bi bi-stop-circle"></i> Arrêter</button>
    </div>
  </div>
    </div>

    <div class="card robot-info-card">
      <div class="title">Robot</div>
      <div class="content-grid">
        <div class="status-params">
          <div class="status-item"><span class="label">Version</span><span id="info-version" class="value">—</span></div>
          <div class="status-item"><span class="label">NAOqi</span><span id="info-naoqi" class="value">—</span></div>
          <div class="status-item"><span class="label">Batterie</span><span id="info-battery" class="value">—</span></div>
          <div class="status-item"><span class="label">IP</span><span id="info-ip" class="value">—</span></div>
          <div class="status-item"><span class="label">Internet</span><span id="info-internet" class="value">—</span></div>
        </div>
        <div class="status-image">
          <img src="img/pepper.png" alt="Pepper Robot"/>
        </div>
        <div class="power-control">
          <i class="bi bi-power" id="power-icon" title="Alimentation"></i>
          <div class="power-menu" id="power-menu">
            <button id="restart-btn-robot" class="btn btn-warning">Redémarrer</button>
            <button id="shutdown-btn-robot" class="btn btn-danger">Éteindre</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Bottom console dock -->
  <div class="console-dock" id="console-dock">
    <div class="console-header">
      <div class="console-title">
        <span class="dot" id="console-dot"></span>
        <span>Console système</span>
        <span class="badge" id="console-badge">Suivi en direct</span>
      </div>
      <div class="console-actions">
        <button class="btn btn-ghost" id="toggle-dock"><i class="bi bi-arrows-angle-contract"></i><span class="hide-sm"> Replier</span></button>
        <button class="btn btn-ghost" id="toggle-fullscreen"><i class="bi bi-arrows-fullscreen"></i><span class="hide-sm"> Agrandir</span></button>
        <button class="btn btn-ghost" id="pause-stream"><i class="bi bi-pause-fill"></i><span class="hide-sm"> Pause</span></button>
        <button class="btn btn-ghost" id="copy-logs"><i class="bi bi-clipboard"></i><span class="hide-sm"> Copier</span></button>
        <button class="btn btn-ghost" id="clear-logs"><i class="bi bi-trash3"></i><span class="hide-sm"> Vider</span></button>
      </div>
    </div>
    <div class="console-body">
      <div class="console-toolbar">
        <input type="text" id="log-filter" placeholder="Filtrer les logs (regex ou texte)..." />
      </div>
      <pre id="logs-container" class="logs"></pre>
    </div>
  </div>
`;

export function render(root, api) {
  root.innerHTML = template;
  init(api);
}

let statusPoller = null;
let logsPollerDisabled = false;
let lastRenderedLogs = [];
let versionCheckDone = false; // Flag to ensure version check runs only once
let versionStatusText = ''; // Persist version status indicator

function parseVersionString(value) {
  if (!value) return null;
  const cleaned = value.trim().replace(/^v/i, '');
  if (!/^\d+(\.\d+)*$/.test(cleaned)) return null;
  return cleaned.split('.').map(n => parseInt(n, 10) || 0);
}

function compareVersionArrays(a, b) {
  const max = Math.max(a.length, b.length);
  for (let i = 0; i < max; i++) {
    const diff = (a[i] || 0) - (b[i] || 0);
    if (diff !== 0) {
      return diff > 0 ? 1 : -1;
    }
  }
  return 0;
}

function showNavTabs(show) {
  document.querySelectorAll('#nav a').forEach(a => {
    if (a.dataset.page !== '#/') {
      a.style.display = show ? '' : 'none';
    }
  });
}

function updateRobotStatus(status, data = null) {
  const naoqiEl = document.getElementById('info-naoqi');
  const batteryEl = document.getElementById('info-battery');
  const ipEl = document.getElementById('info-ip');
  const internetEl = document.getElementById('info-internet');
  const versionEl = document.getElementById('info-version');

  if (status === 'error' || !data) {
    const errorVal = status === 'error' ? 'Erreur' : '—';
    if (naoqiEl) naoqiEl.textContent = errorVal;
    if (batteryEl) batteryEl.textContent = errorVal;
    if (ipEl) ipEl.textContent = errorVal;
    if (internetEl) internetEl.textContent = errorVal;
    if (versionEl) versionEl.textContent = errorVal;
    return;
  }

  let batteryIcon = 'bi-battery';
  if (data.battery && data.battery.charge > 80) batteryIcon = 'bi-battery-full';
  if (data.battery && data.battery.plugged) batteryIcon += '-charging';

  if (naoqiEl) naoqiEl.textContent = data.naoqi_version || 'N/A';
  if (batteryEl) batteryEl.innerHTML = data.battery ? '<i class="bi ' + batteryIcon + '"></i> ' + (data.battery.charge || 'N/A') + '%' : 'N/A';
  if (ipEl) ipEl.innerHTML = (data.ip_addresses || []).join('<br>') || 'N/A';
  if (internetEl) internetEl.textContent = data.internet_connected ? 'OK' : 'Déconnecté';
  if (versionEl) {
    const localVersion = data.version || 'N/A';
    versionEl.innerHTML = '<div>' + localVersion + '</div>'; // Mettre la version dans un div

    if (versionStatusText) {
      versionEl.innerHTML += versionStatusText;
    }

    // Ensuite, vérifie les mises à jour, mais une seule fois
    if (!versionCheckDone) {
      versionCheckDone = true; // Set flag to true
      fetch('https://raw.githubusercontent.com/moz4r/pepper/refs/heads/main/pepperLife/version')
        .then(response => {
          if (!response.ok) { throw new Error('La réponse du réseau n\'était pas ok'); }
          return response.text();
        })
        .then(text => {
          const remoteVersion = text.trim();
          let statusText = '';
          if (remoteVersion) {
            const remoteParsed = parseVersionString(remoteVersion);
            const localParsed = parseVersionString(localVersion);
            if (remoteParsed && localParsed) {
              const cmp = compareVersionArrays(localParsed, remoteParsed);
              statusText = cmp < 0
                ? '<div class="version-status">(mise à jour disponible)</div>'
                : '<div class="version-status">(à jour)</div>';
            } else if (remoteParsed) {
              statusText = '<div class="version-status">(mise à jour disponible)</div>';
            }
          }
          if (statusText) {
            versionStatusText = statusText;
            versionEl.innerHTML += versionStatusText;
          }
        })
        .catch(err => {
          console.error("La vérification de la version a échoué:", err);
        });
    }
  }
}

async function checkLauncherStatus(api) {
  const pythonRunnerStatus = document.getElementById('python-runner-status');
  const statusDot = document.getElementById('status-dot');
  const statusText = document.getElementById('status-text');
  const serviceStatusDot = document.getElementById('service-status-dot');
  const serviceStatusText = document.getElementById('service-status-text');
  const startBtn = document.getElementById('start-btn');
  const stopBtn = document.getElementById('stop-btn');
  const logsContainer = document.getElementById('logs-container');
  const consoleDot = document.getElementById('console-dot');

  try {
    const status = await launcherApi.getStatus();

    // Statut du lanceur Python 3
    if (status.python_runner_installed) {
      pythonRunnerStatus.innerHTML = '<div class="status-dot" style="background-color: #22c55e;"></div> <div>Lanceur Python 3 : OK</div>';
    } else {
      pythonRunnerStatus.innerHTML = '<div class="status-dot" style="background-color: #ef4444;"></div> <div>Lanceur Python 3 : Manquant</div>';
    }

    // Statut du service NaoQI
    if (status.service_status === "OK") {
      serviceStatusText.textContent = 'Service PepperLife NaoQI : OK';
      serviceStatusDot.className = 'status-dot running';
    } else if (status.service_status === "FAILED") {
      serviceStatusText.textContent = 'Service PepperLife NaoQI : FAILED';
      serviceStatusDot.className = 'status-dot stopped';
    } else {
      serviceStatusText.textContent = 'Service PepperLife NaoQI : Vérification...';
      serviceStatusDot.className = 'status-dot';
    }

    // Statut du backend principal
    if (status.is_running) {
      statusText.textContent = 'Backend : Démarré';
      statusDot.className = 'status-dot running';
      startBtn.classList.add('hidden');
      stopBtn.classList.remove('hidden');
      consoleDot.style.background = '#16a34a';
      showNavTabs(true);

      // Le backend tourne, on peut appeler ses APIs
      api.systemInfo().then(data => updateRobotStatus('ok', data)).catch(() => updateRobotStatus('error'));
    } else {
      statusText.textContent = 'Backend : Arrêté';
      statusDot.className = 'status-dot stopped';
      startBtn.classList.remove('hidden');
      stopBtn.classList.add('hidden');
      consoleDot.style.background = '#ef4444';
      showNavTabs(false);
      updateRobotStatus('off'); // Manually set to "off"
    }

    // Logs (sauf si en pause)
    if (!logsPollerDisabled) {
      const logData = await launcherApi.getLogs();
      lastRenderedLogs = (logData.logs || []).map(sanitizeLogLine);
      renderLogs(logsContainer, lastRenderedLogs);
    }
  } catch (e) {
    statusText.textContent = "Erreur de com. avec le lanceur.";
    statusDot.className = 'status-dot'; // Neutral grey
    pythonRunnerStatus.innerHTML = '<div class="status-dot" style="background-color: #ef4444;"></div> <div>Lanceur : Erreur</div>';
    serviceStatusText.textContent = 'Service PepperLife NaoQI : Erreur';
    updateRobotStatus('off');
    showNavTabs(false);

    // Reset buttons to a neutral, non-spinning state
    if (startBtn) {
        startBtn.classList.remove('hidden');
        startBtn.disabled = false;
        startBtn.innerHTML = '<span style="font-size: 1.2em;">🧠</span> Démarrer';
    }
    if (stopBtn) {
        stopBtn.classList.add('hidden');
        stopBtn.disabled = false;
        stopBtn.innerHTML = '<i class="bi bi-stop-circle"></i> Arrêter';
    }
  }
}

/* --- Sanitizer pour interpréter un HTML limité dans les logs --- */
const ALLOWED_TAGS = new Set(['span','b','strong','i','em','u','code','pre','mark','small','br','a']);
function sanitizeAllowedHtml(html){
  // Parser DOM pour filtrer
  const template = document.createElement('template');
  template.innerHTML = html;
  const walk = (node) => {
    const children = Array.from(node.childNodes);
    for (const child of children) {
      if (child.nodeType === Node.ELEMENT_NODE) {
        const tag = child.tagName.toLowerCase();
        if (!ALLOWED_TAGS.has(tag)) {
          // Remplacer l'élément par son texte
          const text = document.createTextNode(child.textContent || '');
          node.replaceChild(text, child);
          continue;
        }
        // Gérer attributs autorisés
        // - span style: autoriser uniquement color
        // - a href: http(s)/mailto, rel noopener, target _blank
        for (const attr of Array.from(child.attributes)) {
          const an = attr.name.toLowerCase();
          const av = attr.value;
          if (tag === 'span' && an === 'style') {
            // garder uniquement color: <valeur>
            const m = /color\s*:\s*([^;]+)\s*;?/i.exec(av);
            const colorVal = m ? m[1].trim() : null;
            if (colorVal && /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(colorVal) ||
                /^rgb(a)?\(/i.test(colorVal) ||
                /^hsl(a)?\(/i.test(colorVal) ||
                /^[a-z]+$/i.test(colorVal)) {
              child.setAttribute('style', 'color:' + colorVal);
            } else {
              child.removeAttribute('style');
            }
          } else if (tag === 'a' && an === 'href') {
            if (!/^(https?:|mailto:)/i.test(av)) {
              child.removeAttribute('href');
            } else {
              child.setAttribute('rel','noopener noreferrer');
              child.setAttribute('target','_blank');
            }
          } else if (!(tag === 'a' && an === 'href')) {
            // supprimer tout autre attribut
            child.removeAttribute(an);
          }
        }
        walk(child);
      } else if (child.nodeType === Node.COMMENT_NODE) {
        node.removeChild(child);
      }
    }
  };
  walk(template.content);
  return template.innerHTML;
}

function sanitizeLogLine(raw){
  if (!raw) return '';
  // Normaliser CRLF / CR -> LF, enlever NUL
  let s = String(raw).replace(/\r\n?/g, '\n').replace(/\u0000/g,'');
  return s;
}

function highlightLog(line){
  // Interprète un HTML "safe" d'abord
  let safe = sanitizeAllowedHtml(line);
  // Ajoute coloration simple: timestamps et niveaux
  safe = safe
    .replace(/\b(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d{3})?(?:Z|[+\-]\d{2}:\d{2})?)\b/g,'<span class="log-ts">$1</span>')
    .replace(/\b(DEBUG)\b/g,'<span class="log-lvl lvl-debug">$1</span>')
    .replace(/\b(INFO)\b/g,'<span class="log-lvl lvl-info">$1</span>')
    .replace(/\b(WARN|WARNING)\b/g,'<span class="log-lvl lvl-warn">$1</span>')
    .replace(/\b(ERR|ERROR|FATAL)\b/g,'<span class="log-lvl lvl-error">$1</span>');
  return safe;
}

function renderLogs(container, logs){
  const filterEl = document.getElementById('log-filter');
  const filter = filterEl && filterEl.value ? filterEl.value.trim() : '';
  let view = logs;
  if (filter) {
    try{
      const rx = new RegExp(filter, 'i');
      view = logs.filter(l => rx.test(l));
    }catch{
      view = logs.filter(l => l.toLowerCase().includes(filter.toLowerCase()));
    }
  }
  // Réduction des multiples lignes vides
  const normalized = view.join('\n').replace(/\n{3,}/g, '\n\n');
  const html = normalized.split('\n').map(highlightLog).join('\n');
  container.innerHTML = html;
  container.scrollTop = container.scrollHeight;
}

function pollUntilReady(api, initialLogCount = 0) {
  const poller = setInterval(async () => {
    try {
      const status = await launcherApi.getStatus();
      const logData = await launcherApi.getLogs();
      const newLogs = (logData.logs || []).slice(initialLogCount).map(sanitizeLogLine);
      
      const isErrorLog = newLogs.some(log => log.includes("--- Script terminé (code: 1) ---"));
      
      if (isErrorLog) {
        clearInterval(poller);
        const startBtn = document.getElementById('start-btn');
        if (startBtn) {
          startBtn.innerHTML = '<span style="font-size: 1.2em;">🧠</span> Démarrer';
          startBtn.disabled = false;
        }
        await checkLauncherStatus(api);
        return;
      }

      if (status.is_running) {
        const isReadyLog = newLogs.some(log => log.includes("Je suis prêt") || log.includes("Je suis réveillé"));
        
        if (isReadyLog) {
          clearInterval(poller);
          // Log message found, now poll the actual service to ensure it's up
          let serviceReady = false;
          const servicePoller = setInterval(async () => {
            try {
              await api.systemInfo();
              serviceReady = true;
              clearInterval(servicePoller);
              await checkLauncherStatus(api);
              const startBtn = document.getElementById('start-btn');
              startBtn.innerHTML = '<span style="font-size: 1.2em;">🧠</span> Démarrer';
              startBtn.disabled = false;
            } catch (e) {
              console.warn("Backend log ready, but service not yet available. Retrying...");
            }
          }, 500);
          // Timeout for service poller
          setTimeout(() => {
            if (!serviceReady) {
              clearInterval(servicePoller);
              checkLauncherStatus(api); // Reset UI
            }
          }, 15000);
        }
      } else {
        clearInterval(poller);
        const startBtn = document.getElementById('start-btn');
        if (startBtn) {
          startBtn.innerHTML = '<span style="font-size: 1.2em;">🧠</span> Démarrer';
          startBtn.disabled = false;
        }
        await checkLauncherStatus(api);
      }
    } catch (e) {
      console.warn("Polling for ready status failed, will retry...");
    }
  }, 1000);

  setTimeout(() => {
    clearInterval(poller);
    const startBtn = document.getElementById('start-btn');
    if (startBtn && startBtn.disabled) {
      checkLauncherStatus(api);
    }
  }, 30000);
}

function pollUntilStopped(api) {
  const poller = setInterval(async () => {
    await checkLauncherStatus(api);
    const stopBtn = document.getElementById('stop-btn');
    if (!stopBtn || stopBtn.classList.contains('hidden')) {
      clearInterval(poller);
      if (stopBtn) {
        stopBtn.innerHTML = '<i class="bi bi-stop-circle"></i> Arrêter';
        stopBtn.disabled = false;
      }
    }
  }, 500);
  setTimeout(() => clearInterval(poller), 30000);
}

export function init(api) {
  const startBtn = document.getElementById('start-btn');
  const stopBtn = document.getElementById('stop-btn');
  const restartServiceBtn = document.getElementById('restart-service-btn');
  const logsContainer = document.getElementById('logs-container');
  const powerIcon = document.getElementById('power-icon');
  const powerMenu = document.getElementById('power-menu');
  const restartBtn = document.getElementById('restart-btn-robot');
  const shutdownBtn = document.getElementById('shutdown-btn-robot');

  const dock = document.getElementById('console-dock');
  const dockToggle = document.getElementById('toggle-dock');
  const fullscreenBtn = document.getElementById('toggle-fullscreen');
  const pauseBtn = document.getElementById('pause-stream');
  const copyBtn = document.getElementById('copy-logs');
  const clearBtn = document.getElementById('clear-logs');
  const filterInput = document.getElementById('log-filter');
  const badge = document.getElementById('console-badge');

  // Interactions - dock
  dockToggle.addEventListener('click', () => {
    dock.classList.toggle('is-collapsed');
    dockToggle.innerHTML = dock.classList.contains('is-collapsed')
      ? '<i class="bi bi-arrows-angle-expand"></i><span class="hide-sm"> Déployer</span>'
      : '<i class="bi bi-arrows-angle-contract"></i><span class="hide-sm"> Replier</span>';
  });

  fullscreenBtn.addEventListener('click', () => {
    dock.classList.toggle('is-fullscreen');
    fullscreenBtn.innerHTML = dock.classList.contains('is-fullscreen')
      ? '<i class="bi bi-fullscreen-exit"></i><span class="hide-sm"> Réduire</span>'
      : '<i class="bi bi-arrows-fullscreen"></i><span class="hide-sm"> Agrandir</span>';
  });

  pauseBtn.addEventListener('click', () => {
    logsPollerDisabled = !logsPollerDisabled;
    pauseBtn.innerHTML = logsPollerDisabled
      ? '<i class="bi bi-play-fill"></i><span class="hide-sm"> Reprendre</span>'
      : '<i class="bi bi-pause-fill"></i><span class="hide-sm"> Pause</span>';
    badge.textContent = logsPollerDisabled ? 'En pause' : 'Suivi en direct';
    if (!logsPollerDisabled) { renderLogs(logsContainer, lastRenderedLogs); }
  });

  clearBtn.addEventListener('click', () => {
    lastRenderedLogs = [];
    renderLogs(logsContainer, lastRenderedLogs);
    api.clearSystemLogs().catch(err => console.error("Failed to clear system logs:", err));
  });

  copyBtn.addEventListener('click', () => {
    const textToCopy = logsContainer.textContent || '';
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(textToCopy).then(() => {
        copyBtn.innerHTML = '<i class="bi bi-clipboard-check"></i><span class="hide-sm"> Copié</span>';
        setTimeout(() => copyBtn.innerHTML = '<i class="bi bi-clipboard"></i><span class="hide-sm"> Copier</span>', 1200);
      }).catch(() => {
        alert('Impossible de copier dans le presse-papiers.');
      });
    } else {
      const textArea = document.createElement("textarea");
      textArea.value = textToCopy;
      textArea.style.position = "fixed";
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      try {
        document.execCommand('copy');
        copyBtn.innerHTML = '<i class="bi bi-clipboard-check"></i><span class="hide-sm"> Copié</span>';
        setTimeout(() => copyBtn.innerHTML = '<i class="bi bi-clipboard"></i><span class="hide-sm"> Copier</span>', 1200);
      } catch (err) {
        alert('Impossible de copier dans le presse-papiers.');
      }
      document.body.removeChild(textArea);
    }
  });

  filterInput.addEventListener('input', () => renderLogs(logsContainer, lastRenderedLogs));

  // Wire Start/Stop
  if (startBtn) {
    startBtn.addEventListener('click', async () => {
      try {
        startBtn.disabled = true;
        startBtn.innerHTML = '<span class="spinner" aria-hidden="true"></span> Démarrage...';
        // Mémoriser nombre initial de logs pour détecter "Je suis prêt"
        const initial = await launcherApi.getLogs().catch(() => ({logs: []}));
        const initialCount = (initial.logs || []).length;
        await launcherApi.start();
        pollUntilReady(api, initialCount);
      } catch (e) {
        startBtn.disabled = false;
        startBtn.innerHTML = '<span style="font-size: 1.2em;">🧠</span> Démarrer';
        alert("Impossible de démarrer le backend.");
      }
    });
  }

  if (stopBtn) {
    stopBtn.addEventListener('click', async () => {
      try {
        stopBtn.disabled = true;
        stopBtn.innerHTML = '<span class="spinner" aria-hidden="true"></span> Arrêt...';
        await launcherApi.stop();
        pollUntilStopped(api);
      } catch (e) {
        stopBtn.disabled = false;
        stopBtn.innerHTML = '<i class="bi bi-stop-circle"></i> Arrêter';
        alert("Impossible d'arrêter le backend.");
      }
    });
  }

  if (restartServiceBtn) {
    restartServiceBtn.addEventListener('click', async () => {
      try {
        restartServiceBtn.disabled = true;
        restartServiceBtn.innerHTML = '<span class="spinner" aria-hidden="true"></span> Relance...';
        await launcherApi.restartService();
        // Attendre un peu avant de réactiver le bouton et de rafraîchir le statut
        setTimeout(() => {
          restartServiceBtn.disabled = false;
          restartServiceBtn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Relancer';
          checkLauncherStatus(api);
        }, 4000); // 4s pour laisser le temps au service de redémarrer
      } catch (e) {
        restartServiceBtn.disabled = false;
        restartServiceBtn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Relancer';
        alert("Impossible de redémarrer le service.");
      }
    });
  }

  // Power menu
  powerIcon.addEventListener('click', () => {
    powerMenu.style.display = powerMenu.style.display === 'block' ? 'none' : 'block';
  });

  restartBtn.addEventListener('click', () => {
    if (confirm('Êtes-vous sûr de vouloir redémarrer le robot ?')) {
      api.restartRobot().then(() => alert('Le robot va redémarrer.')).catch(err => alert('Erreur lors du redémarrage: ' + err.message));
    }
    powerMenu.style.display = 'none';
  });

  shutdownBtn.addEventListener('click', () => {
    if (confirm('Êtes-vous sûr de vouloir éteindre le robot ?')) {
      api.shutdownRobot().then(() => alert("Le robot va s'éteindre.")).catch(err => alert("Erreur lors de l'extinction: " + err.message));
    }
    powerMenu.style.display = 'none';
  });

  // Vérification initiale + polling
  checkLauncherStatus(api);
  statusPoller = setInterval(() => checkLauncherStatus(api), 5000);
}

export function cleanup() {
  if (statusPoller) clearInterval(statusPoller);
}
