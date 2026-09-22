let IS_ADMIN=false;const symbol='XAU/USD';const TV_SYMBOL='OANDA:XAUUSD';let interval='5min',pivotInterval='5min',aiInterval='5min',classicInterval='5min',token=localStorage.getItem('trading_token')||'',authMode='login',chart,series,chart2,series2,countdownData={close_timestamp:null},marketWS=null,liveCandle=null,lastTickTs=0,lastRestQuoteAt=0,streamKey='';
const $=id=>document.getElementById(id);let trendLineInterval='5min';let trendLiveRefreshTimer=null;let trendOverlayChart=null,trendOverlaySeries=null,trendOverlayLayers=[];const setText=(id,v)=>{const el=$(id);if(el)el.textContent=v??'—';};const fmt=v=>v==null?'—':Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:4});

function applyRoleAccess(isAdmin){
  IS_ADMIN=!!isAdmin;
  document.body.classList.toggle('is-admin', IS_ADMIN);
  document.querySelectorAll('.admin-only').forEach(el=>{el.setAttribute('aria-hidden', IS_ADMIN?'false':'true');});
  if(!IS_ADMIN){
    const active=document.querySelector('.section.active.admin-only');
    if(active){ openSection('ictSection'); }
  }
}
function requireAdminClient(){
  if(!IS_ADMIN) throw Error('Bu bo‘lim faqat administrator uchun. Oddiy user AI tizimidan foydalana olmaydi.');
}
function showToast(m){const el=$('toast');if(!el){console.warn('SignalX toast:',m);return;}el.textContent=String(m??'');el.classList.add('show');clearTimeout(showToast._timer);showToast._timer=setTimeout(()=>el.classList.remove('show'),2300)}

// Cloud deployment: when the frontend and FastAPI are on the same Railway service, leave API_BASE_URL empty.
// When hosted separately on Netlify, set window.API_BASE_URL to the public FastAPI URL.
const CONFIGURED_API=(window.API_BASE_URL||document.querySelector('meta[name=api-base]')?.content||'').trim().replace(/\/$/,'');
const LOCAL_API=(location.protocol==='http:'||location.protocol==='https:') ? location.origin.replace(/\/$/,'') : '';
const API_BASE=CONFIGURED_API || ((location.protocol==='http:'||location.protocol==='https:') ? location.origin : (LOCAL_API || 'http://127.0.0.1:8000'));
const API_CANDIDATES=[API_BASE].filter(Boolean);
const NODE_MARKET_URL=(window.NODE_MARKET_URL||'').replace(/\/$/,'');
const IS_NETLIFY=/netlify\.app$|netlify\.com$/i.test(location.hostname);
const DISABLE_MARKET_WS=window.DISABLE_MARKET_WS!==false;
async function nodeMarketHealth(){if(!NODE_MARKET_URL)return null;try{const r=await fetch(`${NODE_MARKET_URL}/health`,{cache:'no-store'});if(!r.ok) return null;return await r.json()}catch{return null}}
async function api(path,opt={}){const headers={'Content-Type':'application/json',...(opt.headers||{})};token=localStorage.getItem('trading_token')||token||'';if(token)headers.Authorization='Bearer '+token;let last;for(const base of API_CANDIDATES){try{const url=path.startsWith('http')?path:base+path;const r=await fetch(url,{...opt,headers,cache:'no-store'});let d={};try{d=await r.json()}catch{}if(!r.ok){ const detail=d?.detail; let msg=d?.message||''; if(Array.isArray(detail)) msg=detail.map(x=>x?.msg||x?.message||JSON.stringify(x)).join('; '); else if(detail&&typeof detail==='object') msg=detail.msg||detail.message||JSON.stringify(detail); else if(detail) msg=String(detail); throw Error(msg||'HTTP '+r.status); }return d}catch(e){last=e}}if(last instanceof TypeError){throw Error('Cloud backendga ulanib bo‘lmadi. Saytning cloud serveri ulanmagan yoki hozircha ishlamayapti.') }throw last}
function tvInterval(tf){return ({'1min':'1','5min':'5','15min':'15','30min':'30','1h':'60','4h':'240','1day':'D'})[tf]||'5'}
function mountTradingView(id, tf=interval){
 const el=$(id); if(!el)return;
 el.innerHTML='';
 const wrap=document.createElement('div');
 wrap.className='tradingview-widget-container';
 wrap.style.cssText='height:100%;width:100%';
 const widget=document.createElement('div');
 widget.className='tradingview-widget-container__widget';
 widget.style.cssText='height:100%;width:100%';
 wrap.appendChild(widget); el.appendChild(wrap);
 const script=document.createElement('script');
 script.type='text/javascript'; script.src='https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'; script.async=true;
 const cfg={
   autosize:true,
   symbol:TV_SYMBOL,
   interval:tvInterval(tf),
   timezone:'Etc/UTC',
   theme:'dark',
   style:'1',
   locale:'en',
   withdateranges:true,
   hide_side_toolbar:false,
   allow_symbol_change:false,
   save_image:false,
   calendar:false,
   details:false,
   hotlist:false,
   studies:[],
   support_host:'https://www.tradingview.com'
 };
 script.innerHTML=JSON.stringify(cfg);
 wrap.appendChild(script);
 $('mode').textContent='TRADINGVIEW LIVE'; $('mode').style.color='var(--green)'; $('chartStatus').textContent='LIVE';
 return true;
}
function applyChart(candles,mode){
 const data=(candles||[]).map(x=>({time:Number(x.time),open:+x.open,high:+x.high,low:+x.low,close:+x.close})).filter((x,i,a)=>i===0||x.time>a[i-1].time);
 liveCandle=data[data.length-1]||null;
 if(data.length){const first=data[0].time,last=data[data.length-1].time,days=Math.max(1,Math.round((last-first)/86400));$('change').textContent=`TradingView LIVE · ${data.length.toLocaleString()} candles · ${days} days history`;$('historyInfo').textContent=`TradingView LIVE · ${days}+ days · ${data.length.toLocaleString()} candles`;}
 $('mode').textContent='TRADINGVIEW LIVE'; $('mode').style.color='var(--green)'; $('chartStatus').textContent='LIVE';
}
function markSignal(signal, candleTime){
 // TradingView Advanced Chart is an isolated live widget, so backend markers are
 // intentionally kept out of the iframe. Signal details remain in the dashboard.
 return;
}
function setTf(v){
 interval=v; liveCandle=null;
 document.querySelectorAll('[data-interval]').forEach(b=>b.classList.toggle('active',b.dataset.interval===v));
 if($('tfLabel'))$('tfLabel').textContent=({'1min':'1 MIN','5min':'5 MIN','15min':'15 MIN','30min':'30 MIN','1h':'1 HOUR','4h':'4 HOUR','1day':'1 DAY'})[v]||v;
 closeMarketStream();
 mountTradingView('chart', interval);
 if($('chartSection')?.classList.contains('active')) setTimeout(()=>mountTradingView('chart2', interval),50);
 loadChartHistory().catch(e=>{setText('signalReason','Chart data error: '+e.message)});

 connectMarketStream();
}
async function loadAIProviders(){
  if(!IS_ADMIN)return;
  const el=$('aiProvidersGrid'); if(!el)return;
  try{
    const d=await api('/api/v1/ai/providers');
    const names={groq:'Groq #1 · GPT-OSS 120B',groq_2:'Groq #2 · Qwen 3.8 27B',gemini:'Google Gemini Flash',anthropic:'Claude Fable 5',anthropic_2:'Claude Opus 5',anthropic_3:'Claude Sonnet 5',openrouter:'OpenRouter Free',mistral:'Mistral',cerebras:'Cerebras',cloudflare:'Cloudflare Workers AI',deepseek:'DeepSeek Flash',openai:'OpenAI',huggingface:'Hugging Face'};
    const safe=(v)=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
    const mode=d.control?.mode||'AUTO';
    ['aiAutoMode','aiAllOn','aiAllOff'].forEach(id=>{const b=$(id);if(b)b.classList.remove('active');});
    const activeId=mode==='AUTO'?'aiAutoMode':mode==='ALL_ON'?'aiAllOn':mode==='ALL_OFF'?'aiAllOff':null;
    if(activeId&&$(activeId))$(activeId).classList.add('active');
        el.innerHTML=(d.providers||[]).map((x,i)=>{const st=x.status||'READY';const cls=st==='ONLINE'?'buy':st==='OFFLINE'?'sell':st==='LIMITED'?'wait':st==='OFF'?'down':'wait';const score=x.score!=null?`<span class="pill">${safe(x.score)} ball</span>`:'';const rank=`#${i+1}`;const code=x.http_status?` · HTTP ${safe(x.http_status)}`:'';const reason=x.reason||({ONLINE:'AI so‘rovi muvaffaqiyatli bajarildi.',LIMITED:'Limit/quota yoki vaqtinchalik cheklov.',OFFLINE:'Provider javob bermadi yoki API xatosi.',READY:'Hali real AI so‘rovi bilan tekshirilmagan.',OFF:'Qo‘lda o‘chirilgan.'}[st]||'Noma’lum holat.');const checked=x.checked_at?` · ${new Date(x.checked_at).toLocaleTimeString()}`:'';const toggle=x.enabled===false?'Yoqish':'O‘chirish';return `<div class="component ai-provider-card"><div style="display:flex;justify-content:space-between;gap:8px;align-items:center"><small>${rank} · ${safe(names[x.id]||x.id)}</small><b class="${cls}">${safe(st)}${code}</b></div><div class="mini" style="display:flex;justify-content:space-between;gap:8px;align-items:center"><span>${safe(x.model||'')}</span>${score}</div><div class="mini ai-reason"><b>Sabab:</b> ${safe(reason)}</div><div class="mini">Kuch ${safe(x.quality??'—')} · Tezlik ${safe(x.speed??'—')} · Limit ${safe(x.capacity??'—')} · Tejamkorlik ${safe(x.cost??'—')}${checked?`<span style="opacity:.65">${safe(checked)}</span>`:''}</div><button class="btn ai-toggle" type="button" data-ai-toggle="${safe(x.id)}" data-enabled="${x.enabled!==false}">${toggle}</button></div>`}).join('') || '<div class="mini">API key sozlangan AI tizimi topilmadi.</div>';
  }catch(e){el.innerHTML='<div class="mini">AI provider status unavailable.</div>'}
}

function fallbackEscape(value){return String(value??'').replace(/[&<>"']/g,ch=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[ch]));}
function fallbackStatusClass(status){const s=String(status||'').toUpperCase();return s==='ONLINE'||s==='LIVE'?'buy':s==='OFFLINE'||s==='FAILED'||s==='BLOCKED'||s==='BILLING'?'sell':'wait';}
async function loadAllFallback(){
  if(!IS_ADMIN)return;
  const aiGrid=$('fallbackAIGrid'), marketGrid=$('fallbackMarketGrid'), summary=$('fallbackSummary'), note=$('fallbackNote');
  if(!aiGrid||!marketGrid||!summary)return;
  aiGrid.innerHTML='<div class="mini">AI providerlar tekshirilmoqda…</div>';
  marketGrid.innerHTML='<div class="mini">Market providerlar tekshirilmoqda…</div>';
  try{
    const [ai,market]=await Promise.all([api('/api/v1/ai/providers'),api('/api/v1/market/providers')]);
    const aiRows=Array.isArray(ai.providers)?ai.providers:[];
    const marketRows=Array.isArray(market.providers)?market.providers:[];
    const online=aiRows.filter(x=>String(x.status).toUpperCase()==='ONLINE').length;
    const ready=aiRows.filter(x=>['READY','ONLINE','LIMITED'].includes(String(x.status).toUpperCase())).length;
    const liveMarket=marketRows.filter(x=>String(x.status||'').toUpperCase()==='ONLINE'||x.last_success_at).length;
    summary.innerHTML=`<div class="metric"><small>AI ulangan</small><b>${aiRows.length}</b></div><div class="metric"><small>AI ONLINE</small><b class="buy">${online}</b></div><div class="metric"><small>AI tayyor</small><b>${ready}</b></div><div class="metric"><small>Market faol</small><b>${liveMarket} / ${marketRows.length}</b></div>`;
    aiGrid.innerHTML=aiRows.map((x,i)=>{const status=String(x.status||'READY').toUpperCase();const reason=x.reason||'Hali real AI so‘rovi bilan tekshirilmagan.';const cooldown=x.cooldown_seconds_remaining?` · ${x.cooldown_seconds_remaining}s cooldown`:'';return `<div class="component"><small>#${i+1} · ${fallbackEscape(x.id)}</small><b class="${fallbackStatusClass(status)}">${fallbackEscape(status)}</b><div class="mini">${fallbackEscape(x.model||'Model tanlanmagan')}</div><div class="mini ai-reason">${fallbackEscape(reason)}${fallbackEscape(cooldown)}</div></div>`;}).join('')||'<div class="mini">Ulangan AI provider topilmadi. Railway API kalitlarini tekshiring.</div>';
    marketGrid.innerHTML=marketRows.map((x,i)=>{const status=String(x.status|| (x.enabled?'READY':'OFF')).toUpperCase();const count=x.candles_count!=null?` · ${x.candles_count} candle`:'';const err=x.error?` · ${x.error}`:'';return `<div class="component"><small>#${i+1} · ${fallbackEscape(x.name||x.id)}</small><b class="${fallbackStatusClass(status)}">${fallbackEscape(status)}</b><div class="mini">${x.enabled?'Enabled':'Disabled'}${fallbackEscape(count)}</div><div class="mini ai-reason">${fallbackEscape(err||x.last_success_at||'Hali so‘rovda tekshirilmagan.')}</div></div>`;}).join('')||'<div class="mini">Market provider topilmadi.</div>';
    if(note)note.textContent=`AI router: ${ai.router||'AUTO'} · Automatic failover: ${ai.automatic_failover?'ON':'OFF'} · Market tartibi: ${(market.order||[]).join(' → ')||'—'}.`;
  }catch(error){
    const message=fallbackEscape(error?.message||'Fallback status yuklanmadi.');
    aiGrid.innerHTML=`<div class="mini sell">${message}</div>`;
    marketGrid.innerHTML='<div class="mini">Market holatini AI statusdan alohida tekshirib bo‘lmadi.</div>';
    summary.innerHTML='<div class="metric"><small>Status</small><b class="sell">ERROR</b></div>';
  }
}

async function controlAIProvider(provider, enabled){ requireAdminClient(); await api('/api/v1/ai/providers/control',{method:'POST',body:JSON.stringify({provider,enabled})}); await loadAIProviders(); }
async function setAIControlMode(mode){ requireAdminClient(); await api('/api/v1/ai/providers/control',{method:'POST',body:JSON.stringify({mode})}); await loadAIProviders(); showToast(`AI rejimi: ${mode}`); }
function bindAIControls(){
  const grid=$('aiProvidersGrid');
  if(grid&&grid.dataset.controlsBound!=='1'){
    grid.dataset.controlsBound='1';
    grid.addEventListener('click',e=>{const b=e.target.closest('[data-ai-toggle]'); if(!b)return; const provider=b.dataset.aiToggle; const enabled=b.dataset.enabled!=='true'; controlAIProvider(provider,enabled).catch(err=>showToast(err.message||'AI boshqaruv xatosi'));});
  }
  [['aiAllOn','ALL_ON'],['aiAllOff','ALL_OFF'],['aiAutoMode','AUTO']].forEach(([id,mode])=>{
    const b=$(id); if(!b||b.dataset.bound==='1')return; b.dataset.bound='1';
    b.addEventListener('click',()=>setAIControlMode(mode).catch(err=>showToast(err.message||'AI boshqaruv xatosi')));
  });
}

async function loadChartHistory(){
 const c=await api(`/api/v1/candles/${encodeURIComponent(symbol)}?interval=${interval}&limit=500`);
 if(c.mode!=='live') throw Error(c.warning||'LIVE market data unavailable');
 applyChart(c.candles,c.mode); countdownData=c.candle; updateCountdown();
}
async function loadAnalysisOnly(){ return window.SignalXSuite.load("technical"); }
async function loadSmartAnalysis(){ return window.SignalXSuite.load("ai-analysis"); }
function mountTradingViewTechnical(containerId, tf){
  const el=$(containerId); if(!el) return; el.innerHTML='';
  const script=document.createElement('script');
  script.src='https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js';
  script.type='text/javascript'; script.async=true;
  const intervalMap={'1min':'1m','5min':'5m','15min':'15m','30min':'30m','1h':'1h','4h':'4h','1day':'1D'};
  script.textContent=JSON.stringify({interval:intervalMap[tf]||'5m',width:'100%',height:500,symbol:TV_SYMBOL,showIntervalTabs:true,displayMode:'single',colorTheme:'dark',isTransparent:true,locale:'en',largeChartUrl:''});
  el.appendChild(script);
}
function mountTradingViewCalendar(){
  const el=$('tvCalendarWidget'); if(!el) return;
  // Use TradingView's official iframe widget. It carries its own market/event data,
  // so the user's Railway project does not need an economic-calendar API key.
  el.innerHTML='';
  const cfg={width:'100%',height:680,importanceFilter:'-1,0,1',colorTheme:'dark',isTransparent:true,locale:'en',utm_source:location.hostname||'xauusd-trading',utm_medium:'widget',utm_campaign:'events'};
  const iframe=document.createElement('iframe');
  iframe.title='TradingView Economic Calendar';
  iframe.loading='lazy';
  iframe.referrerPolicy='origin';
  iframe.frameBorder='0';
  iframe.scrolling='no';
  iframe.style.width='100%'; iframe.style.height='680px'; iframe.style.border='0'; iframe.style.display='block';
  iframe.src='https://www.tradingview-widget.com/embed-widget/events/?locale=en#'+encodeURIComponent(JSON.stringify(cfg));
  el.appendChild(iframe);
  el.dataset.loaded='1';
}
async function loadPivots(tf=pivotInterval){
  pivotInterval=tf;
  try{
    const d=await api(`/api/v1/pivots/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(tf)}`);
    const p=d.timeframes?.[tf]||{};
    $('pivotFilter').textContent=tfName(tf);
    $('pivotSource').textContent=`${tfName(tf)} Pivot · source: ${tfName(p.source_timeframe||tf)}${p.warning?' · '+p.warning:''}`;
    $('levels').innerHTML=[['R3',p.r3,'res'],['R2',p.r2,'res'],['R1',p.r1,'res'],['Pivot',p.pivot,'piv'],['S1',p.s1,'sup'],['S2',p.s2,'sup'],['S3',p.s3,'sup']].map(x=>`<div class="row"><span>${x[0]}</span><b class="${x[2]}">${fmt(x[1])}</b></div>`).join('');
  }catch(e){
    $('pivotSource').textContent='Pivot yuklanmadi: '+e.message;
  }
}
function renderAnalysis(d){const s=d?.setup||{},ta=d?.technical||{},lv=d?.levels||{};setText('signalMain',d?.direction||'WAIT');const sm=$("signalMain");if(sm){const dir=String(d?.direction||'WAIT').toLowerCase();sm.className='signal-main '+(dir==='buy'?'buy':dir==='sell'?'sell':'wait')}setText('signalReason',d?.headline||s.reason||'—');setText('entry',fmt(s.entry));setText('sl',fmt(s.stop_loss));setText('tp1',fmt((s.take_profit||[])[0]));setText('tp2',fmt((s.take_profit||[])[1]));setText('bias',lv.bias||s.pivot_filter||'—');setText('pivotFilter',lv.bias||'—');const levelsEl=$("levels");if(levelsEl){levelsEl.innerHTML=[['R3',lv.r3,'res'],['R2',lv.r2,'res'],['R1',lv.r1,'res'],['Pivot',lv.pivot,'piv'],['S1',lv.s1,'sup'],['S2',lv.s2,'sup'],['S3',lv.s3,'sup']].map(x=>`<div class="row"><span>${x[0]}</span><b class="${x[2]}">${fmt(x[1])}</b></div>`).join('')}setText('rsi',fmt(ta.rsi));setText('atr',fmt(ta.atr));setText('rsiState',ta.rsi_state||'—');setText('taTrend',ta.trend||'—');setText('taState',d?.interval?.toUpperCase()||interval);setText('taSummary',(ta.summary||'—')+(ta.ai_validation?` | AI: ${ta.ai_consensus||'—'} · ${ta.ai_validation.confidence??0}%`:'')); const f=ta.fibonacci||d?.fibonacci||{}; setText('taFibonacciSignal',f.signal||'WAIT'); setText('taFibonacciNearest',f.nearest_fibonacci?.ratio?`${f.nearest_fibonacci.ratio} · ${fmt(f.nearest_fibonacci.price)}`:'—'); setText('taFibonacciCluster',`${f.fib_cluster?.count??0} · ${f.fib_cluster?.qualified?'QUALIFIED':'WAIT'}`); setText('taFibonacciMusang',f.musang?.qualified?'QUALIFIED':'WAIT'); setText('taFibonacciReason',f.reason||'—'); setText('taFibonacciState',f.state||'—');const ai=d?.ai||{};setText('aiMode',ai.mode||'—');setText('aiSummary',ai.summary||'—');setText('confidence',ai.confidence!=null?ai.confidence+'%':'—');setText('aiBias',ai.bias||'—');setText('aiAdvice',ai.advice||'—');}
function updateCountdown(){const ts=countdownData?.close_timestamp; if(!ts)return;$('countdown').textContent=fmtDuration(Math.max(0,ts*1000-Date.now())); const close=new Date(ts*1000); $('closeTime').textContent='Close time: '+close.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});}function fmtDuration(ms){let s=Math.floor(ms/1000),h=Math.floor(s/3600);s%=3600;let m=Math.floor(s/60);s%=60;return h?`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`}
async function loadSessions(){try{const d=await api('/api/v1/sessions');const html=(d.sessions||[]).map(x=>`<div class="session ${x.open?'open':''}"><b>${x.name}</b><div class="sub">${x.local_time||''}</div><div class="status ${x.open?'up':'muted'}">${x.open?'OPEN':'CLOSED'}</div></div>`).join('');$('sessions').innerHTML=html;$('sessions2').innerHTML=html;$('sessionClock').textContent=d.utc_time||'—';$('sessionClock2').textContent=d.utc_time||'—';const g=d.market_gate||{};const gs=$('marketGateStatus');if(gs)gs.textContent=`Market Gate: ${g.status||'UNKNOWN'} · ${g.reason||'—'}`;}catch(e){}}
async function loadCalendar(){ mountTradingViewCalendar(); }

async function loadMtf(){
  try{
    const d=await api(`/api/v1/multi-timeframe/${encodeURIComponent(symbol)}`);
    $('mtfOverall').textContent=d.overall||'—';
    const order=['1min','5min','15min','30min','1h','4h','1day'];
    const frames=d.timeframes||{};
    $('mtfGrid').innerHTML=order.map(tf=>{
      const x=frames[tf]||{};
      const tr=(x.trend||'UNAVAILABLE').toUpperCase();
      const cls=tr==='BULLISH'?'buy':tr==='BEARISH'?'sell':'wait';
      return `<div class="metric"><small>${tfName(tf)}</small><b class="${cls}">${tr}</b><div class="mini">Price ${x.price!=null?fmt(x.price):'—'} · RSI ${x.rsi!=null?fmt(x.rsi):'—'}</div><div class="mini">${x.mode||''}</div></div>`;
    }).join('');
  }catch(e){$('mtfGrid').innerHTML=`<div class="card">MTF LIVE error: ${e.message}</div>`}
}
async function loadStats(){
  const zero=()=>{['totalSignals','completedSignals','wins','losses','winrate'].forEach(id=>setText(id,id==='winrate'?'0%':'0'));};
  if(!token){zero();return;}
  try{
    const d=await api(`/api/v1/signals/analytics?symbol=${encodeURIComponent(symbol)}`);
    setText('totalSignals',d.total_signals??0);setText('completedSignals',d.completed_trades??0);setText('wins',d.wins??0);setText('losses',d.losses??0);setText('winrate',(d.winrate??0)+'%');
  }catch(e){console.warn('SignalX stats:',e?.message||e);}
}
const SIGNAL_RECORD_SEEN=new Map();
function recordModuleSignal(source, response, item, intervalName, candleTime){
  if(!token) return;
  const x=item||{}; const direction=String(x.signal||response?.direction||'WAIT').toUpperCase();
  if(!['BUY','SELL'].includes(direction)) return;
  const tf=intervalName||response?.interval||interval;
  const ct=String(candleTime??x.candle_time??response?.candle_time??'');
  const key=`${symbol}|${tf}|${source}|${direction}|${ct}`;
  const now=Date.now();
  const seenAt=SIGNAL_RECORD_SEEN.get(key)||0;
  if(now-seenAt<120000) return;
  SIGNAL_RECORD_SEEN.set(key,now);
  if(SIGNAL_RECORD_SEEN.size>2000){for(const [k,t] of SIGNAL_RECORD_SEEN){if(now-t>900000) SIGNAL_RECORD_SEEN.delete(k);}}
  api('/api/v1/signals/record-module',{method:'POST',body:JSON.stringify({symbol,interval:tf,source,direction,confidence:x.confidence??response?.ai?.confidence??null,entry:x.entry??response?.setup?.entry??null,stop_loss:x.stop_loss??response?.setup?.stop_loss??null,take_profit:x.take_profit??response?.setup?.take_profit??[],headline:`${source} · ${direction}`,candle_time:ct,payload:{response:item||response}})}).catch(e=>console.warn('Signal history record',source,e));
}
let historyV2Offset=0;
const HISTORY_DETAIL_CACHE=new Map();
async function loadHistory(append=false){const list=document.getElementById('historyV2List');if(!list)return;if(!token){list.innerHTML='<div class="sx-empty">Kirish kerak.</div>';return;}const p=new URLSearchParams(),s=document.getElementById('historyV2Start')?.value||'',e=document.getElementById('historyV2End')?.value||'',sym=document.getElementById('historyV2Symbol')?.value||'',dir=document.getElementById('historyV2Direction')?.value||'',res=document.getElementById('historyV2Result')?.value||'',mod=document.getElementById('historyV2Module')?.value||'';if(s)p.set('start_date',s);if(e)p.set('end_date',e);if(sym)p.set('symbol',sym);if(dir)p.set('direction',dir);if(res)p.set('result',res);if(mod)p.set('module',mod);try{p.set('offset',String(historyV2Offset));const [rows,stats]=await Promise.all([api('/api/v2/signal-history?limit=20&'+p.toString()),api('/api/v2/signal-history/stats?'+p.toString())]),o=stats.overall||{};const K=(l,v,c='')=>`<div class="sx-kpi"><small>${l}</small><b class="${c}">${v}</b></div>`;document.getElementById('historyV2Kpis').innerHTML=[K('TOTAL SIGNALS',o.signals??0),K('WIN RATE',`${Number(o.winrate||0).toFixed(2)}%`),K('WINS',o.wins??0,'buy'),K('LOSSES',o.losses??0,'sell'),K('ACTIVE',o.active??0,'wait'),K('AVG RR',o.avg_rr?`1:${Number(o.avg_rr).toFixed(2)}`:'—'),K('TOTAL R',`${Number(o.total_r||0)>=0?'+':''}${Number(o.total_r||0).toFixed(2)}R`),K('TOTAL PROFIT',`${Number(o.total_profit||0)>=0?'+':''}${Number(o.total_profit||0).toFixed(2)}`)].join('');const days=Object.entries(stats.by_day||{});document.getElementById('historyV2Daily').innerHTML=days.length?days.slice(0,8).map(([d,x])=>`<div class="sx-kpi"><small>${d}</small><b>${Number(x.winrate||0).toFixed(2)}%</b><div class="mini">${x.signals} signals · ${x.wins} wins · ${x.losses} losses · ${Number(x.total_r||0)>=0?'+':''}${Number(x.total_r||0).toFixed(2)}R</div></div>`).join(''):'<div class="sx-empty">Tanlangan period uchun kunlik statistika yo‘q.</div>';const modules=Object.entries(stats.by_module||{});document.getElementById('historyV2Modules').innerHTML=modules.length?modules.map(([m,x])=>`<div class="sx-module"><small>${escapeHtml(m)}</small><b>${Number(x.winrate||0).toFixed(2)}%</b><div class="line">${x.signals} signals · ${x.wins} wins · ${x.losses} losses</div><div class="line">R: ${Number(x.total_r||0)>=0?'+':''}${Number(x.total_r||0).toFixed(2)} · Avg RR: ${x.avg_rr?`1:${Number(x.avg_rr).toFixed(2)}`:'—'}</div></div>`).join(''):'<div class="sx-empty">Module statistikasi yo‘q.</div>';document.getElementById('historyV2Count').textContent=`${rows.count||0} ta signal`;const items=(rows.items||[]); items.forEach(x=>{if(x&&x.signal_id)HISTORY_DETAIL_CACHE.set(String(x.signal_id),x);}); const rendered=items.map(signalCardV2).join('');list.innerHTML=append?(list.innerHTML.replace(/<div class="sx-history-more">[\s\S]*?<\/div>$/,'')+rendered):rendered;list.innerHTML=list.innerHTML||'<div class="sx-empty">Signal topilmadi.</div>';if((historyV2Offset+20)<Number(rows.total_count||0)){list.insertAdjacentHTML('beforeend',`<div class="sx-history-more"><button class="btn" type="button" id="historyV2LoadMore">Yana 20 ta yuklash</button></div>`);}}catch(err){list.innerHTML=`<div class="sx-empty">History yuklanmadi: ${escapeHtml(err?.message||'server xatosi')}</div>`;}}
function escapeHtml(v){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
function histFmt(v){if(v===null||v===undefined||v==='')return '—';const n=Number(v);return Number.isFinite(n)&&n!==0?n.toFixed(Math.abs(n)>=100?2:4):'—';}
function histTime(v){try{return new Date(v).toLocaleString('uz-UZ',{timeZone:'Asia/Tashkent'})}catch(_){return v||'—';}}
function signalCardV2(x){const cls=x.direction==='BUY'?'buy':x.direction==='SELL'?'sell':'',status=x.status||'ACTIVE',rr=x.rr?`1:${Number(x.rr).toFixed(2)}`:'—',dur=x.duration_minutes!=null?`${Number(x.duration_minutes).toFixed(0)} min`:'ACTIVE',orderType=String(x.order_type||'').toUpperCase(),pending=x.pending||['BUY_STOP','SELL_STOP','BUY_LIMIT','SELL_LIMIT'].includes(orderType),cancelReason=x.cancel_reason||((x.snapshot||{}).result||{}).reason||((x.snapshot||{}).execution||{}).reason||'';const isCancelled=String(status).toUpperCase().startsWith('CANCELLED')||String(status).toUpperCase().includes('INVALID');const statusText=isCancelled&&cancelReason?`CANCELLED · ${cancelReason}`:(isCancelled&&String(status).toUpperCase()!=='CANCELLED'?`CANCELLED · ${status.replace(/^CANCELLED[_ ]?/i,'').replace(/_/g,' ')}`:status);return `<article class="sx-signal-card ${cls}"><div class="sx-signal-top"><div><div class="sx-signal-badge">${x.direction==='BUY'?'🟢':x.direction==='SELL'?'🔴':'⚪'} ${escapeHtml(x.direction||'—')} ${pending&&orderType?`· ${escapeHtml(orderType)}`:''}</div><div class="sx-signal-meta">${escapeHtml(x.symbol)} · ${tfName(x.interval)} · ${escapeHtml(x.source||'Signals')} · ${histTime(x.created_at)}</div></div><div class="sx-status">${escapeHtml(statusText)} ${x.score!=null?`· ${histFmt(x.score)}%`:''}</div></div><div class="sx-signal-levels"><div class="sx-level"><span>ENTRY</span><b>${histFmt(x.entry)}</b></div><div class="sx-level"><span>SL</span><b>${histFmt(x.sl)}</b></div><div class="sx-level"><span>TP1</span><b>${histFmt(x.tp1)}</b></div><div class="sx-level"><span>TP2</span><b>${histFmt(x.tp2)}</b></div><div class="sx-level"><span>RR</span><b>${rr}</b></div><div class="sx-level"><span>R-MULTIPLE</span><b>${x.r_multiple!=null?(Number(x.r_multiple)>=0?'+':'')+Number(x.r_multiple).toFixed(2)+'R':'—'}</b></div></div><div class="sx-signal-bottom"><div class="sx-signal-meta">ID: <b>${escapeHtml(x.signal_id)}</b> · ${pending?'Pending: '+escapeHtml(orderType||'ORDER'):''}${pending?' · ':''}Duration: ${dur}${x.closed_at?` · Closed: ${histTime(x.closed_at)}`:''}</div><button class="btn" data-history-detail="${escapeHtml(x.signal_id)}" type="button">View Details</button></div></article>`}
function renderHistoryDetail(x){const snap=x.snapshot||{},time=snap.timeline||{},execution=snap.execution||{},executionTimeline=execution.timeline||{},setup=snap.setup||{},entries=[];function walk(obj,p=''){if(!obj||typeof obj!=='object')return;Object.entries(obj).forEach(([k,v])=>{if(k==='history_snapshot'||k==='payload')return;const key=p?p+'.'+k:k;if(v&&typeof v==='object'&&Object.keys(v).length<12)walk(v,key);else entries.push([key,typeof v==='object'?JSON.stringify(v):v]);});}walk(snap);return `<div class="sx-detail-grid"><div class="metric"><small>SYMBOL</small><b>${escapeHtml(x.symbol)}</b></div><div class="metric"><small>DIRECTION</small><b>${escapeHtml(x.direction)}</b></div><div class="metric"><small>SCORE</small><b>${histFmt(x.score)}%</b></div><div class="metric"><small>STRENGTH</small><b>${escapeHtml(x.strength||'—')}</b></div><div class="metric"><small>ENTRY</small><b>${histFmt(x.entry)}</b></div><div class="metric"><small>SL</small><b>${histFmt(x.sl)}</b></div><div class="metric"><small>TP1 / TP2</small><b>${histFmt(x.tp1)} / ${histFmt(x.tp2)}</b></div><div class="metric"><small>RR</small><b>${x.rr?`1:${Number(x.rr).toFixed(2)}`:'—'}</b></div></div><div class="sx-detail-section"><h4>Signal Evidence</h4><div class="sx-evidence-grid">${entries.slice(0,30).map(([k,v])=>`<div class="sx-evidence"><small>${escapeHtml(k)}</small><div>${escapeHtml(String(v).slice(0,600))}</div></div>`).join('')||'<div class="sx-empty">Snapshot evidence mavjud emas.</div>'}</div></div><div class="sx-detail-section"><h4>Timeline</h4><div class="sx-timeline">${[['Signal Created',x.created_at],['Pending Created',executionTimeline.PENDING_CREATED],['Pending Triggered',executionTimeline.PENDING_TRIGGERED],['Market Opened',executionTimeline.MARKET_OPENED],['Entry Activated',setup.entry?x.created_at:null],['TP1 Hit',time.tp1_hit],['Signal Closed',x.closed_at]].filter(a=>a[1]).map(a=>`<div class="sx-timeline-item"><b>${escapeHtml(a[0])}</b><div class="mini">${histTime(a[1])}</div></div>`).join('')||'<div class="sx-empty">Timeline hali bo‘sh.</div>'}</div></div><div class="sx-detail-section"><h4>Performance</h4><div class="sx-detail-grid"><div class="metric"><small>STATUS</small><b>${escapeHtml(x.status)}</b></div><div class="metric"><small>PROFIT / LOSS</small><b>${x.profit_loss!=null?histFmt(x.profit_loss):'—'}</b></div><div class="metric"><small>R-MULTIPLE</small><b>${x.r_multiple!=null?(Number(x.r_multiple)>=0?'+':'')+Number(x.r_multiple).toFixed(2)+'R':'—'}</b></div><div class="metric"><small>DURATION</small><b>${x.duration_minutes!=null?Number(x.duration_minutes).toFixed(0)+' min':'ACTIVE'}</b></div></div></div>`}

function componentText(v){if(v==null)return '—';if(typeof v==='object'){if(v.type)return v.type+(v.low!=null?' · '+fmt(v.low)+'–'+fmt(v.high):'');if(v.support!=null)return 'S '+fmt(v.support)+' · R '+fmt(v.resistance);return JSON.stringify(v)}return String(v)}
function tfName(tf){return ({'1min':'1 MIN','5min':'5 MIN','15min':'15 MIN','30min':'30 MIN','1h':'1 HOUR','4h':'4 HOUR','1day':'1 DAY'})[tf]||tf;}
function advCard(tf,x){const sig=x.signal||'WAIT', cls=sig==='BUY'?'buy':sig==='SELL'?'sell':'wait', badge=sig==='BUY'?'badge-buy':sig==='SELL'?'badge-sell':'badge-wait';const c=x.components||{};return `<div class="advanced-card ${cls}"><div class="advanced-head"><div><div class="mini">${tfName(tf)}</div><div class="advanced-signal ${badge}">${sig}</div></div><span class="pill">${x.confidence||0}%</span></div><div class="mini" style="margin-top:4px">Score ${x.score??0} · ${x.setup||'—'}</div><div class="grid4" style="margin-top:9px"><div class="metric"><small>Entry</small><b>${fmt(x.entry)}</b></div><div class="metric"><small>SL</small><b>${fmt(x.stop_loss)}</b></div><div class="metric"><small>TP1</small><b>${fmt((x.take_profit||[])[0])}</b></div><div class="metric"><small>TP2</small><b>${fmt((x.take_profit||[])[1])}</b></div></div><div class="component-grid"><div class="component"><small>ICT / Structure</small><b>${componentText(c['ICT'])}</b></div><div class="component"><small>Order Block</small><b>${componentText(c['Order Block'])}</b></div><div class="component"><small>FVG</small><b>${componentText(c['FVG'])}</b></div><div class="component"><small>Liquidity</small><b>${componentText(c['Liquidity'])}</b></div><div class="component"><small>Trend Line</small><b>${componentText(c['Trend Line'])}</b></div><div class="component"><small>Global Trend</small><b>${componentText(c['Global Trend Line'])}</b></div><div class="component"><small>BOS</small><b>${componentText(c['BOS'])}</b></div><div class="component"><small>CHOCH</small><b>${componentText(c['CHOCH'])}</b></div><div class="component"><small>Internal</small><b>${componentText(c['Internal Structure'])}</b></div><div class="component"><small>RSI / ATR</small><b>${fmt(x.rsi)} / ${fmt(x.atr)}</b></div></div><div class="advanced-actions"><div class="mini">${x.reason||'—'}</div>${sig==='BUY'||sig==='SELL'?`<button class="btn" data-save-advanced="${tf}">Saqlash</button>`:''}</div></div>`}

function ictRange(x){return x&&x.low!=null&&x.high!=null?`${fmt(x.low)} – ${fmt(x.high)}`:'—'}
function ictState(v){return v?'PASS':'MISS'}
async function loadICTAIPro(){ return window.SignalXSuite.load("ict-ai-pro"); }

async function loadClassicTrade(){ return window.SignalXSuite.load("classic"); }
let msaiInterval='5min';
let smcInterval='5min';
function msaiFmt(v){return v==null||!Number.isFinite(Number(v))?'—':fmt(Number(v));}
function msaiStateClass(sig){return sig==='BUY'?'buy':sig==='SELL'?'sell':'wait';}
function msaiYN(v){return v===true?'PASS':v===false?'MISS':'—';}
function renderMsaiCheckGrid(checks){
  const labels={storyline:'Storyline',fresh_snr:'Fresh SNR',wick_rejection:'Wick Rejection',liquidity_sweep:'Liquidity Sweep',miss:'MISS',engulfing:'Engulfing',trendline:'Trendline',qml_hns:'QML / HNS',breakout:'LTF Breakout',retest:'LTF Retest',mtf_match:'MTF Match',two_tf_confirmation:'2-TF Confirm'};
  const grid=$('msaiChecks'); if(!grid)return;
  grid.innerHTML=Object.entries(labels).map(([k,label])=>{const v=checks?.[k];const cls=v===true?'msai-pass':v===false?'msai-miss':'';return `<div class="component"><small>${label}</small><b class="${cls}">${msaiYN(v)}</b></div>`}).join('');
}
async function loadMSAI(){ return window.SignalXSuite.load("snr"); }
document.addEventListener('click',e=>{const b=e.target.closest('[data-msai-interval]');if(b){document.querySelectorAll('[data-msai-interval]').forEach(x=>x.classList.toggle('active',x===b));msaiInterval=b.dataset.msaiInterval;loadMSAI(msaiInterval).catch(()=>{})}});
document.addEventListener('click',e=>{const b=e.target.closest('#refreshMSAI');if(b)loadMSAI(msaiInterval).catch(()=>{})});

function smcFmt(v){return v==null||!Number.isFinite(Number(v))?'—':fmt(Number(v));}
function smcStateClass(sig){return sig==='BUY'?'buy':sig==='SELL'?'sell':'wait';}
function smcYN(v){return v===true?'PASS':v===false?'MISS':'—';}
function renderSmcChecks(checks){
  const labels={structure_bos_choch:'BOS / CHoCH',liquidity:'Liquidity',eqh_or_eql:'EQH / EQL',liquidity_sweep:'Liquidity Sweep',session_liquidity_proxy:'Session Liquidity',inducement_idm:'IDM / Inducement',order_block:'Order Block',fvg:'FVG',poi:'POI',ob_touch:'OB Touch',fvg_touch:'FVG Touch',entry_module:'Entry Module',idm_choch:'IDM + CHoCH',idm_flip:'IDM + FLIP',previous_candle_liquidity:'Prev Candle Liquidity',single_candle_liquidity_check:'Single Candle',engulfing_confirmation:'Candle Confirmation',mtf_match:'MTF Match',rr_ok:'RR OK',ltf_confirmation:'LTF Confirm',mtf_alignment:'MTF Alignment'};
  const grid=$('smcChecks'); if(!grid)return;
  grid.innerHTML=Object.entries(labels).map(([k,label])=>{const v=checks?.[k];const cls=v===true?'smc-pass':v===false?'smc-miss':'';return `<div class="component"><small>${label}</small><b class="${cls}">${smcYN(v)}</b></div>`}).join('');
}
function renderSmcEntryModules(modules){
  const labels={idm_choch:'IDM + CHoCH',idm_flip:'IDM + FLIP',previous_candle_liquidity:'Previous Candle Liquidity',single_candle_liquidity_check:'Single Candle + Liquidity',engulfing_confirmation:'Engulfing Confirmation',ob_confirmation:'Order Block Confirmation',fvg_confirmation:'FVG Confirmation',bos_or_choch:'BOS / CHoCH'};
  const grid=$('smcEntryModules'); if(!grid)return;
  grid.innerHTML=Object.entries(labels).map(([k,label])=>{const v=modules?.[k];const cls=v===true?'smc-pass':v===false?'smc-miss':'';return `<div class="component"><small>${label}</small><b class="${cls}">${smcYN(v)}</b></div>`}).join('');
}
async function loadSMC(){ return window.SignalXSuite.load("ob"); }
document.addEventListener('click',e=>{const b=e.target.closest('[data-smc-interval]');if(b){e.preventDefault();document.querySelectorAll('[data-smc-interval]').forEach(x=>x.classList.toggle('active',x===b));smcInterval=b.dataset.smcInterval;loadSMC(smcInterval).catch(()=>{});}});
document.addEventListener('click',e=>{const b=e.target.closest('#refreshSMC');if(b)loadSMC(smcInterval).catch(()=>{})});

let algoSmcInterval='5min';
function algoSmcFmt(v){return v==null||!Number.isFinite(Number(v))?'—':fmt(Number(v));}
function algoSmcStateClass(sig){sig=String(sig||'WAIT').toUpperCase();return sig==='BUY'?'buy':sig==='SELL'?'sell':'wait';}
function algoSmcYN(v){return v===true?'PASS':v===false?'MISS':'—';}
function renderAlgoSmcChecks(checks){
  const labels={major_liquidity:'Major Liquidity',liquidity_sweep:'Liquidity Sweep',money_transfer:'Money Transfer',structure_bos_choch:'BOS / CHoCH',strong_high_low_context:'Strong H/L',fake_bms_filter:'Fake BMS Filter',amd_cycle:'AMD Cycle',premium_discount:'Premium / Discount',fvg:'FVG / Void',algo_candle:'Algo Candle',displacement:'Displacement',previous_candle_liquidity:'Prev Candle Liquidity',bos_choch_confirmation:'Structure Confirmation',engulfing_confirmation:'Candle Confirmation',ping_pong:'Ping Pong',mtf_alignment:'MTF Alignment',rr_ok:'RR OK',hard_deterministic_gate:'Hard Gate'};
  const grid=$('algoSmcChecks');if(!grid)return;
  grid.innerHTML=Object.entries(labels).map(([k,l])=>{const v=checks?.[k];const cls=v===true?'as-pass':v===false?'as-miss':'';return `<div class="component"><small>${l}</small><b class="${cls}">${algoSmcYN(v)}</b></div>`}).join('');
}
async function loadAlgoSMC(tf=algoSmcInterval){
  const page=$('algoSmcSection');if(!page)return;
  try{
    setText('algoSmcReason','Algo/SMC strategiya hisoblanmoqda…');
    const d=await api(`/api/v1/algo-smc/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(tf)}`);
    const x=d.strategy||{};const ai=x.ai||{};const sig=String(x.signal||'WAIT').toUpperCase();const structure=x.structure||{};const liq=x.liquidity||{};const sweep=x.sweep||{};const amd=x.amd||{};const pd=x.premium_discount||{};const fvg=x.fvg||{};const disp=x.displacement||{};const checks=x.checks||{};const mtf=x.mtf||{};const modules=x.entry_modules||{};
    const se=$('algoSmcSignal');if(se){se.textContent=sig;se.className='signal-main '+algoSmcStateClass(sig);}
    const ae=$('algoSmcAI');if(ae){const as=String(ai.signal||'WAIT').toUpperCase();ae.textContent=as;ae.className='advanced-signal '+algoSmcStateClass(as);}
    setText('algoSmcPrice',algoSmcFmt(d.current_price));setText('algoSmcScore',`${x.score??0} / 100`);setText('algoSmcAIConfidence',`${ai.confidence??0}%`);setText('algoSmcAIGate',x.ai_gate?.passed?'PASS':'WAIT');setText('algoSmcState',x.state||'—');setText('algoSmcReason',x.reason||'—');setText('algoSmcProvider',ai.mode||ai.provider||'—');setText('algoSmcAIReason',ai.reasoning||'—');setText('algoSmcAIValidation',ai.validation?'PASS':'WAIT');setText('algoSmcAIAgreement',`${ai.agreement??0}%`);setText('algoSmcAIRisk',(ai.risk_flags||[]).join(', ')||'NONE');setText('algoSmcAIDirection',ai.signal||'WAIT');
    setText('algoSmcRR',x.risk_reward!=null?`RR ${x.risk_reward}`:'RR —');setText('algoSmcEntry',algoSmcFmt(x.entry));setText('algoSmcSL',algoSmcFmt(x.stop_loss));setText('algoSmcTP1',algoSmcFmt((x.take_profit||[])[0]));setText('algoSmcTP2',algoSmcFmt((x.take_profit||[])[1]));setText('algoSmcSetup',x.setup||'—');
    setText('algoSmcMajorLiq',`${algoSmcFmt(liq.major?.PDL)} ↔ ${algoSmcFmt(liq.major?.PDH)}`);setText('algoSmcMediumLiq',`${algoSmcFmt(liq.medium?.low)} ↔ ${algoSmcFmt(liq.medium?.high)}`);setText('algoSmcMinorLiq',`${algoSmcFmt(liq.minor?.low)} ↔ ${algoSmcFmt(liq.minor?.high)}`);setText('algoSmcSweep',sweep.valid?`${sweep.side||'SWEEP'} · ${algoSmcFmt(sweep.level)}`:'NONE');
    setText('algoSmcCyclePhase',amd.phase||'—');setText('algoSmcAMD',`${amd.phase||'—'} · ${x.weekly_cycle?.phase||'—'}`);setText('algoSmcMoneyTransfer',x.money_transfer||'NONE');setText('algoSmcPD',`${pd.zone||'—'} · ${pd.midpoint_zone||'—'}`);setText('algoSmc90m',x.cycle_90m?.valid?`${x.cycle_90m.block_start} · +${x.cycle_90m.minutes_into_block}m`:'—');
    setText('algoSmcTrend',structure.trend||'—');setText('algoSmcBOS',structure.bos||'—');setText('algoSmcCHoCH',structure.choch||'—');setText('algoSmcStrongHL',`${algoSmcFmt(structure.strong_high)} / ${algoSmcFmt(structure.strong_low)}`);setText('algoSmcFakeBMS',x.fake_break?.valid?`${x.fake_break.direction||'RISK'}`:'CLEAR');
    setText('algoSmcAlgoCandle',disp.body_atr!=null?(x.entry_modules?.algo_candle?'CONFIRMED':'NONE'):'—');setText('algoSmcFVG',fvg.valid?`${fvg.type||'FVG'} · ${algoSmcFmt(fvg.low)}–${algoSmcFmt(fvg.high)}`:'NONE');setText('algoSmcDisplacement',disp.body_atr!=null?`${disp.body_atr} ATR`:'—');setText('algoSmcOB',x.order_block?.valid?`${x.order_block.type||'OB'} · ${algoSmcFmt(x.order_block.low)}–${algoSmcFmt(x.order_block.high)}`:'NONE');setText('algoSmcBreaker',x.breaker_block?.valid?`${x.breaker_block.type||'BREAKER'} · ${x.breaker_block.retest?'RETEST':'WATCH'}`:'NONE');setText('algoSmcRejection',x.rejection_block?.valid?`${x.rejection_block.type||'REJECTION'} · ${x.rejection_block.wick_ratio??0}`:'NONE');setText('algoSmcHVI',x.hvi?.valid?`${x.hvi.ratio}× VOL`:'NONE');
    const activeModules=Object.entries(modules).filter(([,v])=>v).map(([k])=>k.replaceAll('_',' '));setText('algoSmcEntryModule',activeModules[0]||'WAIT');
    setText('algoSmcMTFState',mtf.alignment?'ALIGNED':'MIXED');const grid=$('algoSmcMTFGrid');if(grid){grid.innerHTML=(mtf.rows||[]).map(r=>{const t=String(r.trend||'NEUTRAL');const c=t==='BULLISH'?'buy':t==='BEARISH'?'sell':'wait';return `<div class="advanced-card"><div class="advanced-head"><div><div class="mini">${r.label||'TF'}</div><div class="advanced-signal ${c}">${t}</div></div><span class="pill">${r.bos||r.choch||'STRUCTURE'}</span></div></div>`}).join('');}
    renderAlgoSmcChecks(checks);
    const warns=[];if(x.errors&&Object.keys(x.errors).length)warns.push(`TF errors: ${Object.keys(x.errors).join(', ')}`);if(!x.ai_gate?.passed)warns.push('Strict AI validation PASS emas.');if(x.state==='WAIT_AI_VALIDATION')warns.push('AI tasdiqlash kutilmoqda.');if(!checks.rr_ok)warns.push('RR minimum 1.40 emas.');if(x.fake_break?.valid)warns.push('Fake BMS/FMS xavfi bor.');if(!warns.length)warns.push('Hard gate: NO AI VALIDATION → NO TRADE');setText('algoSmcWarnings',warns.join(' · '));setText('algoSmcUpdated',`${symbol} · ${tfName(tf)} · ${new Date(d.generated_at||Date.now()).toLocaleString()}`);
    if(token&&['BUY','SELL'].includes(sig)) recordModuleSignal('Algo/SMC',d,x,tf,x.candle_time||liveCandle?.time);
  }catch(e){const se=$('algoSmcSignal');if(se){se.textContent='WAIT';se.className='signal-main wait';}setText('algoSmcState','ERROR');setText('algoSmcAIGate','WAIT');setText('algoSmcReason','Algo/SMC error: '+(e.message||'server error'));setText('algoSmcAIReason','Strategiya hisoblanmadi.');}
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-algo-smc-interval]');if(b){e.preventDefault();document.querySelectorAll('[data-algo-smc-interval]').forEach(x=>x.classList.toggle('active',x===b));algoSmcInterval=b.dataset.algoSmcInterval;loadAlgoSMC(algoSmcInterval).catch(()=>{});}});
document.addEventListener('click',e=>{const b=e.target.closest('#refreshAlgoSMC');if(b)loadAlgoSMC(algoSmcInterval).catch(()=>{})});

async function loadAISignals(){ return window.SignalXSuite.load("ai-analysis"); }
function tlClass(sig){return sig==='BUY'||sig==='STRONG BUY'?'buy':sig==='SELL'||sig==='STRONG SELL'?'sell':'wait'}
function trendCard(tf,x){
  const tl=x.trendline||{}, fib=x.fibonacci||{}, adv=x.advanced||{}; const sig=adv.signal||tl.signal||'WAIT'; const power=tl.trend_power??0;
  return `<div class="trend-card"><div class="section-head"><div><div class="mini">${tfName(tf)}</div><div class="tl-big ${tlClass(sig)}">${sig}</div></div><span class="pill">${adv.confidence??0}%</span></div><div class="mini">${tl.type||'NONE'} · Trend ${tl.trend||'NEUTRAL'}</div><div class="tl-grid"><div><div class="tl-mini">TOUCH</div><b>${tl.touches??0}</b></div><div><div class="tl-mini">POWER</div><b>${power}%</b></div><div><div class="tl-mini">BREAK</div><b>${tl.breakout||'NO'}</b></div><div><div class="tl-mini">RETEST</div><b>${tl.retest||'NO'}</b></div><div><div class="tl-mini">FIB</div><b>${fib.nearest_level??'—'}</b></div><div><div class="tl-mini">FIB SIG</div><b>${fib.signal||'WAIT'}</b></div></div><div class="mini" style="margin-top:8px">${fib.reason||adv.reason||tl.reason||'—'}</div></div>`;
}

function removeLegacyTrendCharts(){
  const section=$('trendLineSection');
  if(!section) return;
  section.querySelectorAll('#trendChart, .trend-chart-legacy, [data-legacy-trend-chart=\"1\"]').forEach(el=>{ try{el.remove()}catch(_){} });
  // Keep exactly one chart container in Auto Trend Line.
  const keep=$('tvTrendChart');
  section.querySelectorAll('.chart').forEach(el=>{ if(el!==keep) { try{el.remove()}catch(_){} } });
}

function clearTrendOverlay(){
  try{ if(trendOverlayChart){ trendOverlayChart.remove(); } }catch(_){ }
  trendOverlayChart=null; trendOverlaySeries=null; trendOverlayLayers=[];
  const el=$('tvTrendChart'); if(el) el.innerHTML='';
}
function trendOverlayLineData(candles, startTime, startPrice, endTime, endPrice){
  if(!Array.isArray(candles)||!candles.length) return [];
  const a=Number(startTime), b=Number(endTime);
  if(!Number.isFinite(a)||!Number.isFinite(b)||!Number.isFinite(Number(startPrice))||!Number.isFinite(Number(endPrice))) return [];
  return [{time:a,value:Number(startPrice)},{time:b,value:Number(endPrice)}];
}
function mountAutoTrendFibChart(tf,candles,t,fib){
  const el=$('tvTrendChart');
  if(!el || !window.LightweightCharts || !Array.isArray(candles) || candles.length<2) return;
  removeLegacyTrendCharts();
  clearTrendOverlay();
  const LC=window.LightweightCharts;
  const width=Math.max(320,el.clientWidth||900);
  trendOverlayChart=LC.createChart(el,{width,height:560,layout:{backgroundColor:'#080d13',textColor:'#cbd5e1'},grid:{vertLines:{color:'#17202b'},horzLines:{color:'#17202b'}},crosshair:{mode:LC.CrosshairMode.Normal},rightPriceScale:{borderColor:'#26313d'},timeScale:{borderColor:'#26313d',timeVisible:true,secondsVisible:false},handleScroll:true,handleScale:true});
  trendOverlaySeries=trendOverlayChart.addCandlestickSeries({upColor:'#20c997',downColor:'#ff5d72',borderVisible:false,wickUpColor:'#20c997',wickDownColor:'#ff5d72'});
  const data=candles.map(c=>({time:Number(c.time),open:+c.open,high:+c.high,low:+c.low,close:+c.close})).filter((x,i,a)=>Number.isFinite(x.time)&& (i===0||x.time>a[i-1].time));
  trendOverlaySeries.setData(data);
  const timeByIndex=i=>data[Math.max(0,Math.min(data.length-1,Number(i)||0))]?.time;
  const addLine=(points,opts)=>{if(points.length<2)return null;const ss=trendOverlayChart.addLineSeries(opts);ss.setData(points);trendOverlayLayers.push(ss);return ss;};

  // Trend line: use backend anchor TIMES, never array indexes. This avoids the
  // classic bug where the API calculates on 319 candles but the chart displays
  // only the last 220 and the line is therefore shifted/off-screen.
  if(t?.available && t?.p1 && t?.p2){
    const p1Time=Number(t.p1.time)||timeByIndex(t.p1.index);
    const p2Time=Number(t.p2.time)||timeByIndex(t.p2.index);
    const endTime=data[data.length-1].time;
    const endValue=Number(t.current_line);
    if(Number.isFinite(p1Time)&&Number.isFinite(p2Time)&&Number.isFinite(endValue)){
      addLine(trendOverlayLineData(data,p1Time,t.p1.price,endTime,endValue),{color:t.trend==='BULLISH'?'#21b6ff':'#4aa3ff',lineWidth:3,lineStyle:0,lastValueVisible:false,priceLineVisible:false});
    }
  }

  // Fibonacci: draw only from the selected timeframe's actual impulse anchors
  // to the latest candle. Every level therefore changes when TF/structure changes.
  if(fib?.available && fib.levels){
    const startTime=Number(fib.draw_start_time)||timeByIndex(fib.draw_start_index);
    const endTime=Number(fib.draw_end_time)||data[data.length-1].time;
    if(Number.isFinite(startTime)&&Number.isFinite(endTime)){
      const levs=[['0','#8ea0b5',1],['0.236','#70859b',1],['0.382','#5f9ee8',1],['0.5','#f5c15d',2],['0.618','#ff9f43',2],['0.786','#a98cff',1],['1','#70859b',1],['1.272','#31d39a',1],['1.618','#31d39a',1]];
      levs.forEach(([k,col,w])=>{const v=Number(fib.levels[k]);if(!Number.isFinite(v))return;addLine(trendOverlayLineData(data,startTime,v,endTime,v),{color:col,lineWidth:w,lineStyle:0,lastValueVisible:true,priceLineVisible:false});});
      const z=fib.retracement_zone;
      if(z && Number.isFinite(Number(z.low)) && Number.isFinite(Number(z.high))){
        addLine(trendOverlayLineData(data,startTime,Number(z.low),endTime,Number(z.low)),{color:'#f5c15d',lineWidth:1,lineStyle:2,lastValueVisible:false,priceLineVisible:false});
        addLine(trendOverlayLineData(data,startTime,Number(z.high),endTime,Number(z.high)),{color:'#f5c15d',lineWidth:1,lineStyle:2,lastValueVisible:false,priceLineVisible:false});
      }
    }
  }
  trendOverlayChart.timeScale().fitContent();
  if(window.ResizeObserver){const ro=new ResizeObserver(()=>{if(trendOverlayChart&&el.clientWidth)trendOverlayChart.applyOptions({width:el.clientWidth});});ro.observe(el);el._trendResizeObserver=ro;}
}
async function loadTrendLines(){ return window.SignalXSuite.load("trendline"); }

const AI_QA_STATE={messages:[],bound:false,sending:false};
function renderAiQaMessages(){
  const el=$('aiQaChat'); if(!el)return;
  if(!AI_QA_STATE.messages.length){el.innerHTML='<div class="ai-qa-empty">Savolingizni yozing. Masalan: <b>“Bugun XAUUSD qanaqa trendda?”</b></div>';return;}
  el.innerHTML=AI_QA_STATE.messages.map(m=>{
    const role=m.role==='user'?'user':'assistant';
    const meta=m.meta?`<div class="ai-qa-meta">${safeText(m.meta)}</div>`:'';
    return `<div class="ai-qa-msg ${role}"><div class="ai-qa-bubble">${safeText(m.text)}${meta}</div></div>`;
  }).join('');
  el.scrollTop=el.scrollHeight;
}
function aiQaEnsureVisible(){
  const section=$('aiQaSection');
  if(!section)return;
  section.classList.add('active');
  document.querySelectorAll('.section').forEach(s=>{if(s!==section)s.classList.remove('active');});
  document.querySelectorAll('.sidebar .nav button[data-section]').forEach(b=>b.classList.toggle('active',b.dataset.section==='aiQaSection'));
  setText('pageTitle','AI Q&A');
  try{window.scrollTo({top:0,left:0,behavior:'auto'});}catch{}
}
async function askAiQa(question){
  token=localStorage.getItem('trading_token')||token||'';
  if(!token){showToast('AI Q&A uchun avval tizimga kiring');$('authModal')?.classList.add('show');return;}
  if(AI_QA_STATE.sending)return;
  const input=$('aiQaInput'), send=$('aiQaSend'), provider=$('aiQaProvider'), ctx=$('aiQaContext');
  const q=(question||input?.value||'').trim(); if(!q)return;
  AI_QA_STATE.sending=true;
  if(input)input.value='';
  aiQaEnsureVisible();
  AI_QA_STATE.messages.push({role:'user',text:q});
  AI_QA_STATE.messages.push({role:'assistant',text:'AI tahlil qilmoqda…',meta:'Live market + news context tekshirilmoqda'});
  renderAiQaMessages();
  if(send)send.disabled=true;
  try{
    const d=await api('/api/v1/ai/chat',{method:'POST',body:JSON.stringify({question:q,symbol,interval})});
    AI_QA_STATE.messages.pop();
    const meta=[d.provider?`Provider: ${d.provider}`:'Context fallback',d.context?.economic_events_count!=null?`News/events: ${d.context.economic_events_count}`:''].filter(Boolean).join(' · ');
    AI_QA_STATE.messages.push({role:'assistant',text:d.answer||'Javob tayyorlanmadi.',meta});
    if(provider)provider.textContent=d.provider?`AI · ${d.provider}`:(d.ok?'CONTEXT':'AI ERROR');
    if(ctx)ctx.textContent=d.context?.quote_source?`LIVE · ${d.context.quote_source}`:'LIVE CONTEXT';
  }catch(e){
    AI_QA_STATE.messages.pop();
    AI_QA_STATE.messages.push({role:'assistant',text:'AI Q&A xatosi: '+(e.message||'server error'),meta:'So‘rov bajarilmadi. AI provider/API holatini tekshiring.'});
    if(provider)provider.textContent='AI ERROR';
  }finally{AI_QA_STATE.sending=false;if(send)send.disabled=false;renderAiQaMessages();}
}
function bindAiQa(){
  if(AI_QA_STATE.bound)return;
  AI_QA_STATE.bound=true;
  const form=$('aiQaForm');
  form?.addEventListener('submit',e=>{e.preventDefault();e.stopPropagation();askAiQa();});
  document.addEventListener('click',e=>{const b=e.target.closest('[data-aiq]');if(!b)return;e.preventDefault();e.stopPropagation();askAiQa(b.dataset.aiq);},true);
}
bindAiQa();

async function loadPatterns(){
  const grid=$('patternsGrid'); if(!grid)return;
  grid.innerHTML='<div class="card">Pattern detector hisoblanmoqda…</div>';
  try{
    const d=await api(`/api/v1/patterns/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(interval)}`);
    const order=['1min','5min','15min','30min','1h','4h','1day'];
    grid.innerHTML=order.map(tf=>{
      const x=d.timeframes?.[tf]||{};
      const sig=String(x.signal||'WAIT').toUpperCase();
      const cls=sig==='BUY'?'buy':sig==='SELL'?'sell':'wait';
      const best=x.best||{};
      const band=x.pattern_score_band||'WAIT';
      const ai=x.ai_validation||{};
      const aiState=x.ai_consensus||'—';
      const mtf=x.mtf_alignment?.state||best.mtf_alignment?.state||'—';
      const pats=(x.patterns||[]).slice(0,4).map(p=>`${escapeHtml(p.name||'Pattern')} · ${escapeHtml(p.category||'')}${p.breakout?.confirmed?' ✓':''}`).join('<br>')||'Pattern topilmadi';
      return `<article class="advanced-card pattern-card ${cls}"><div class="advanced-head"><div><div class="mini">${tfName(tf)}</div><div class="advanced-signal ${cls}">${sig}</div></div><span class="pill">${x.final_score??x.pattern_score??x.confidence??0}% · ${band}</span></div><div class="pattern-name">${escapeHtml(x.pattern||best.name||'No confirmed pattern')}</div><div class="pattern-meta"><span>Type: <b>${escapeHtml(x.pattern_type||best.category||'—')}</b></span><span>Breakout: <b>${x.breakout_confirmed?'YES':'NO'}</b></span><span>MTF: <b>${escapeHtml(mtf)}</b></span><span>AI: <b>${escapeHtml(aiState)}</b></span></div><div class="grid4" style="margin-top:9px"><div class="metric"><small>Entry</small><b>${fmt(x.entry??best.entry)}</b></div><div class="metric"><small>SL</small><b>${fmt(x.stop_loss??best.stop_loss)}</b></div><div class="metric"><small>TP1</small><b>${fmt((x.take_profit||best.take_profit||[])[0])}</b></div><div class="metric"><small>TP2</small><b>${fmt((x.take_profit||best.take_profit||[])[1])}</b></div></div><div class="component-grid" style="margin-top:9px"><div class="component"><small>Pattern Score</small><b>${x.pattern_score??x.confidence??0}/100</b></div><div class="component"><small>AI Confidence</small><b>${ai.confidence??x.ai_score??0}%</b></div><div class="component"><small>MTF Alignment</small><b>${escapeHtml(x.mtf_alignment?.state||'—')}</b></div><div class="component"><small>False Breakout</small><b>${escapeHtml(best.breakout?.false_breakout_risk||'—')}</b></div></div><div class="mini pattern-reason">${escapeHtml(x.reason||'—')}</div><div class="mini pattern-list">${pats}</div></article>`;
    }).join('');
    $('patternsStatus').textContent=`${symbol} · Pattern AI Strategy · ${new Date(d.generated_at).toLocaleString()}`;
    if(token && d.selected && d.timeframes?.[d.selected]?.signal && ['BUY','SELL'].includes(String(d.timeframes[d.selected].signal).toUpperCase())){
      const x=d.timeframes[d.selected];
      recordModuleSignal('Patterns',d,x,d.selected,x.candle_time||liveCandle?.time);
    }
  }catch(e){$('patternsStatus').textContent='Pattern error: '+(e.message||'server error');grid.innerHTML='<div class="card">Pattern signal yuklanmadi.</div>';}
}

let trendChannelInterval = '5min';
let newStrategyInterval = '15min';
async function loadTrendChannel(){ return window.SignalXSuite.load("trend"); }
async function loadFibonacci(){ return window.SignalXSuite.load("fibonacci"); }
let fibonacciInterval='15min';
async function loadNewStrategy(tf=newStrategyInterval){
  const d=await api(`/api/v1/new-strategy/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(tf)}`); const x=d.strategy||{}; const sig=String(x.signal||'WAIT').toUpperCase(); const cls=sig==='BUY'?'buy':sig==='SELL'?'sell':'wait';
  $('nsSignal').textContent=sig; $('nsSignal').className='signal-main '+cls; $('nsConfidence').textContent=`${x.confidence??0}%`; $('nsReason').textContent=x.reason||'—'; $('nsEntry').textContent=fmt(x.entry); $('nsSL').textContent=fmt(x.stop_loss); $('nsTP1').textContent=fmt((x.take_profit||[])[0]); $('nsRR').textContent=x.risk_reward?`1:${Number(x.risk_reward).toFixed(2)}`:'—';
  $('nsBuyVote').textContent=x.vote_buy??'—'; $('nsSellVote').textContent=x.vote_sell??'—'; $('nsHTF').textContent=x.mtf?.direction_bias||'—'; $('nsPD').textContent=x.macro_context?.premium_discount||'—'; $('nsConsensus').textContent=x.raw_direction||'WAIT'; $('nsSelectedEngine').textContent=x.selected_engine||'—';
  const ai=x.ai_validation||{}; const as=String(ai.signal||'WAIT').toUpperCase(); $('nsAI').textContent=as; $('nsAI').className='advanced-signal '+(as==='BUY'?'buy':as==='SELL'?'sell':'wait'); $('nsAIProvider').textContent=ai.mode||'—'; $('nsAIConfidence').textContent=`${ai.confidence??0}%`; $('nsAIAgreement').textContent=`${ai.agreement??0}%`; $('nsAIGate').textContent=x.ai_gate?.passed?'PASS':'WAIT'; $('nsAIReason').textContent=ai.reasoning||ai.reason||'—';
  $('nsComponents').innerHTML=(x.components||[]).map(r=>`<tr><td><b>${escapeHtml(r.engine)}</b></td><td class="${r.signal==='BUY'?'book-pass':r.signal==='SELL'?'book-fail':'book-wait'}">${escapeHtml(r.signal)}</td><td>${r.confidence}%</td><td>${r.weight}</td><td>${r.rr?`1:${Number(r.rr).toFixed(2)}`:'—'}</td><td>${escapeHtml(r.state||'—')}</td></tr>`).join('');
  const m=x.macro_context||{}; const l=m.lookback||{}; $('nsMacro').innerHTML=`<b>Quarter context:</b> ${escapeHtml(m.quarter_context||'—')}<br><b>PD:</b> ${escapeHtml(m.premium_discount||'—')} · EQ ${fmt(m.equilibrium)}<br><b>20D:</b> ${fmt(l['20d_low'])} → ${fmt(l['20d_high'])}<br><b>40D:</b> ${fmt(l['40d_low'])} → ${fmt(l['40d_high'])}<br><b>60D:</b> ${fmt(l['60d_low'])} → ${fmt(l['60d_high'])}<br><b>Daily Open:</b> ${fmt(l.daily_open)}`;
  const ext=m.external_feeds||{}; $('nsExternal').innerHTML=Object.entries(ext).map(([k,v])=>`<span class="book-chip"><b>${escapeHtml(k)}</b> · ${escapeHtml(v)}</span>`).join('')||'—';
  $('nsBookRouting').innerHTML=[['01','Malaysian SNR → MSAI'],['02','SMC → SMC'],['03','Algo/SMC → Algo/SMC'],['04','Advanced ICT Institutional → ICT'],['05','ICT Killzones → ICT timing'],['06','ICT Trading Strategy → ICT sweep/MSS/FVG'],['07','ICT Mentorship Core → ICT institutional models'],['08','September → ICT price delivery'],['09','October → ICT OB + risk'],['10','November → ICT institutional sponsorship'],['11','December → ICT order flow + macro'],['12','January → ICT macro / IPDA'],['13','February → ICT swing / PD arrays'],['14','April → ICT daytrading / CBDR'],['15','June → ICT COT / OI / SMT'],['16','July → ICT megatrades'],['17','August → ICT top-down'],['18','ICT Order Block → ICT block variants'],['19','Trendline → Trend Line Engine'],['20','Trend chiziqlari → Trend Line Engine'],['21','Trend strategy → Trend Engine'],['22','Trend kanallari → Trend Channel Engine'],['23','Parabolic SAR → Trend Channel Engine'],['24','M&W Trendline → Trend Channel + MTF'],['25','Fibo Musang BOBI → Fibonacci/Pattern'],['26','Fibo Musang Elite → Fibonacci Engine'],['27','Fibonacci for Active Trader → Fib/Risk'],['28','Advanced Fibonacci Guide → Fib/Technical'],['29','Fibonacci Trading → Price/Time Confluence'],['30','Fibonachchi Darajalari 2 → 50% Pin Bar'],['31','Rahsia Fibo Musang → Initial Break/CBR'],['32','6 Powerful Fibo Musang Setups → Setup Classifier']].map(([a,b])=>`<span class="book-chip"><b>${a}</b> → ${b}</span>`).join('');
  const hc=x.hard_checks||{}; $('nsHardChecks').innerHTML=[['Consensus',hc.consensus_direction],['MTF alignment',hc.mtf_alignment],['RR ≥ 1.40',hc.rr_ge_1_40],['Majority separation',hc.no_conflicting_majority]].map(([k,v])=>`<div class="metric"><small>${k}</small><b class="${v?'book-pass':'book-wait'}">${v?'PASS':'WAIT'}</b></div>`).join(''); $('nsUpdated').textContent=`${symbol} · ${tfName(tf)} · ${new Date(d.generated_at||Date.now()).toLocaleString()}`; if(sig!=='WAIT') recordModuleSignal('Yangi Strategiya',d,x,tf,x.candle_time||liveCandle?.time);
}
function openSection(id){
  const target=$(id); if(!target)return;
  document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));
  target.classList.add('active');
  document.querySelectorAll('.nav button').forEach(b=>b.classList.toggle('active',b.dataset.section===id));
  const titles={overview:'Dashboard',chartSection:'Chart',ictSection:'ICT AI Pro',msaiStrategySection:'SNR',smartAnalysisSection:'AI Analysis',fallbackSection:'All Fallback',trendChannelSection:'Trend',trendLineSection:'Trend liniya',analysisSection:'Technical Analysis',classicSection:'Classic Trade',smcSection:'OB Trade',fibonacciSection:'Fibonacci Trade',mt5Section:'MT5',historySection:'History'};
  const title=$('pageTitle'); if(title)title.textContent=titles[id]||'SignalX';
  if(id==='overview')setTimeout(()=>{mountTradingView('chart',interval);loadChartHistory().catch(()=>{});loadSessions().catch(()=>{});loadPivots(pivotInterval).catch(()=>{});loadStats().catch(()=>{});},50);
  if(id==='chartSection')setTimeout(()=>{mountTradingView('chart2',interval);loadChartHistory().catch(()=>{});},50);
  if(id==='ictSection')loadICTAIPro().catch(()=>{});
  if(id==='msaiStrategySection')loadMSAI(msaiInterval).catch(()=>{});
  if(id==='smartAnalysisSection')loadSmartAnalysis().catch(()=>{});
  if(id==='fallbackSection')loadAllFallback().catch(()=>{});
  if(id==='trendChannelSection')loadTrendChannel(trendChannelInterval).catch(()=>{});
  if(id==='trendLineSection')loadTrendLines(trendLineInterval).catch(()=>{});
  if(id==='analysisSection')loadAnalysisOnly().catch(()=>{});
  if(id==='classicSection')loadClassicTrade(classicInterval).catch(()=>{});
  if(id==='smcSection')loadSMC(smcInterval).catch(()=>{});
  if(id==='fibonacciSection')loadFibonacci(fibonacciInterval).catch(()=>{});
  if(id==='mt5Section'){loadMT5Status().catch(()=>{});loadMT5GatewayAccounts().catch(()=>{});}
  if(id==='historySection'){loadStats().catch(()=>{});loadHistory().catch(()=>{});}
}

function bucketStart(ts, secs){return Math.floor(ts/secs)*secs}
function currentIntervalSeconds(){return ({'1min':60,'5min':300,'15min':900,'30min':1800,'1h':3600,'4h':14400,'1day':86400})[interval]||300}
function updateLiveCandle(price, ts){
  const secs=currentIntervalSeconds(), bucket=bucketStart(ts,secs);
  if(!liveCandle || liveCandle.time!==bucket){
    liveCandle={time:bucket,open:price,high:price,low:price,close:price};
  } else {
    liveCandle.high=Math.max(liveCandle.high,price);liveCandle.low=Math.min(liveCandle.low,price);liveCandle.close=price;
  }
  $('price').textContent=fmt(price); $('change').textContent='TradingView LIVE · Real-time'; $('change').className='change up'; lastTickTs=Date.now();
}
function closeMarketStream(){try{marketWS?.close()}catch(e){} marketWS=null;streamKey=''}
async function quoteHeartbeat(){
  // When Node.js WS is healthy, do not poll Twelve Data REST every few seconds.
  // That was causing 429 responses and flipping the UI into LIVE RETRY.
  const wsFresh = marketWS && marketWS.readyState===WebSocket.OPEN && (Date.now()-lastTickTs < 5000);
  if(wsFresh){
    $('mode').textContent='LIVE STREAM'; $('mode').style.color='var(--green)'; $('chartStatus').textContent='LIVE';
    return true;
  }
  const now=Date.now();
  if(now-lastRestQuoteAt < 3000) return false;
  lastRestQuoteAt=now;
  try{
    const q=await api(`/api/v1/quote/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(interval)}`);
    if(q?.mode==='live' && q.price!=null){
      const price=+q.price; $('price').textContent=fmt(price);
      $('mode').textContent=marketWS&&marketWS.readyState===WebSocket.OPEN?'LIVE STREAM':'LIVE REST'; $('mode').style.color='var(--green)'; $('chartStatus').textContent='LIVE';
      updateLiveCandle(price,Math.floor(Date.parse(q.timestamp)/1000)||Math.floor(Date.now()/1000));
      return true;
    }
    throw Error(q?.warning||'Live quote unavailable');
  }catch(e){
    // The TradingView chart remains independently live even if our backend quote
    // heartbeat is temporarily unavailable.
    $('mode').textContent='TRADINGVIEW LIVE'; $('mode').style.color='var(--green)'; $('chartStatus').textContent='LIVE';
    $('change').textContent='TradingView live chart · backend REST retrying';
    return false;
  }
}

function connectMarketStream(){
 // TradingView's embedded chart owns its own real-time connection. The dashboard
 // must not create a second fragile WS dependency that can leave the UI stuck on
 // RECONNECTING. Backend prices/analysis use the stable REST heartbeat instead.
 if(DISABLE_MARKET_WS){
   closeMarketStream();
   $('mode').textContent='TRADINGVIEW LIVE'; $('mode').style.color='var(--green)';
   $('chartStatus').textContent='LIVE';
   $('change').textContent='TradingView live chart · same TradingView data for analysis';
   return;
 }
 closeMarketStream();
 const wsBase=API_BASE.replace(/^http/,'ws');
 const wsUrl=wsBase+`/api/v1/ws/market/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(interval)}`;
 try{
   streamKey=symbol+'|'+interval; marketWS=new WebSocket(wsUrl);
   marketWS.onopen=()=>{ $('mode').textContent='LIVE STREAM'; $('mode').style.color='var(--green)'; $('chartStatus').textContent='LIVE'; };
   marketWS.onmessage=ev=>{
     try{ const m=JSON.parse(ev.data); if(m.type==='tick') updateLiveCandle(+m.price,+m.timestamp); }catch(_){}
   };
   marketWS.onclose=()=>{ marketWS=null; $('mode').textContent='TRADINGVIEW LIVE'; $('mode').style.color='var(--green)'; $('chartStatus').textContent='LIVE'; };
   marketWS.onerror=()=>{ try{marketWS.close()}catch{} };
 }catch(e){ marketWS=null; }
}
function setAuth(mode){authMode=mode;$('authTitle').textContent=mode==='login'?'Kirish':'Ro‘yxatdan o‘tish';$('authSubmit').textContent=mode==='login'?'Kirish':'Ro‘yxatdan o‘tish';$('authSwitch').textContent=mode==='login'?'Hisobingiz yo‘qmi? Ro‘yxatdan o‘tish':'Hisobingiz bormi? Kirish';$('email').placeholder=mode==='login'?'Login yoki elektron pochta':'Elektron pochta';$('email').autocomplete=mode==='login'?'username':'email';$('passwordLabel').style.display=mode==='login'?'block':'none';$('password').required=mode==='login';$('password').style.display=mode==='login'?'block':'none';$('password').value='';$('authMsg').textContent=mode==='register'?'Email kiriting — login va parol avtomatik yaratiladi.':''}
function safeText(v){return String(v??'').replace(/[&<>\"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[m]||m));}
async function loadActiveSessions(){
  const grid=$('activeSessionsGrid'); if(!grid)return;
  if(!token){ grid.innerHTML='<div class="mini">Aktiv seanslarni ko‘rish uchun avval tizimga kiring.</div>'; return; }
  grid.innerHTML='<div class="mini">Seanslar tekshirilmoqda…</div>';
  try{
    const d=await api('/api/auth/sessions');
    const rows=d.sessions||[];
    if(!rows.length){ grid.innerHTML='<div class="mini">Aktiv seans topilmadi.</div>'; return; }
    grid.innerHTML=rows.map(x=>{
      const seen=x.last_seen_at?new Date(x.last_seen_at).toLocaleString(): '—';
      const created=x.created_at?new Date(x.created_at).toLocaleString(): '—';
      const status=x.active?'🟢 Faol':'🟡 Faol emas';
      const current=x.current?' · Joriy qurilma':'';
      const owner=IS_ADMIN&&x.username?`<div class="mini">👤 ${safeText(x.username)}${x.email?` · ${safeText(x.email)}`:''}</div>`:'';
      const action=`<button class="btn danger active-session-revoke" type="button" data-session-id="${safeText(x.id)}" data-current="${x.current?'1':'0'}">${x.current?'Chiqish':'Yopish'}</button>`;
      return `<div class="advanced-card"><div class="advanced-head"><div>${owner}<div class="mini">${status}${current}</div><div class="advanced-signal wait">${safeText(x.device_model||'Noma’lum qurilma')}</div></div><div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap"><span class="pill">ID ${safeText(x.id)}</span>${action}</div></div><div class="mini">Oxirgi faollik: ${safeText(seen)}</div><div class="mini">Yaratilgan: ${safeText(created)}</div></div>`;
    }).join('');
  }catch(e){ grid.innerHTML=`<div class="mini">Seanslar xatosi: ${safeText(e.message||'server xatosi')}</div>`; }
}
async function revokeOtherSessions(){
  if(!token) throw Error('Avval tizimga kiring.');
  const d=await api('/api/auth/sessions/revoke-others',{method:'POST'});
  await loadActiveSessions();
  showToast(`Boshqa seanslar yopildi: ${d.revoked||0}`);
}
async function revokeOneSession(sessionId, isCurrent=false){
  if(!token) throw Error('Avval tizimga kiring.');
  const msg=isCurrent ? 'Joriy qurilmadagi seans yopiladi va tizimdan chiqasiz. Davom etilsinmi?' : 'Shu qurilma seansini yopilsinmi?';
  if(!window.confirm(msg)) return;
  const d=await api(`/api/auth/sessions/${encodeURIComponent(sessionId)}/revoke`,{method:'POST'});
  if(isCurrent){
    token=''; localStorage.removeItem('trading_token'); applyRoleAccess(false); setText('plan','Guest'); setText('authBtn','Kirish');
    showToast('Joriy seans yopildi');
    openSection('ictSection');
    return;
  }
  await loadActiveSessions();
  showToast(`Seans yopildi: ${d.session_id||sessionId}`);
}
async function revokeAllSessions(){
  if(!token) throw Error('Avval tizimga kiring.');
  if(!window.confirm('Barcha seanslaringiz, shu jumladan joriy qurilma ham yopiladi. Tizimdan chiqasiz. Davom etilsinmi?')) return;
  const d=await api('/api/auth/sessions/revoke-all',{method:'POST'});
  token=''; localStorage.removeItem('trading_token'); applyRoleAccess(false); setText('plan','Guest'); setText('authBtn','Kirish');
  showToast(`Barcha seanslar yopildi: ${d.revoked||0}`);
  openSection('ictSection');
}

async function loadMT5GatewayAccounts(){
  const grid=$('mt5GatewayAccounts'); if(!grid)return;
  if(!token){grid.innerHTML='<div class="mini">MT5 hisoblarini ko‘rish uchun tizimga kiring.</div>';return;}
  grid.innerHTML='<div class="mini">MT5 hisoblar tekshirilmoqda…</div>';
  try{
    const d=await api('/api/v1/mt5/gateway/accounts');
    const rows=d.items||[];
    if(!rows.length){grid.innerHTML='<div class="mini">Hali MT5 hisob ulanmagan. Pairing code oling va SignalX_MultiBroker_Gateway_EA.mq5 orqali MT5 terminalni ulang.</div>';return;}
    grid.innerHTML=`<div class="mt5-account-grid">${rows.map(a=>{
      const connected=!!a.connected;
      const type=(a.account_type||'demo').toUpperCase();
      const status=connected?'ONLINE':'OFFLINE';
      const statusClass=connected?'buy':'sell';
      const autoOn=!!a.auto_trade_enabled;
      const pendingOn=a.pending_trade_enabled!==false;
      const canEnable=connected && !!a.trade_allowed;
      const autoLabel=autoOn?'AUTO TRADE: ON':'AUTO TRADE: OFF';
      const actionLabel=autoOn?'⏹ AUTO TRADE OFF':'▶ AUTO TRADE ON';
      const actionDisabled=!autoOn && !canEnable;
      const disableReason=!connected?'MT5 terminal / EA offline':(!a.trade_allowed?'MT5 trading permission OFF':'');
      return `<article class="advanced-card mt5-account-card ${connected?'is-online':'is-offline'}">
        <div class="mt5-account-top">
          <div>
            <div class="mt5-account-title"><span class="mt5-type-badge ${type==='REAL'?'real':'demo'}">${type}</span><span>${safeText(a.broker||'Broker')}</span></div>
            <div class="mt5-account-sub">${safeText(a.label||'MT5 Account')}</div>
          </div>
          <div class="mt5-account-status ${statusClass}"><span class="status-dot"></span>${status}</div>
        </div>
        <div class="mt5-account-identity"><span>Login <b>${safeText(a.login||'—')}</b></span><span>Server <b>${safeText(a.server||'—')}</b></span></div>
        <div class="grid4 mt5-account-metrics">
          <div class="metric"><small>Balance</small><b>${a.balance==null?'—':fmt(a.balance)} ${safeText(a.currency||'')}</b></div>
          <div class="metric"><small>Equity</small><b>${a.equity==null?'—':fmt(a.equity)} ${safeText(a.currency||'')}</b></div>
          <div class="metric"><small>Free Margin</small><b>${a.free_margin==null?'—':fmt(a.free_margin)} ${safeText(a.currency||'')}</b></div>
          <div class="metric"><small>Leverage</small><b>1:${safeText(a.leverage||0)}</b></div>
        </div>
        <div class="mt5-account-meta">
          <span>Trade Allowed: <b>${a.trade_allowed?'YES':'NO'}</b></span>
          <span>EA: <b>${safeText(a.ea_version||'—')}</b></span>
          <span>Heartbeat: <b>${a.last_seen_seconds==null?'—':a.last_seen_seconds+'s'}</b></span>
        </div>
        <div class="mt5-account-lot">
          <div><div class="mt5-autotrade-title">LOT SIZE</div><div class="mini">Faqat shu ${type} account uchun</div></div>
          <div class="mt5-lot-controls"><select class="mt5-lot-select" data-mt5-lot="${a.id}" aria-label="${type} lot">${mt5LotOptions(a.lot)}</select><button class="mt5-lot-save" type="button" data-mt5-lot-save="${a.id}">SAQLASH</button></div>
        </div>
        <div class="mt5-account-autotrade ${autoOn?'on':'off'}">
          <div><div class="mt5-autotrade-title">${autoLabel}</div><div class="mini">Faqat shu ${type} account uchun.</div></div>
          <button class="mt5-auto-toggle ${autoOn?'off':'on'}" type="button" data-mt5-gateway-auto="${a.id}" data-enabled="${autoOn?'0':'1'}" ${actionDisabled?'disabled':''} title="${safeText(disableReason)}">${actionLabel}</button>
        </div>
        <div class="mt5-account-autotrade ${pendingOn?'on':'off'}">
          <div><div class="mt5-autotrade-title">${pendingOn?'AUTO PENDING: ON':'AUTO PENDING: OFF'}</div><div class="mini">BUY/SELL STOP va LIMIT orderlari faqat shu ${type} account uchun.</div></div>
          <button class="mt5-auto-toggle ${pendingOn?'off':'on'}" type="button" data-mt5-gateway-pending="${a.id}" data-enabled="${pendingOn?'0':'1'}" ${(!pendingOn&&!connected)?'disabled':''}>${pendingOn?'⏹ PENDING OFF':'▶ PENDING ON'}</button>
        </div>
        ${disableReason && !autoOn ? `<div class="mt5-disabled-note">⚠ ${safeText(disableReason)}</div>`:''}
        <div class="mt5-account-actions"><button class="btn danger" type="button" data-mt5-gateway-disconnect="${a.id}">DISCONNECT</button></div>
      </article>`;
    }).join('')}</div>`;
  }catch(e){grid.innerHTML=`<div class="mini">MT5 Gateway xatosi: ${safeText(e.message||'server xatosi')}</div>`;}
}
async function createMT5Pairing(){
  const out=$('mt5PairingOut');
  try{
    const label=String($('mt5PairingLabel')?.value||'My MT5 Account').trim()||'My MT5 Account';
    const d=await api('/api/v1/mt5/gateway/pair',{method:'POST',body:JSON.stringify({label})});
    if(out)out.innerHTML=`<div class="signal-box"><b>PAIRING CODE: ${safeText(d.pairing_code)}</b><div class="mini">Kod ${safeText(d.expires_in)} soniya amal qiladi. MT5 terminalda SignalX_MultiBroker_Gateway_EA.mq5 → PairingCode maydoniga kiriting.</div></div>`;
  }catch(e){if(out)out.textContent=e.message||'Pairing xatosi';}
}
function mt5LotOptions(selected){
  const values=[0.01,0.02,0.03,0.05,0.10,0.20,0.50,1,2,5,10];
  const s=Number(selected||0.01);
  if(!values.some(v=>Math.abs(v-s)<1e-9) && s>0) values.push(s);
  values.sort((a,b)=>a-b);
  return values.map(v=>`<option value="${v}" ${Math.abs(v-s)<1e-9?'selected':''}>${v.toFixed(2)}</option>`).join('');
}
async function mt5GatewaySetLot(id,lot){
  const raw=Number(lot);
  if(!Number.isFinite(raw)||raw<0.01||raw>100) throw Error('Lot 0.01 dan 100 gacha bo‘lishi kerak.');
  await api(`/api/v1/mt5/gateway/accounts/${id}/lot`,{method:'POST',body:JSON.stringify({lot:raw})});
  await loadMT5GatewayAccounts();
  showToast(`Lot saqlandi: ${raw.toFixed(2)}`);
}
async function mt5GatewayToggle(id,enabled){await api(`/api/v1/mt5/gateway/accounts/${id}/auto-trade`,{method:'POST',body:JSON.stringify({enabled})});await loadMT5GatewayAccounts();}
async function mt5GatewayPendingToggle(id,enabled){await api(`/api/v1/mt5/gateway/accounts/${id}/pending-trade`,{method:'POST',body:JSON.stringify({enabled})});await loadMT5GatewayAccounts();}
async function mt5GatewayDisconnect(id){if(!confirm('Ushbu MT5 hisobni SignalXdan uzasizmi?'))return;await api(`/api/v1/mt5/gateway/accounts/${id}`,{method:'DELETE'});await loadMT5GatewayAccounts();}
async function loadMT5Status(){ if(!IS_ADMIN)return;
  const d=await api(`/api/v1/mt5/status?symbol=${encodeURIComponent(symbol)}`); const st=d.state||{};
  const connState=String(st.connection_state||'').toUpperCase();
  const connLabel=connState==='CONNECTED' || st.connected ? '🟢 CONNECTED' : (connState==='STALE' ? '🟡 STALE' : '🔴 DISCONNECTED');
  setText('mt5Status', connLabel);
  setText('mt5Balance', st.balance==null?'—':fmt(st.balance)); setText('mt5Equity',st.equity==null?'—':fmt(st.equity)); setText('mt5FreeMargin',st.free_margin==null?'—':fmt(st.free_margin)); setText('mt5Positions',st.positions??0);
  const hb=st.heartbeat_age_sec==null?'—':`${Number(st.heartbeat_age_sec).toFixed(1)} s`; setText('mt5Heartbeat',hb); setText('mt5LastError',st.last_error|| (connState==='CONNECTED'?'Heartbeat OK':'MT5 terminal/EA heartbeat kutilyapti…'));
  const on=!!d.auto_trading;
  setText('mt5AutoState',on?'🟢 ON':'🔴 OFF');
  setText('mt5AutoInfo',on ? 'FAQAT XAUUSD uchun yangi auto orderlar MT5 queue’ga yuboriladi.' : "OFF bo‘lsa yangi orderlar MT5'ga yuborilmaydi.");
}
async function setMT5Auto(enabled){ requireAdminClient(); await api('/api/v1/mt5/auto-trading?enabled='+(enabled?'true':'false'),{method:'POST'}); await loadMT5Status(); showToast(enabled?'AUTO TRADING ON':'AUTO TRADING OFF'); }
function bindCriticalButtons(){
  const run=(id,fn)=>{const b=$(id);if(!b||b.dataset.directBound==='1')return;b.dataset.directBound='1';b.addEventListener('click',async e=>{e.preventDefault();e.stopPropagation();if(b.disabled)return;const old=b.innerHTML;b.disabled=true;b.innerHTML='⟳ Ishlanmoqda…';try{await fn();showToast(id==='authBtn'?'':'Yangilandi')}catch(err){console.error('DIRECT BUTTON',id,err);showToast((err?.message||'Server xatosi'))}finally{b.disabled=false;b.innerHTML=old}});};
  const auth=$('authBtn');
  if(auth&&auth.dataset.directBound!=='1'){auth.dataset.directBound='1';auth.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();if(String(auth.textContent||'').trim()==='Chiqish'){logoutUser();return;}setAuth('login');setText('authMsg','');$('authModal')?.classList.add('show');setTimeout(()=>$('email')?.focus(),50);});}
  const openRegister=$('openRegisterDirect'); if(openRegister&&openRegister.dataset.bound!=='1'){openRegister.dataset.bound='1';openRegister.addEventListener('click',e=>{e.preventDefault();setAuth('register');$('email')?.focus();});}
  const authClose=$('authClose'); if(authClose&&authClose.dataset.bound!=='1'){authClose.dataset.bound='1';authClose.addEventListener('click',()=>{$('authModal')?.classList.remove('show');});}
  const authModal=$('authModal'); if(authModal&&authModal.dataset.bound!=='1'){authModal.dataset.bound='1';authModal.addEventListener('click',e=>{if(e.target===authModal)authModal.classList.remove('show');});}
  const authSwitch=$('authSwitch'); if(authSwitch&&authSwitch.dataset.bound!=='1'){authSwitch.dataset.bound='1';authSwitch.addEventListener('click',e=>{e.preventDefault();setAuth(authMode==='login'?'register':'login');});authSwitch.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setAuth(authMode==='login'?'register':'login');}});} run('refreshAIProviders',async()=>{await loadAIProviders();bindAIControls()}); run('refreshFallback',()=>loadAllFallback()); run('refreshICT',()=>loadICTAIPro()); run('refreshClassic',()=>loadClassicTrade(classicInterval)); run('refreshSMC',()=>loadSMC(smcInterval)); run('refreshAlgoSMC',()=>loadAlgoSMC(algoSmcInterval)); run('refreshStats',async()=>{await loadStats();await loadHistory()}); run('refreshSmartAnalysis',()=>loadSmartAnalysis()); run('refreshAISignals',()=>loadAISignals()); run('getAIAnalysis',()=>loadAISignals()); run('refreshCalendar',()=>loadCalendar()); run('refreshHistory',async()=>{await loadStats();await loadHistory()}); run('refreshTrendLines',()=>loadTrendLines(trendLineInterval)); run('refreshTrendChannel',()=>loadTrendChannel(trendChannelInterval)); run('refreshFibonacci',()=>loadFibonacci(fibonacciInterval)); run('refreshNewStrategy',()=>loadNewStrategy(newStrategyInterval)); run('refreshPatterns',()=>loadPatterns()); run('mt5AutoOn',()=>setMT5Auto(true)); run('mt5AutoOff',()=>setMT5Auto(false)); run('refreshMT5',async()=>{await loadMT5Status();await loadMT5GatewayAccounts();}); run('refreshMT5Gateway',()=>loadMT5GatewayAccounts()); run('createMT5Pairing',()=>createMT5Pairing()); run('refreshActiveSessions',()=>loadActiveSessions()); run('revokeOtherSessions',()=>revokeOtherSessions()); run('revokeAllSessions',()=>revokeAllSessions()); run('openFullHistory',()=>{openSection('historySection');});
}
function bindUIActions(){
  document.querySelectorAll('.tfbar').forEach(bar=>{if(bar.dataset.bound==='1')return;bar.dataset.bound='1';bar.addEventListener('click',e=>{const b=e.target.closest('[data-interval]');if(b&&bar.contains(b))setTf(b.dataset.interval);const c=e.target.closest('[data-classic-interval]');if(c&&bar.contains(c)){document.querySelectorAll('[data-classic-interval]').forEach(x=>x.classList.toggle('active',x===c));classicInterval=c.dataset.classicInterval;loadClassicTrade(classicInterval).catch(()=>{});}const m=e.target.closest('[data-msai-interval]');if(m&&bar.contains(m)){document.querySelectorAll('[data-msai-interval]').forEach(x=>x.classList.toggle('active',x===m));msaiInterval=m.dataset.msaiInterval;loadMSAI(msaiInterval).catch(()=>{});}const sm=e.target.closest('[data-smc-interval]');if(sm&&bar.contains(sm)){document.querySelectorAll('[data-smc-interval]').forEach(x=>x.classList.toggle('active',x===sm));smcInterval=sm.dataset.smcInterval;loadSMC(smcInterval).catch(()=>{});}const asm=e.target.closest('[data-algo-smc-interval]');if(asm&&bar.contains(asm)){document.querySelectorAll('[data-algo-smc-interval]').forEach(x=>x.classList.toggle('active',x===asm));algoSmcInterval=asm.dataset.algoSmcInterval;loadAlgoSMC(algoSmcInterval).catch(()=>{});}})});
  document.querySelectorAll('.nav button[data-section]').forEach(b=>{if(b.dataset.bound==='1')return;b.dataset.bound='1';b.addEventListener('click',e=>{e.preventDefault();openSection(b.dataset.section);});});
  if(document.body.dataset.actionsBound==='1')return;document.body.dataset.actionsBound='1';
  document.addEventListener('click',e=>{
    const ga=e.target.closest?.('[data-mt5-gateway-auto]'); if(ga){e.preventDefault();e.stopPropagation();mt5GatewayToggle(Number(ga.dataset.mt5GatewayAuto),ga.dataset.enabled==='1').catch(err=>showToast(err?.message||'MT5 AutoTrade xatosi'));return;}
    const gp=e.target.closest?.('[data-mt5-gateway-pending]'); if(gp){e.preventDefault();e.stopPropagation();mt5GatewayPendingToggle(Number(gp.dataset.mt5GatewayPending),gp.dataset.enabled==='1').catch(err=>showToast(err?.message||'MT5 Auto Pending xatosi'));return;}
    const gl=e.target.closest?.('[data-mt5-lot-save]'); if(gl){e.preventDefault();e.stopPropagation();const id=Number(gl.dataset.mt5LotSave);const sel=document.querySelector(`[data-mt5-lot="${id}"]`);mt5GatewaySetLot(id,sel?.value).catch(err=>showToast(err?.message||'Lot saqlash xatosi'));return;}
    const gd=e.target.closest?.('[data-mt5-gateway-disconnect]'); if(gd){e.preventDefault();e.stopPropagation();mt5GatewayDisconnect(Number(gd.dataset.mt5GatewayDisconnect)).catch(err=>showToast(err?.message||'MT5 uzish xatosi'));return;}
    const revoke=e.target.closest?.('.active-session-revoke');
    if(revoke){e.preventDefault();e.stopPropagation();revokeOneSession(revoke.dataset.sessionId,revoke.dataset.current==='1').catch(err=>showToast(err?.message||'Seansni yopib bo\'lmadi'));return;}
    const b=e.target.closest?.('button');if(!b)return;const id=b.id;
    if(id==='authBtn'){e.preventDefault();e.stopPropagation();const modal=$('authModal');if(!modal)return;if(String(b.textContent||'').trim()==='Chiqish'){logoutUser();return;}setAuth('login');setText('authMsg','');modal.classList.add('show');setTimeout(()=>$('email')?.focus(),50);return;}
    if(id==='authSwitch'){e.preventDefault();setAuth(authMode==='login'?'register':'login');return;}
    const actions={refreshAIProviders:()=>loadAIProviders(),refreshFallback:()=>loadAllFallback(),refreshICT:()=>loadICTAIPro(),refreshClassic:()=>loadClassicTrade(classicInterval),refreshMSAI:()=>loadMSAI(msaiInterval),refreshSMC:()=>loadSMC(smcInterval),refreshAlgoSMC:()=>loadAlgoSMC(algoSmcInterval),refreshStats:async()=>{await loadStats();await loadHistory()},refreshSmartAnalysis:()=>loadSmartAnalysis(),refreshAISignals:()=>loadAISignals(),refreshCalendar:()=>loadCalendar(),refreshHistory:async()=>{await loadStats();await loadHistory()},refreshTrendChannel:()=>loadTrendChannel(trendChannelInterval),refreshFibonacci:()=>loadFibonacci(fibonacciInterval),refreshNewStrategy:()=>loadNewStrategy(newStrategyInterval),mt5AutoOn:()=>setMT5Auto(true),mt5AutoOff:()=>setMT5Auto(false),refreshMT5:async()=>{await loadMT5Status();await loadMT5GatewayAccounts()},refreshMT5Gateway:()=>loadMT5GatewayAccounts(),createMT5Pairing:()=>createMT5Pairing(),refreshActiveSessions:()=>loadActiveSessions(),revokeOtherSessions:()=>revokeOtherSessions(),revokeAllSessions:()=>revokeAllSessions()};
    if(actions[id]){e.preventDefault();e.stopPropagation();b.disabled=true;const old=b.innerHTML;b.innerHTML='⟳ Ishlanmoqda…';Promise.resolve().then(actions[id]).then(()=>showToast(id.startsWith('refresh')?'Yangilandi':'Bajarildi')).catch(err=>{console.error('UI ACTION ERROR',id,err);showToast((id.startsWith('refresh')?'Yangilash':'Amal')+' xatosi: '+(err?.message||'server xatosi'));}).finally(()=>{b.disabled=false;b.innerHTML=old;});}
  });
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-trend-interval]');if(b){e.preventDefault();document.querySelectorAll('[data-trend-interval]').forEach(x=>x.classList.toggle('active',x===b));trendLineInterval=b.dataset.trendInterval;loadTrendLines(trendLineInterval);}});
document.addEventListener('click',e=>{const f=e.target.closest('[data-fibonacci-interval]');if(f){e.preventDefault();document.querySelectorAll('[data-fibonacci-interval]').forEach(x=>x.classList.toggle('active',x===f));fibonacciInterval=f.dataset.fibonacciInterval;loadFibonacci(fibonacciInterval).catch(()=>{});return;}const b=e.target.closest('[data-channel-interval]');if(b){e.preventDefault();document.querySelectorAll('[data-channel-interval]').forEach(x=>x.classList.toggle('active',x===b));trendChannelInterval=b.dataset.channelInterval;loadTrendChannel(trendChannelInterval).catch(()=>{});return;}const n=e.target.closest('[data-fusion-interval]');if(n){e.preventDefault();document.querySelectorAll('[data-fusion-interval]').forEach(x=>x.classList.toggle('active',x===n));newStrategyInterval=n.dataset.fusionInterval;loadNewStrategy(newStrategyInterval).catch(()=>{});}});
if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',()=>{bindUIActions();bindCriticalButtons()},{once:true});}else{bindUIActions();bindCriticalButtons();}
async function logoutUser(){await api('/api/auth/logout',{method:'POST'}).catch(()=>{});token='';localStorage.removeItem('trading_token');applyRoleAccess(false);$('plan').textContent='Guest';$('authBtn').textContent='Kirish';loadStats();loadHistory();$('authModal').classList.remove('show');$('authMsg').textContent='';showToast('Tizimdan chiqildi')};$('authForm').onsubmit=async e=>{
 e.preventDefault();
 const identity=String($('email').value||'').trim();
 const password=String($('password').value||'');
 $('authMsg').textContent='Tekshirilmoqda…';
 if(!identity || (authMode==='login' && !password)){ $('authMsg').textContent='Login va parolni kiriting.'; return; }
 try{
   const path=authMode==='login'?'/api/auth/login':'/api/auth/register';
   const payload=authMode==='login'?{username:identity,password:password}:{email:identity};
   const d=await api(path,{method:'POST',body:JSON.stringify(payload)});
   if(!d || !d.token) throw Error('Server login javobida token qaytarmadi.');
   token=d.token;
   localStorage.setItem('trading_token',token);
   const u=d.user||{};
   applyRoleAccess(!!(u.is_admin||u.role==='admin'||u.plan==='admin'));
   $('plan').textContent=IS_ADMIN?'ADMIN':(u.plan||'free');
   $('authBtn').textContent='Chiqish';
   if(authMode==='register' && d.credentials){
     $('authMsg').textContent=(d.email_message||'Hisob yaratildi')+' Login: '+d.credentials.login+' | Parol: '+d.credentials.password;
     return;
   }
   $('authMsg').textContent='';
   $('authModal').classList.remove('show');
   showToast(authMode==='login'?'Muvaffaqiyatli kirdingiz':'Hisob yaratildi');
   try{loadStats()}catch(_){}
   try{loadHistory()}catch(_){}
 }catch(err){
   console.error('AUTH ERROR',err);
   $('authMsg').textContent='Kirish xatosi: '+(err?.message||'Server xatosi');
 }
};
(async()=>{
  try{
    try{bindUIActions()}catch(e){console.error('UI binding',e)}
    const phoneStartup=window.innerWidth<=1100;
    mountTradingView('chart', interval);
    loadChartHistory().catch(e=>{const el=$('change');if(el)el.textContent='Chart: '+e.message;});
    connectMarketStream();
    loadSessions().catch(()=>{});
    loadPivots(pivotInterval).catch(()=>{});
    quoteHeartbeat().catch(()=>{});
    if(token){
      try{
        const me=await api('/api/auth/me');
        const u=me.user||{};
        IS_ADMIN=!!(u.is_admin||u.role==='admin'||u.plan==='admin');
        applyRoleAccess(IS_ADMIN);
        if($('plan'))$('plan').textContent=IS_ADMIN?'ADMIN':(u.plan||'free');
        if($('authBtn'))$('authBtn').textContent='Chiqish';
      }catch(_){
        token='';localStorage.removeItem('trading_token');applyRoleAccess(false);
      }
    }
    const refreshMs=phoneStartup?30000:15000;
    setInterval(()=>quoteHeartbeat().catch(()=>{}),phoneStartup?10000:3000);
    setInterval(()=>{
      if(document.visibilityState!=='visible')return;
      if($('ictSection')?.classList.contains('active')) loadICTAIPro().catch(()=>{});
      if($('msaiStrategySection')?.classList.contains('active')) loadMSAI(msaiInterval).catch(()=>{});
      if($('smartAnalysisSection')?.classList.contains('active')) loadSmartAnalysis().catch(()=>{});
      if($('trendChannelSection')?.classList.contains('active')) loadTrendChannel(trendChannelInterval).catch(()=>{});
      if($('trendLineSection')?.classList.contains('active')) loadTrendLines(trendLineInterval).catch(()=>{});
      if($('analysisSection')?.classList.contains('active')) loadAnalysisOnly().catch(()=>{});
      if($('classicSection')?.classList.contains('active')) loadClassicTrade(classicInterval).catch(()=>{});
      if($('smcSection')?.classList.contains('active')) loadSMC(smcInterval).catch(()=>{});
      if($('fibonacciSection')?.classList.contains('active')) loadFibonacci(fibonacciInterval).catch(()=>{});
      if($('mt5Section')?.classList.contains('active')&&IS_ADMIN) loadMT5Status().catch(()=>{});
      if($('historySection')?.classList.contains('active')&&token){loadStats().catch(()=>{});loadHistory().catch(()=>{});}
    },refreshMs);
    setInterval(updateCountdown,phoneStartup?1000:250);
  }catch(e){
    console.error('Dashboard init error',e);
    if($('mode'))$('mode').textContent='UI READY';
    try{mountTradingView('chart', interval)}catch(_){ }
  }
})();;


(function bindHistoryV2(){
  function dateKeyLocal(d){return d.toLocaleDateString('en-CA',{timeZone:'Asia/Tashkent'});}
  function applyRange(range){const s=document.getElementById('historyV2Start'),e=document.getElementById('historyV2End');const now=new Date();if(range==='all'){s.value='';e.value='';}else if(range==='today'){const k=dateKeyLocal(now);s.value=k;e.value=k;}else if(range==='yesterday'){const d=new Date(now.getTime()-86400000);const k=dateKeyLocal(d);s.value=k;e.value=k;}else{const k=dateKeyLocal(now);const d=new Date(now.getTime()-Number(range)*86400000);s.value=dateKeyLocal(d);e.value=k;}document.querySelectorAll('.h2-date').forEach(b=>b.classList.toggle('active',b.dataset.range===range));loadHistory();}
  document.addEventListener('click',async e=>{if(e.target.closest('#historyV2LoadMore')){historyV2Offset+=20;loadHistory(true);return;}const b=e.target.closest('.h2-date');if(b){historyV2Offset=0;applyRange(b.dataset.range);return;}if(e.target.closest('#historyV2Refresh')){historyV2Offset=0;loadHistory();loadStats?.();return;}const d=e.target.closest('[data-history-detail]');if(d){e.preventDefault();e.stopPropagation();const id=String(d.dataset.historyDetail||'');let x=HISTORY_DETAIL_CACHE.get(id);if(!x){try{const r=await api('/api/v2/signal-history?limit=500');x=(r.items||[]).find(i=>String(i.signal_id)===id);if(x)HISTORY_DETAIL_CACHE.set(id,x);}catch(err){showToast(err?.message||'Signal tafsilotlarini yuklab bo‘lmadi');return;}}if(!x){showToast('Signal tafsiloti topilmadi');return;}const modal=document.getElementById('historyDetailModal');if(!modal)return;document.getElementById('historyDetailTitle').textContent=`${x.direction} · ${x.symbol}`;document.getElementById('historyDetailMeta').textContent=`${x.signal_id} · ${x.source} · ${tfName(x.interval)}`;document.getElementById('historyDetailBody').innerHTML=renderHistoryDetail(x);modal.setAttribute('aria-hidden','false');modal.classList.add('show');}});
  document.addEventListener('change',e=>{if(e.target.id&&['historyV2Start','historyV2End','historyV2Symbol','historyV2Direction','historyV2Result','historyV2Module'].includes(e.target.id)){historyV2Offset=0;loadHistory();}});
  document.addEventListener('click',e=>{const modal=document.getElementById('historyDetailModal');if(!modal)return;if(e.target.closest('#historyDetailClose')||e.target===modal){modal.setAttribute('aria-hidden','true');modal.classList.remove('show');}});document.addEventListener('keydown',e=>{if(e.key==='Escape'){const modal=document.getElementById('historyDetailModal');if(modal){modal.setAttribute('aria-hidden','true');modal.classList.remove('show');}}});
})();

;
