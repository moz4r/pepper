export function router(routes, api){
  const app = document.getElementById('app');
  let currentModule = null;

  function render(){
    // Cleanup old module
    if (currentModule && typeof currentModule.cleanup === 'function') {
      currentModule.cleanup();
    }

    const key = location.hash || '#/';
    const mod = routes[key] || routes['#/'];
    currentModule = mod;

    app.innerHTML = '';
    if (typeof mod.render === 'function') {
      mod.render(app, api);
    }

    setActive();
  }

  function setActive(){
    document.querySelectorAll('nav a').forEach(a=>{
      if(a.getAttribute('href') === (location.hash || '#/')) a.classList.add('active'); else a.classList.remove('active');
    });
  }

  window.addEventListener('hashchange', render);
  render();
}
export const linkTo = (h)=>{ location.hash = h; };
