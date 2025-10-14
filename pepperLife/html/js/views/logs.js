import {api} from '../api.js';

export function render(root) {
  const el = document.createElement('section');
  el.className = 'card span-12';
  el.innerHTML = `
    <div class="title">Logs</div>
    <div class="logs-header">
      <div class="log-sources">
        <button class="btn" data-source="launcher">Lanceur</button>
        <button class="btn active" data-source="service">Service</button>
      </div>
    </div>
    <pre id="pre" style="white-space:pre-wrap; min-height: 300px; background: #000; color: #fff; border: 1px solid #333; padding: 10px; border-radius: 4px;"></pre>
  `;
  root.appendChild(el);

  const pre = el.querySelector('#pre');
  const sourceButtons = el.querySelectorAll('.log-sources .btn');
  let currentSource = 'service'; // Source par défaut

  const apiMap = {
    launcher: '/api/logs/launcher',
    service: '/api/logs/service'
  };

  async function refresh(source) {
    pre.innerHTML = '<div class="spinner" style="margin: 20px auto;"></div>';
    try {
      const endpoint = apiMap[source];
      if (!endpoint) {
        throw new Error(`Source de log inconnue: ${source}`);
      }
      
      const d = await api.get(endpoint); 
      const logs = d.logs || [];
      
      if (logs.length > 0) {
        pre.innerHTML = logs.join('<br>');
      } else {
        pre.textContent = '(Logs vides)';
      }
    } catch(e) {
      pre.textContent = `Erreur au chargement des logs: ${e.message || e}`;
    }
  }

  sourceButtons.forEach(button => {
    button.addEventListener('click', () => {
      currentSource = button.dataset.source;
      
      sourceButtons.forEach(btn => btn.classList.remove('active'));
      button.classList.add('active');
      
      refresh(currentSource);
    });
  });

  sourceButtons.forEach(btn => {
    btn.classList.toggle('active', btn.dataset.source === currentSource);
  });

  refresh(currentSource);
}
