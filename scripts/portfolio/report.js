(() => {
  'use strict';
  const viewer = document.getElementById('chart-viewer');
  const image = document.getElementById('viewer-image');
  const title = document.getElementById('viewer-title');
  const caption = document.getElementById('viewer-caption');
  const scroll = viewer.querySelector('.viewer-scroll');
  const toggle = document.getElementById('size-toggle');
  let opener;
  const resetSize = () => {
    scroll.classList.remove('full');
    toggle.setAttribute('aria-pressed', 'false');
    toggle.textContent = 'Use full size';
  };
  if (typeof viewer.showModal === 'function') {
    document.querySelectorAll('.zoom').forEach(button => {
      button.hidden = false;
      button.addEventListener('click', () => {
        const figure = button.closest('figure');
        const source = figure.querySelector('img');
        opener = button;
        image.src = source.src;
        image.alt = source.alt;
        title.textContent = figure.querySelector('h3').textContent;
        caption.textContent = figure.querySelector('figcaption').textContent;
        resetSize();
        viewer.showModal();
        scroll.scrollTop = 0;
        scroll.scrollLeft = 0;
        document.getElementById('close-viewer').focus();
      });
    });
  }
  document.getElementById('close-viewer').addEventListener('click', () => viewer.close());
  viewer.addEventListener('click', event => {
    if (event.target === viewer) {
      const box = viewer.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right ||
          event.clientY < box.top || event.clientY > box.bottom) viewer.close();
    }
  });
  viewer.addEventListener('close', () => { if (opener) opener.focus(); });
  toggle.addEventListener('click', () => {
    const full = scroll.classList.toggle('full');
    toggle.setAttribute('aria-pressed', String(full));
    toggle.textContent = full ? 'Fit to window' : 'Use full size';
  });
  const revealHash = () => {
    const target = document.getElementById(location.hash.slice(1));
    if (!target) return;
    if (target.tagName === 'DETAILS') target.open = true;
    let parent = target.parentElement;
    while (parent) {
      if (parent.tagName === 'DETAILS') parent.open = true;
      parent = parent.parentElement;
    }
  };
  window.addEventListener('hashchange', revealHash);
  revealHash();
  if ('IntersectionObserver' in window) {
    const links = [...document.querySelectorAll('nav a')];
    const observer = new IntersectionObserver(entries => {
      const visible = entries.filter(entry => entry.isIntersecting);
      if (!visible.length) return;
      links.forEach(link => link.removeAttribute('aria-current'));
      const link = links.find(item => item.hash === '#' + visible[0].target.id);
      if (link) link.setAttribute('aria-current', 'location');
    }, {rootMargin: '-5% 0px -65% 0px'});
    document.querySelectorAll('main > section, main > details').forEach(section => observer.observe(section));
  }
  let closedForPrint = [];
  window.addEventListener('beforeprint', () => {
    if (viewer.open) viewer.close();
    closedForPrint = [...document.querySelectorAll('details:not([open])')];
    closedForPrint.forEach(detail => { detail.open = true; });
  });
  window.addEventListener('afterprint', () => {
    closedForPrint.forEach(detail => { detail.open = false; });
    closedForPrint = [];
  });
})();
