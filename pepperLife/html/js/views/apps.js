
import {api} from '../api.js';

function renderState(state) {
    if (!state) return '';
    const cssClass = state === 'running' ? 'ok' : 'off';
    return `<span class="status ${cssClass}">${state}</span>`;
}

export function render(root){
  const el = document.createElement('section');
  el.className = 'card span-12';
  el.innerHTML = `
    <div class="title">Applications</div>
    <div class="row">
        <button class="btn" id="refresh-apps">Rafraîchir la liste</button>
    </div>
    <table class="table">
        <thead><tr><th>Nom</th><th>État</th><th>Actions</th></tr></thead>
        <tbody id="tb"></tbody>
    </table>
  `;
  root.appendChild(el);

  const tbody = el.querySelector('#tb');

  async function refresh() {
    tbody.innerHTML = '<tr><td colspan="3">Chargement...</td></tr>';
    try {
      const r = await api.appsList();
      if (r.error) {
        tbody.innerHTML = `<tr><td colspan="3">Erreur: ${r.error}</td></tr>`;
        return;
      }
      if (!r.apps || r.apps.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3">Aucune application trouvée.</td></tr>';
        return;
      }
      tbody.innerHTML = (r.apps).map(app => `
        <tr>
          <td>${app.name}</td>
          <td>${renderState(app.state)}</td>
          <td>
            <button class="btn" data-action="start" data-name="${app.name}">Démarrer</button>
            <button class="btn secondary" data-action="stop" data-name="${app.name}">Arrêter</button>
          </td>
        </tr>
      `).join('');
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="3">Erreur: ${e.message || e}</td></tr>`;
    }
  }

  tbody.addEventListener('click', async (e) => {
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
      // Attendre un peu pour que l'état se mette à jour sur le robot
      setTimeout(refresh, 1000);
    } catch (err) {
      alert(`Erreur: ${err.message || err}`);
      // Réactiver le bouton en cas d'erreur
      e.target.disabled = false;
      e.target.textContent = action === 'start' ? 'Démarrer' : 'Arrêter';
    }
  });

  el.querySelector('#refresh-apps').addEventListener('click', refresh);

  // Initial load
  refresh();
}
