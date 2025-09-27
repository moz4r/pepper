
export function render(root){
  const el = document.createElement('section');
  el.className = 'card span-12';
  el.innerHTML = `
    <div class="title">Caméra</div>
    <div class="row">
        <button class="btn" id="start">Démarrer le flux</button>
        <button class="btn secondary" id="stop" disabled>Arrêter le flux</button>
        <a class="btn" href="/last_capture.png" target="_blank">Voir la dernière capture vision</a>
    </div>
    <div class="row">
        <div class="imgbox" style="min-height: 240px; display: flex; align-items: center; justify-content: center;">
            <img id="cam" alt="Le flux de la caméra apparaîtra ici" style="max-width: 100%; height: auto;"/>
            <span id="cam-error" style="color: red; display: none;"></span>
        </div>
    </div>
  `;
  root.appendChild(el);

  const startBtn = el.querySelector('#start');
  const stopBtn = el.querySelector('#stop');
  const img = el.querySelector('#cam');
  const errorSpan = el.querySelector('#cam-error');

  let timer = null;

  function updateButtons(isStreaming) {
    startBtn.disabled = isStreaming;
    stopBtn.disabled = !isStreaming;
  }

  function step() {
    // Arrêter la boucle si l'élément n'est plus dans le DOM
    if (!el.isConnected) {
      if (timer) clearTimeout(timer);
      return;
    }
    img.src = '/cam.png?t=' + Date.now();
    timer = setTimeout(step, 250); // Rafraîchir toutes les 250ms
  }

  img.onerror = () => {
    img.style.display = 'none';
    errorSpan.style.display = 'inline';
    errorSpan.textContent = 'Erreur de chargement du flux. Le service caméra est-il démarré ?';
    if (timer) clearTimeout(timer);
    updateButtons(false);
  };

  img.onload = () => {
    img.style.display = 'block';
    errorSpan.style.display = 'none';
  };

  startBtn.addEventListener('click', () => {
    api.cameraStartStream().then(() => {
        updateButtons(true);
        step();
    }).catch(err => {
        errorSpan.textContent = 'Erreur au démarrage du flux: ' + err.message;
        errorSpan.style.display = 'inline';
    });
  });

  stopBtn.addEventListener('click', () => {
    api.cameraStopStream().then(() => {
        if (timer) clearTimeout(timer);
        updateButtons(false);
    }).catch(err => {
        alert('Erreur à l\'arrêt du flux: ' + err.message);
    });
  });

  // Cleanup au cas où la vue est détruite sans que l'élément soit déconnecté
  // (sécurité, même si isConnected est la méthode principale)
  const observer = new MutationObserver((mutations) => {
    if (!document.body.contains(el)) {
      if (timer) clearTimeout(timer);
      observer.disconnect();
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}
