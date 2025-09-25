
import {api} from '../api.js';

export function render(root){
  const el = document.createElement('section');
  el.className = 'card span-12';
  el.innerHTML = `
    <div class="title">Tethering / Wi-Fi</div>
    <div class="row">
        <button class="btn" id="scan">Scanner les réseaux</button>
        <span style="margin-left: 10px;">Statut: <span id="status" class="status">…</span></span>
    </div>
    <table class="table">
        <thead><tr><th>SSID</th><th>Signal</th><th>Sécurité</th></tr></thead>
        <tbody id="tb"></tbody>
    </table>
    <div id="connect-form-container" style="margin-top: 15px;"></div>
  `;
  root.appendChild(el);

  const tbody = el.querySelector('#tb');
  const statusEl = el.querySelector('#status');
  const scanBtn = el.querySelector('#scan');
  const connectFormContainer = el.querySelector('#connect-form-container');

  async function refreshStatus() {
    statusEl.textContent = 'Chargement...';
    statusEl.className = 'status';
    try {
      const d = await api.wifiStatus();
      const state = d.status || 'inconnu';
      statusEl.textContent = state;
      if (state === 'online' || state === 'ready') {
        statusEl.classList.add('ok');
      } else if (state === 'offline' || state === 'disconnect') {
        statusEl.classList.add('off');
      }
    } catch (e) {
      statusEl.textContent = 'Erreur';
      statusEl.classList.add('off');
    }
  }

  async function scan() {
    tbody.innerHTML = '<tr><td colspan="3">Scan en cours...</td></tr>';
    connectFormContainer.innerHTML = '';
    try {
      const r = await api.wifiScan();
      tbody.innerHTML = (r.list || []).map(net => `
        <tr data-ssid="${net.ssid}" style="cursor: pointer;">
          <td>${net.ssid}</td>
          <td>${net.rssi || 'N/A'}</td>
          <td>${net.sec || 'Ouvert'}</td>
        </tr>
      `).join('');
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="3">Erreur: ${e.message || e}</td></tr>`;
    }
  }

  tbody.addEventListener('click', (e) => {
    const row = e.target.closest('tr');
    if (!row || !row.dataset.ssid) return;

    const ssid = row.dataset.ssid;
    connectFormContainer.innerHTML = `
      <div class="title">Connexion à ${ssid}</div>
      <div class="row">
        <input type="password" id="psk-input" placeholder="Mot de passe"/>
        <button class="btn" id="connect-btn">Connecter</button>
        <span id="connect-feedback"></span>
      </div>
    `;

    el.querySelector('#connect-btn').addEventListener('click', async () => {
      const psk = el.querySelector('#psk-input').value;
      const feedback = el.querySelector('#connect-feedback');
      feedback.textContent = 'Connexion en cours...';
      try {
        await api.wifiConnect(ssid, psk);
        feedback.textContent = 'Demande de connexion envoyée !';
        setTimeout(refreshStatus, 3000);
      } catch (err) {
        feedback.textContent = `Erreur: ${err.message || err}`;
      }
    });
  });

  scanBtn.addEventListener('click', scan);

  // Initial load
  refreshStatus();
  scan();
}
