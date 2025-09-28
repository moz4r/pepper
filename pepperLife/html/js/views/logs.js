
import {api} from '../api.js';
export function render(root){
  const el = document.createElement('section'); el.className='card span-12';
  el.innerHTML = `<div class="title">Logs</div>
  <div class="row">
    <label for="n">Nombre de lignes:</label>
    <input id="n" type="number" min="10" max="2000" value="200" style="width: 80px;"/>
    <button class="btn" id="load">Rafraîchir</button>
  </div>
  <pre id="pre" style="white-space:pre-wrap; min-height: 100px;"></pre>`;
  root.appendChild(el);

  const pre = el.querySelector('#pre');
  const nInput = el.querySelector('#n');

  async function refresh() {
    pre.innerHTML = '<div class="spinner" style="margin: 20px auto;"></div>';
    try {
      const n = parseInt(nInput.value, 10) || 200;
      const d = await api.logsTail(n);
      // La réponse peut être un objet {text: "..."} ou un tableau de lignes
      const logText = Array.isArray(d) ? d.join('\n') : (d.text || '');
      if (logText) {
        const ansi_up = new AnsiUp();
        pre.innerHTML = ansi_up.ansi_to_html(logText);
      } else {
        pre.textContent = '(Logs vides)';
      }
    } catch(e) {
      pre.textContent = `Erreur au chargement des logs: ${e.message || e}`;
    }
  }

  el.querySelector('#load').addEventListener('click', refresh);

  // Charger les logs au démarrage
  refresh();
}
