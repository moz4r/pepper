
import {api} from '../api.js';
export function render(root){
  const el = document.createElement('section'); el.className='card span-12';
  el.innerHTML = `<div class="title">Posture</div>
  <div class="row">
    <span id="st" class="status">…</span>
    <button class="btn" id="tg">Réveiller / Mettre en veille</button>
  </div>`;
  root.appendChild(el);

  const statusEl = el.querySelector('#st');

  async function refresh(){
    try {
      const d = await api.postureState();
      const isAwake = d.is_awake;
      statusEl.textContent = isAwake ? 'Debout' : 'Au repos';
      statusEl.classList.remove('ok', 'off');
      statusEl.classList.add(isAwake ? 'ok' : 'off');
    } catch(e) {
      statusEl.textContent = 'Erreur';
      statusEl.classList.remove('ok', 'off');
    }
  }

  el.querySelector('#tg').addEventListener('click', async()=>{
    try {
      await api.postureToggle();
      await refresh();
    } catch(e) {
      alert(e.message || e);
    }
  });

  refresh();
}
