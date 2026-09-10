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
async function loadAIProviders(){
  const el=$('aiProvidersGrid'); if(!el)return;
  try{
    const d=await api('/api/v1/ai/providers');
    const names={groq:'Groq GPT-OSS 120B',gemini:'Google Gemini Flash',openrouter:'OpenRouter Free',groq_qwen:'Groq Qwen 3.6 27B',mistral:'Mistral',cerebras:'Cerebras',cloudflare:'Cloudflare Workers AI',huggingface:'Hugging Face',openai:'OpenAI'};
    el.innerHTML=(d.providers||[]).map(x=>{const st=x.status||'—';const cls=st==='ONLINE'?'buy':st==='OFFLINE'?'sell':st==='NOT_CONFIGURED'?'wait':'wait';return `<div class="component"><small>${names[x.id]||x.id}</small><b class="${cls}">${st}</b><div class="mini">${x.configured?x.model:'Key yo‘q'}</div></div>`}).join('');
  }catch(e){el.innerHTML='<div class="mini">AI provider status unavailable.</div>'}
}

async function loadSignalEngine(){
  const grid=$('signalEngineGrid'); if(!grid)return;
  const order=['1min','5min','15min','30min','1h','4h','1day'];
  grid.innerHTML=order.map(tf=>`<div class="metric"><small>${tfName(tf)}</small><b class="wait">...</b><div class="mini">Signal hisoblanmoqda</div></div>`).join('');
  try{
    const d=await api(`/api/v1/signals/live/${encodeURIComponent(symbol)}`);
    const frames=d?.timeframes||{};
    grid.innerHTML=order.map(tf=>{
      const x=frames[tf]||{}; const sig=String(x.signal||'WAIT').toUpperCase();
      const cls=sig==='BUY'?'buy':sig==='SELL'?'sell':'wait';
      return `<div class="advanced-card ${cls}"><div class="advanced-head"><div><div class="mini">${tfName(tf)}</div><div class="advanced-signal ${cls}">${sig}</div></div><span class="pill">${fmt(x.confidence??0)}%</span></div><div class="mini">${x.setup||'—'} · Score ${fmt(x.score??0)}</div><div class="grid4" style="margin-top:8px"><div class="metric"><small>Entry</small><b>${fmt(x.entry)}</b></div><div class="metric"><small>SL</small><b>${fmt(x.stop_loss)}</b></div><div class="metric"><small>TP1</small><b>${fmt((x.take_profit||[])[0])}</b></div><div class="metric"><small>TP2</small><b>${fmt((x.take_profit||[])[1])}</b></div></div><div class="mini" style="margin-top:7px">${x.reason||x.warning||'—'}</div></div>`;
    }).join('');
    const current=frames[interval]||{};
    if(current.signal){
      const sig=String(current.signal).toUpperCase(); $('signalMain').textContent=sig; $('signalMain').className='signal-main '+(sig==='BUY'?'buy':sig==='SELL'?'sell':'wait');
      $('signalReason').textContent=current.reason||current.warning||'—'; $('entry').textContent=fmt(current.entry); $('sl').textContent=fmt(current.stop_loss); $('tp1').textContent=fmt((current.take_profit||[])[0]); $('tp2').textContent=fmt((current.take_profit||[])[1]); $('bias').textContent=`${tfName(interval)} · ${current.confidence??0}%`;
    }
    return d;
  }catch(e){ grid.innerHTML=`<div class="card">Signal Engine error: ${e.message}</div>`; }
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
  try{
    const d=await api(`/api/v1/analysis/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(interval)}`);
    renderAnalysis(d);
    await recordModuleSignal('Technical Analysis',d,d?.setup||{},interval,d?.candle_time);
    if(d?.ok===false){ $('taState').textContent='TV ERROR'; }
    mountTradingViewTechnical('tvTechnicalWidget', interval);
    return d;
  }catch(e){ $('taState').textContent='ERROR'; $('taSummary').textContent='Technical Analysis error: '+e.message; return null; }
}
async function loadSmartAnalysis(){
  try{
    const d=await api(`/api/v1/ai-smart-analysis/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(interval)}`);
    const ai=d?.ai||{}; const bias=ai.bias||d?.direction||'NEUTRAL'; const signal=d?.direction||'WAIT';
    $('smartBias').textContent=bias; $('smartConfidence').textContent=(ai.confidence??0)+'%'; $('smartSignal').textContent=signal; $('smartMode').textContent=ai.mode||'LIVE';
    $('smartSummary').textContent=ai.summary||'AI Smart Analysis natijasi mavjud emas.'; $('smartAdvice').textContent=ai.advice||'—'; await recordModuleSignal('AI Smart Analysis',d,{signal:d?.direction,confidence:ai.confidence,entry:d?.levels?.entry,stop_loss:d?.levels?.stop_loss,take_profit:d?.levels?.take_profit, candle_time:d?.candle_time},aiInterval,d?.candle_time); return d;
  }catch(e){ $('smartSummary').textContent='AI Smart Analysis error: '+(e.message||'server error'); return null; }
}
function mountTradingViewTechnical(containerId, tf){
  const el=$(containerId); if(!el) return; el.innerHTML='';
  const script=document.createElement('script');
  script.src='https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js';
  script.type='text/javascript'; script.async=true;
  const intervalMap={'1min':'1m','5min':'5m','15min':'15m','30min':'30m','1h':'1h','4h':'4h','1day':'1D'};
  script.textContent=JSON.stringify({interval:intervalMap[tf]||'5m',width:'100%',height:500,symbol:'OANDA:XAUUSD',showIntervalTabs:true,displayMode:'single',colorTheme:'dark',isTransparent:true,locale:'en',largeChartUrl:''});
  el.appendChild(script);
}
function mountTradingViewCalendar(){
  const el=$('tvCalendarWidget'); if(!el || el.dataset.loaded==='1') return; el.dataset.loaded='1'; el.innerHTML='';
  const script=document.createElement('script');
  script.src='https://www.tradingview.com/static/bundles/embed-widget-events.js';
  script.type='text/javascript'; script.async=true;
  script.textContent=JSON.stringify({width:'100%',height:680,colorTheme:'dark',isTransparent:true,locale:'en',importanceFilter:'-1,0,1'});
  el.appendChild(script);
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
function renderAnalysis(d){const s=d.setup||{},ta=d.technical||{};$('signalMain').textContent=d.direction||'WAIT';$('signalMain').className='signal-main '+((d.direction||'WAIT').toLowerCase()==='buy'?'buy':(d.direction||'').toLowerCase()==='sell'?'sell':'wait');$('signalReason').textContent=d.headline||s.reason||'—';$('entry').textContent=fmt(s.entry);$('sl').textContent=fmt(s.stop_loss);$('tp1').textContent=fmt((s.take_profit||[])[0]);$('tp2').textContent=fmt((s.take_profit||[])[1]);$('bias').textContent=d.levels?.bias||s.pivot_filter||'—';$('pivotFilter').textContent=d.levels?.bias||'—';const p=d.levels||{};$('levels').innerHTML=[['R3',p.r3,'res'],['R2',p.r2,'res'],['R1',p.r1,'res'],['Pivot',p.pivot,'piv'],['S1',p.s1,'sup'],['S2',p.s2,'sup'],['S3',p.s3,'sup']].map(x=>`<div class="row"><span>${x[0]}</span><b class="${x[2]}">${fmt(x[1])}</b></div>`).join('');$('rsi').textContent=fmt(ta.rsi);$('atr').textContent=fmt(ta.atr);$('rsiState').textContent=ta.rsi_state||'—';$('taTrend').textContent=ta.trend||'—';$('taState').textContent=d.interval?.toUpperCase()||interval;$('taSummary').textContent=(ta.summary||'—') + (ta.ai_validation ? ` | AI: ${ta.ai_consensus||'—'} · ${ta.ai_validation.confidence??0}%` : '');const ai=d.ai||{};$('aiMode').textContent=ai.mode||'—';$('aiSummary').textContent=ai.summary||'—';$('confidence').textContent=ai.confidence!=null?ai.confidence+'%':'—';$('aiBias').textContent=ai.bias||'—';$('aiAdvice').textContent=ai.advice||'—';}
function updateCountdown(){const ts=countdownData?.close_timestamp; if(!ts)return;$('countdown').textContent=fmtDuration(Math.max(0,ts*1000-Date.now())); const close=new Date(ts*1000); $('closeTime').textContent='Close time: '+close.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});}function fmtDuration(ms){let s=Math.floor(ms/1000),h=Math.floor(s/3600);s%=3600;let m=Math.floor(s/60);s%=60;return h?`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`}
async function loadSessions(){try{const d=await api('/api/v1/sessions');const html=d.sessions.map(x=>`<div class="session ${x.open?'open':''}"><b>${x.name}</b><div class="sub">${x.local_time||''}</div><div class="status ${x.open?'up':'muted'}">${x.open?'OPEN':'CLOSED'}</div></div>`).join('');$('sessions').innerHTML=html;$('sessions2').innerHTML=html;$('sessionClock').textContent=d.utc_time||'—';$('sessionClock2').textContent=d.utc_time||'—'}catch(e){}}
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
  if(!token){
    ['totalSignals','completedSignals','wins','losses','winrate'].forEach(id=>$(id).textContent=id==='winrate'?'0%':'0');
    if($('historySourceStats'))$('historySourceStats').innerHTML='';
    if($('historySummary'))$('historySummary').innerHTML='';
    return;
  }
  try{
    const d=await api('/api/v1/signals/analytics');
    $('totalSignals').textContent=d.total_signals??0; $('completedSignals').textContent=d.completed_trades??0; $('wins').textContent=d.wins??0; $('losses').textContent=d.losses??0; $('winrate').textContent=(d.winrate??0)+'%';
    if($('historySummary')) $('historySummary').innerHTML=`<div class="metric"><small>TP HIT</small><b class="buy">${d.wins??0}</b></div><div class="metric"><small>SL HIT</small><b class="sell">${d.losses??0}</b></div><div class="metric"><small>OPEN</small><b class="wait">${d.open??0}</b></div><div class="metric"><small>AMBIGUOUS</small><b>${d.ambiguous??0}</b></div>`;
    if($('historySourceStats')) $('historySourceStats').innerHTML=Object.entries(d.by_source||{}).map(([src,x])=>`<div class="metric"><small>${src}</small><b>${x.winrate}% Win Rate</b><div class="mini">${x.total_signals} signals · ${x.wins} TP / ${x.losses} SL · ${x.completed_trades} completed</div></div>`).join('');
  }catch(e){ if($('historySummary'))$('historySummary').innerHTML=`<div class="card">Analytics error: ${e.message}</div>`; }
}
async function recordModuleSignal(source, response, item, intervalName, candleTime){
  if(!token) return;
  const x=item||{}; const direction=String(x.signal||response?.direction||'WAIT').toUpperCase();
  if(!['BUY','SELL'].includes(direction)) return;
  try{ await api('/api/v1/signals/record-module',{method:'POST',body:JSON.stringify({symbol,interval:intervalName||response?.interval||interval,source,direction,confidence:x.confidence??response?.ai?.confidence??null,entry:x.entry??response?.setup?.entry??null,stop_loss:x.stop_loss??response?.setup?.stop_loss??null,take_profit:x.take_profit??response?.setup?.take_profit??[],headline:`${source} · ${direction}`,candle_time:String(candleTime??x.candle_time??response?.candle_time??''),payload:{response:item||response}})}); }catch(e){ console.warn('Signal history record',source,e); }
}
async function loadHistory(){if(!token){$('history').innerHTML='<tr><td colspan="10">Kirish kerak.</td></tr>';return}try{const d=await api('/api/v1/signals/history?limit=100');$('history').innerHTML=(d.items||[]).map(x=>{const dur=x.duration_minutes!=null?(x.duration_minutes<60?`${fmt(x.duration_minutes)} min`:`${fmt(x.duration_minutes/60)} h`):'OPEN';const closed=x.closed_at?new Date(x.closed_at).toLocaleString():'—';return `<tr><td>${new Date(x.created_at).toLocaleString()}</td><td>${x.source||'Signals'}</td><td>${x.interval}</td><td class="${x.direction==='BUY'?'buy':x.direction==='SELL'?'sell':''}">${x.direction}${x.auto_entry?' · AUTO':''}${x.confidence!=null?` · ${fmt(x.confidence)}%`:''}</td><td>${fmt(x.entry)}</td><td>${(x.tp||[]).map(fmt).join(' / ')||'—'}</td><td>${fmt(x.sl)}</td><td class="outcome-${x.outcome==='TP HIT'?'tp':x.outcome==='SL HIT'?'sl':x.outcome==='OPEN'?'open':'amb'}">${x.outcome}${x.result_price!=null?` · ${fmt(x.result_price)}`:''}</td><td>${dur}</td><td>${closed}</td></tr>`}).join('')||'<tr><td colspan="10">Signal yo‘q.</td></tr>'}catch(e){$('history').innerHTML='<tr><td colspan="10">History yuklanmadi.</td></tr>'}}
function componentText(v){if(v==null)return '—';if(typeof v==='object'){if(v.type)return v.type+(v.low!=null?' · '+fmt(v.low)+'–'+fmt(v.high):'');if(v.support!=null)return 'S '+fmt(v.support)+' · R '+fmt(v.resistance);return JSON.stringify(v)}return String(v)}
function tfName(tf){return ({'1min':'1 MIN','5min':'5 MIN','15min':'15 MIN','30min':'30 MIN','1h':'1 HOUR','4h':'4 HOUR','1day':'1 DAY'})[tf]||tf;}
function advCard(tf,x){const sig=x.signal||'WAIT', cls=sig==='BUY'?'buy':sig==='SELL'?'sell':'wait', badge=sig==='BUY'?'badge-buy':sig==='SELL'?'badge-sell':'badge-wait';const c=x.components||{};return `<div class="advanced-card ${cls}"><div class="advanced-head"><div><div class="mini">${tfName(tf)}</div><div class="advanced-signal ${badge}">${sig}</div></div><span class="pill">${x.confidence||0}%</span></div><div class="mini" style="margin-top:4px">Score ${x.score??0} · ${x.setup||'—'}</div><div class="grid4" style="margin-top:9px"><div class="metric"><small>Entry</small><b>${fmt(x.entry)}</b></div><div class="metric"><small>SL</small><b>${fmt(x.stop_loss)}</b></div><div class="metric"><small>TP1</small><b>${fmt((x.take_profit||[])[0])}</b></div><div class="metric"><small>TP2</small><b>${fmt((x.take_profit||[])[1])}</b></div></div><div class="component-grid"><div class="component"><small>ICT</small><b>${componentText(c['ICT'])}</b></div><div class="component"><small>SNR</small><b>${componentText(c['SNR'])}</b></div><div class="component"><small>SNR Malaysia</small><b>${componentText(c['SNR Malaysia'])}</b></div><div class="component"><small>Order Block</small><b>${componentText(c['Order Block'])}</b></div><div class="component"><small>FVG</small><b>${componentText(c['FVG'])}</b></div><div class="component"><small>Liquidity</small><b>${componentText(c['Liquidity'])}</b></div><div class="component"><small>Trend Line</small><b>${componentText(c['Trend Line'])}</b></div><div class="component"><small>Global Trend</small><b>${componentText(c['Global Trend Line'])}</b></div><div class="component"><small>BOS</small><b>${componentText(c['BOS'])}</b></div><div class="component"><small>CHOCH</small><b>${componentText(c['CHOCH'])}</b></div><div class="component"><small>Internal</small><b>${componentText(c['Internal Structure'])}</b></div><div class="component"><small>RSI / ATR</small><b>${fmt(x.rsi)} / ${fmt(x.atr)}</b></div></div><div class="advanced-actions"><div class="mini">${x.reason||'—'}</div>${sig==='BUY'||sig==='SELL'?`<button class="btn" data-save-advanced="${tf}">Saqlash</button>`:''}</div></div>`}

function ictRange(x){return x&&x.low!=null&&x.high!=null?`${fmt(x.low)} – ${fmt(x.high)}`:'—'}
function ictState(v){return v?'PASS':'MISS'}
async function loadICTSignals(){
  const status=$('ictStatus'); if(status) status.textContent='M30 → M5 ICT hisoblanmoqda…';
  try{
    const d=await api(`/api/v1/ict-signals/${encodeURIComponent(symbol)}`);
    if(!d.ok) throw Error(d.error||'ICT unavailable');
    const x=d.ict||{}, m30=x.m30||{}, m5=x.m5||{}, liq=x.liquidity||{}, pd=x.premium_discount||{};
    const sig=x.signal||'WAIT', cls=sig==='BUY'?'buy':sig==='SELL'?'sell':'wait';
    $('ictSymbol').textContent=`${symbol} · M30 → M5`;
    $('ictSignal').textContent=sig; $('ictSignal').className='signal-main '+cls;
    $('ictConfidence').textContent=`${x.confidence??0}%`;
    $('ictScore').textContent=`${x.score??0} / 100`;
    $('ictReason').textContent=(x.reason||'—') + (x.ai_validation ? ` | AI ${x.ai_consensus||'—'} · ${x.ai_validation.confidence??0}%` : '');
    $('ictEntry').textContent=fmt(x.entry); $('ictSL').textContent=fmt(x.stop_loss);
    $('ictTP1').textContent=fmt((x.take_profit||[])[0]); $('ictTP2').textContent=fmt((x.take_profit||[])[1]);
    $('ictBias').textContent=x.bias||'—'; $('ictLiquidity').textContent=`Liquidity ${liq.type||'—'}`;
    $('ictPD').textContent=pd.zone||'—'; $('ictEquilibrium').textContent=`EQ ${fmt(pd.equilibrium)}`;
    $('ictMSS').textContent=m5.mss?'CONFIRMED':'WAIT'; $('ictMSSLevel').textContent=`Level ${fmt(m5.mss_level)}`;
    $('ictRR').textContent=x.risk_reward?`1 : ${x.risk_reward}`:'—';
    $('ictM30FVG').textContent=m30.fvg?.type||'NONE'; $('ictM30FVG').className='advanced-signal '+(m30.fvg?.type==='BULLISH'?'buy':m30.fvg?.type==='BEARISH'?'sell':'wait');
    $('ictM30FVGRange').textContent=ictRange(m30.fvg); $('ictM30OB').textContent=`OB ${m30.order_block?.type||'NONE'}`; $('ictM30OBRange').textContent=ictRange(m30.order_block);
    $('ictM30EMA').textContent=`${fmt(m30.ema20)} / ${fmt(m30.ema50)}`; $('ictDraw').textContent=x.draw_on_liquidity||'—';
    $('ictM5FVG').textContent=m5.fvg?.type||'NONE'; $('ictM5FVG').className='advanced-signal '+(m5.fvg?.type==='BULLISH'?'buy':m5.fvg?.type==='BEARISH'?'sell':'wait');
    $('ictM5FVGRange').textContent=ictRange(m5.fvg); $('ictM5MSS').textContent=m5.mss?'CONFIRMED':'WAIT';
    $('ictDisp').textContent=`Displacement ${m5.displacement?'✓':'—'}`; $('ictDispRatio').textContent=`${m5.displacement_atr??0} ATR`; $('ictLiqLevel').textContent=fmt(liq.level);
    $('ictChecks').innerHTML=(x.checks||[]).map(c=>`<div class="component"><small>${c.name}</small><b>${ictState(c.status==='PASS')} · +${c.points||0}</b></div>`).join('');
    $('ictStatus').textContent=`Live · M30 ${d.m30_candles} candles · M5 ${d.m5_candles} candles · ${new Date(d.generated_at).toLocaleString()}`;; recordModuleSignal('ICT Signals',d,x,'30min',d.m30_candle_time||liveCandle?.time)
  }catch(e){
    $('ictStatus').textContent='ICT error: '+(e.message||'server error');
    $('ictReason').textContent='Signal unavailable — market data/API ni tekshiring.';
  }
}

async function loadAdvancedSignals(){$('advancedStatus').textContent='7 timeframe hisoblanmoqda…';$('advancedGrid').innerHTML='<div class="card">Signal hisoblanmoqda...</div>';try{const d=await api(`/api/v1/signals/advanced/${encodeURIComponent(symbol)}`);const order=['1min','5min','15min','30min','1h','4h','1day'];$('advancedGrid').innerHTML=order.map(tf=>advCard(tf,d.timeframes?.[tf]||{})).join('');if(token) order.forEach(tf=>recordModuleSignal('Signal Lab',d,d.timeframes?.[tf]||{},tf,d.timeframes?.[tf]?.candle_time||liveCandle?.time));$('advancedStatus').textContent=`${symbol} · ${new Date(d.generated_at).toLocaleString()} · har bir timeframe alohida`; }catch(e){$('advancedStatus').textContent=e.message;$('advancedGrid').innerHTML='<div class="card">Signal yuklanmadi.</div>'}}
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
    $('autoSignalUpdated').textContent='AUTO ENTRY > 85% · LIVE · '+new Date(d.generated_at).toLocaleTimeString();if(token) order.forEach(tf=>recordModuleSignal('Signals',d,d.timeframes?.[tf]||{},tf,d.timeframes?.[tf]?.candle_time||liveCandle?.time));
    if(token){ try{ const saved=await api(`/api/v1/signals/auto-record?symbol=${encodeURIComponent(symbol)}`,{method:'POST'}); if(saved.count) { loadStats(); if($('historySection').classList.contains('active')) loadHistory(); } }catch(_){} }
  }catch(e){$('autoSignalsGrid').innerHTML=`<div class="card">Live Signals error: ${e.message}</div>`}
}
async function autoEntryTick(){if(!token)return;try{const d=await api(`/api/v1/signals/auto-record?symbol=${encodeURIComponent(symbol)}`,{method:'POST'});if(d.count){showToast(`AUTO ENTRY: ${d.count} ta savdo ochildi`);loadStats();loadHistory();}else if(d.history_count!=null){loadStats();}}catch(e){console.warn('AUTO ENTRY',e)}}
async function loadClassicTrade(tf=interval){try{const d=await api(`/api/v1/classic-trade/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(tf)}`);const x=d.classic||{};const sig=x.signal||'WAIT';const cls=sig==='BUY'?'buy':sig==='SELL'?'sell':'wait';$('classicSymbol').textContent=`${symbol} · ${tfName(tf)}`;$('classicSignal').textContent=sig;$('classicSignal').className='signal-main '+cls;$('classicConfidence').textContent=(x.confidence??0)+'% · Score '+(x.score??0);$('classicReason').textContent=x.reason||'—';$('classicEntry').textContent=fmt(x.entry);$('classicSL').textContent=fmt(x.stop_loss);$('classicTP1').textContent=fmt((x.take_profit||[])[0]);$('classicTP2').textContent=fmt((x.take_profit||[])[1]);$('classicTrend').textContent=x.trend||'—';$('classicEma').textContent=`EMA20 ${fmt(x.ema20)} · EMA50 ${fmt(x.ema50)}`;$('classicSNR').textContent=`S ${fmt((x.support||[])[0])} · R ${fmt((x.resistance||[])[0])}`;$('classicPivot').textContent=`Pivot ${fmt(x.pivot)}`;$('classicRSI').textContent=fmt(x.rsi);$('classicRSIState').textContent=x.rsi_state||'—';$('classicMACD').textContent=`${fmt(x.macd)} · ${x.macd_state||'—'}`;$('classicPattern').textContent=x.pattern||'—'; await recordModuleSignal('Classic Trade',d,x,tf,x.candle_time); }catch(e){$('classicReason').textContent='Classic Trade error: '+(e.message||'server error')}}
let snrInterval='5min';
function snrFmt(v){return v==null||!Number.isFinite(Number(v))?'—':fmt(Number(v));}
async function loadSNR(tf=snrInterval){try{const d=await api(`/api/v1/snr/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(tf)}`);const x=d.snr||{};$('snrPrice').textContent=snrFmt(d.current_price);$('snrPosition').textContent=x.position||'—';const sig=x.signal||'WAIT',el=$('snrSignal');el.textContent=sig;el.className=sig==='BUY'?'buy':sig==='SELL'?'sell':'wait';$('snrConfidence').textContent=`${x.confidence??0}%`;$('snrSupportZone').textContent=snrFmt(x.support?.mid);$('snrSupportRange').textContent=`${snrFmt(x.support?.low)} – ${snrFmt(x.support?.high)}`;$('snrSupportStrength').textContent=`${x.support?.strength??0}%`;$('snrSupportRetests').textContent=x.support?.retests??0;$('snrSupportDistance').textContent=x.support?.distance_pct!=null?`${Number(x.support.distance_pct).toFixed(2)}%`:'—';$('snrSupportStatus').textContent=x.support?.status||'—';$('snrResistanceZone').textContent=snrFmt(x.resistance?.mid);$('snrResistanceRange').textContent=`${snrFmt(x.resistance?.low)} – ${snrFmt(x.resistance?.high)}`;$('snrResistanceStrength').textContent=`${x.resistance?.strength??0}%`;$('snrResistanceRetests').textContent=x.resistance?.retests??0;$('snrResistanceDistance').textContent=x.resistance?.distance_pct!=null?`${Number(x.resistance.distance_pct).toFixed(2)}%`:'—';$('snrResistanceStatus').textContent=x.resistance?.status||'—';$('snrReason').textContent=x.reason||'—';$('snrMethod').textContent=`${tfName(tf)} · ${x.method||'SNR engine'}`; await recordModuleSignal('SNR',d,x,tf,d.candle_time); }catch(e){$('snrReason').textContent='SNR error: '+(e.message||'server error')}}
document.addEventListener('click',e=>{const b=e.target.closest('[data-snr-interval]');if(b){document.querySelectorAll('[data-snr-interval]').forEach(x=>x.classList.toggle('active',x===b));snrInterval=b.dataset.snrInterval;loadSNR(snrInterval).catch(()=>{})}});
async function loadAISignals(){ try{ const d=await api(`/api/v1/signals/live/${encodeURIComponent(symbol)}`); const x=d?.timeframes?.[interval]||{}; const sig=String(x.signal||'WAIT'); $('aiSigSignal').textContent=sig; $('aiSigSignal').className=sig==='BUY'?'buy':sig==='SELL'?'sell':'wait'; $('aiSigConfidence').textContent=(x.confidence??0)+'%'; $('aiSigEntry').textContent=fmt(x.entry); $('aiSigSL').textContent=fmt(x.stop_loss); $('aiSigTP1').textContent=fmt((x.take_profit||[])[0]); $('aiSigTP2').textContent=fmt((x.take_profit||[])[1]); $('aiSigRR').textContent=x.risk_reward?`1 : ${x.risk_reward}`:'—'; $('aiSigMode').textContent=(x.confidence??0)>=85?'SIGNAL':'WAIT'; $('aiSigReason').textContent=(x.reason||'Quantitative + AI signal') + (x.ai_validation ? ` | AI ${x.ai_consensus||'—'} · ${x.ai_validation.confidence??0}%` : ''); await recordModuleSignal('AI Signals',d,x,interval,x.candle_time||d.candle_time); }catch(e){ $('aiSigReason').textContent='AI Signals error: '+(e.message||'server error'); } }
function openSection(id){const target=$(id);if(!target)return;document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));target.classList.add('active');document.querySelectorAll('.nav button').forEach(b=>b.classList.toggle('active',b.dataset.section===id));const titles={overview:'Market Overview',chartSection:'Live Chart',analysisSection:'Technical Analysis',smartAnalysisSection:'AI Smart Analysis',aiSignalsSection:'AI Signals',classicSection:'Classic Trade',snrSection:'SNR',mtfSection:'Multi-Timeframe Analysis',signalSection:'Signal Lab',signalsSection:'Signals',ictSection:'ICT Signals',calendarSection:'Economic Calendar',sessionsSection:'Market Sessions',historySection:'Signal History'};$('pageTitle').textContent=titles[id]||'Trading SaaS';if(id==='chartSection'){setTimeout(()=>{mountTradingView('chart2',interval);loadChartHistory().catch(()=>{})},50);}if(id==='overview'){setTimeout(()=>{mountTradingView('chart',interval);loadChartHistory().catch(()=>{})},50);}if(id==='analysisSection')loadAnalysisOnly().catch(()=>{});if(id==='smartAnalysisSection')loadSmartAnalysis().catch(()=>{});if(id==='aiSignalsSection')loadAISignals().catch(()=>{});if(id==='classicSection')loadClassicTrade(classicInterval).catch(()=>{});if(id==='snrSection')loadSNR(snrInterval).catch(()=>{});if(id==='signalSection')loadSelectedSignal(signalInterval);if(id==='classicSection')loadClassicTrade(classicInterval);if(id==='calendarSection')loadCalendar();if(id==='sessionsSection')loadSessions();if(id==='mtfSection')loadMtf();if(id==='historySection')loadHistory();if(id==='signalsSection')loadAutoSignals();if(id==='ictSection')loadICTSignals()}

document.addEventListener('click',e=>{const b=e.target.closest('[data-classic-interval]');if(b){document.querySelectorAll('[data-classic-interval]').forEach(x=>x.classList.toggle('active',x===b));classicInterval=b.dataset.classicInterval;loadClassicTrade(classicInterval)}});
document.addEventListener('click',e=>{
  const b=e.target.closest('[data-pivot-interval]');
  if(b){
    document.querySelectorAll('[data-pivot-interval]').forEach(x=>x.classList.toggle('active',x===b));
    loadPivots(b.dataset.pivotInterval);
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
document.querySelectorAll('.tfbar').forEach(bar=>bar.addEventListener('click',e=>{const b=e.target.closest('[data-interval]');if(b && bar.contains(b))setTf(b.dataset.interval)}));document.querySelectorAll('.nav button').forEach(b=>b.addEventListener('click',()=>openSection(b.dataset.section)));$('saveSignal').onclick=saveSignal;$('refreshSignalEngine').onclick=()=>loadSignalEngine(); loadAIProviders();$('refreshICT').onclick=()=>loadICTSignals();$('refreshAdvanced').onclick=()=>loadAdvancedSignals();$('refreshClassic').onclick=()=>loadClassicTrade(classicInterval);$('refreshStats').onclick=()=>{loadStats();loadHistory()};$('refreshSmartAnalysis').onclick=()=>loadSmartAnalysis();$('refreshAISignals').onclick=()=>loadAISignals();$('refreshCalendar').onclick=()=>loadCalendar();$('refreshHistory').onclick=()=>{loadStats();loadHistory()};$('authBtn').onclick=()=>{ setAuth('login'); $('authMsg').textContent=''; $('authModal').classList.add('show'); setTimeout(()=>$('email').focus(),50); }; $('authSwitch').onclick=()=>setAuth(authMode==='login'?'register':'login');async function logoutUser(){await api('/api/auth/logout',{method:'POST'}).catch(()=>{});token='';localStorage.removeItem('trading_token');$('plan').textContent='Guest';$('authBtn').textContent='Kirish';loadStats();loadHistory();$('authModal').classList.remove('show');$('authMsg').textContent='';showToast('Tizimdan chiqildi')};$('authForm').onsubmit=async e=>{
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
      autoEntryTick().catch(()=>{});
      try{const me=await api('/api/auth/me');$('plan').textContent=me.plan||'free';$('authBtn').textContent='Chiqish'}
      catch(_){token='';localStorage.removeItem('trading_token')}
      loadStats().catch(()=>{}); loadHistory().catch(()=>{});
    }
    // Lightweight quote heartbeat; do not hammer REST APIs.
    setInterval(()=>quoteHeartbeat().catch(()=>{}),3000);
    // Main signal/analysis refresh.
    setInterval(()=>{
      if(document.visibilityState!=='visible') return;
      if(token) autoEntryTick().catch(()=>{});
      loadAnalysisOnly().catch(()=>{});
      if($('overview').classList.contains('active')) loadSignalEngine().catch(()=>{});
      if($('signalsSection').classList.contains('active')) loadAutoSignals().catch(()=>{});if($('aiSignalsSection').classList.contains('active')) loadAISignals().catch(()=>{});if($('ictSection').classList.contains('active')) loadICTSignals().catch(()=>{});
      if($('signalSection').classList.contains('active')) loadSelectedSignal(signalInterval).catch(()=>{});
      if($('classicSection').classList.contains('active')) loadClassicTrade(classicInterval).catch(()=>{});
      if($('snrSection').classList.contains('active')) loadSNR(snrInterval).catch(()=>{});
    },15000);
    // Expensive modules refresh only while visible.
    setInterval(()=>{
      if(document.visibilityState!=='visible') return;
      if($('mtfSection').classList.contains('active')) loadMtf().catch(()=>{});
      
      if($('calendarSection').classList.contains('active')) loadCalendar().catch(()=>{});
      if($('sessionsSection').classList.contains('active')) loadSessions().catch(()=>{});
      loadAIProviders().catch(()=>{});
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