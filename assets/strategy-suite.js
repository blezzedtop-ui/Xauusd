/* Independent sections share rendering, never trading decisions. */
(function () {
  'use strict';
  const sections = {
    ictSection: 'ict-ai-pro', msaiStrategySection: 'snr', smartAnalysisSection: 'ai-analysis',
    trendChannelSection: 'trend', trendLineSection: 'trendline', analysisSection: 'technical',
    classicSection: 'classic', smcSection: 'ob', fibonacciSection: 'fibonacci'
  };
  const inFlight = new Map();
  const configs = new Map();
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = x => x == null ? '—' : Number(x).toLocaleString('en-US', {maximumFractionDigits:5});
  const sectionFor = mid => document.getElementById(Object.keys(sections).find(k => sections[k] === mid));
  const metric = (label, value) => `<div class="metric"><small>${esc(label)}</small><b>${esc(value)}</b></div>`;

  function frame(mid, cfg) {
    const el = sectionFor(mid);
    if (!el || el.querySelector('.sx9-panel')) return;
    el.innerHTML = `<div class="card sx9-panel"><div class="section-head"><div><h2>${esc(cfg.source)}</h2>
      <p class="mini">${esc(cfg.name)}</p></div><button class="btn" type="button" data-sx9-refresh="${mid}">Yangilash</button></div>
      <p class="sx9-rules">${esc(cfg.rules)}</p>
      <form class="sx9-config" data-sx9-config="${mid}"><label>Timeframe<select name="interval" aria-label="${esc(cfg.source)} timeframe">
      ${(mid === 'ict-ai-pro' ? ['5min'] : ['5min','15min','30min','1h','4h']).map(tf=>`<option ${tf===cfg.interval?'selected':''}>${tf}</option>`).join('')}</select></label>
      <label>Target RR — 1:<input name="target_rr" type="number" min="1" step="any" required value="${cfg.target_rr}" aria-label="${esc(cfg.source)} target RR"></label>
      <button type="submit" class="btn primary">Saqlash</button><span class="mini sx9-config-note">Admin sozlaydi. RR ≥ 1, yuqori chegara yo‘q. Yangi yopilgan shamdan qo‘llanadi.</span></form>
      <div class="sx9-live" role="status" aria-live="polite">Ma’lumot yuklanmoqda…</div>
      <p class="mini">AI bahosi — yutuq ehtimoli emas. Spread/slippage sabab MT5 qayta tekshiradi. Real hisobdan oldin demo forward-test zarur.</p></div>`;
  }

  function plot(x) {
    const cs = (x.candles || []).filter(c=>['time','open','high','low','close'].every(k=>Number.isFinite(c[k])));
    if (!cs.length) return '<div class="sx9-chart-empty">Tekshirilgan real shamlar mavjud emas.</div>';
    const levels = [['ENTRY',x.entry,'#a7b8e8'],['SL',x.stop_loss,'#ff7785'],['TP',x.take_profit?.[0],'#52dec1']].filter(a=>Number.isFinite(a[1]));
    const values = cs.flatMap(c=>[c.low,c.high]).concat(levels.map(a=>a[1]));
    const lo = Math.min(...values), hi = Math.max(...values), span = Math.max(hi-lo,.01);
    const y = v => 270-(v-lo)/span*240;
    const step = 690/cs.length, cx = i=>15+step*(i+.5);
    const grid = [0,1,2,3,4].map(i=>{const v=lo+i*span/4;return `<line x1="10" y1="${y(v)}" x2="708" y2="${y(v)}" stroke="#27354f"/><text x="716" y="${y(v)+4}">${esc(num(v))}</text>`;}).join('');
    const bars = cs.map((c,i)=>{const color=c.close>=c.open?'#52dec1':'#ff7785';return `<line x1="${cx(i)}" y1="${y(c.high)}" x2="${cx(i)}" y2="${y(c.low)}" stroke="${color}"/><rect x="${cx(i)-step*.3}" y="${Math.min(y(c.open),y(c.close))}" width="${Math.max(1,step*.6)}" height="${Math.max(1,Math.abs(y(c.open)-y(c.close)))}" fill="${color}"/>`;}).join('');
    const lines = levels.map(([name,v,color])=>`<line x1="10" y1="${y(v)}" x2="708" y2="${y(v)}" stroke="${color}" stroke-dasharray="5 4"/><text x="20" y="${y(v)-5}" fill="${color}">${name} ${esc(num(v))}</text>`).join('');
    const stamp=c=>new Date(c.time*1000).toLocaleString();
    return `<div class="sx9-chart"><svg viewBox="0 0 810 310" role="img" aria-label="${esc(x.source)}: real yopilgan shamlar, Entry SL TP"><title>${esc(x.symbol)} · ${esc(x.interval)} · ${esc(x.provider)}</title>${grid}${bars}${lines}<text x="15" y="300">${esc(stamp(cs[0]))}</text><text x="475" y="300">${esc(stamp(cs.at(-1)))}</text></svg></div>`;
  }

  function render(x, journal, catalog) {
    const ai=x.ai_validation || {}, sig=x.signal || 'WAIT';
    const state=sig==='WAIT' ? x.state : 'RULES + AI PASS';
    const evidence=x.evidence && Object.keys(x.evidence).length ? x.evidence : (x.checks || {});
    const status=journal?.saved ? `History: ${journal.signal_id}` : 'History: tasdiqlangan BUY/SELL kutilmoqda';
    return `<div class="section-head"><strong class="signal-main ${sig.toLowerCase()}">${esc(sig)}</strong><span class="pill">${esc(state)}</span></div>
      <p class="mini">${esc(x.symbol || 'XAU/USD')} · ${esc(x.interval)} / HTF ${esc(x.higher_interval)} · ${esc(x.provider || 'LIVE DATA REQUIRED')} · ${x.candle_time?esc(new Date(Number(x.candle_time)*1000).toLocaleString()):'—'}</p>
      <div class="sx9-metrics">${metric('ENTRY',num(x.entry))}${metric('STOP LOSS',num(x.stop_loss))}${metric('TAKE PROFIT',num(x.take_profit?.[0]))}${metric('ACTUAL RR',x.risk_reward!=null?'1:'+num(x.risk_reward):'—')}</div>
      ${plot(x)}<div class="sx9-metrics">${metric('AI provider',ai.mode || 'Setup kutilmoqda')}${metric('AI bahosi',ai.confidence!=null?ai.confidence+' / 100':'—')}${metric('AI agreement',ai.agreement!=null?ai.agreement+' / 100':'—')}${metric('AutoTrade',catalog.autotrade_enabled?'ON · '+catalog.transport:'OFF')}</div>
      <p>${esc(ai.reasoning || x.reason || 'Setup kutilmoqda')}</p><p class="mini">${esc(status)} · MT5: ${journal?.queued?'navbatga yuborildi':'serverdagi mustaqil skaner va execution tekshiruvlari orqali'}</p>
      <details><summary>Strategiya dalillari</summary><dl class="sx9-evidence">${Object.entries(evidence).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(typeof v==='object'?JSON.stringify(v):v)}</dd>`).join('')}</dl></details>`;
  }

  async function load(mid) {
    if (inFlight.has(mid)) return inFlight.get(mid);
    const task = (async()=>{
      const el=sectionFor(mid); if(!el) return;
      try {
        const catalog=await api('/api/v1/strategies');
        catalog.items.forEach(c=>configs.set(c.module_id,c));
        const cfg=configs.get(mid); frame(mid,cfg);
        el.querySelectorAll('.sx9-config input,.sx9-config select,.sx9-config button').forEach(n=>n.disabled=!catalog.can_configure);
        const x=await api('/api/v1/strategies/'+mid);
        const journal=['BUY','SELL'].includes(x.signal) ? await api('/api/v1/strategies/'+mid+'/record?event_id='+encodeURIComponent(x.event_id),{method:'POST'}) : null;
        el.querySelector('.sx9-live').innerHTML=render(x,journal,catalog);
      } catch(e) {
        const panel=el.querySelector('.sx9-live') || el;
        panel.innerHTML=`<div class="card"><h3>WAIT — signal berilmadi</h3><p>${esc(e.message || 'Serverga ulanib bo‘lmadi')}</p><p class="mini">Hisobga kiring va real data/AI ulanishini tekshiring.</p><button class="btn" data-sx9-refresh="${mid}">Qayta urinish</button></div>`;
      }
    })().finally(()=>inFlight.delete(mid));
    inFlight.set(mid,task); return task;
  }

  document.addEventListener('click',e=>{
    const nav=e.target.closest('[data-sx9-open]');if(nav){e.preventDefault();openSection(nav.dataset.sx9Open);return;}
    const btn=e.target.closest('[data-sx9-refresh]'); if(btn){e.preventDefault();load(btn.dataset.sx9Refresh);}
  });
  document.addEventListener('submit',async e=>{
    const form=e.target.closest('[data-sx9-config]'); if(!form)return;
    e.preventDefault(); if(!form.reportValidity())return;
    const mid=form.dataset.sx9Config, rr=Number(form.elements.target_rr.value);
    if(!Number.isFinite(rr)||rr<1){showToast('RR kamida 1 va chekli son bo‘lishi kerak.');return;}
    const button=form.querySelector('button'); button.disabled=true;
    try {
      await api('/api/v1/strategies/'+mid+'/config',{method:'PUT',body:JSON.stringify({interval:form.elements.interval.value,target_rr:rr})});
      form.querySelector('.sx9-config-note').textContent='Saqlandi. Mavjud signal o‘zgarmaydi; keyingi yangi shamdan qo‘llanadi.';
      await load(mid);
    } catch(err){showToast(err.message);} finally{button.disabled=false;}
  });
  window.SignalXSuite={load,sections,plot};
})();
