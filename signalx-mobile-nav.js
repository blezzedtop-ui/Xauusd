/* SignalX mobile navigation. Keeps existing section IDs/actions intact. */
(function(){
  function init(){
    const nav=document.querySelector('.sidebar .nav');
    const more=document.getElementById('mobileMoreBtn');
    if(!nav||!more||nav.dataset.sxMobileReady==='1') return;
    nav.dataset.sxMobileReady='1';
    const overlay=document.createElement('div');
    overlay.className='sx-mobile-more';
    overlay.id='sxMobileMore';
    overlay.innerHTML='<div class="sx-mobile-more-card"><button type="button" class="btn primary sx-mobile-more-close">✕ Close menu</button><div class="sx-mobile-more-grid"></div></div>';
    document.body.appendChild(overlay);
    const grid=overlay.querySelector('.sx-mobile-more-grid');
    nav.querySelectorAll('button[data-section],form.nav-external-form').forEach(item=>{
      const source=item.matches('form')?item.querySelector('button'):item;
      if(!source) return;
      const section=source.dataset.section;
      if(!section && !source.id) return;
      const b=document.createElement('button');
      b.type='button'; b.textContent=source.textContent.trim();
      if(source.classList.contains('admin-only')) b.classList.add('admin-only');
      b.dataset.section=section||'';
      if(section) b.addEventListener('click',function(){
        overlay.classList.remove('open');
        if(typeof window.openSection==='function') window.openSection(section);
        else source.click();
      });
      if(source.id==='eurUsdPageBtn') b.addEventListener('click',function(){window.location.assign(new URL('/eurusd',window.location.origin).href)});
      grid.appendChild(b);
    });
    more.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();overlay.classList.add('open')});
    overlay.addEventListener('click',function(e){if(e.target===overlay)overlay.classList.remove('open')});
    overlay.querySelector('.sx-mobile-more-close').addEventListener('click',function(){overlay.classList.remove('open')});
    // Any non-functional visual button gets a visible response instead of doing nothing.
    document.addEventListener('click',function(e){
      const b=e.target.closest?.('button'); if(!b) return;
      if(b.id==='mobileMoreBtn'||b.classList.contains('sx-mobile-more-close')) return;
      if(b.dataset.section||b.dataset.interval||b.dataset.signalInterval||b.dataset.classicInterval||b.dataset.snrInterval) return;
      if(b.id||b.classList.contains('sx-pro-btn')) return;
      if(b.closest('.sx-mobile-more')) return;
      const toast=document.getElementById('toast');
      if(toast){toast.textContent=(b.textContent.trim()||'Tugma')+' — tayyor';toast.classList.add('show');clearTimeout(window.__sxBtnToast);window.__sxBtnToast=setTimeout(()=>toast.classList.remove('show'),1500)}
    },true);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init,{once:true}); else init();
})();
