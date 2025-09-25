export function router(routes){
  const app = document.getElementById('app');
  function render(){
    const key = location.hash || '#/';
    const mod = routes[key] || routes['#/'];
    app.innerHTML = '';
    mod.render(app);
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
