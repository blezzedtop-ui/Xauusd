const symbol='XAU/USD';let interval='5min',pivotInterval='5min',aiInterval='5min',signalInterval='5min',token=localStorage.getItem('trading_token')||'',authMode='login',chart,series,chart2,series2,countdownData={close_timestamp:null},marketWS=null,liveCandle=null,lastTickTs=0,lastRestQuoteAt=0,streamKey='';
const $=id=>document.getElementById(id);const fmt=v=>v==null?'—':Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:4});
function showToast(m){$('toast').textContent=m;$('toast').classList.add('show');setTimeout(()=>$('toast').classList.remove('show'),2300)}

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
async function api(path,opt={}){const headers={'Content-Type':'application/json',...(opt.headers||{})};if(token)headers.Authorization='Bearer '+token;let last;for(const base of API_CANDIDATES){try{const url=path.startsWith('http')?path:base+path;const r=await fetch(url,{...opt,headers,cache:'no-store'});let d={};try{d=await r.json()}catch{}if(!r.ok)throw Error(d.detail||d.message||'HTTP '+r.status);return d}catch(e){last=e}}if(last instanceof TypeError){throw Error('Cloud backendga ulanib bo‘lmadi. Saytning cloud serveri ulanmagan yoki hozircha ishlamayapti.') }throw last}
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
   symbol:'OANDA:XAUUSD',
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
 if($('chartSection').classList.contains('active')) setTimeout(()=>mountTradingView('chart2', interval),50);
 loadChartHistory().catch(e=>{$('signalReason').textContent='Chart data error: '+e.message});
 loadMain(true);
 connectMarketStream();
}
async function loadMain(force=false){
  try{
    const d=await api(`/api/v1/book-openai-analysis/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(interval)}${force?'&fresh=1':''}`);
    renderBookOpenAI(d);
    // The price beside the chart is updated only by the canonical TradingView/OANDA quote heartbeat.
    // Do not paint the Book candle-feed price here: it can be a different provider/feed.
    countdownData=d.candle||countdownData; updateCountdown();
    if(d.signal) markSignal(d.signal, d.candles?.[d.candles.length-1]?.time || Math.floor(Date.now()/1000));
    return d;
  }catch(e){$('signalReason').textContent='Book/OpenAI analysis error: '+(e.message||'unknown');return null;}
}
async function loadChartHistory(){
 const c=await api(`/api/v1/candles/${encodeURIComponent(symbol)}?interval=${interval}&limit=500`);
 if(c.mode!=='live') throw Error(c.warning||'LIVE market data unavailable');
 applyChart(c.candles,c.mode); countdownData=c.candle; updateCountdown();
}
async function loadAnalysisOnly(){
  const d=await loadMain(false);
  if(d?.ok===false){ $('mode').textContent='LIVE ERROR'; $('mode').style.color='var(--amber)'; }
  return d;
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
async function loadAISmart(tf=aiInterval){
  aiInterval=tf; $('aiSummary').textContent='OpenAI second opinion yuklanmoqda...';
  try{ const d=await api(`/api/v1/book-openai-analysis/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(tf)}`); renderBookOpenAI(d); }
  catch(e){ $('aiMode').textContent='ERROR'; $('aiSummary').textContent=e.message||'OpenAI analysis ishlamadi'; }
}
function renderBookOpenAI(d){
 const sig=d.signal||'WAIT', cls=sig==='BUY'?'buy':sig==='SELL'?'sell':'wait';
 $('signalMain').textContent=sig; $('signalMain').className='signal-main '+cls;
 const book=d.book||{}, ai=d.openai||{};
 const confirmed=(book.patterns||[]).filter(x=>x.signal==='BUY'||x.signal==='SELL').map(x=>x.name).join(', ');
 $('signalReason').textContent=`Book: ${book.signal||'WAIT'}${confirmed?' · '+confirmed:''} | OpenAI: ${ai.signal||'WAIT'} · ${ai.reason||'—'}`;
 $('entry').textContent=fmt(d.entry);$('sl').textContent=fmt(d.stop_loss);$('tp1').textContent=fmt((d.take_profit||[])[0]);$('tp2').textContent=fmt((d.take_profit||[])[1]);
 $('bias').textContent=`Book ${book.signal||'WAIT'} · AI ${ai.signal||'WAIT'}`;
 $('aiMode').textContent=ai.mode||'—';$('aiSummary').textContent=ai.reason||'—';$('confidence').textContent=ai.confidence!=null?ai.confidence+'%':'—';$('aiBias').textContent=ai.signal||'WAIT';$('aiAdvice').textContent=sig==='WAIT'?'Book va OpenAI bir xil yo‘nalishda tasdiqlamadi.':'Book pattern + OpenAI second opinion bir xil yo‘nalishni tasdiqladi.';
}
function renderAnalysis(d){const s=d.setup||{},ta=d.technical||{};$('signalMain').textContent=d.direction||'WAIT';$('signalMain').className='signal-main '+((d.direction||'WAIT').toLowerCase()==='buy'?'buy':(d.direction||'').toLowerCase()==='sell'?'sell':'wait');$('signalReason').textContent=d.headline||s.reason||'—';$('entry').textContent=fmt(s.entry);$('sl').textContent=fmt(s.stop_loss);$('tp1').textContent=fmt((s.take_profit||[])[0]);$('tp2').textContent=fmt((s.take_profit||[])[1]);$('bias').textContent=d.levels?.bias||s.pivot_filter||'—';$('pivotFilter').textContent=d.levels?.bias||'—';const p=d.levels||{};$('levels').innerHTML=[['R3',p.r3,'res'],['R2',p.r2,'res'],['R1',p.r1,'res'],['Pivot',p.pivot,'piv'],['S1',p.s1,'sup'],['S2',p.s2,'sup'],['S3',p.s3,'sup']].map(x=>`<div class="row"><span>${x[0]}</span><b class="${x[2]}">${fmt(x[1])}</b></div>`).join('');$('rsi').textContent=fmt(ta.rsi);$('atr').textContent=fmt(ta.atr);$('rsiState').textContent=ta.rsi_state||'—';$('taTrend').textContent=ta.trend||'—';$('taState').textContent=d.interval?.toUpperCase()||interval;$('taSummary').textContent=ta.summary||'—';const ai=d.ai||{};$('aiMode').textContent=ai.mode||'—';$('aiSummary').textContent=ai.summary||'—';$('confidence').textContent=ai.confidence!=null?ai.confidence+'%':'—';$('aiBias').textContent=ai.bias||'—';$('aiAdvice').textContent=ai.advice||'—';}
function updateCountdown(){const ts=countdownData?.close_timestamp; if(!ts)return;$('countdown').textContent=fmtDuration(Math.max(0,ts*1000-Date.now())); const close=new Date(ts*1000); $('closeTime').textContent='Close time: '+close.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});}function fmtDuration(ms){let s=Math.floor(ms/1000),h=Math.floor(s/3600);s%=3600;let m=Math.floor(s/60);s%=60;return h?`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`}
async function loadSessions(){try{const d=await api('/api/v1/sessions');const html=d.sessions.map(x=>`<div class="session ${x.open?'open':''}"><b>${x.name}</b><div class="sub">${x.local_time||''}</div><div class="status ${x.open?'up':'muted'}">${x.open?'OPEN':'CLOSED'}</div></div>`).join('');$('sessions').innerHTML=html;$('sessions2').innerHTML=html;$('sessionClock').textContent=d.utc_time||'—';$('sessionClock2').textContent=d.utc_time||'—'}catch(e){}}
async function loadCalendar(){try{const d=await api('/api/v1/calendar?days=14');const source=d.provider?` · Source: ${d.provider}`:'';if(!d.events?.length){$('calendar').innerHTML=`<div class="mini">${d.warning||'USA/USD economic events topilmadi.'}</div>`;return}const now=Date.now();const rows=d.events.map(x=>{const dt=x.time?Date.parse(x.time):NaN;const until=Number.isFinite(dt)?(dt-now):null;const when=until!=null?(until>0?` · T−${fmtDuration(until)}`:` · ${Math.abs(until)<3600000?'LIVE/RECENT':'o‘tgan'}`):'';return `<div class="calendar-item"><div><span class="tag">${x.impact||'MEDIUM'}</span> · ${x.country||'USD'} · ${x.time||''}${when}</div><b>${x.event||'Economic event'}</b><div class="mini">Kutilmoqda: ${x.forecast??x.estimate??'—'} · Oldingi: ${x.previous??'—'} · Actual: ${x.actual??'—'} ${x.unit||''}</div><div class="mini">Source: ${x.source||d.provider||'—'}</div></div>`}).join('');$('calendar').innerHTML=`<div class="mini" style="margin-bottom:8px">ALL CURRENCIES · ALL IMPACT${source} · ${d.events.length} event</div>`+rows}catch(e){$('calendar').innerHTML=`<div class="mini">Calendar ma’lumoti hozircha mavjud emas: ${e.message}</div>`}}
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
async function loadStats(){if(!token){$('totalSignals').textContent='0';$('completedSignals').textContent='0';$('wins').textContent='0';$('losses').textContent='0';$('winrate').textContent='0%';return}try{const d=await api('/api/v1/signals/analytics');$('totalSignals').textContent=d.total_signals;$('completedSignals').textContent=d.completed_trades;$('wins').textContent=d.wins;$('losses').textContent=d.losses;$('winrate').textContent=d.winrate+'%'}catch(e){}}
async function loadHistory(){if(!token){$('history').innerHTML='<tr><td colspan="7">Kirish kerak.</td></tr>';return}try{const d=await api('/api/v1/signals/history?limit=50');$('history').innerHTML=(d.items||[]).map(x=>`<tr><td>${new Date(x.created_at).toLocaleString()}</td><td>${x.interval}</td><td class="${x.direction==='BUY'?'buy':x.direction==='SELL'?'sell':''}">${x.direction}</td><td>${fmt(x.entry)}</td><td>${(x.tp||[]).map(fmt).join(' / ')||'—'}</td><td>${fmt(x.sl)}</td><td class="outcome-${x.outcome==='TP HIT'?'tp':x.outcome==='SL HIT'?'sl':x.outcome==='OPEN'?'open':'amb'}">${x.outcome}</td></tr>`).join('')||'<tr><td colspan="7">Signal yo‘q.</td></tr>'}catch(e){$('history').innerHTML='<tr><td colspan="7">History yuklanmadi.</td></tr>'}}
function componentText(v){if(v==null)return '—';if(typeof v==='object'){if(v.type)return v.type+(v.low!=null?' · '+fmt(v.low)+'–'+fmt(v.high):'');if(v.support!=null)return 'S '+fmt(v.support)+' · R '+fmt(v.resistance);return JSON.stringify(v)}return String(v)}
function tfName(tf){return ({'1min':'1 MIN','5min':'5 MIN','15min':'15 MIN','30min':'30 MIN','1h':'1 HOUR','4h':'4 HOUR','1day':'1 DAY'})[tf]||tf;}
function advCard(tf,x){const sig=x.signal||'WAIT', cls=sig==='BUY'?'buy':sig==='SELL'?'sell':'wait', badge=sig==='BUY'?'badge-buy':sig==='SELL'?'badge-sell':'badge-wait';const c=x.components||{};return `<div class="advanced-card ${cls}"><div class="advanced-head"><div><div class="mini">${tfName(tf)}</div><div class="advanced-signal ${badge}">${sig}</div></div><span class="pill">${x.confidence||0}%</span></div><div class="mini" style="margin-top:4px">Score ${x.score??0} · ${x.setup||'—'}</div><div class="grid4" style="margin-top:9px"><div class="metric"><small>Entry</small><b>${fmt(x.entry)}</b></div><div class="metric"><small>SL</small><b>${fmt(x.stop_loss)}</b></div><div class="metric"><small>TP1</small><b>${fmt((x.take_profit||[])[0])}</b></div><div class="metric"><small>TP2</small><b>${fmt((x.take_profit||[])[1])}</b></div></div><div class="component-grid"><div class="component"><small>ICT</small><b>${componentText(c['ICT'])}</b></div><div class="component"><small>SNR</small><b>${componentText(c['SNR'])}</b></div><div class="component"><small>SNR Malaysia</small><b>${componentText(c['SNR Malaysia'])}</b></div><div class="component"><small>Order Block</small><b>${componentText(c['Order Block'])}</b></div><div class="component"><small>FVG</small><b>${componentText(c['FVG'])}</b></div><div class="component"><small>Liquidity</small><b>${componentText(c['Liquidity'])}</b></div><div class="component"><small>Trend Line</small><b>${componentText(c['Trend Line'])}</b></div><div class="component"><small>Global Trend</small><b>${componentText(c['Global Trend Line'])}</b></div><div class="component"><small>BOS</small><b>${componentText(c['BOS'])}</b></div><div class="component"><small>CHOCH</small><b>${componentText(c['CHOCH'])}</b></div><div class="component"><small>Internal</small><b>${componentText(c['Internal Structure'])}</b></div><div class="component"><small>RSI / ATR</small><b>${fmt(x.rsi)} / ${fmt(x.atr)}</b></div></div><div class="advanced-actions"><div class="mini">${x.reason||'—'}</div>${sig==='BUY'||sig==='SELL'?`<button class="btn" data-save-advanced="${tf}">Saqlash</button>`:''}</div></div>`}
async function loadAdvancedSignals(){$('advancedStatus').textContent='7 timeframe hisoblanmoqda…';$('advancedGrid').innerHTML='<div class="card">Signal hisoblanmoqda...</div>';try{const d=await api(`/api/v1/signals/advanced/${encodeURIComponent(symbol)}`);const order=['1min','5min','15min','30min','1h','4h','1day'];$('advancedGrid').innerHTML=order.map(tf=>advCard(tf,d.timeframes?.[tf]||{})).join('');$('advancedStatus').textContent=`${symbol} · ${new Date(d.generated_at).toLocaleString()} · har bir timeframe alohida`; }catch(e){$('advancedStatus').textContent=e.message;$('advancedGrid').innerHTML='<div class="card">Signal yuklanmadi.</div>'}}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-save-advanced]');if(!b)return;const tf=b.dataset.saveAdvanced;b.disabled=true;try{await api(`/api/v1/signals/save-advanced?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(tf)}`,{method:'POST'});showToast(tfName(tf)+' signal saqlandi');loadStats();if($('historySection').classList.contains('active'))loadHistory()}catch(err){showToast(err.message)}finally{b.disabled=false}});
async function loadAutoSignals(){
  try{
    const d=await api(`/api/v1/signals/live/${encodeURIComponent(symbol)}`);
    const order=['1min','5min','15min','30min','1h','4h','1day'];
    $('autoSignalsGrid').innerHTML=order.map(tf=>{
      const x=d.timeframes?.[tf]||{};
      const sig=x.signal||'WAIT';
      const cls=sig==='BUY'?'buy':sig==='SELL'?'sell':'wait';
      return `<div class="signal-box auto-signal"><div class="section-head"><b>${tfName(tf)}</b><span class="pill">${x.confidence||0}% · ${x.mode||'LIVE'}</span></div><div class="signal-main ${cls}">${sig}</div><div class="mini">Live price: ${fmt(x.current_price)} · Entry: ${fmt(x.entry)} · SL: ${fmt(x.stop_loss)} · TP: ${(x.take_profit||[]).map(fmt).join(' / ')||'—'}</div><div class="mini">${x.reason||'Live engine'}</div><div class="mini">${x.evaluated_at?new Date(x.evaluated_at).toLocaleTimeString():''}</div></div>`;
    }).join('');
    $('autoSignalUpdated').textContent='LIVE · '+new Date(d.generated_at).toLocaleTimeString();
    if(token){ try{ const saved=await api(`/api/v1/signals/auto-record?symbol=${encodeURIComponent(symbol)}`,{method:'POST'}); if(saved.count) { loadStats(); if($('historySection').classList.contains('active')) loadHistory(); } }catch(_){} }
  }catch(e){$('autoSignalsGrid').innerHTML=`<div class="card">Live Signals error: ${e.message}</div>`}
}
function openSection(id){const target=$(id);if(!target)return;document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));target.classList.add('active');document.querySelectorAll('.nav button').forEach(b=>b.classList.toggle('active',b.dataset.section===id));const titles={overview:'Market Overview',chartSection:'Live Chart',analysisSection:'Technical Analysis',mtfSection:'Multi-Timeframe Analysis',aiSection:'AI Smart Analysis',signalSection:'Signal Lab',signalsSection:'Signals',calendarSection:'Economic Calendar',sessionsSection:'Market Sessions',historySection:'Signal History'};$('pageTitle').textContent=titles[id]||'Trading SaaS';if(id==='chartSection'){setTimeout(()=>{mountTradingView('chart2',interval);loadChartHistory().catch(()=>{})},50);}if(id==='overview'){setTimeout(()=>{mountTradingView('chart',interval);loadChartHistory().catch(()=>{})},50);}if(id==='analysisSection')loadAnalysisOnly().catch(()=>{});if(id==='aiSection')loadAISmart(aiInterval);if(id==='signalSection')loadSelectedSignal(signalInterval);if(id==='calendarSection')loadCalendar();if(id==='sessionsSection')loadSessions();if(id==='mtfSection')loadMtf();if(id==='historySection')loadHistory();if(id==='signalsSection')loadAutoSignals()}

document.addEventListener('click',e=>{
  const b=e.target.closest('[data-pivot-interval]');
  if(b){
    document.querySelectorAll('[data-pivot-interval]').forEach(x=>x.classList.toggle('active',x===b));
    loadPivots(b.dataset.pivotInterval);
  }
  const a=e.target.closest('[data-ai-interval]');
  if(a){
    document.querySelectorAll('[data-ai-interval]').forEach(x=>x.classList.toggle('active',x===a));
    loadAISmart(a.dataset.aiInterval);
  }
  const s=e.target.closest('[data-signal-interval]');
  if(s){
    document.querySelectorAll('[data-signal-interval]').forEach(x=>x.classList.toggle('active',x===s));
    signalInterval=s.dataset.signalInterval;
    loadSelectedSignal(signalInterval);
  }
});
async function loadSelectedSignal(tf){
  try{
    const d=await api(`/api/v1/signals/advanced/${encodeURIComponent(symbol)}`);
    const x=d.timeframes?.[tf]||{};
    $('advancedStatus').textContent=`${tfName(tf)} signal · ${x.provider||'local engine'} · ${x.confidence||0}%`;
    $('advancedGrid').innerHTML=advCard(tf,x);
  }catch(e){
    $('advancedStatus').textContent=e.message;
    $('advancedGrid').innerHTML='<div class="card">Signal yuklanmadi.</div>';
  }
}
async function saveSignal(){if(!token){showToast('Avval tizimga kiring');$('authModal').classList.add('show');return}try{await api(`/api/v1/signals/save?symbol=${encodeURIComponent(symbol)}&interval=${interval}`,{method:'POST'});showToast('Signal saqlandi');loadStats();loadHistory()}catch(e){showToast(e.message)}}

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
function setAuth(mode){authMode=mode;$('authTitle').textContent=mode==='login'?'Kirish':'Ro‘yxatdan o‘tish';$('authSubmit').textContent=mode==='login'?'Kirish':'Ro‘yxatdan o‘tish';$('authSwitch').textContent=mode==='login'?'Hisobingiz yo‘qmi? Ro‘yxatdan o‘tish':'Hisobingiz bormi? Kirish';$('email').placeholder=mode==='login'?'Login yoki elektron pochta':'Elektron pochta';$('password').required=mode==='login';$('password').style.display=mode==='login'?'block':'none';$('password').value='';$('authMsg').textContent=mode==='register'?'Email kiriting — login va parol avtomatik yaratiladi.':''}
document.querySelectorAll('.tfbar').forEach(bar=>bar.addEventListener('click',e=>{const b=e.target.closest('[data-interval]');if(b && bar.contains(b))setTf(b.dataset.interval)}));document.querySelectorAll('.nav button').forEach(b=>b.addEventListener('click',()=>openSection(b.dataset.section)));$('saveSignal').onclick=saveSignal;$('refreshAdvanced').onclick=loadAdvancedSignals;$('refreshStats').onclick=loadStats;$('refreshCalendar').onclick=loadCalendar;$('refreshHistory').onclick=loadHistory;$('authBtn').onclick=()=>{ setAuth('login'); $('authMsg').textContent=''; $('authModal').classList.add('show'); setTimeout(()=>$('email').focus(),50); }; $('authSwitch').onclick=()=>setAuth(authMode==='login'?'register':'login');async function logoutUser(){await api('/api/auth/logout',{method:'POST'}).catch(()=>{});token='';localStorage.removeItem('trading_token');$('plan').textContent='Guest';$('authBtn').textContent='Kirish';loadStats();loadHistory();$('authModal').classList.remove('show');$('authMsg').textContent='';showToast('Tizimdan chiqildi')};$('authForm').onsubmit=async e=>{
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
   $('plan').textContent=d.user?.plan||'free';
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
// Auth fallback: keep the login modal usable even if a non-auth dashboard module fails during startup.
document.addEventListener('click',e=>{
  const btn=e.target.closest && e.target.closest('#authBtn');
  if(!btn) return;
  const modal=$('authModal');
  if(!modal) return;
  if(btn.textContent.trim()==='Chiqish'){ return; }
  try{setAuth('login'); $('authMsg').textContent=''; modal.classList.add('show'); setTimeout(()=>$('email').focus(),50);}catch(err){console.error('AUTH UI ERROR',err);}
});
(async()=>{
  // Stable startup: chart first, then independent data modules. No login modal
  // may block navigation or public market analysis. Authentication is only
  // required for saving signals/history.
  try{
    mountTradingView('chart', interval);
    loadChartHistory().catch(e=>{ $('change').textContent='Chart: '+e.message; });
    connectMarketStream();
    $('mode').textContent='TRADINGVIEW LIVE'; $('mode').style.color='var(--green)'; $('chartStatus').textContent='LIVE';
    // Market source is intentionally fixed to the TradingView OANDA:XAUUSD series.
    $('mode').textContent='TRADINGVIEW LIVE'; $('mode').style.color='var(--green)'; $('chartStatus').textContent='LIVE';
    // Never let one slow/failing module prevent the rest of the dashboard.
    loadMain(true).catch(e=>{$('signalReason').textContent='Live analysis unavailable: '+(e.message||'server error')});
    quoteHeartbeat().catch(()=>{});
    loadSessions().catch(()=>{});
    if(token){
      try{const me=await api('/api/auth/me');$('plan').textContent=me.plan||'free';$('authBtn').textContent='Chiqish'}
      catch(_){token='';localStorage.removeItem('trading_token')}
      loadStats().catch(()=>{}); loadHistory().catch(()=>{});
    }
    // Lightweight quote heartbeat; do not hammer REST APIs.
    setInterval(()=>quoteHeartbeat().catch(()=>{}),3000);
    // Main signal/analysis refresh.
    setInterval(()=>{
      if(document.visibilityState!=='visible') return;
      loadAnalysisOnly().catch(()=>{});
      if($('signalsSection').classList.contains('active')) loadAutoSignals().catch(()=>{});
      if($('signalSection').classList.contains('active')) loadSelectedSignal(signalInterval).catch(()=>{});
    },15000);
    // Expensive modules refresh only while visible.
    setInterval(()=>{
      if(document.visibilityState!=='visible') return;
      if($('mtfSection').classList.contains('active')) loadMtf().catch(()=>{});
      if($('aiSection').classList.contains('active')) loadAISmart(aiInterval).catch(()=>{});
      if($('calendarSection').classList.contains('active')) loadCalendar().catch(()=>{});
      if($('sessionsSection').classList.contains('active')) loadSessions().catch(()=>{});
      if(token && $('historySection').classList.contains('active')) loadHistory().catch(()=>{});
    },30000);
    setInterval(updateCountdown,250);
  }catch(e){
    console.error('Dashboard init error',e);
    $('mode').textContent='UI READY';
    // Keep the navigation/chart usable even when the backend is temporarily down.
    try{mountTradingView('chart', interval)}catch(_){}
  }
})();;