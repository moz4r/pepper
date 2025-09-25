
import {api} from '../api.js';
export function render(root){
  const el = document.createElement('section'); el.className='card span-12';
  el.innerHTML = `<div class="title">Vie autonome</div>
  <div class="row">
    <span id="st" class="status">…</span>
    <button class="btn" id="tg">Basculer l'état</button>
  </div>`;
  root.appendChild(el);

  const statusEl = el.querySelector('#st');

  async function refresh(){
    try {
      const d = await api.lifeState();
      const state = d.state || '?';
      statusEl.textContent = state;
      statusEl.classList.remove('ok', 'off');
      if (state === 'disabled') {
        statusEl.classList.add('off');
      } else if (state === 'interactive' || state === 'solitary') {
        statusEl.classList.add('ok');
      }
    } catch(e) {
      statusEl.textContent = 'Erreur';
      statusEl.classList.remove('ok', 'off');
    }
  }

  el.querySelector('#tg').addEventListener('click', async()=>{
    try {
      await api.lifeToggle();
      await refresh();
    } catch(e) {
      alert(e.message || e);
    }
  });

  refresh();
}
