import { api } from '../api.js';

const template = `
<div class="view-container">
    <h2><i class="bi bi-chat-dots"></i> Gestion du Chatbot</h2>
    <p>Sélectionnez un mode de conversation ou arrêtez le service de chat actif.</p>
    
    <div id="chat-status" style="display: flex; align-items: center; gap: 20px; margin-bottom: 15px;">
        <strong>État actuel :</strong> <span id="current-chat-status">INCONNU</span>
        <button id="stop-chat-btn" class="btn btn-danger">Arrêter le Chat</button>
    </div>

    <hr>

    <div class="chat-mode-section">
        <h3><i class="bi bi-mic"></i> Basic Channel (Écoute locale)</h3>
        <p>Le robot écoute les commandes locales simples, sans IA externe.</p>
        <button id="start-basic-btn" class="btn btn-success">Activer</button>
    </div>

    <hr>

    <div class="chat-mode-section">
        <h3><i class="bi bi-robot"></i> GPT Chatbot (OpenAI)</h3>
        <p>Active le chatbot complet avec l'intelligence artificielle d'OpenAI.</p>
        <button id="start-gpt-btn" class="btn btn-primary">Activer</button>
    </div>
</div>
`;

let isViewActive = false;

function updateStatus(status) {
    if (!isViewActive) return;

    const statusEl = document.getElementById('current-chat-status');
    const startGptBtn = document.getElementById('start-gpt-btn');
    const startBasicBtn = document.getElementById('start-basic-btn');
    const stopChatBtn = document.getElementById('stop-chat-btn');

    // Reset buttons state
    startGptBtn.disabled = false;
    startGptBtn.innerHTML = 'Activer';
    startBasicBtn.disabled = false;
    startBasicBtn.innerHTML = 'Activer';
    stopChatBtn.disabled = false;
    stopChatBtn.innerHTML = 'Arrêter le Chat';

    if (status === 'gpt') {
        statusEl.textContent = 'GPT Chatbot Actif';
        statusEl.className = 'status-active';
        startGptBtn.disabled = true;
        startGptBtn.textContent = 'Activé';
    } else if (status === 'basic') {
        statusEl.textContent = 'Basic Channel Actif';
        statusEl.className = 'status-basic';
        startBasicBtn.disabled = true;
        startBasicBtn.textContent = 'Activé';
    } else {
        statusEl.textContent = 'Arrêté';
        statusEl.className = 'status-inactive';
        stopChatBtn.disabled = true;
    }
}

async function getChatStatus() {
    try {
        const status = await api.getChatStatus();
        updateStatus(status.mode);
    } catch (e) {
        if (e.message.includes('Failed to fetch')) {
            console.log("Impossible de récupérer le statut du chat, le backend est probablement hors ligne.");
        } else {
            console.error("Erreur lors de la récupération du statut du chat:", e);
        }
        updateStatus('stopped'); // Assume stopped on error
    }
}

export function render() {
    const app = document.getElementById('app');
    app.innerHTML = template;
    init();
}

export function init() {
    isViewActive = true;

    // Initial status check
    getChatStatus();

    // --- Event Listeners ---
    const setupButton = (id, action) => {
        document.getElementById(id).addEventListener('click', (e) => {
            const button = e.target;
            button.disabled = true;
            const spinner = document.createElement('span');
            spinner.className = 'inline-spinner';
            button.appendChild(spinner);
            action().then(getChatStatus);
        });
    };

    setupButton('start-basic-btn', () => api.startChat('basic'));
    setupButton('start-gpt-btn', () => api.startChat('gpt'));
    setupButton('stop-chat-btn', () => api.stopChat());
}

export function cleanup() {
    isViewActive = false;
}
