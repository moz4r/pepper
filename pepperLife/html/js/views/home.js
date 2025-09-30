// API pour le lanceur lui-même (servi sur le même port que la page, 8080)
const launcherApi = {
  getStatus: () => fetch('/api/launcher/status').then(r => r.json()),
  start: () => fetch('/api/launcher/start', { method: 'POST' }).then(r => r.json()),
  stop: () => fetch('/api/launcher/stop', { method: 'POST' }).then(r => r.json()),
  getLogs: () => fetch('/api/launcher/logs').then(r => r.json()),
};

const template = `
  <style>
    .home-grid { display: grid; grid-template-columns: 1.5fr 1fr; gap: 16px; }
    
    /* Styles for backend manager card */
    .backend-manager .status-line { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
    .backend-manager .status-dot { width: 16px; height: 16px; border-radius: 50%; background-color: #ccc; }
    .backend-manager .status-dot.running { background-color: #4caf50; }
    .backend-manager .status-dot.stopped { background-color: #f44336; }
    .backend-manager .actions { display: flex; gap: 8px; margin-bottom: 16px; }
    .backend-manager .logs { background: #1e1e1e; color: #d4d4d4; font-family: monospace; height: 300px; overflow-y: scroll; padding: 12px; border-radius: 4px; white-space: pre-wrap; }
    .hidden { display: none; }
    .python-status { font-size: 0.9em; opacity: 0.8; }

    /* New Styles for robot info card */
    .robot-info-card .content-grid {
        display: grid;
        grid-template-columns: 1fr auto auto;
        align-items: center;
        gap: 0.2rem;
    }
    .robot-info-card .status-params {
        display: flex;
        flex-direction: column;
        gap: 0.2rem;
    }
    .robot-info-card .status-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.15rem 0.3rem;
        background: #f9f9f9;
        border-radius: 8px;
        border: 1px solid #eee;
    }
    .robot-info-card .status-item .label { font-weight: bold; color: #555; font-size: 0.9em; }
    .robot-info-card .status-item .value { color: #333; text-align: right; font-size: 0.9em; }
    .robot-info-card .status-item .value .bi { vertical-align: -0.125em; }
    .robot-info-card .status-image {
        padding-left: 1rem;
        border-left: 1px solid #eee;
    }
    .robot-info-card .status-image img {
        max-height: 150px;
    }
    .power-control {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    #power-icon {
        font-size: 2rem;
        cursor: pointer;
        padding: 10px;
    }

    .power-menu {
        display: none;
        position: absolute;
        top: 100%;
        right: 0;
        background-color: #fff;
        border: 1px solid #ccc;
        border-radius: 5px;
        padding: 10px;
        z-index: 100;
    }

    .power-menu button {
        display: block;
        width: 100%;
        margin-bottom: 5px;
    }
  </style>

  <div class="home-grid">
    
    <div class="card backend-manager">
      <div class="title">Service pepperLife</div>
      <div id="python-runner-status" class="status-line python-status" style="margin-bottom: 8px; margin-top: -8px;"></div>
      <div class="status-line">
        <div id="status-dot" class="status-dot"></div>
        <div id="status-text">Vérification...</div>
      </div>
      <div class="actions">
        <button id="start-btn" class="btn hidden">Démarrer</button>
        <button id="stop-btn" class="btn hidden">Arrêter</button>
      </div>
      <div id="error-log" class="hidden" style="color: red; margin-top: 10px;"></div>
      <pre id="logs-container" class="logs hidden"></pre>
    </div>

    <div class="card robot-info-card">
        <div class="content-grid">
            <div class="status-params">
                <div class="status-item"><span class="label">Version</span><span id="info-version" class="value">...</span></div>
                <div class="status-item"><span class="label">NAOqi</span><span id="info-naoqi" class="value">...</span></div>
                <div class="status-item"><span class="label">Batterie</span><span id="info-battery" class="value">...</span></div>
                <div class="status-item"><span class="label">Adresse IP</span><span id="info-ip" class="value">...</span></div>
                <div class="status-item"><span class="label">Internet</span><span id="info-internet" class="value">...</span></div>
            </div>
            <div class="status-image">
                <img src="img/pepper.png" alt="Pepper Robot"/>
            </div>
            <div class="power-control">
                <i class="bi bi-power" id="power-icon"></i>
                <div class="power-menu" id="power-menu">
                    <button id="restart-btn-robot" class="btn btn-warning">Redémarrer</button>
                    <button id="shutdown-btn-robot" class="btn btn-danger">Éteindre</button>
                </div>
            </div>
        </div>
    </div>

  </div>
`;

export function render(root, api) {
  root.innerHTML = template;
  init(api);
}

let statusPoller = null;

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
        const errorVal = status === 'error' ? 'Erreur' : 'Backend off';
        if (naoqiEl) naoqiEl.textContent = errorVal;
        if (batteryEl) batteryEl.textContent = errorVal;
        if (ipEl) ipEl.textContent = errorVal;
        if (internetEl) internetEl.textContent = errorVal;
        if (versionEl) versionEl.textContent = errorVal;
        return;
    }

    let batteryIcon = 'bi-battery';
    if (data.battery.charge > 80) batteryIcon = 'bi-battery-full';
    if (data.battery.plugged) batteryIcon += '-charging';

    if (naoqiEl) naoqiEl.textContent = data.naoqi_version || 'N/A';
    if (batteryEl) batteryEl.innerHTML = `<i class="bi ${batteryIcon}"></i> ${data.battery.charge || 'N/A'}%`;
    if (ipEl) ipEl.innerHTML = (data.ip_addresses || []).join('<br>') || 'N/A';
    if (internetEl) internetEl.textContent = data.internet_connected ? 'Connecté' : 'Déconnecté';
    if (versionEl) versionEl.textContent = data.version || 'N/A';
}

async function checkLauncherStatus(api) {
  const pythonRunnerStatus = document.getElementById('python-runner-status');
  const statusDot = document.getElementById('status-dot');
  const statusText = document.getElementById('status-text');
  const startBtn = document.getElementById('start-btn');
  const stopBtn = document.getElementById('stop-btn');
  const logsContainer = document.getElementById('logs-container');

  try {
    const status = await launcherApi.getStatus();

    if (status.python_runner_installed) {
      pythonRunnerStatus.innerHTML = `<div class="status-dot" style="background-color: #4caf50;"></div> <div>Lanceur Python 3 : Trouvé</div>`;
    } else {
      pythonRunnerStatus.innerHTML = `<div class="status-dot" style="background-color: #f44336;"></div> <div>Lanceur Python 3 : Manquant</div>`;
    }

    if (status.is_running) {
      statusText.textContent = 'Backend démarré.';
      statusDot.className = 'status-dot running';
      startBtn.classList.add('hidden');
      stopBtn.classList.remove('hidden');
      logsContainer.classList.remove('hidden');
      showNavTabs(true);
      
      const logData = await launcherApi.getLogs();
      logsContainer.innerHTML = logData.logs.join('<br>');
      logsContainer.scrollTop = logsContainer.scrollHeight;

      // Backend is running, so now we can poll its APIs
      api.systemInfo().then(data => updateRobotStatus('ok', data)).catch(() => updateRobotStatus('error'));

    } else {
      statusText.textContent = 'Backend arrêté.';
      statusDot.className = 'status-dot stopped';
      startBtn.classList.remove('hidden');
      stopBtn.classList.add('hidden');
      logsContainer.classList.add('hidden');
      showNavTabs(false);
      updateRobotStatus('off'); // Manually set to "Backend off"
    }
  } catch (e) {
    statusText.textContent = "Erreur de com. avec le lanceur.";
    pythonRunnerStatus.innerHTML = `<div class="status-dot" style="background-color: #f44336;"></div> <div>Lanceur : Erreur</div>`;
    updateRobotStatus('off');
  }
}

export function init(api) {
  const startBtn = document.getElementById('start-btn');
  const stopBtn = document.getElementById('stop-btn');
  const powerIcon = document.getElementById('power-icon');
  const powerMenu = document.getElementById('power-menu');
  const restartBtn = document.getElementById('restart-btn-robot');
  const shutdownBtn = document.getElementById('shutdown-btn-robot');

  startBtn.addEventListener('click', async () => {
    document.getElementById('status-text').textContent = 'Démarrage en cours...';
    await launcherApi.start();
    setTimeout(() => checkLauncherStatus(api), 1500);
  });

  stopBtn.addEventListener('click', async () => {
    document.getElementById('status-text').textContent = 'Arrêt en cours...';
    await launcherApi.stop();
    setTimeout(() => checkLauncherStatus(api), 1500);
  });

  powerIcon.addEventListener('click', () => {
    if (powerMenu.style.display === 'block') {
        powerMenu.style.display = 'none';
    } else {
        powerMenu.style.display = 'block';
    }
  });

  restartBtn.addEventListener('click', () => {
    if (confirm('Êtes-vous sûr de vouloir redémarrer le robot ?')) {
        api.restartRobot().then(() => {
            alert('Le robot va redémarrer.');
        }).catch(err => {
            alert('Erreur lors du redémarrage: ' + err.message);
        });
    }
    powerMenu.style.display = 'none';
  });

  shutdownBtn.addEventListener('click', () => {
    if (confirm('Êtes-vous sûr de vouloir éteindre le robot ?')) {
        api.shutdownRobot().then(() => {
            alert('Le robot va s\'éteindre.');
        }).catch(err => {
            alert('Erreur lors de l\'extinction: ' + err.message);
        });
    }
    powerMenu.style.display = 'none';
  });

  // Lancer la vérification initiale
  checkLauncherStatus(api);
  
  // Polling pour le statut
  statusPoller = setInterval(() => checkLauncherStatus(api), 5000);
}

export function cleanup() {
  if (statusPoller) clearInterval(statusPoller);
}
