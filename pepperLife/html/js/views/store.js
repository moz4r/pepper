import { api } from '../api.js';

const AGENT_HINT_DEFAULT = 'Agent PepperShop local introuvable.';

const template = `
  <style>
    .store-view {
      display: grid;
      grid-template-columns: minmax(0, 480px);
      gap: 16px;
    }
    .store-card {
      background: #fbfbfd;
      border-radius: 16px;
      border: 1px solid rgba(2,6,23,0.08);
      box-shadow: 0 10px 30px rgba(2,6,23,0.06);
      padding: 20px;
    }
    .store-summary {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
      gap: 12px;
    }
    .summary-info {
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 600;
      color: #0f172a;
    }
    .summary-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: rgba(2,6,23,0.25);
    }
    .summary-dot[data-state="ok"] {
      background: #22c55e;
    }
    .summary-dot[data-state="pending"] {
      background: #f97316;
    }
    .summary-dot[data-state="error"] {
      background: #ef4444;
    }
    .summary-refresh {
      border: none;
      background: transparent;
      font-size: 1.1rem;
      cursor: pointer;
      color: #0f172a;
      padding: 0 4px;
    }
    .summary-refresh:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }
    .status-pill {
      padding: 8px 12px;
      border-radius: 999px;
      font-size: 0.85rem;
      font-weight: 600;
      background: rgba(2,6,23,0.06);
      color: #0f172a;
      margin-bottom: 8px;
      display: inline-flex;
    }
    .status-pill[data-state="pending"] {
      background: rgba(249, 115, 22, 0.15);
      color: #c2410c;
    }
    .status-pill[data-state="error"] {
      background: rgba(248,113,113,0.18);
      color: #b91c1c;
    }
    .status-pill[data-state="ok"] {
      background: rgba(34,197,94,0.2);
      color: #166534;
    }
    .muted {
      color: #475569;
      font-size: 0.95rem;
    }
    .store-fallback {
      margin-top: 12px;
      padding: 12px 14px;
      border-radius: 12px;
      background: rgba(248,113,113,0.12);
      color: #7f1d1d;
      font-size: 0.9rem;
      border: 1px solid rgba(248,113,113,0.35);
    }
    .store-fallback a {
      color: inherit;
      font-weight: 600;
    }
  </style>
  <section class="store-view">
    <div class="store-card">
      <div class="store-summary">
        <div class="summary-info">
          <span class="summary-dot" data-role="summary-dot" data-state="idle"></span>
          <span data-role="summary-text">Connexion non vérifiée.</span>
        </div>
        <button type="button" class="summary-refresh" data-role="refresh" title="Actualiser le statut">↻</button>
      </div>
      <p class="muted">
        PepperLife affiche uniquement l'état de connexion au store distant. Configurez ou mettez à jour vos identifiants directement dans PepperShop.
      </p>
      <div class="status-pill" data-role="status-pill" data-state="idle">Aucune vérification effectuée.</div>
      <p class="muted" data-role="connection-details">En attente d'un premier contrôle.</p>
      <div class="store-fallback" data-role="fallback-hint" hidden></div>
    </div>
  </section>
`;

let cleanupFns = [];

export function render(root) {
  cleanupFns = [];
  root.innerHTML = template;
  const statusPill = root.querySelector('[data-role="status-pill"]');
  const summaryDot = root.querySelector('[data-role="summary-dot"]');
  const summaryText = root.querySelector('[data-role="summary-text"]');
  const detailsBox = root.querySelector('[data-role="connection-details"]');
  const fallbackHint = root.querySelector('[data-role="fallback-hint"]');
  const refreshBtn = root.querySelector('[data-role="refresh"]');

  function setStatus(state, message) {
    if (statusPill) {
      statusPill.dataset.state = state;
      statusPill.textContent = message;
    }
    if (summaryDot) {
      summaryDot.dataset.state = state;
    }
    if (summaryText) {
      summaryText.textContent = message;
    }
  }

  function setDetails(message) {
    if (detailsBox) {
      detailsBox.textContent = message || 'Aucune information disponible.';
    }
  }

  function setFallbackHint(message) {
    if (!fallbackHint) {
      return;
    }
    if (!message) {
      fallbackHint.hidden = true;
      fallbackHint.innerHTML = '';
      return;
    }
    fallbackHint.hidden = false;
    fallbackHint.innerHTML = '';
    const lead = document.createElement('strong');
    lead.textContent = message || AGENT_HINT_DEFAULT;
    fallbackHint.appendChild(lead);
    fallbackHint.appendChild(document.createElement('br'));
    fallbackHint.appendChild(document.createTextNode("Téléchargez ou relancez l'agent PepperShop local (package disponible sur "));
    const link = document.createElement('a');
    link.href = STORE_PORTAL_URL;
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = STORE_PORTAL_URL;
    fallbackHint.appendChild(link);
    fallbackHint.appendChild(document.createTextNode(') puis relancez-le sur le robot.'));
  }

  function applyAgentOfflineHint(err) {
    if (err && err.storeAgentUnreachable) {
      setFallbackHint(err.message || AGENT_HINT_DEFAULT);
      return true;
    }
    return false;
  }

  function extractErrorMessage(err) {
    if (!err) return 'Erreur inconnue.';
    const raw = typeof err === 'string' ? err : (err.message || '');
    if (!raw) return 'Erreur inconnue.';
    const trimmed = raw.trim();
    if (trimmed.startsWith('{')) {
      try {
        const parsed = JSON.parse(trimmed);
        if (parsed && parsed.error) {
          return parsed.error;
        }
      } catch (_) {}
    }
    return trimmed;
  }

  function formatConnectionDetails(status) {
    if (!status) {
      return 'Aucune donnée disponible.';
    }
    const parts = [];
    const server = status.server || (status.details && status.details.server) || status.api_base;
    const email = status.stored_email || (status.details && status.details.stored_email);
    const latency = status.details && (status.details.latency_ms || status.details.latencyMs);
    const httpCode = status.details && status.details.status;
    if (server) {
      parts.push(`Serveur ${server}`);
    }
    if (email) {
      parts.push(`Compte ${email}`);
    }
    if (latency) {
      parts.push(`${latency} ms`);
    }
    if (httpCode) {
      parts.push(`HTTP ${httpCode}`);
    }
    return parts.join(' • ') || 'Connexion active.';
  }

  async function refreshStatus({ silent } = {}) {
    if (!silent) {
      setStatus('pending', 'Vérification de la connexion en cours…');
    }
    try {
      const status = await api.storeStatus();
      setFallbackHint(null);
      if (status.status === 'connected') {
        const warningSuffix = status.warning ? ` ${status.warning}` : '';
        setStatus('ok', status.message || `Connecté au store.${warningSuffix}`);
        setDetails(formatConnectionDetails(status));
      } else if (status.status === 'missing-credentials') {
        setStatus('idle', status.message || 'Aucun identifiant enregistré.');
        setDetails("Configurez vos identifiants via l'agent PepperShop.");
      } else {
        const message = status.message || 'Connexion impossible.';
        setStatus('error', message);
        const detailError = status.details && (status.details.error || status.details.preview);
        setDetails(detailError || message);
      }
      return status;
    } catch (err) {
      const message = extractErrorMessage(err);
      setStatus('error', message);
      setDetails('Erreur lors de la vérification de la connexion.');
      if (!applyAgentOfflineHint(err)) {
        setFallbackHint(null);
      }
      return null;
    }
  }

  function onRefresh(ev) {
    ev.preventDefault();
    refreshStatus();
  }

  if (refreshBtn) {
    refreshBtn.addEventListener('click', onRefresh);
    cleanupFns.push(() => refreshBtn.removeEventListener('click', onRefresh));
  }

  setStatus('idle', 'Aucune vérification effectuée.');
  setDetails("Cliquez sur Actualiser pour interroger l'état du store.");
  setFallbackHint(null);
  refreshStatus();
}

export function cleanup() {
  cleanupFns.forEach(fn => {
    try { fn(); } catch (_) {}
  });
  cleanupFns = [];
}
