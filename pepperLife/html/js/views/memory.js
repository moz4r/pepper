

export function render(root, api){
  const el = document.createElement('div');
  el.className = 'grid-memory'; // Custom grid for this view
  el.innerHTML = `
    <style>
      .grid-memory { display: grid; grid-template-columns: 300px 1fr; gap: 20px; }
      .key-list { list-style: none; margin: 0; padding: 0; max-height: 400px; overflow-y: auto; border: 1px solid #ddd; border-radius: 6px; }
      .key-list li { padding: 8px 12px; cursor: pointer; border-bottom: 1px solid #eee; }
      .key-list li:hover { background-color: #f0f2f5; }
      .key-list li.selected { background-color: #1877f2; color: white; }
      .value-display pre { white-space: pre-wrap; word-wrap: break-word; background-color: #f0f2f5; padding: 10px; border-radius: 6px; }
      .value-display textarea { width: 100%; min-height: 150px; box-sizing: border-box; border: 1px solid #ccc; border-radius: 6px; padding: 8px; font-family: monospace; }
    </style>
    <div class="card">
        <div class="title">Clés ALMemory</div>
        <div class="row">
            <input id="pat" placeholder="^/PepperLife/" style="flex-grow:1;"/>
            <button class="btn" id="search">Chercher</button>
        </div>
        <ul id="key-list" class="key-list"></ul>
    </div>
    <div class="card">
        <div class="title">Valeur</div>
        <div id="value-display" class="value-display">
            <pre id="value-pre">Sélectionnez une clé pour voir sa valeur.</pre>
            <textarea id="value-edit" placeholder="Modifiez la valeur ici..."></textarea>
            <div class="row" style="margin-top: 10px;">
                <button class="btn" id="save-value" disabled>Enregistrer</button>
            </div>
        </div>
    </div>
  `;
  root.appendChild(el);

  const keyList = el.querySelector('#key-list');
  const valuePre = el.querySelector('#value-pre');
  const valueEdit = el.querySelector('#value-edit');
  const saveBtn = el.querySelector('#save-value');
  const searchInput = el.querySelector('#pat');

  let selectedKey = null;

  async function searchKeys() {
    const pattern = searchInput.value || '';
    keyList.innerHTML = '<li>Chargement...</li>';
    try {
      const keys = await api.memorySearch(pattern);
      keyList.innerHTML = keys.map(key => `<li>${key}</li>`).join('');
    } catch (e) {
      keyList.innerHTML = `<li>Erreur: ${e.message || e}</li>`;
    }
  }

  keyList.addEventListener('click', async (e) => {
    if (e.target.tagName !== 'LI') return;

    // Remove selection from previous
    const prevSelected = keyList.querySelector('.selected');
    if (prevSelected) prevSelected.classList.remove('selected');

    // Select new
    selectedKey = e.target.textContent;
    e.target.classList.add('selected');
    saveBtn.disabled = true;
    valuePre.textContent = 'Chargement...';
    valueEdit.value = '';

    try {
      const response = await api.memoryGet(selectedKey);
      // La valeur qui nous intéresse est dans la propriété 'value' de la réponse.
      const value = response.value;
      const valueStr = JSON.stringify(value, null, 2);
      valuePre.textContent = valueStr;
      valueEdit.value = valueStr;
      saveBtn.disabled = false;
    } catch (e) {
      valuePre.textContent = `Erreur: ${e.message || e}`;
    }
  });

  saveBtn.addEventListener('click', async () => {
    if (!selectedKey) return;
    let valueToSave;
    try {
      // Try to parse as JSON, fallback to string
      valueToSave = JSON.parse(valueEdit.value);
    } catch (e) {
      valueToSave = valueEdit.value;
    }

    try {
      await api.memorySet(selectedKey, valueToSave);
      alert('Valeur enregistrée !');
    } catch (e) {
      alert(`Erreur lors de l'enregistrement: ${e.message || e}`);
    }
  });

  el.querySelector('#search').addEventListener('click', searchKeys);
  searchInput.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') searchKeys();
  });

  // Initial search
  searchKeys();
}
