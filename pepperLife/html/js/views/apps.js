import {api} from '../api.js';

const choreoFallbackApi = (() => {
  const hostname = window.location.hostname;
  const base =
    hostname === '127.0.0.1' || hostname === 'localhost'
      ? 'http://198.18.0.1:8088'
      : `http://${hostname}:8088`;

  async function jget(path) {
    const resp = await fetch(base + path, { cache: 'no-store' });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(text || `HTTP error ${resp.status}`);
    }
    return resp.json();
  }

  async function jpost(path, payload) {
    const resp = await fetch(base + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {})
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(text || `HTTP error ${resp.status}`);
    }
    const contentType = resp.headers.get('content-type') || '';
    if (contentType.indexOf('application/json') !== -1) {
      return resp.json();
    }
    return { text: await resp.text() };
  }

  return {
    choreoState: () => jget('/api/choreo/state'),
    choreoAddProgram: (payload) => jpost('/api/choreo/programs/add', payload),
    choreoRemoveProgram: (payload) => jpost('/api/choreo/programs/remove', payload),
    choreoSelectRobots: (payload) => jpost('/api/choreo/robots/select', payload),
    choreoStart: (payload) => jpost('/api/choreo/start', payload),
    choreoConnect: () => jpost('/api/choreo/connect', {}),
    choreoDisconnect: () => jpost('/api/choreo/disconnect', {}),
    choreoResetRemote: () => jpost('/api/choreo/reset_remote', {})
  };
})();

function renderState(state) {
    if (!state) return '';
    const cssClass = state === 'running' ? 'ok' : 'off';
    return `<span class="status ${cssClass}">${state}</span>`;
}

function renderRow(app) {
    const isRunning = app.status === 'running';
    const rowClass = isRunning ? 'running-row' : '';

    let buttons = 'Non supporté';
    if (app.runnable) {
        buttons = `
          <button type="button" class="btn" data-action="start" data-name="${app.name}" ${isRunning ? 'disabled' : ''}>Démarrer</button>
          <button type="button" class="btn secondary" data-action="stop" data-name="${app.name}" ${!isRunning ? 'disabled' : ''}>Arrêter</button>
        `;
    }
    return `
      <tr class="${rowClass}">
        <td>${app.name}</td>
        <td><span class="nature-tag">${app.nature || 'N/A'}</span></td>
        <td>${renderState(app.status)}</td>
        <td>${buttons}</td>
      </tr>
    `;
}

class ChoreographyPanel {
  constructor(container, apiClient) {
    this.api = apiClient;
    this.container = container;
    this.visible = false;
    this.programOptions = [];
    this.state = { program_queue: [], robots: [], selected_robot_ids: [] };
    this.pollHandle = null;
    this.isBusy = false;
    this.connectionBusy = false;
    this.latestState = null;
    this.configInputs = {};
    this.configFeedback = null;
    this.autoConnectAttempted = false;
    this.generatedRoomCode = null;
    this._build();
  }

  _build() {
    if (!this.container) return;
    this.container.innerHTML = `
      <div class="choreo-panel card hidden">
        <div class="row" style="align-items:center; gap:12px;">
          <div>
            <h3 style="margin:0;">Chorégraphie multi-robots</h3>
            <p style="margin:4px 0 0; opacity:0.7;">Préparez une file d'applications principales et synchronisez leur lancement.</p>
          </div>
          <span data-role="status" class="status-chip idle" style="margin-left:auto;">Idle</span>
          <button type="button" class="btn ghost" data-role="close">Fermer</button>
        </div>
        <div class="status-grid">
          <div class="status-item">
            <div class="label">Internet</div>
            <div class="value">
              <span class="status-dot off" data-role="net-dot"></span>
              <span data-role="net-label">Inconnu</span>
            </div>
          </div>
          <div class="status-item">
            <div class="label">MQTT</div>
            <div class="value">
              <span class="status-dot off" data-role="mqtt-dot"></span>
              <span data-role="mqtt-label">Déconnecté</span>
            </div>
          </div>
          <div class="status-actions">
            <button type="button" class="btn" data-role="connect">Connexion</button>
            <button type="button" class="btn secondary" data-role="disconnect">Déconnexion</button>
            <button type="button" class="btn ghost" data-role="reset-robots">Vider robots distants</button>
          </div>
        </div>
        <section class="config-card">
          <h4>Configuration MQTT</h4>
          <div class="config-grid">
            <label>
              Serveur
              <input type="text" placeholder="mqtt://hote:port" data-role="cfg-broker" autocomplete="off">
            </label>
            <label>
              Utilisateur
              <input type="text" data-role="cfg-username" autocomplete="off">
            </label>
            <label>
              Mot de passe
              <input type="password" data-role="cfg-password" autocomplete="new-password">
            </label>
            <label class="checkbox">
              <input type="checkbox" data-role="cfg-insecure">
              TLS non vérifié
            </label>
            <label>
              Salon
              <input type="text" data-role="cfg-room" placeholder="pepperparty_xxxxx" autocomplete="off">
            </label>
          </div>
          <div class="config-actions">
            <button type="button" class="btn secondary" data-role="save-config">Sauvegarder la configuration</button>
            <span class="hint" data-role="config-feedback"></span>
          </div>
        </section>
        <div class="panel-footer" style="margin-top:12px;">
          <div class="hint">Les robots connectés via MQTT apparaissent ici automatiquement.</div>
          <div class="error-box" data-role="error"></div>
        </div>
        <div class="choreo-grid">
          <section>
            <h4>Applications sélectionnées</h4>
            <div class="program-picker">
              <select data-role="program-select">
                <option value="">Choisir une application…</option>
              </select>
              <button type="button" class="btn" data-role="add-program">Ajouter</button>
            </div>
            <div class="hint">La file respecte l'ordre d'ajout.</div>
            <table>
              <thead>
                <tr><th>#</th><th>Nom</th><th>Nature</th><th>Ajouté</th><th>Actions</th></tr>
              </thead>
              <tbody data-role="programs-body">
                <tr><td colspan="5">Aucune application dans la file.</td></tr>
              </tbody>
            </table>
          </section>
          <section>
            <h4>Robots prêts</h4>
            <div class="hint">Cochez les robots à synchroniser (le robot local est inclus automatiquement).</div>
            <table>
              <thead>
                <tr><th></th><th>Robot</th><th>Statut</th><th>Identifiant</th></tr>
              </thead>
              <tbody data-role="robots-body">
                <tr><td colspan="4">En attente de présence MQTT…</td></tr>
              </tbody>
            </table>
          </section>
        </div>
        <div class="panel-footer">
          <button type="button" class="btn" data-role="start">Démarrer la chorégraphie</button>
          <span class="hint" data-role="mqtt-info"></span>
        </div>
      </div>
    `;
    this.panel = this.container.querySelector('.choreo-panel');
    this.statusBadge = this.container.querySelector('[data-role="status"]');
    this.programSelect = this.container.querySelector('[data-role="program-select"]');
    this.programTableBody = this.container.querySelector('[data-role="programs-body"]');
    this.robotTableBody = this.container.querySelector('[data-role="robots-body"]');
    this._lastRobotMarkup = '';
    this.addProgramBtn = this.container.querySelector('[data-role="add-program"]');
    this.startButton = this.container.querySelector('[data-role="start"]');
    this.errorBox = this.container.querySelector('[data-role="error"]');
    this.mqttInfo = this.container.querySelector('[data-role="mqtt-info"]');
    this.netStatusDot = this.container.querySelector('[data-role="net-dot"]');
    this.netStatusLabel = this.container.querySelector('[data-role="net-label"]');
    this.mqttStatusDot = this.container.querySelector('[data-role="mqtt-dot"]');
    this.mqttStatusLabel = this.container.querySelector('[data-role="mqtt-label"]');
    this.connectBtn = this.container.querySelector('[data-role="connect"]');
    this.disconnectBtn = this.container.querySelector('[data-role="disconnect"]');
    this.configInputs = {
      broker: this.container.querySelector('[data-role="cfg-broker"]'),
      username: this.container.querySelector('[data-role="cfg-username"]'),
      password: this.container.querySelector('[data-role="cfg-password"]'),
      insecure: this.container.querySelector('[data-role="cfg-insecure"]'),
      room: this.container.querySelector('[data-role="cfg-room"]')
    };
    this.configSaveBtn = this.container.querySelector('[data-role="save-config"]');
    this.configFeedback = this.container.querySelector('[data-role="config-feedback"]');
    this.resetRobotsBtn = this.container.querySelector('[data-role="reset-robots"]');
    const closeBtn = this.container.querySelector('[data-role="close"]');

    if (closeBtn) {
      closeBtn.addEventListener('click', () => this.toggle(false));
    }
    if (this.addProgramBtn) {
      this.addProgramBtn.addEventListener('click', () => this._handleAddProgram());
    }
    if (this.programTableBody) {
      this.programTableBody.addEventListener('click', (event) => {
        const btn = event.target.closest('button[data-program-id]');
        if (!btn) return;
        this._removeProgram(btn.dataset.programId);
      });
    }
    if (this.robotTableBody) {
      this.robotTableBody.addEventListener('change', (event) => {
        const checkbox = event.target.closest('.robot-select');
        if (!checkbox) return;
        const selected = Array.from(this.robotTableBody.querySelectorAll('.robot-select:checked')).map(el => el.dataset.id);
        this._updateRobotSelection(selected);
      });
    }
    if (this.startButton) {
      this.startButton.addEventListener('click', () => this._startChoreo());
    }
    if (this.connectBtn) {
      this.connectBtn.addEventListener('click', () => this._connectBroker());
    }
    if (this.disconnectBtn) {
      this.disconnectBtn.addEventListener('click', () => this._disconnectBroker());
    }
    if (this.configSaveBtn) {
      this.configSaveBtn.addEventListener('click', () => this._saveConfig());
    }
    if (this.resetRobotsBtn) {
      this.resetRobotsBtn.addEventListener('click', () => this._resetRemoteRobots());
    }
    this._syncStartButton();
  }

  _callChoreoApi(method, payload, fallbackPayload) {
    const fbPayload = arguments.length >= 3 ? fallbackPayload : payload;
    if (this.api && typeof this.api[method] === 'function') {
      return this.api[method](payload);
    }
    if (choreoFallbackApi && typeof choreoFallbackApi[method] === 'function') {
      return choreoFallbackApi[method](fbPayload);
    }
    return Promise.reject(new Error("API chorégraphie indisponible sur cette version."));
  }

  toggle(force) {
    if (!this.panel) return;
    if (typeof force === 'boolean') {
      this.visible = force;
    } else {
      this.visible = !this.visible;
    }
    this.panel.classList.toggle('hidden', !this.visible);
    if (this.visible) {
      this.refreshState().then((state) => this._autoConnectIfNeeded(state));
      this._startPolling();
      if (typeof this.panel.scrollIntoView === 'function') {
        this.panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    } else {
      this._stopPolling();
    }
  }

  destroy() {
    this._stopPolling();
  }

  setProgramOptions(programs) {
    if (!Array.isArray(programs) || !this.programSelect) {
      return;
    }
    const seen = new Set();
    this.programOptions = programs
      .filter(item => item && item.name)
      .map(item => ({
        value: item.name,
        label: `[${item.nature || 'app'}] ${item.name}`,
        nature: item.nature || 'interactive',
        source: item.source || 'applications'
      }))
      .filter(option => {
        if (seen.has(option.value)) return false;
        seen.add(option.value);
        return true;
      })
      .sort((a, b) => a.label.localeCompare(b.label));
    const optionsHtml = ['<option value="">Choisir une application…</option>']
      .concat(this.programOptions.map(opt => `<option value="${opt.value}">${opt.label}</option>`))
      .join('');
    this.programSelect.innerHTML = optionsHtml;
  }

  async refreshState() {
    if (!this.visible) {
      return null;
    }
    try {
      const state = await this._callChoreoApi('choreoState');
      this.state = state || {};
      this._renderState();
      this._clearError();
      this.latestState = this.state;
      return this.state;
    } catch (err) {
      this._showError(err);
      this._stopPolling();
      return null;
    }
  }

  _renderState() {
    if (!this.panel) return;
    const status = (this.state.status || 'idle').toLowerCase();
    this.statusBadge.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    this.statusBadge.className = `status-chip ${status}`;
    this._renderPrograms();
    this._renderRobots();
    const mqtt = this.state.mqtt || {};
    this._updateConnectionBadges(this.state);
    this._populateConfigFields(this.state);
    this._syncConnectionButtons(this.state);
    if (this.mqttInfo) {
      if (mqtt.enabled) {
        const broker = mqtt.broker_url || 'non défini';
        const client = mqtt.client_id || 'N/A';
        this.mqttInfo.textContent = `Broker ${broker} • Client ${client}`;
      } else {
        this.mqttInfo.textContent = 'MQTT désactivé dans la configuration.';
      }
    }
    this._syncStartButton();
  }

  _renderPrograms() {
    if (!this.programTableBody) return;
    const queue = this.state.program_queue || [];
    if (!queue.length) {
      this.programTableBody.innerHTML = '<tr><td colspan="5">Aucune application dans la file.</td></tr>';
      return;
    }
    this.programTableBody.innerHTML = queue.map((prog, idx) => {
      const added = prog.added_at ? new Date(prog.added_at * 1000) : null;
      const timeLabel = added ? added.toLocaleTimeString() : '—';
      return `
        <tr>
          <td>${idx + 1}</td>
          <td>${prog.name}</td>
          <td><span class="nature-tag">${prog.nature || 'N/A'}</span></td>
          <td>${timeLabel}</td>
          <td>
            <button class="btn secondary" data-program-id="${prog.id}">Retirer</button>
          </td>
        </tr>
      `;
    }).join('');
  }

  _renderRobots() {
    if (!this.robotTableBody) return;
    const robots = (this.state.robots || []).slice().sort((a, b) => {
      if (a.is_self && !b.is_self) return -1;
      if (!a.is_self && b.is_self) return 1;
      return (a.display_name || a.name || '').localeCompare(b.display_name || b.name || '');
    });
    if (!robots.length) {
      const emptyMarkup = '<tr><td colspan="4">Aucun robot connecté.</td></tr>';
      if (this._lastRobotMarkup !== emptyMarkup) {
        this.robotTableBody.innerHTML = emptyMarkup;
        this._lastRobotMarkup = emptyMarkup;
      }
      return;
    }
    const selected = new Set(this.state.selected_robot_ids || []);
    const nextMarkup = robots.map(robot => {
      const alive = robot.alive !== false;
      const checkboxAttrs = [
        'type="checkbox"',
        'class="robot-select"',
        `data-id="${robot.id}"`
      ];
      if (selected.has(robot.id) || robot.is_self) {
        checkboxAttrs.push('checked');
      }
      if (robot.is_self) {
        checkboxAttrs.push('disabled');
      }
      const displayName = robot.display_name || robot.name || robot.id;
      const nameMarkup = robot.is_self ? `<strong>${displayName}</strong>` : displayName;
      const serial = robot.serial || (robot.meta && robot.meta.serial);
      const robotType = (robot.meta && robot.meta.type) || '';
      let identifier = '';
      if (robot.is_self) {
        identifier = serial || robot.id || '-';
      } else if (robotType && serial) {
        identifier = `${robotType} — ${serial}`;
      } else if (serial) {
        identifier = serial;
      } else if (robotType) {
        identifier = robotType;
      } else {
        identifier = '-';
      }
      return `
        <tr>
          <td><input ${checkboxAttrs.join(' ')}></td>
          <td>${nameMarkup}</td>
          <td><span class="robot-dot ${alive ? 'ok' : 'off'}"></span>${robot.status || (alive ? 'ready' : 'offline')}</td>
          <td>${identifier}</td>
        </tr>
      `;
    }).join('');
    if (this._lastRobotMarkup === nextMarkup) {
      return;
    }
    this._lastRobotMarkup = nextMarkup;
    this.robotTableBody.innerHTML = nextMarkup;
  }

  async _handleAddProgram() {
    if (this.isBusy || !this.programSelect) return;
    const selectedValue = this.programSelect.value;
    if (!selectedValue) return;
    const meta = this.programOptions.find(item => item.value === selectedValue);
    try {
      this._setBusy(true);
      await this._callChoreoApi('choreoAddProgram', {
        name: selectedValue,
        nature: (meta && meta.nature) || 'interactive',
        source: (meta && meta.source) || 'applications'
      });
      await this.refreshState();
    } catch (err) {
      this._showError(err);
    } finally {
      this._setBusy(false);
    }
  }

  async _removeProgram(programId) {
    if (!programId || this.isBusy) return;
    try {
      this._setBusy(true);
      await this._callChoreoApi('choreoRemoveProgram', programId, { program_id: programId });
      await this.refreshState();
    } catch (err) {
      this._showError(err);
    } finally {
      this._setBusy(false);
    }
  }

  async _updateRobotSelection(robotIds) {
    try {
      await this._callChoreoApi('choreoSelectRobots', robotIds, { robot_ids: robotIds });
      this.state.selected_robot_ids = robotIds;
      this._syncStartButton();
    } catch (err) {
      this._showError(err);
    }
  }

  async _startChoreo() {
    if (this.isBusy || !this._canStart()) return;
    try {
      this._setBusy(true);
      const metadata = {
        requested_by: 'tablet-ui',
        requested_at: Date.now()
      };
      await this._callChoreoApi('choreoStart', metadata, { metadata });
      await this.refreshState();
    } catch (err) {
      this._showError(err);
    } finally {
      this._setBusy(false);
    }
  }

  _canStart() {
    const queueHasItems = (this.state.program_queue || []).length > 0;
    const selectedCount = (this.state.selected_robot_ids || []).length;
    return queueHasItems && selectedCount > 0;
  }

  _syncStartButton() {
    if (!this.startButton) return;
    this.startButton.disabled = !this._canStart() || this.isBusy;
  }

  _syncConnectionButtons(state) {
    if (!this.connectBtn || !this.disconnectBtn) return;
    const mqttState = state && state.mqtt ? state.mqtt : {};
    const wantsConnection = !!mqttState.should_run;
    const isConnected = !!mqttState.connected;
    this.connectBtn.disabled = this.connectionBusy || wantsConnection;
    this.disconnectBtn.disabled = this.connectionBusy || (!wantsConnection && !isConnected);
  }

  _updateConnectionBadges(state) {
    const networkOnline = state && state.network && state.network.online;
    this._applyStatusBadge(
      this.netStatusDot,
      this.netStatusLabel,
      networkOnline === null ? 'pending' : networkOnline ? 'ok' : 'off',
      networkOnline === null ? 'Inconnu' : networkOnline ? 'Connecté' : 'Hors-ligne'
    );
    const mqttState = state && state.mqtt ? state.mqtt : {};
    let badgeClass = 'off';
    let text = 'Déconnecté';
    if (mqttState.connected) {
      badgeClass = 'ok';
      text = 'Connecté';
    } else if (mqttState.should_run) {
      badgeClass = 'pending';
      text = 'Connexion…';
    }
    this._applyStatusBadge(this.mqttStatusDot, this.mqttStatusLabel, badgeClass, text);
  }

  _applyStatusBadge(dotEl, labelEl, statusClass, text) {
    if (!dotEl || !labelEl) return;
    dotEl.classList.remove('ok', 'off', 'pending');
    dotEl.classList.add(statusClass || 'off');
    labelEl.textContent = text || '';
  }

  _populateConfigFields(state) {
    const cfg = (state && state.mqtt && state.mqtt.config) || {};
    const roomCode = this._ensureRoomCode(cfg.room_code || '');
    this._setInputValue(this.configInputs.broker, cfg.broker_url || '');
    this._setInputValue(this.configInputs.username, cfg.username || '');
    if (this.configInputs.insecure) {
      this.configInputs.insecure.checked = !!cfg.allow_insecure_tls;
    }
    this._setInputValue(this.configInputs.room, roomCode);
  }

  _setInputValue(input, value) {
    if (!input) return;
    if (document.activeElement === input) return;
    input.value = value == null ? '' : value;
  }

  _setConnectionBusy(flag) {
    this.connectionBusy = !!flag;
    if (this.latestState) {
      this._syncConnectionButtons(this.latestState);
    }
  }

  _autoConnectIfNeeded(state) {
    if (this.autoConnectAttempted) {
      return;
    }
    const mqttState = state && state.mqtt;
    if (mqttState && mqttState.should_run) {
      this.autoConnectAttempted = true;
      return;
    }
    this.autoConnectAttempted = true;
    this._connectBroker();
  }

  _ensureRoomCode(preferred) {
    if (this.configInputs.room) {
      const manual = (this.configInputs.room.value || '').trim();
      if (manual) {
        return manual;
      }
    }
    let current = (preferred || '').trim();
    if (!current && this.generatedRoomCode) {
      current = this.generatedRoomCode;
    }
    if (!current) {
      current = `pepperparty_${Math.random().toString(36).replace(/[^a-z0-9]/gi, '').slice(0, 5) || '00000'}`;
      this.generatedRoomCode = current;
    }
    if (this.configInputs.room && document.activeElement !== this.configInputs.room) {
      this.configInputs.room.value = current;
    }
    return current;
  }

  _getRoomCodeInput() {
    if (!this.configInputs.room) return '';
    return this.configInputs.room.value.trim();
  }

  async _persistRoomCodeIfNeeded(roomCode) {
    if (!roomCode || !this.api || typeof this.api.configSetUser !== 'function') {
      return;
    }
    const current = this.latestState && this.latestState.mqtt && this.latestState.mqtt.config && this.latestState.mqtt.config.room_code;
    if (current && current === roomCode) {
      return;
    }
    try {
      await this.api.configSetUser({ mqtt: { room_code: roomCode } });
      if (this.configInputs.password) {
        this.configInputs.password.value = '';
      }
    } catch (err) {
      this._showError(err);
    }
  }

  async _connectBroker() {
    if (this.connectionBusy) return;
    this._setConnectionBusy(true);
    try {
      const roomCode = this._ensureRoomCode(this.latestState && this.latestState.mqtt && this.latestState.mqtt.config && this.latestState.mqtt.config.room_code);
      await this._persistRoomCodeIfNeeded(roomCode);
      await this._callChoreoApi('choreoConnect');
      await this.refreshState();
    } catch (err) {
      this._showError(err);
    } finally {
      this._setConnectionBusy(false);
    }
  }

  async _disconnectBroker() {
    if (this.connectionBusy) return;
    this._setConnectionBusy(true);
    try {
      await this._callChoreoApi('choreoDisconnect');
      await this.refreshState();
    } catch (err) {
      this._showError(err);
    } finally {
      this._setConnectionBusy(false);
    }
  }

  async _saveConfig() {
    if (!this.api || typeof this.api.configSetUser !== 'function') {
      this._setConfigFeedback("API configSetUser indisponible.", false);
      return;
    }
    const roomCode = this._ensureRoomCode(this.latestState && this.latestState.mqtt && this.latestState.mqtt.config && this.latestState.mqtt.config.room_code);
    const patch = {
      mqtt: {
        broker_url: (this.configInputs.broker && this.configInputs.broker.value || '').trim(),
        username: (this.configInputs.username && this.configInputs.username.value || '').trim(),
        allow_insecure_tls: this.configInputs.insecure ? !!this.configInputs.insecure.checked : false,
        room_code: roomCode
      }
    };
    const passwordValue = this.configInputs.password ? this.configInputs.password.value : '';
    if (passwordValue) {
      patch.mqtt.password = passwordValue;
    }
    this._setConfigFeedback('Sauvegarde...', true);
    if (this.configSaveBtn) this.configSaveBtn.disabled = true;
    try {
      await this.api.configSetUser(patch);
      if (this.configInputs.password) {
        this.configInputs.password.value = '';
      }
      this._setConfigFeedback('Configuration enregistrée.', true);
      await this.refreshState();
      setTimeout(() => this._setConfigFeedback('', true), 2000);
    } catch (err) {
      this._setConfigFeedback(err && err.message ? err.message : 'Erreur de sauvegarde.', false);
    } finally {
      if (this.configSaveBtn) this.configSaveBtn.disabled = false;
    }
  }

  _setConfigFeedback(message, success) {
    if (!this.configFeedback) return;
    this.configFeedback.textContent = message || '';
    this.configFeedback.classList.remove('success', 'error');
    if (!message) return;
    this.configFeedback.classList.add(success ? 'success' : 'error');
  }

  _setBusy(flag) {
    this.isBusy = !!flag;
    if (this.addProgramBtn) this.addProgramBtn.disabled = this.isBusy;
    this._syncStartButton();
    if (this.latestState) {
      this._syncConnectionButtons(this.latestState);
    }
  }

  async _resetRemoteRobots() {
    if (!window.confirm("Effacer la liste des robots distants ?")) {
      return;
    }
    try {
      await this._callChoreoApi('choreoResetRemote');
      await this.refreshState();
    } catch (err) {
      this._showError(err);
    }
  }

  _showError(err) {
    if (!this.errorBox) return;
    const message = (err && err.message) || err || 'Erreur inattendue.';
    this.errorBox.textContent = message;
  }

  _clearError() {
    if (this.errorBox) {
      this.errorBox.textContent = '';
    }
  }

  _startPolling() {
    if (this.pollHandle) return;
    this.pollHandle = setInterval(() => this.refreshState(), 5000);
  }

  _stopPolling() {
    if (this.pollHandle) {
      clearInterval(this.pollHandle);
      this.pollHandle = null;
    }
  }
}

export function render(root){
  const el = document.createElement('section');
  el.className = 'card span-12';
  el.innerHTML = `
    <style>
      .table {
        background-color: white;
        color: black;
      }
      .table tbody tr:nth-child(odd) {
        background-color: #f2f2f2;
      }
      .table tbody tr:nth-child(even) {
        background-color: #e6e6e6;
      }
      .running-row {
        background-color: #A5D6A7 !important;
      }
      .choreo-panel {
        margin-top: 24px;
        border: 1px solid rgba(0,0,0,0.1);
        border-radius: 12px;
        padding: 24px;
        background: #ffffff;
        color: #000000;
      }
      .choreo-panel.hidden {
        display: none;
      }
      .choreo-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 24px;
        margin-top: 16px;
      }
      .choreo-panel table {
        width: 100%;
        border-collapse: collapse;
      }
      .choreo-panel table th,
      .choreo-panel table td {
        padding: 8px 6px;
        border-bottom: 1px solid rgba(0,0,0,0.08);
        text-align: left;
        font-size: 0.9rem;
      }
      .choreo-panel table th {
        font-weight: 600;
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
      }
      .choreo-panel .program-picker {
        display: flex;
        gap: 8px;
        margin-bottom: 12px;
      }
      .choreo-panel .program-picker select {
        flex: 1;
        padding: 6px 8px;
        border-radius: 6px;
        border: 1px solid rgba(0,0,0,0.2);
        font-size: 0.9rem;
      }
      .status-chip {
        display: inline-flex;
        align-items: center;
        padding: 3px 8px;
        border-radius: 999px;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }
      .status-chip.idle {
        background: #E0E0E0;
        color: #333;
      }
      .status-chip.running {
        background: #C8E6C9;
        color: #2E7D32;
      }
      .status-chip.scheduled {
        background: #FFF3E0;
        color: #E65100;
      }
      .robot-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        display: inline-block;
        margin-right: 6px;
      }
      .robot-dot.ok {
        background: #2E7D32;
      }
      .robot-dot.off {
        background: #C62828;
      }
      .choreo-panel .panel-footer {
        margin-top: 18px;
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: center;
      }
      .choreo-panel .hint {
        font-size: 0.8rem;
        opacity: 0.7;
      }
      .choreo-panel .error-box {
        color: #D32F2F;
        font-size: 0.85rem;
      }
      .btn.ghost {
        background: transparent;
        border: 1px solid rgba(0,0,0,0.4);
        color: inherit;
      }
      .status-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 12px;
        margin-top: 16px;
      }
      .status-item {
        background: #f5f5f5;
        border-radius: 8px;
        padding: 12px;
      }
      .status-item .label {
        font-size: 0.75rem;
        text-transform: uppercase;
        opacity: 0.6;
        margin-bottom: 4px;
      }
      .status-item .value {
        display: flex;
        align-items: center;
        gap: 8px;
        font-weight: 600;
      }
      .status-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        display: inline-block;
        background: #C62828;
      }
      .status-dot.ok {
        background: #2E7D32;
      }
      .status-dot.pending {
        background: #F9A825;
      }
      .status-actions {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 10px;
      }
      .config-card {
        margin-top: 16px;
        padding: 16px;
        border: 1px solid rgba(0,0,0,0.1);
        border-radius: 8px;
        background: #fafafa;
      }
      .config-card h4 {
        margin-top: 0;
      }
      .config-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 12px;
        margin-top: 12px;
      }
      .config-grid label {
        font-size: 0.85rem;
        font-weight: 600;
        display: flex;
        flex-direction: column;
      }
      .config-grid input[type="text"],
      .config-grid input[type="password"] {
        margin-top: 4px;
        padding: 6px 8px;
        border: 1px solid rgba(0,0,0,0.2);
        border-radius: 5px;
        font-size: 0.9rem;
      }
      .config-grid label.checkbox {
        flex-direction: row;
        align-items: center;
        font-weight: 500;
      }
      .config-grid label.checkbox input {
        margin-right: 8px;
      }
      .config-actions {
        margin-top: 12px;
        display: flex;
        align-items: center;
        gap: 12px;
      }
      .config-actions .hint {
        font-size: 0.8rem;
        opacity: 0.7;
      }
      .config-actions .hint.success {
        color: #2E7D32;
        opacity: 1;
      }
      .config-actions .hint.error {
        color: #C62828;
        opacity: 1;
      }
    </style>
    <div class="title">Gestionnaire d'applications</div>
    <div class="row">
        <button class="btn" id="refresh-apps">Rafraîchir la liste</button>
        <button class="btn secondary" id="toggle-choreo">Chorégraphie multi-robots</button>
        <span id="naoqi-version-display" style="margin-left: auto; opacity: 0.7;"></span>
    </div>
    <div id="choreo-panel-host"></div>

    <h3 style="margin-top: 20px;">Applications Principales</h3>
    <p style="margin-top: -10px; opacity: 0.8;">Comportements de haut niveau (nature interactive ou solitary).</p>
    <div style="overflow-x: auto;"><table class="table">
        <thead><tr><th>Nom</th><th>Nature</th><th>État</th><th>Actions</th></tr></thead>
        <tbody id="apps-tb"></tbody>
    </table></div>

    <h3 style="margin-top: 20px;">Animations & Comportements</h3>
    <p style="margin-top: -10px; opacity: 0.8;">Comportements de plus bas niveau (ex: gestes, dialogues simples).</p>
    <div style="overflow-x: auto;"><table class="table">
        <thead><tr><th>Nom</th><th>Nature</th><th>État</th><th>Actions</th></tr></thead>
        <tbody id="anims-tb"></tbody>
    </table></div>
  `;
  root.appendChild(el);

  const configReloadPromise = api.configReload ? api.configReload().catch(() => null) : Promise.resolve();
  const apps_tbody = el.querySelector('#apps-tb');
  const anims_tbody = el.querySelector('#anims-tb');
  const version_display = el.querySelector('#naoqi-version-display');
  const choreoPanelHost = el.querySelector('#choreo-panel-host');
  const choreoPanel = choreoPanelHost ? new ChoreographyPanel(choreoPanelHost, api) : null;
  const toggleChoreoBtn = el.querySelector('#toggle-choreo');
  if (toggleChoreoBtn) {
    if (choreoPanel) {
      toggleChoreoBtn.addEventListener('click', () => choreoPanel.toggle(true));
    } else {
      toggleChoreoBtn.disabled = true;
      toggleChoreoBtn.title = 'Gestionnaire chorégraphie indisponible.';
    }
  }

  async function refresh() {
    await configReloadPromise;
    const spinnerRow = '<tr><td colspan="4" style="text-align: center; padding: 20px;"><div class="spinner" style="margin: 0 auto;"></div></td></tr>';
    apps_tbody.innerHTML = spinnerRow;
    anims_tbody.innerHTML = spinnerRow;
    try {
      const r = await api.appsList();
      if (r.error) {
        apps_tbody.innerHTML = `<tr><td colspan="4">Erreur: ${r.error}</td></tr>`;
        anims_tbody.innerHTML = '';
        return;
      }
      
      version_display.textContent = `NAOqi v${r.naoqi_version || 'inconnue'}`;

      if (!r.applications || r.applications.length === 0) {
        apps_tbody.innerHTML = '<tr><td colspan="4">Aucune application principale trouvée.</td></tr>';
      } else {
        apps_tbody.innerHTML = r.applications.map(app => renderRow(app)).join('');
      }

      if (!r.animations || r.animations.length === 0) {
        anims_tbody.innerHTML = '<tr><td colspan="4">Aucune animation trouvée.</td></tr>';
      } else {
        anims_tbody.innerHTML = r.animations.map(app => renderRow(app)).join('');
      }

      if (choreoPanel) {
        choreoPanel.setProgramOptions(r.applications || []);
      }

    } catch (e) {
      apps_tbody.innerHTML = `<tr><td colspan="4">Erreur: ${e.message || e}</td></tr>`;
      anims_tbody.innerHTML = '';
    }
  }

  el.addEventListener('click', async (e) => {
    const button = e.target.closest('button[data-action]');
    if (!button) return;

    const action = button.dataset.action;
    const name = button.dataset.name;
    if (!action || !name) return;

    e.preventDefault();
    e.stopPropagation();

    const originalContent = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<span class="inline-spinner"></span>';

    try {
      if (action === 'start') {
        await api.appStart(name);
      } else if (action === 'stop') {
        await api.appStop(name);
      }
      setTimeout(async () => {
        const scrollY = window.scrollY;
        await refresh();
        window.scrollTo(0, scrollY);
      }, 1500);

    } catch (err) {
      alert(`Erreur: ${err.message || err}`);
      button.disabled = false;
      button.innerHTML = originalContent;
    }
  });

  el.querySelector('#refresh-apps').addEventListener('click', refresh);

  refresh();
}
