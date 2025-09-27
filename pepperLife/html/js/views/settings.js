import { api } from '../api.js';

export async function render(root) {
    root.innerHTML = `
    <style>
        .settings-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 16px; }
        .settings-card .title { border-bottom: 1px solid #eee; padding-bottom: 0.5rem; margin-bottom: 1rem; }
        .settings-card .section-comment { font-size: 0.9em; color: #666; margin-bottom: 1rem; }
        .form-group { margin-bottom: 1rem; }
        .form-group label { font-weight: bold; display: block; margin-bottom: 0.5rem; font-size: 0.9em; }
        .form-group .form-control { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-family: monospace; }
        .form-group .comment { font-size: 0.8em; color: #888; margin-top: 0.3rem; }
        .actions { grid-column: 1 / -1; margin-top: 1rem; padding: 1rem; background: #f9f9f9; border-radius: 8px; text-align: right; }
        #save-feedback.error { color: red; }
        #save-feedback.success { color: green; }
    </style>
    <div class="title">Gestion de config.json</div>
    <div id="settings-grid-container" class="settings-grid">Chargement...</div>
    <div class="actions">
        <button id="save-config-btn" class="btn">Sauvegarder les modifications</button>
        <span id="save-feedback" style="margin-left: 1rem;"></span>
    </div>
    `;

    const gridContainer = root.querySelector('#settings-grid-container');
    const saveBtn = root.querySelector('#save-config-btn');
    const feedback = root.querySelector('#save-feedback');
    let originalUserConfig = {};

    // --- Helper to build a single input field ---
    function createFormField(key, value, comment) {
        const group = document.createElement('div');
        group.className = 'form-group';
        const label = document.createElement('label');
        label.textContent = key.split('.').pop(); // Display only the sub-key
        group.appendChild(label);

        const input = document.createElement('input');
        input.dataset.key = key;
        input.className = 'form-control';

        if (typeof value === 'boolean') {
            input.type = 'checkbox';
            input.checked = value;
            input.dataset.type = 'boolean';
        } else {
            input.type = 'text';
            input.dataset.type = (typeof value === 'number') ? 'number' : (Array.isArray(value) || (value !== null && typeof value === 'object')) ? 'json' : 'string';
            input.value = (input.dataset.type === 'json') ? JSON.stringify(value, null, 2) : value;
            if (input.dataset.type === 'json') {
                const ta = document.createElement('textarea');
                ta.dataset.key = key;
                ta.className = 'form-control';
                ta.dataset.type = 'json';
                ta.rows = 3;
                ta.value = input.value;
                group.appendChild(ta);
            } else {
                 group.appendChild(input);
            }
        }
        
        if (comment) {
            const p = document.createElement('p');
            p.className = 'comment';
            p.textContent = comment;
            group.appendChild(p);
        }
        return group;
    }

    // --- Main logic ---
    try {
        const [defaultConfigText, userConfig] = await Promise.all([
            api.configGetDefault(),
            api.configGetUser()
        ]);
        originalUserConfig = userConfig;

        // Parse comments from default config
        const comments = {};
        let currentComment = '';
        defaultConfigText.split('\n').forEach(line => {
            const trimmed = line.trim();
            if (trimmed.startsWith('//')) {
                currentComment += trimmed.replace('//', '').trim() + ' ';
            } else if (trimmed.includes(':')) {
                const key = trimmed.split(':')[0].replace(/"/g, '').trim();
                if (key && currentComment) {
                    comments[key] = currentComment.trim();
                }
                currentComment = '';
            }
        });

        // Build the form, grouped into cards
        gridContainer.innerHTML = '';
        for (const sectionKey in userConfig) {
            if (!userConfig.hasOwnProperty(sectionKey)) continue;

            const card = document.createElement('div');
            card.className = 'card settings-card';
            const title = document.createElement('div');
            title.className = 'title';
            title.textContent = sectionKey;
            card.appendChild(title);

            if (comments[sectionKey]) {
                const p = document.createElement('p');
                p.className = 'section-comment';
                p.textContent = comments[sectionKey];
                card.appendChild(p);
            }

            const sectionValue = userConfig[sectionKey];
            if (typeof sectionValue === 'object' && sectionValue !== null && !Array.isArray(sectionValue)) {
                for (const subKey in sectionValue) {
                    const fullKey = `${sectionKey}.${subKey}`;
                    card.appendChild(createFormField(fullKey, sectionValue[subKey], comments[fullKey]));
                }
            } else {
                card.appendChild(createFormField(sectionKey, sectionValue, comments[sectionKey]));
            }
            gridContainer.appendChild(card);
        }

    } catch (e) {
        gridContainer.innerHTML = `<p style="color:red; grid-column: 1 / -1;">Erreur lors du chargement de la configuration: ${e.message}</p>`;
    }

    // --- Save Logic ---
    saveBtn.addEventListener('click', async () => {
        feedback.textContent = 'Sauvegarde...';
        feedback.className = '';
        const inputs = gridContainer.querySelectorAll('[data-key]');
        let newConfig = JSON.parse(JSON.stringify(originalUserConfig)); // Deep copy
        let parseError = false;

        inputs.forEach(input => {
            if (parseError) return;
            const keys = input.dataset.key.split('.');
            let current = newConfig;
            for (let i = 0; i < keys.length - 1; i++) {
                current = current[keys[i]];
            }
            
            let value;
            const originalType = input.dataset.type;

            try {
                if (input.type === 'checkbox') {
                    value = input.checked;
                } else if (originalType === 'number') {
                    value = input.value === '' ? null : parseFloat(input.value);
                } else if (originalType === 'json') {
                    value = JSON.parse(input.value);
                } else {
                    value = input.value;
                }
                current[keys[keys.length - 1]] = value;
            } catch (e) {
                parseError = true;
                feedback.textContent = `Erreur de format JSON dans le champ '${input.dataset.key}' !`;
                feedback.className = 'error';
                console.error(`JSON parse error for key ${input.dataset.key}:`, e);
            }
        });

        if (parseError) return;

        try {
            await api.configSetUser(newConfig);
            feedback.textContent = 'Enregistré avec succès !';
            feedback.className = 'success';
            originalUserConfig = newConfig; // Update local state
            setTimeout(() => { feedback.textContent = ''; feedback.className = ''; }, 3000);
        } catch (e) {
            feedback.textContent = `Erreur de sauvegarde: ${e.message}`;
            feedback.className = 'error';
        }
    });
}

export function init() {}
export function cleanup() {}
