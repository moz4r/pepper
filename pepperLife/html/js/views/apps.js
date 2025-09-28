
import {api} from '../api.js';

function renderState(state) {
    if (!state) return '';
    const cssClass = state === 'running' ? 'ok' : 'off';
    return `<span class="status ${cssClass}">${state}</span>`;
}

// Helper to render a row
function renderRow(app) {
    let buttons = 'Non supporté';
    if (app.runnable) {
        buttons = `
          <button class="btn" data-action="start" data-name="${app.name}" ${app.status === 'running' ? 'disabled' : ''}>Démarrer</button>
          <button class="btn secondary" data-action="stop" data-name="${app.name}" ${app.status !== 'running' ? 'disabled' : ''}>Arrêter</button>
        `;
    }
    return `
      <tr>
        <td>${app.name}</td>
        <td><span class="nature-tag">${app.nature || 'N/A'}</span></td>
        <td>${renderState(app.status)}</td>
        <td>${buttons}</td>
      </tr>
    `;
}


export function render(root){
  const el = document.createElement('section');
  el.className = 'card span-12';
  el.innerHTML = `
    <div class="title">Gestionnaire d'applications</div>
    <div class="row">
        <button class="btn" id="refresh-apps">Rafraîchir la liste</button>
        <span id="naoqi-version-display" style="margin-left: auto; opacity: 0.7;"></span>
    </div>

    <h3 style="margin-top: 20px;">Applications Principales</h3>
    <p style="margin-top: -10px; opacity: 0.8;">Comportements de haut niveau (nature interactive ou solitary).</p>
    <table class="table">
        <thead><tr><th>Nom</th><th>Nature</th><th>État</th><th>Actions</th></tr></thead>
        <tbody id="apps-tb"></tbody>
    </table>

    <h3 style="margin-top: 20px;">Animations & Comportements</h3>
    <p style="margin-top: -10px; opacity: 0.8;">Comportements de plus bas niveau (ex: gestes, dialogues simples).</p>
    <table class="table">
        <thead><tr><th>Nom</th><th>Nature</th><th>État</th><th>Actions</th></tr></thead>
        <tbody id="anims-tb"></tbody>
    </table>
  `;
  root.appendChild(el);

  const apps_tbody = el.querySelector('#apps-tb');
  const anims_tbody = el.querySelector('#anims-tb');
  const version_display = el.querySelector('#naoqi-version-display');

  async function refresh() {
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

      // Populate Applications
      if (!r.applications || r.applications.length === 0) {
        apps_tbody.innerHTML = '<tr><td colspan="4">Aucune application principale trouvée.</td></tr>';
      } else {
        apps_tbody.innerHTML = r.applications.map(renderRow).join('');
      }

      // Populate Animations
      if (!r.animations || r.animations.length === 0) {
        anims_tbody.innerHTML = '<tr><td colspan="4">Aucune animation trouvée.</td></tr>';
      } else {
        anims_tbody.innerHTML = r.animations.map(renderRow).join('');
      }

    } catch (e) {
      apps_tbody.innerHTML = `<tr><td colspan="4">Erreur: ${e.message || e}</td></tr>`;
      anims_tbody.innerHTML = '';
    }
  }

  // Event listener needs to be on a parent element
  el.addEventListener('click', async (e) => {
    const action = e.target.dataset.action;
    const name = e.target.dataset.name;
    if (!action || !name) return;

    e.target.disabled = true;
    e.target.textContent = '...';

    try {
      if (action === 'start') {
        await api.appStart(name);
      } else if (action === 'stop') {
        await api.appStop(name);
      }
      setTimeout(refresh, 1000);
    } catch (err) {
      alert(`Erreur: ${err.message || err}`);
      refresh(); // Refresh to restore button state
    }
  });

  el.querySelector('#refresh-apps').addEventListener('click', refresh);

  refresh();
}
