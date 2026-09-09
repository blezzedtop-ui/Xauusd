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
const DISABLE_MARKET_WS=IS_NETLIFY || window.DISABLE_MARKET_WS===true;
async function nodeMarketHealth(){if(!NODE_MARKET_URL)return null;try{const r=await fetch(`${NODE_MARKET_URL}/health`,{cache:'no-store'});if(!r.ok) return null;return await r.json()}catch{return null}}
async function api(path,opt={}){const headers={'Content-Type':'application/json',...(opt.headers||{})};if(token)headers.Authorization='Bearer '+token;let last;for(const base of API_CANDIDATES){try{const url=path.startsWith('http')?path:base+path;const r=await fetch(url,{...opt,headers,cache:'no-store'});let d={};try{d=await r.json()}catch{}if(!r.ok)throw Error(d.detail||d.message||'HTTP '+r.status);return d}catch(e){last=e}}if(last instanceof TypeError){throw Error('Cloud backendga ulanib bo‘lmadi. Saytning cloud serveri ulanmagan yoki hozircha ishlamayapti.') }throw last}
function tvInterval(tf){return ({'1min':'1','5min':'5','15min':'15','30min':'30','1h':'60','4h':'240','1day':'D'})[tf]||'5'}
function mountTradingView(id, tf=interval){
 const el=$(id); if(!el)return;
 el.innerHTML=''; el.style.minHeight=innerWidth<700?'420px':'520px'; el.style.height=innerWidth<700?'420px':'560px';
 const wrap=document.createElement('div'); wrap.className='tradingview-widget-container'; wrap.style.cssText='height:100%;width:100%';
 const host=document.createElement('div'); host.className='tradingview-widget-container__widget'; host.style.cssText='height:calc(100% - 32px);width:100%';
 const note=document.createElement('div'); note.className='tv-data-note'; note.textContent='TradingView chart • Analysis/Signal: same XAUUSD backend candle feed';
 const script=document.createElement('script'); script.src='https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'; script.type='text/javascript'; script.async=true;
 script.textContent=JSON.stringify({autosize:true,symbol:'OANDA:XAUUSD',interval:tvInterval(tf),timezone:'Asia/Tashkent',theme:'dark',style:'1',locale:'en',allow_symbol_change:false,calendar:false,hide_top_toolbar:false,hide_legend:false,save_image:false,withdateranges:true,hide_volume:false,support_host:'https://www.tradingview.com'});
 wrap.appendChild(host); wrap.appendChild(script); el.appendChild(wrap); el.appendChild(note);
}
function initChart(id){ mountTradingView(id, interval); return {c:null,s:null}; }
function applyChart(candles,mode){
 const data=(candles||[]).map(x=>({time:x.time,open:+x.open,high:+x.high,low:+x.low,close:+x.close})).filter((x,i,a)=>i===0||x.time>a[i-1].time);
 liveCandle=data[data.length-1]||null;
 if(data.length){
   const first=data[0].time,last=data[data.length-1].time,days=Math.max(1,Math.round((last-first)/86400));
   $('change').textContent=`${data.length.toLocaleString()} candles · ${days} days history`;
   $('historyInfo').textContent=`${days}+ days · ${data.length.toLocaleString()} candles`;
 }
 $('mode').textContent=mode==='live'?'LIVE MARKET':'LIVE RETRY'; $('mode').style.color=mode==='live'?'var(--green)':'var(--amber)'; $('chartStatus').textContent=mode==='live'?'LIVE MARKET':'RETRYING';
}
function setTf(v){
 interval=v;
 liveCandle=null;
 document.querySelectorAll('[data-interval]').forEach(b=>b.classList.toggle('active',b.dataset.interval===v));
 if($('tfLabel'))$('tfLabel').textContent=({'1min':'1 MIN','5min':'5 MIN','15min':'15 MIN','30min':'30 MIN','1h':'1 HOUR','4h':'4 HOUR','1day':'1 DAY'})[v]||v;
 mountTradingView('chart', interval); if($('chartSection').classList.contains('active')) setTimeout(()=>mountTradingView('chart2', interval),50); loadMain(true);
}
async function loadMain(force=false){
  try{
    const d=await api(`/api/v1/analysis/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(interval)}${force?'&fresh=1':''}`);
    renderAnalysis(d);
    if(d.current_price!=null) $('price').textContent=fmt(d.current_price);
    countdownData=d.candle||countdownData; updateCountdown();
    // Pivot is independent: never block the main chart/analysis render on it.
    loadPivots(pivotInterval).catch(()=>{});
    return d;
  }catch(e){
    $('signalReason').textContent='LIVE analysis error: '+(e.message||'unknown');
    return null;
  }
}
async function loadChartHistory(){
 const c=await api(`/api/v1/candles/${encodeURIComponent(symbol)}?interval=${interval}&limit=500`);
 if(c.mode!=='live') throw Error(c.warning||'LIVE market data unavailable');
 applyChart(c.candles,c.mode);
 countdownData=c.candle;
 updateCountdown();
}
async function loadAnalysisOnly(){
  try{
    const d=await api(`/api/v1/analysis/${encodeURIComponent(symbol)}?interval=${interval}`);
    renderAnalysis(d);
    await loadPivots(pivotInterval);
    if(d.ok===false){
      $('signalReason').textContent='Analysis xatosi: '+(d.error||d.headline||'unknown error');
      $('mode').textContent='LIVE ERROR'; $('mode').style.color='var(--amber)';
    } else if(d.mode==='live'){
      $('mode').textContent='LIVE DATA'; $('mode').style.color='var(--green)'; $('chartStatus').textContent='LIVE';
    }
    countdownData=d.candle||countdownData; updateCountdown(); return d;
  }catch(e){
    $('signalReason').textContent='Analysis vaqtincha mavjud emas: '+(e.message||'unknown error');
    throw e;
  }
}
function zoneCard(z,side,primary=false){const cls=side==='support'?'zone-demand':'zone-supply';const ev=(z.evidence||[]).map(x=>x.replaceAll('_',' ')).join(' · ');return `<div class="zone-card ${cls} ${primary?'primary':''}"><div class="zone-top"><b>${primary?'★ ':''}${side==='support'?'DEMAND / SUPPORT':'SUPPLY / RESISTANCE'}</b><span>${z.strength||0}/100</span></div><div class="zone-price">${fmt(z.min)} — ${fmt(z.max)}</div><div class="zone-meta">Center ${fmt(z.center)} · ${z.touches||0} touches · ${ev||'real OHLC'}</div></div>`}
function renderPivotZones(z,ai,tf){const s=z.support_zones||[],r=z.resistance_zones||[],ps=ai?.primary_support_id,pr=ai?.primary_resistance_id;let cards=[];if(ps!=null&&s[ps])cards.push(zoneCard(s[ps],'support',true));if(pr!=null&&r[pr])cards.push(zoneCard(r[pr],'resistance',true));s.filter((_,i)=>i!==ps).slice(0,3).forEach(x=>cards.push(zoneCard(x,'support')));r.filter((_,i)=>i!==pr).slice(0,3).forEach(x=>cards.push(zoneCard(x,'resistance')));$('levels').innerHTML=cards.length?cards.join(''):`<div class="zone-empty">${tfName(tf)} real grafikdan zona topilmadi.</div>`;let summary=`AI ZONE BIAS: ${ai?.bias||'NEUTRAL'}`;if(z.current_price!=null)summary+=` · Price ${fmt(z.current_price)}`;if(ai?.reasoning?.length)summary+=`<br>• ${ai.reasoning.slice(0,4).join('<br>• ')}`;$('pivotAiSummary').innerHTML=summary}
async function loadPivots(tf=pivotInterval){pivotInterval=tf;$('pivotFilter').textContent=`${tfName(tf)} · AI ZONES`;$('pivotSource').textContent='Real XAU/USD OHLC → zones → AI ranking...';try{const d=await api(`/api/v1/pivots/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(tf)}`);const z=d.zones||{},ai=z.ai||{};renderPivotZones(z,ai,tf);$('pivotSource').textContent=`REAL OHLC · ${tfName(tf)} · ${ai.mode==='openai'?'OPENAI AI ZONE ANALYSIS':'RULE-BASED ZONE ANALYSIS'}${d.warning?' · '+d.warning:''}`}catch(e){$('levels').innerHTML=`<div class="zone-empty">${tfName(tf)} real market zones yuklanmadi.</div>`;$('pivotAiSummary').textContent='AI zone analysis xatosi: '+e.message;$('pivotSource').textContent='Real market data unavailable'}}
async function loadAISmart(tf=aiInterval){
  aiInterval=tf;
  $('aiSummary').textContent='AI tahlil yuklanmoqda...';
  try{
    const d=await api(`/api/v1/ai-smart-analysis/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(tf)}`);
    const ai=d.ai_smart||d.ai||{};
    $('aiMode').textContent=ai.mode||'fallback';
    $('aiSummary').textContent=ai.summary||d.error||'—';
    $('confidence').textContent=ai.confidence!=null?ai.confidence+'%':'—';
    $('aiBias').textContent=ai.bias||'—';
    $('aiAdvice').textContent=ai.advice||'—';
  }catch(e){
    $('aiMode').textContent='ERROR';
    $('aiSummary').textContent=e.message||'AI Smart Analysis ishlamadi';
  }
}
function renderAnalysis(d){const s=d.setup||{},ta=d.technical||{},c=ta.confluence||{};$('signalMain').textContent=d.direction||'WAIT';$('signalMain').className='signal-main '+((d.direction||'WAIT').toLowerCase()==='buy'?'buy':(d.direction||'').toLowerCase()==='sell'?'sell':'wait');$('signalReason').textContent=d.headline||s.reason||'—';$('entry').textContent=fmt(s.entry);$('sl').textContent=fmt(s.stop_loss);$('tp1').textContent=fmt((s.take_profit||[])[0]);$('tp2').textContent=fmt((s.take_profit||[])[1]);$('bias').textContent=d.levels?.bias||s.pivot_filter||'—';$('pivotFilter').textContent=d.levels?.bias||'—';renderPivotZones(d.zones||{},d.zones?.ai||{},d.interval||interval);$('rsi').textContent=fmt(ta.rsi);$('atr').textContent=fmt(ta.atr);$('rsiState').textContent=ta.rsi_state||'—';$('taTrend').textContent=ta.trend||'—';$('taState').textContent=d.interval?.toUpperCase()||interval;$('taSummary').textContent=ta.summary||'—';$('ema20').textContent=fmt(c.ema20);$('ema50').textContent=fmt(c.ema50);$('ema200').textContent=fmt(c.ema200);$('taConfluence').textContent=(c.direction||'—')+' '+(c.score!=null?`(${c.score>0?'+':''}${c.score})`:'');$('macdState').textContent=c.macd?`${c.macd.state} · ${fmt(c.macd.histogram)}`:'—';$('adxValue').textContent=c.adx?`${fmt(c.adx.adx)} · ${c.adx.state}`:'—';$('stochValue').textContent=c.stochastic?`${fmt(c.stochastic.k)}/${fmt(c.stochastic.d)}`:'—';$('bbState').textContent=c.bollinger?`${c.bollinger.state} · ${fmt(c.bollinger.position)}%`:'—';$('taReasons').textContent=(c.reasons||[]).slice(0,8).join(' · ')||'No dominant confirmation';const ai=d.ai||{};$('aiMode').textContent=ai.mode||'—';$('aiSummary').textContent=ai.summary||'—';$('confidence').textContent=ai.confidence!=null?ai.confidence+'%':'—';$('aiBias').textContent=ai.bias||'—';$('aiAdvice').textContent=ai.advice||'—';}
function updateCountdown(){const ts=countdownData?.close_timestamp; if(!ts)return;$('countdown').textContent=fmtDuration(Math.max(0,ts*1000-Date.now())); const close=new Date(ts*1000); $('closeTime').textContent='Close time: '+close.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});}function fmtDuration(ms){let s=Math.floor(ms/1000),h=Math.floor(s/3600);s%=3600;let m=Math.floor(s/60);s%=60;return h?`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`}
async function loadSessions(){try{const d=await api('/api/v1/sessions');const html=d.sessions.map(x=>`<div class="session ${x.open?'open':''}"><b>${x.name}</b><div class="sub">${x.local_time||''}</div><div class="status ${x.open?'up':'muted'}">${x.open?'OPEN':'CLOSED'}</div></div>`).join('');$('sessions').innerHTML=html;$('sessions2').innerHTML=html;$('sessionClock').textContent=d.utc_time||'—';$('sessionClock2').textContent=d.utc_time||'—'}catch(e){}}
async function loadCalendar(){try{const d=await api('/api/v1/calendar?days=7');const source=d.provider?` · Source: ${d.provider}`:'';if(!d.events?.length){$('calendar').innerHTML=`<div class="mini">${d.warning||'USA/USD economic events topilmadi.'}</div>`;return}const now=Date.now();const rows=d.events.map(x=>{const dt=x.time?Date.parse(x.time):NaN;const until=Number.isFinite(dt)?(dt-now):null;const when=until!=null?(until>0?` · T−${fmtDuration(until)}`:` · ${Math.abs(until)<3600000?'LIVE/RECENT':'o‘tgan'}`):'';return `<div class="calendar-item"><div><span class="tag">${x.impact||'MEDIUM'}</span> · ${x.country||'USD'} · ${x.time||''}${when}</div><b>${x.event||'Economic event'}</b><div class="mini">Kutilmoqda: ${x.forecast??x.estimate??'—'} · Oldingi: ${x.previous??'—'} · Actual: ${x.actual??'—'} ${x.unit||''}</div><div class="mini">Source: ${x.source||d.provider||'—'}</div></div>`}).join('');$('calendar').innerHTML=`<div class="mini" style="margin-bottom:8px">USA / USD · ALL IMPACT${source} · ${d.events.length} event</div>`+rows}catch(e){$('calendar').innerHTML=`<div class="mini">Calendar ma’lumoti hozircha mavjud emas: ${e.message}</div>`}}
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
function openSection(id){const target=$(id);if(!target)return;document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));target.classList.add('active');document.querySelectorAll('.nav button').forEach(b=>b.classList.toggle('active',b.dataset.section===id));const titles={overview:'Market Overview',chartSection:'Live Chart',analysisSection:'Technical Analysis',mtfSection:'Multi-Timeframe Analysis',aiSection:'AI Smart Analysis',signalSection:'Signal Lab',signalsSection:'Signals',calendarSection:'Economic Calendar',sessionsSection:'Market Sessions',historySection:'Signal History'};$('pageTitle').textContent=titles[id]||'Trading SaaS';if(id==='chartSection'){setTimeout(()=>mountTradingView('chart2',interval),50);setTimeout(()=>window.dispatchEvent(new Event('resize')),150);}if(id==='overview'){setTimeout(()=>mountTradingView('chart',interval),50);}if(id==='analysisSection')loadAnalysisOnly().catch(()=>{});if(id==='aiSection')loadAISmart(aiInterval);if(id==='signalSection')loadSelectedSignal(signalInterval);if(id==='calendarSection')loadCalendar();if(id==='sessionsSection')loadSessions();if(id==='mtfSection')loadMtf();if(id==='historySection')loadHistory();if(id==='signalsSection')loadAutoSignals()}

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
  $('price').textContent=fmt(price); $('change').textContent='Real-time tick'; $('change').className='change up';
  lastTickTs=Date.now();
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
    const q=await api(`/api/v1/quote/${encodeURIComponent(symbol)}`);
    if(q?.mode==='live' && q.price!=null){
      const price=+q.price; $('price').textContent=fmt(price);
      $('mode').textContent=marketWS&&marketWS.readyState===WebSocket.OPEN?'LIVE STREAM':'LIVE REST'; $('mode').style.color='var(--green)'; $('chartStatus').textContent='LIVE';
      updateLiveCandle(price,Math.floor(Date.parse(q.timestamp)/1000)||Math.floor(Date.now()/1000));
      return true;
    }
    throw Error(q?.warning||'Live quote unavailable');
  }catch(e){
    if(!marketWS||marketWS.readyState!==WebSocket.OPEN){ $('mode').textContent='LIVE RETRY'; $('mode').style.color='var(--amber)'; $('chartStatus').textContent='RETRYING'; }
    $('change').textContent=e.message||'Live quote unavailable';
    return false;
  }
}

function connectMarketStream(){
 if(DISABLE_MARKET_WS) return;
 closeMarketStream();
 const wsBase=API_BASE.replace(/^http/,'ws');
 const nodeWsBase=NODE_MARKET_URL.replace(/^http/,'ws');
 const wsUrl=wsBase+`/api/v1/ws/market/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(interval)}`;
 try{
   streamKey=symbol+'|'+interval; marketWS=new WebSocket(wsUrl);
   marketWS.onopen=()=>{ $('mode').textContent='LIVE STREAM'; $('mode').style.color='var(--green)'; $('chartStatus').textContent='LIVE'; $('change').textContent='WebSocket real-time tick'; };
   marketWS.onmessage=ev=>{
     const m=JSON.parse(ev.data);
     if(m.type==='tick') updateLiveCandle(+m.price,+m.timestamp); if(m.type==='candle'&&m.candle){ const cc=m.candle; liveCandle=cc; series.update(cc); if(series2) series2.update(cc); $('price').textContent=fmt(+m.price); }
     if(m.type==='reconnecting'){ if(Date.now()-lastTickTs>20000){ $('mode').textContent='RECONNECTING'; $('mode').style.color='var(--amber)'; } } if(m.type==='error'){ $('mode').textContent='LIVE ERROR'; showToast(m.message||'Stream error'); }
   };
   marketWS.onclose=()=>{ $('chartStatus').textContent='RECONNECTING'; $('mode').textContent='RECONNECTING'; setTimeout(()=>{if(document.visibilityState!=='hidden')connectMarketStream()},500)};
   marketWS.onerror=()=>{ $('chartStatus').textContent='STREAM ERROR'; try{marketWS.close()}catch{} setTimeout(()=>{if(document.visibilityState!=='hidden')connectMarketStream()},500) };
 }catch(e){showToast('Real-time stream could not start')}
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
    $('mode').textContent='CONNECTING…';
    try{
      const md=await api('/api/market/diagnostics');
      if(md.live_ready){
        const ok=Object.entries(md.providers||{}).filter(([,v])=>v.ok).map(([k])=>k.toUpperCase()).join(' + ');
        $('mode').textContent='LIVE '+(ok||'READY');
        $('mode').style.color='var(--green)';
      }
    }catch(_){ $('mode').textContent='LIVE RETRY'; }
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