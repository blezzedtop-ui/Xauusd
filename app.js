const symbol='XAU/USD';let interval='5min',pivotInterval='5min',aiInterval='5min',signalInterval='5min',token=localStorage.getItem('trading_token')||'',authMode='login',chart,series,chart2,series2,countdownData={close_timestamp:null},marketWS=null,liveCandle=null,lastTickTs=0,lastRestQuoteAt=0,streamKey='';
const $=id=>document.getElementById(id);let trendLineInterval='5min';let trendLiveRefreshTimer=null;let trendOverlayChart=null,trendOverlaySeries=null,trendOverlayLayers=[];const setText=(id,v)=>{const el=$(id);if(el)el.textContent=v??'—';};const fmt=v=>v==null?'—':Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:4});
function showToast(m){$('toast').textContent=m;$('toast').classList.add('show');setTimeout(()=>$('toast').classList.remove('show'),2300)}

// Cloud deployment: when the frontend and FastAPI are on the same Railway service, leave API_BASE_URL empty.
// When hosted separately on Netlify, set window.API_BASE_URL to the public FastAPI URL.
const CONFIGURED_API=(window.API_BASE_URL||document.querySelector('meta[name=api-base]')?.content||'').trim().replace(/\/$/,'');
const LOCAL_API=(location.protocol==='http:'||location.protocol==='https:') ? location.origin.replace(/\/$/,'') : '';
const API_BASE=CONFIGURED_API || ((location.protocol==='http:'||location.protocol==='https:') ? location.origin : (LOCAL_API || 'http://127.0.0.1:8000'));
const API_CANDIDATES=[API_BASE,location.origin].filter((v,i,a)=>v&&a.indexOf(v)===i);
const NODE_MARKET_URL=(window.NODE_MARKET_URL||'').replace(/\/$/,'');
const IS_NETLIFY=/netlify\.app$|netlify\.com$/i.test(location.hostname);
const DISABLE_MARKET_WS=window.DISABLE_MARKET_WS!==false;
async function nodeMarketHealth(){if(!NODE_MARKET_URL)return null;try{const r=await fetch(`${NODE_MARKET_URL}/health`,{cache:'no-store'});if(!r.ok) return null;return await r.json()}catch{return null}}
async function api(path,opt={}){const headers={'Content-Type':'application/json',...(opt.headers||{})};if(token)headers.Authorization='Bearer '+token;let last;for(const base of API_CANDIDATES){try{const url=path.startsWith('http')?path:base+path;const r=await fetch(url,{...opt,headers,cache:'no-store'});let d={};try{d=await r.json()}catch{}if(!r.ok){ const detail=d?.detail; let msg=d?.message||''; if(Array.isArray(detail)) msg=detail.map(x=>x?.msg||x?.message||JSON.stringify(x)).join('; '); else if(detail&&typeof detail==='object') msg=detail.msg||detail.message||JSON.stringify(detail); else if(detail) msg=String(detail); throw Error(msg||'HTTP '+r.status); }return d}catch(e){last=e}}if(last instanceof TypeError){throw Error('Cloud backendga ulanib bo‘lmadi. Saytning cloud serveri ulanmagan yoki hozircha ishlamayapti.') }throw last}
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
    if(token && d.signal && ['BUY','SELL'].includes(String(d.signal).toUpperCase())){
      const ai=d.openai||{};
      await recordModuleSignal('Book + OpenAI',d,{signal:d.signal,confidence:ai.confidence,entry:d.entry,stop_loss:d.stop_loss,take_profit:d.take_profit||[],candle_time:d.candle?.time||d.candle_time},interval,d.candle?.time||d.candle_time);
    }
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
 setText('aiMode',ai.mode||'—');setText('aiSummary',ai.reason||'—');setText('confidence',ai.confidence!=null?ai.confidence+'%':'—');setText('aiBias',ai.signal||'WAIT');setText('aiAdvice',sig==='WAIT'?'Book va OpenAI bir xil yo‘nalishda tasdiqlamadi.':'Book pattern + OpenAI second opinion bir xil yo‘nalishni tasdiqladi.');
}
function renderAnalysis(d){const s=d?.setup||{},ta=d?.technical||{},lv=d?.levels||{};setText('signalMain',d?.direction||'WAIT');const sm=$("signalMain");if(sm){const dir=String(d?.direction||'WAIT').toLowerCase();sm.className='signal-main '+(dir==='buy'?'buy':dir==='sell'?'sell':'wait')}setText('signalReason',d?.headline||s.reason||'—');setText('entry',fmt(s.entry));setText('sl',fmt(s.stop_loss));setText('tp1',fmt((s.take_profit||[])[0]));setText('tp2',fmt((s.take_profit||[])[1]));setText('bias',lv.bias||s.pivot_filter||'—');setText('pivotFilter',lv.bias||'—');const levelsEl=$("levels");if(levelsEl){levelsEl.innerHTML=[['R3',lv.r3,'res'],['R2',lv.r2,'res'],['R1',lv.r1,'res'],['Pivot',lv.pivot,'piv'],['S1',lv.s1,'sup'],['S2',lv.s2,'sup'],['S3',lv.s3,'sup']].map(x=>`<div class="row"><span>${x[0]}</span><b class="${x[2]}">${fmt(x[1])}</b></div>`).join('')}setText('rsi',fmt(ta.rsi));setText('atr',fmt(ta.atr));setText('rsiState',ta.rsi_state||'—');setText('taTrend',ta.trend||'—');setText('taState',d?.interval?.toUpperCase()||interval);setText('taSummary',(ta.summary||'—')+(ta.ai_validation?` | AI: ${ta.ai_consensus||'—'} · ${ta.ai_validation.confidence??0}%`:''));const ai=d?.ai||{};setText('aiMode',ai.mode||'—');setText('aiSummary',ai.summary||'—');setText('confidence',ai.confidence!=null?ai.confidence+'%':'—');setText('aiBias',ai.bias||'—');setText('aiAdvice',ai.advice||'—');}
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
let historyPeriod = localStorage.getItem('history_period') || 'all';
function historyPeriodLabel(p){ return p==='day'?'Bugun':p==='month'?'Shu oy':'Barchasi'; }
let historyDate = localStorage.getItem('history_date') || '';
function historyQuery(){ const q=[]; if(historyPeriod && historyPeriod!=='all') q.push('period='+encodeURIComponent(historyPeriod)); if(historyDate) q.push('date='+encodeURIComponent(historyDate)); return q.length?'?'+q.join('&'):''; }
function syncHistoryPeriodButtons(){ document.querySelectorAll('.history-period').forEach(b=>{ b.classList.toggle('active', b.dataset.historyPeriod===historyPeriod); }); }
function syncHistoryDate(){ const el=$('historyDate'); if(el) el.value=historyDate||''; const sel=$('historyDateSelect'); if(sel) sel.value=historyDate||''; }


async function loadStats(){
  const zero=()=>{['totalSignals','completedSignals','wins','losses','winrate'].forEach(id=>setText(id,id==='winrate'?'0%':'0'));if($('historySourceStats'))$('historySourceStats').innerHTML='<div class="metric">Kirish kerak.</div>';if($('historyTfStats'))$('historyTfStats').innerHTML='';if($('historySummary'))$('historySummary').innerHTML='';};
  if(!token){zero();return;}
  try{
    const d=await api(`/api/v1/signals/analytics${historyQuery()}`);
    setText('totalSignals',d.total_signals??0);setText('completedSignals',d.completed_trades??0);setText('wins',d.wins??0);setText('losses',d.losses??0);setText('winrate',(d.winrate??0)+'%');
    if($('historySummary')) $('historySummary').innerHTML=`<div class="metric"><small>TOTAL SIGNALS</small><b>${d.total_signals??0}</b></div><div class="metric"><small>COMPLETED</small><b>${d.completed_trades??0}</b></div><div class="metric"><small>TAKE PROFIT</small><b class="buy">${d.wins??0}</b></div><div class="metric"><small>STOP LOSS</small><b class="sell">${d.losses??0}</b></div><div class="metric"><small>OPEN</small><b class="wait">${d.open??0}</b></div><div class="metric"><small>AMBIGUOUS</small><b>${d.ambiguous??0}</b></div><div class="metric"><small>WIN RATE</small><b>${d.winrate??0}%</b><div class="mini">TP / (TP + SL)</div></div>`;
    const sources=Object.entries(d.by_source||{});
    if($('historySourceStats')) $('historySourceStats').innerHTML=sources.length?sources.map(([src,x])=>`<div class="source-stat"><div class="source-title">${src}</div><div class="source-win">${Number(x.winrate||0).toFixed(2)}% <span class="mini">WIN RATE</span></div><div class="source-line">${x.total_signals??0} signal · <span class="buy">${x.wins??0} TP</span> · <span class="sell">${x.losses??0} SL</span> · ${x.open??0} OPEN · ${x.ambiguous??0} AMBIGUOUS</div><div class="source-line">Completed: ${x.completed_trades??0} · Formula: TP / (TP + SL)</div></div>`).join(''):'<div class="metric">Hozircha signal yo‘q.</div>';
    if($('historyTfStats')) $('historyTfStats').innerHTML=Object.entries(d.by_timeframe||{}).map(([tf,x])=>`<div class="source-stat"><div class="source-title">${tfName(tf)}</div><div class="source-win">${Number(x.winrate||0).toFixed(2)}%</div><div class="source-line">${x.total_signals??0} signal · <span class="buy">${x.wins??0} TP</span> · <span class="sell">${x.losses??0} SL</span> · ${x.open??0} OPEN</div></div>`).join('');
  }catch(e){if($('historySummary'))$('historySummary').innerHTML=`<div class="card">Analytics error: ${e?.message||'server xatosi'}</div>`;}
}
async function recordModuleSignal(source, response, item, intervalName, candleTime){
  if(!token) return;
  const x=item||{}; const direction=String(x.signal||response?.direction||'WAIT').toUpperCase();
  if(!['BUY','SELL'].includes(direction)) return;
  try{ await api('/api/v1/signals/record-module',{method:'POST',body:JSON.stringify({symbol,interval:intervalName||response?.interval||interval,source,direction,confidence:x.confidence??response?.ai?.confidence??null,entry:x.entry??response?.setup?.entry??null,stop_loss:x.stop_loss??response?.setup?.stop_loss??null,take_profit:x.take_profit??response?.setup?.take_profit??[],headline:`${source} · ${direction}`,candle_time:String(candleTime??x.candle_time??response?.candle_time??''),payload:{response:item||response}})}); }catch(e){ console.warn('Signal history record',source,e); }
}
async function loadHistory(){
  syncHistoryPeriodButtons(); syncHistoryDate();
  const body=$('history');
  if(!body)return;
  if(!token){body.innerHTML='<tr><td colspan="12">Kirish kerak.</td></tr>';return;}
  try{
    const d=await api(`/api/v1/signals/history?limit=200${historyQuery().replace('?', '&')}`);
    const dateSelect=$('historyDateSelect'); if(dateSelect){ const dates=[...new Set((d.items||[]).map(x=>{try{return new Date(x.created_at).toISOString().slice(0,10)}catch(_){return ''}}).filter(Boolean))].sort().reverse(); dateSelect.innerHTML='<option value="">Barcha kunlar</option>'+dates.map(v=>{const [y,m,dd]=v.split('-'); return `<option value="${v}">${dd}.${m}.${y}</option>`}).join(''); dateSelect.value=historyDate||''; }
    const items=[...(d.items||[])].sort((a,b)=>String(b.created_at||'').localeCompare(String(a.created_at||'')));
    let lastDate='', lastSource='';
    body.innerHTML=items.map(x=>{
      const src=x.source||'Signals';
      const dt=new Date(x.created_at);
      const dateKey=dt.toLocaleDateString('uz-UZ');
      const dateGroup=dateKey!==lastDate?`<tr class="history-group"><td colspan="12"><b>${dateKey}</b></td></tr>`:''; lastDate=dateKey;
      const sourceGroup=src!==lastSource?`<tr class="history-group"><td colspan="12"><span>${src}</span></td></tr>`:''; lastSource=src;
      const dur=x.duration_minutes!=null?(x.duration_minutes<60?`${fmt(x.duration_minutes)} min`:`${fmt(x.duration_minutes/60)} h`):'OPEN';
      const closed=x.closed_at?new Date(x.closed_at).toLocaleString():'—';
      const dir=String(x.direction||'').toUpperCase();
      const out=x.outcome||'OPEN';
      const oc=out==='TP HIT'?'tp':out==='SL HIT'?'sl':out==='OPEN'?'open':'amb';
      return dateGroup+sourceGroup+`<tr><td>${dateKey}</td><td>${dt.toLocaleTimeString()}</td><td><b>${src}</b></td><td>${tfName(x.interval)}</td><td class="${dir==='BUY'?'buy':dir==='SELL'?'sell':''}"><b>${dir}</b>${x.auto_entry?' · AUTO':''}${x.confidence!=null?` · ${fmt(x.confidence)}%`:''}</td><td><span class="setup-badge ${x.strong_setup?'strong':''}">${x.setup_grade||'SETUP'} ${x.setup_strength!=null?fmt(x.setup_strength)+'%':''}</span></td><td>${fmt(x.entry)}</td><td>${(x.tp||[]).map(fmt).join(' / ')||'—'}</td><td>${fmt(x.sl)}</td><td class="outcome-${oc}">${out}${x.result_price!=null?` · ${fmt(x.result_price)}`:''}</td><td>${dur}</td><td>${closed}</td></tr>`;
    }).join('')||'<tr><td colspan="12">Signal yo‘q.</td></tr>';
  }catch(e){body.innerHTML=`<tr><td colspan="12">History yuklanmadi: ${e?.message||'server xatosi'}</td></tr>`;}
}
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
document.addEventListener('click',e=>{ const b=e.target.closest('.history-period'); if(!b)return; historyPeriod=b.dataset.historyPeriod||'all'; localStorage.setItem('history_period',historyPeriod); syncHistoryPeriodButtons(); loadStats().catch(()=>{}); loadHistory().catch(()=>{});  });

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
async function loadTrendLines(tf=trendLineInterval){
  trendLineInterval=tf;
  removeLegacyTrendCharts();
  try{
    if($('trendChartTf')) $('trendChartTf').textContent=tfName(tf);
    $('trendLineStatus').textContent=`${tfName(tf)} · faqat ${tfName(tf)} candlelari asosida Trend Line + Fibonacci hisoblanmoqda…`;
    const results=await Promise.allSettled([api(`/api/v1/trend-lines/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(tf)}`),api(`/api/v1/signals/advanced/${encodeURIComponent(symbol)}`)]); const tl=results[0].status==='fulfilled'?results[0].value:null; const adv=results[1].status==='fulfilled'?results[1].value:null; if(!tl && !adv) throw new Error('Trend Line data unavailable');
    const x=adv?.timeframes?.[tf]||{}, t=(tl?.trendline)||x.trendline||{}, fib=(tl?.fibonacci)||x.fibonacci||{};
    if(tl?.candles?.length) mountAutoTrendFibChart(tf,tl.candles,t,fib);
    $('tlTrend').textContent=t.trend||'NEUTRAL'; $('tlTrend').className=t.trend==='BULLISH'?'buy':t.trend==='BEARISH'?'sell':'wait';
    $('tlTouches').textContent=t.touches??0; $('tlPower').textContent=(t.trend_power??0)+'%'; $('tlBreakRetest').textContent=`${t.breakout||'NO'} / ${t.retest||'NO'}`;
    const sig=x.signal||t.signal||'WAIT'; $('tlSignal').textContent=sig; $('tlSignal').className='signal-main '+tlClass(sig); $('tlFinalConfidence').textContent=(x.confidence??0)+'%';
    $('tlReason').textContent=(x.reason||t.reason||'—')+` | Trend Line: ${t.confirmation||'WAIT'} | Fibonacci: ${fib.reason||'WAIT'}`;
    $('fibSignal').textContent=fib.signal||'WAIT'; $('fibSignal').className='pill '+(fib.signal==='BUY'?'buy':fib.signal==='SELL'?'sell':'wait');
    $('fibDirection').textContent=fib.direction||'—'; $('fibLow').textContent=fmt(fib.anchor_low?.price); $('fibHigh').textContent=fmt(fib.anchor_high?.price); $('fibLevel').textContent=fib.nearest_level!=null?String(fib.nearest_level):'—';
    $('fib382').textContent=fmt(fib.levels?.['0.382']); $('fib500').textContent=fmt(fib.levels?.['0.5']); $('fib618').textContent=fmt(fib.levels?.['0.618']); $('fib786').textContent=fmt(fib.levels?.['0.786']); $('fibPA').textContent=fib.confirmation||'WAIT'; $('fibRSI').textContent=Number.isFinite(Number(fib.rsi))?Number(fib.rsi).toFixed(2):'—'; $('fib1272').textContent=fmt(fib.extension_targets?.['1.272']); $('fib1618').textContent=fmt(fib.extension_targets?.['1.618']); $('fibReason').textContent=fib.reason||'—';
    const order=['5min','15min','30min','1h','4h','1day'];
    const matrix=await Promise.allSettled(order.map(k=>api(`/api/v1/trend-lines/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(k)}`)));
    const frames=Object.fromEntries(order.map((k,i)=>[k,matrix[i].status==='fulfilled'?matrix[i].value:null]));
    $('trendLineMatrix').innerHTML=order.map(k=>{const z=frames[k]||{};const tt=z.trendline||{};const ff=z.fibonacci||{};return trendCard(k,{trendline:tt,fibonacci:ff,advanced:{signal:tt.signal||'WAIT',confidence:tt.trend_power||0,candle_time:(z.candles||[]).at(-1)?.time}});}).join('');
    const dirs=order.map(k=>(frames[k]?.trendline?.signal||'WAIT'));
    const buys=dirs.filter(v=>v==='BUY').length,sells=dirs.filter(v=>v==='SELL').length;
    $('trendMatrixFinal').textContent=buys>=4?'🟢 STRONG BUY':sells>=4?'🔴 STRONG SELL':buys>=3?'🟢 BUY':sells>=3?'🔴 SELL':'🟡 WAIT';
    if(token){ await recordModuleSignal('Auto Trend Line', {interval:tf,candle_time:(tl.candles||[]).at(-1)?.time,signal:t.signal||'WAIT',confidence:t.trend_power??0,entry:x.entry,stop_loss:x.stop_loss,take_profit:x.take_profit,trendline:t,fibonacci:fib}, x, tf, (tl.candles||[]).at(-1)?.time); }
    $('trendLineStatus').textContent=`${symbol} · ${tfName(tf)} · Trend Line + Fibonacci · FAQAT Exness MT5 XAUUSDm candlelari · ${new Date(tl.generated_at).toLocaleString()}`;
    if($('trendChartTf')) $('trendChartTf').textContent=tfName(tf);
  }catch(e){$('trendLineStatus').textContent='Trend Line error: '+e.message;}
}
function openSection(id){const target=$(id);if(!target)return;window.scrollTo({top:0,left:0,behavior:'auto'});document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));target.classList.add('active');document.querySelectorAll('.nav button').forEach(b=>b.classList.toggle('active',b.dataset.section===id));const titles={overview:'Market Overview',chartSection:'Live Chart',analysisSection:'Technical Analysis',smartAnalysisSection:'AI Smart Analysis',aiSignalsSection:'AI Signals',classicSection:'Classic Trade',snrSection:'SNR',mtfSection:'Multi-Timeframe Analysis',signalSection:'Signal Lab',signalsSection:'Signals',ictSection:'ICT Signals',mt5Section:'MetaTrader 5',calendarSection:'Economic Calendar',sessionsSection:'Market Sessions',historySection:'Signal History',trendLineSection:'Auto Trend Line'};$('pageTitle').textContent=titles[id]||'Trading SaaS';if(id==='chartSection'){setTimeout(()=>{mountTradingView('chart2',interval);loadChartHistory().catch(()=>{})},50);}if(id==='overview'){setTimeout(()=>{mountTradingView('chart',interval);loadChartHistory().catch(()=>{})},50);}if(id==='analysisSection')loadAnalysisOnly().catch(()=>{});if(id==='smartAnalysisSection')loadSmartAnalysis().catch(()=>{});if(id==='aiSignalsSection')loadAISignals().catch(()=>{});if(id==='classicSection')loadClassicTrade(classicInterval).catch(()=>{});if(id==='snrSection')loadSNR(snrInterval).catch(()=>{});if(id==='signalSection')loadSelectedSignal(signalInterval);if(id==='classicSection')loadClassicTrade(classicInterval);if(id==='calendarSection')loadCalendar();if(id==='sessionsSection')loadSessions();if(id==='mtfSection')loadMtf();if(id==='historySection')loadHistory();if(id==='signalsSection')loadAutoSignals();if(id==='ictSection')loadICTSignals();if(id==='mt5Section')loadMT5Status().catch(()=>{});if(id==='trendLineSection'){if(trendLiveRefreshTimer){clearInterval(trendLiveRefreshTimer);trendLiveRefreshTimer=null;} loadTrendLines(trendLineInterval).catch(()=>{});} else if(trendLiveRefreshTimer){clearInterval(trendLiveRefreshTimer);trendLiveRefreshTimer=null;}}

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
async function loadMT5Status(){
  const d=await api('/api/v1/mt5/status'); const st=d.state||{};
  setText('mt5Status', st.connected?'🟢 CONNECTED':'🔴 DISCONNECTED');
  setText('mt5Balance', st.balance==null?'—':fmt(st.balance)); setText('mt5Equity',st.equity==null?'—':fmt(st.equity)); setText('mt5FreeMargin',st.free_margin==null?'—':fmt(st.free_margin)); setText('mt5Positions',st.positions??0); setText('mt5Lot', d.lot==null?'0.01':String(d.lot));
  const on=!!d.auto_trading; setText('mt5AutoState',on?'🟢 ON':'🔴 OFF'); setText('mt5AutoInfo',on?'Auto trading yoqilgan. Faqat ≥85% + Strong Zone + AI tasdiq + MTF moslik + RR≥1.50 setup navbatiga tushadi.':"OFF bo‘lsa yangi orderlar MT5'ga yuborilmaydi.");
  
}
async function connectMT5(){
  const login=String($('mt5Login')?.value||'').trim(), server=String($('mt5Server')?.value||'').trim(), password=String($('mt5Password')?.value||'');
  if(!login||!server||!password) throw Error('MT5 Login, Server va Trading Password kiriting.');
  const d=await api('/api/v1/mt5/connect',{method:'POST',body:JSON.stringify({login,server,password,demo:true})});
  sessionStorage.setItem('mt5_login',login); sessionStorage.setItem('mt5_server',server); sessionStorage.removeItem('mt5_password');
  $('mt5Password').value=''; await loadMT5Status(); showToast(d.message||'MT5 ma’lumotlari qabul qilindi');
}
async function saveMT5Lot(){ const raw=parseFloat(String($('mt5Lot')?.value||'0')); if(!Number.isFinite(raw)||raw<0.01||raw>100) throw Error('Lot 0.01 dan 100 gacha bo‘lishi kerak.'); const d=await api('/api/v1/mt5/lot',{method:'POST',body:JSON.stringify({lot:raw})}); setText('mt5Lot',String(d.lot??raw)); showToast('Lot saqlandi: '+(d.lot??raw)); await loadMT5Status(); }
async function setMT5Auto(enabled){ const d=await api('/api/v1/mt5/auto-trading?enabled='+(enabled?'true':'false'),{method:'POST'}); await loadMT5Status(); showToast(enabled?'AUTO TRADING ON':'AUTO TRADING OFF'); }
function bindCriticalButtons(){
  const bindOnce=(el,type,fn)=>{if(!el||el.dataset.bound==='1')return;el.dataset.bound='1';el.addEventListener(type,fn);};
  const withBusy=(el,fn)=>async()=>{if(el.disabled)return;const old=el.innerHTML;el.disabled=true;el.innerHTML='⟳ Ishlanmoqda…';try{await fn();}catch(err){console.error('BUTTON ERROR',el.id,err);showToast(err?.message||'Server xatosi');}finally{el.disabled=false;el.innerHTML=old;}};
  const actionMap={
    refreshSignalEngine:()=>loadSignalEngine(), refreshAIProviders:()=>loadAIProviders(), refreshAdvanced:()=>loadAdvancedSignals(),
    refreshICT:()=>loadICTSignals(), refreshClassic:()=>loadClassicTrade(classicInterval), refreshSNR:()=>loadSNR(snrInterval),
    refreshStats:async()=>{await loadStats();await loadHistory()}, refreshSmartAnalysis:()=>loadSmartAnalysis(), refreshAISignals:()=>loadAISignals(),
    refreshCalendar:()=>loadCalendar(), refreshHistory:async()=>{await loadStats();await loadHistory()}, refreshTrendLines:()=>loadTrendLines(trendLineInterval),
    refreshMT5:()=>loadMT5Status(), connectMT5:()=>connectMT5(), saveMT5Lot:()=>saveMT5Lot(), mt5AutoOn:()=>setMT5Auto(true), mt5AutoOff:()=>setMT5Auto(false)
  };
  Object.entries(actionMap).forEach(([id,fn])=>{const el=$(id);bindOnce(el,'click',async e=>{e.preventDefault();e.stopPropagation();await withBusy(el,fn)();showToast(id.startsWith('refresh')?'Yangilandi':'Bajarildi');});});
  const auth=$('authBtn');
  bindOnce(auth,'click',e=>{e.preventDefault();e.stopPropagation();if(String(auth.textContent||'').trim()==='Chiqish'){logoutUser();return;}setAuth('login');setText('authMsg','');$('authModal')?.classList.add('show');setTimeout(()=>$('email')?.focus(),50);});
  bindOnce($('authClose'),'click',e=>{$('authModal')?.classList.remove('show');});
  bindOnce($('authSwitch'),'click',e=>{e.preventDefault();e.stopPropagation();setAuth(authMode==='login'?'register':'login');setTimeout(()=>$('email')?.focus(),50);});
  bindOnce($('authModal'),'click',e=>{if(e.target.id==='authModal')e.currentTarget.classList.remove('show');});
  bindOnce(document,'keydown',e=>{if(e.key==='Escape')$('authModal')?.classList.remove('show');});
}

function bindUIActions(){
  document.querySelectorAll('.tfbar').forEach(bar=>{
    if(bar.dataset.bound==='1')return;bar.dataset.bound='1';
    bar.addEventListener('click',e=>{
      const b=e.target.closest('[data-interval]'); if(b&&bar.contains(b)){setTf(b.dataset.interval);return;}
      const s=e.target.closest('[data-signal-interval]'); if(s&&bar.contains(s)){document.querySelectorAll('[data-signal-interval]').forEach(x=>x.classList.toggle('active',x===s));signalInterval=s.dataset.signalInterval;loadSelectedSignal(signalInterval).catch(()=>{});return;}
      const c=e.target.closest('[data-classic-interval]'); if(c&&bar.contains(c)){document.querySelectorAll('[data-classic-interval]').forEach(x=>x.classList.toggle('active',x===c));classicInterval=c.dataset.classicInterval;loadClassicTrade(classicInterval).catch(()=>{});return;}
      const n=e.target.closest('[data-snr-interval]'); if(n&&bar.contains(n)){document.querySelectorAll('[data-snr-interval]').forEach(x=>x.classList.toggle('active',x===n));snrInterval=n.dataset.snrInterval;loadSNR(snrInterval).catch(()=>{});}
    });
  });
  document.querySelectorAll('.nav button').forEach(b=>{if(b.dataset.bound==='1')return;b.dataset.bound='1';b.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();openSection(b.dataset.section);});});
}

document.addEventListener('click',e=>{const b=e.target.closest('[data-trend-interval]');if(b){e.preventDefault();e.stopPropagation();document.querySelectorAll('[data-trend-interval]').forEach(x=>x.classList.toggle('active',x===b));trendLineInterval=b.dataset.trendInterval;loadTrendLines(trendLineInterval).catch(err=>showToast(err?.message||'Trend Line yangilanmadi'));}});
if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',()=>{bindUIActions();bindCriticalButtons()},{once:true});}else{bindUIActions();bindCriticalButtons();}
async function logoutUser(){await api('/api/auth/logout',{method:'POST'}).catch(()=>{});token='';localStorage.removeItem('trading_token');$('plan').textContent='Guest';$('authBtn').textContent='Kirish';loadStats();loadHistory();$('authModal').classList.remove('show');$('authMsg').textContent='';showToast('Tizimdan chiqildi')};$('authForm').onsubmit=async e=>{
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
(async()=>{
  try{bindUIActions()}catch(e){console.error("UI binding",e)}
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
    loadSessions().catch(()=>{}); loadMT5Status().catch(()=>{});
    if(token){
      autoEntryTick().catch(()=>{});
      try{const me=await api('/api/auth/me');$('plan').textContent=me.plan||'free';$('authBtn').textContent='Chiqish'}
      catch(_){token='';localStorage.removeItem('trading_token')}
      loadStats().catch(()=>{}); loadHistory().catch(()=>{});
    }
    // One synchronized dashboard refresh cycle. All visible modules refresh from
    // the same cycle instead of having independent 12s/15s/30s timers that can
    // show different moments/candles. A new cycle starts only after the previous
    // cycle finishes; stale overlapping requests are therefore avoided.
    let syncRefreshRunning=false;
    let syncRefreshSeq=0;
    const syncRefreshCycle=async()=>{
      if(document.visibilityState!=='visible' || syncRefreshRunning) return;
      syncRefreshRunning=true; const seq=++syncRefreshSeq;
      try{
        // First establish the current market snapshot. Other visible modules are
        // refreshed immediately after it, so the UI moves forward as one batch.
        await Promise.allSettled([
          loadMain(true),
          loadAnalysisOnly()
        ]);
        if(seq!==syncRefreshSeq) return;
        const tasks=[];
        if(token) tasks.push(autoEntryTick());
        if($('overview')?.classList.contains('active')) tasks.push(loadSignalEngine());
        if($('signalsSection')?.classList.contains('active')) tasks.push(loadAutoSignals());
        if($('aiSignalsSection')?.classList.contains('active')) tasks.push(loadAISignals());
        if($('ictSection')?.classList.contains('active')) tasks.push(loadICTSignals());
        if($('signalSection')?.classList.contains('active')) tasks.push(loadSelectedSignal(signalInterval));
        if($('classicSection')?.classList.contains('active')) tasks.push(loadClassicTrade(classicInterval));
        if($('snrSection')?.classList.contains('active')) tasks.push(loadSNR(snrInterval));
        if($('mtfSection')?.classList.contains('active')) tasks.push(loadMtf());
        if($('calendarSection')?.classList.contains('active')) tasks.push(loadCalendar());
        if($('sessionsSection')?.classList.contains('active')) tasks.push(loadSessions());
        if($('trendLineSection')?.classList.contains('active')) tasks.push(loadTrendLines(trendLineInterval));
        if($('mt5Section')?.classList.contains('active')) tasks.push(loadMT5Status());
        if(token && $('historySection')?.classList.contains('active')) tasks.push(loadHistory());
        tasks.push(loadAIProviders());
        await Promise.allSettled(tasks);
      }catch(e){ console.warn('SYNC REFRESH',e); }
      finally{ syncRefreshRunning=false; }
    };
    // Lightweight quote heartbeat; this is price-only and does not alter the
    // analysis snapshot cadence.
    setInterval(()=>quoteHeartbeat().catch(()=>{}),3000);
    // All dashboard/analysis modules now share one refresh cadence.
    setInterval(()=>{syncRefreshCycle().catch(()=>{})},15000);
    // Run one synchronized cycle shortly after startup.
    setTimeout(()=>syncRefreshCycle().catch(()=>{}),1200);
    setInterval(updateCountdown,250);
  }catch(e){
    console.error('Dashboard init error',e);
    $('mode').textContent='UI READY';
    // Keep the navigation/chart usable even when the backend is temporarily down.
    try{mountTradingView('chart', interval)}catch(_){}
  }
})();;