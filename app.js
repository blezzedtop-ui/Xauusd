const symbol='XAU/USD';let interval='5min',pivotInterval='5min',aiInterval='5min',signalInterval='5min',token=localStorage.getItem('trading_token')||'',authMode='login',chart,series,chart2,series2,countdownData={close_timestamp:null},marketWS=null,liveCandle=null,lastTickTs=0,streamKey='';
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
const lwcCharts={};
const pivotOverlays={};
function chartTheme(){return {layout:{background:{type:'solid',color:'#07090d'},textColor:'#9aa3af'},grid:{vertLines:{color:'rgba(255,255,255,.055)'},horzLines:{color:'rgba(255,255,255,.055)'}},rightPriceScale:{borderColor:'rgba(255,215,120,.16)',scaleMargins:{top:.08,bottom:.12}},timeScale:{borderColor:'rgba(255,215,120,.12)',timeVisible:true,secondsVisible:false},crosshair:{mode:0}}}
function clearPivotChart(id){
 const item=lwcCharts[id]; if(!item)return;
 (pivotOverlays[id]?.lines||[]).forEach(line=>{try{item.series.removePriceLine(line)}catch(e){}});
 if(pivotOverlays[id]?.root)pivotOverlays[id].root.remove();
 pivotOverlays[id]=null;
}
function positionPivotZones(id){
 const item=lwcCharts[id], ov=pivotOverlays[id]; if(!item||!ov)return;
 const root=ov.root, h=root.clientHeight;
 const zones=ov.zones||[];
 zones.forEach(z=>{
   const y1=item.series.priceToCoordinate(z.top), y2=item.series.priceToCoordinate(z.bottom);
   if(y1==null||y2==null){z.el.style.display='none';return}
   const top=Math.max(0,Math.min(y1,y2)), height=Math.min(h,Math.abs(y2-y1));
   z.el.style.display='block'; z.el.style.top=top+'px'; z.el.style.height=Math.max(2,height)+'px';
 });
}
function drawPivotOnChart(id,p){
 const item=lwcCharts[id]; if(!item||!p||p.pivot==null)return;
 clearPivotChart(id);
 const colors={R3:'#e85d68',R2:'#ef7a82',R1:'#f29aa0',Pivot:'#f5c15d',S1:'#6be0b0',S2:'#45cf99',S3:'#2eb983'};
 const vals=[['R3',p.r3],['R2',p.r2],['R1',p.r1],['Pivot',p.pivot],['S1',p.s1],['S2',p.s2],['S3',p.s3]].filter(([,v])=>Number.isFinite(Number(v)));
 const lines=vals.map(([name,v])=>item.series.createPriceLine({price:Number(v),color:colors[name],lineWidth:name==='Pivot'?2:1,lineStyle:name==='Pivot'?0:2,axisLabelVisible:true,title:name}));
 const root=document.createElement('div'); root.className='pivot-chart-overlay'; item.el.appendChild(root);
 const zones=[];
 if(Number.isFinite(+p.r1)&&Number.isFinite(+p.r2)){
   const el=document.createElement('div'); el.className='pivot-zone resistance-zone'; el.innerHTML='<span>RESISTANCE R1–R2</span>'; root.appendChild(el); zones.push({el,top:Math.max(+p.r1,+p.r2),bottom:Math.min(+p.r1,+p.r2)});
 }
 if(Number.isFinite(+p.s1)&&Number.isFinite(+p.s2)){
   const el=document.createElement('div'); el.className='pivot-zone support-zone'; el.innerHTML='<span>SUPPORT S1–S2</span>'; root.appendChild(el); zones.push({el,top:Math.max(+p.s1,+p.s2),bottom:Math.min(+p.s1,+p.s2)});
 }
 pivotOverlays[id]={root,lines,zones,p};
 positionPivotZones(id);
 item.chart.timeScale().subscribeVisibleLogicalRangeChange(()=>positionPivotZones(id));
}
function applyCurrentPivotToCharts(){
 const p=window.__selectedPivot; if(!p)return;
 Object.keys(lwcCharts).forEach(id=>drawPivotOnChart(id,p));
}
function mountTradingView(id, tf=interval){
 const el=$(id); if(!el)return;
 if(lwcCharts[id]){try{lwcCharts[id].chart.remove()}catch(e){} delete lwcCharts[id];}
 el.innerHTML=''; el.style.minHeight=innerWidth<700?'420px':'520px'; el.style.height=innerWidth<700?'420px':'560px'; el.style.position='relative';
 const ch=LightweightCharts.createChart(el,{...chartTheme(),width:el.clientWidth,height:el.clientHeight,localization:{priceFormatter:p=>Number(p).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}});
 const ser=ch.addCandlestickSeries({upColor:'#2fd49a',downColor:'#ef6471',borderVisible:false,wickUpColor:'#2fd49a',wickDownColor:'#ef6471'});
 lwcCharts[id]={chart:ch,series:ser,el,tf};
 if(id==='chart'){window.chart=ch;window.series=ser;chart=ch;series=ser;} else {window.chart2=ch;window.series2=ser;chart2=ch;series2=ser;}
 new ResizeObserver(()=>{try{ch.applyOptions({width:el.clientWidth,height:el.clientHeight});positionPivotZones(id)}catch(e){}}).observe(el);
 if(window.__selectedPivot) setTimeout(()=>drawPivotOnChart(id,window.__selectedPivot),50);
 api(`/api/v1/candles/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(tf)}&limit=500`).then(d=>{if(d.candles) applyChart(d.candles,d.mode||'live')}).catch(e=>{if(id==='chart')showToast(e.message||'Chart data unavailable')});
}
function initChart(id){mountTradingView(id, interval); return {c:lwcCharts[id]?.chart||null,s:lwcCharts[id]?.series||null};}
function applyChart(candles,mode){
 const data=(candles||[]).map(x=>({time:Number(x.time),open:+x.open,high:+x.high,low:+x.low,close:+x.close})).filter((x,i,a)=>i===0||x.time>a[i-1].time);
 liveCandle=data[data.length-1]||null;
 if(data.length){const first=data[0].time,last=data[data.length-1].time,days=Math.max(1,Math.round((last-first)/86400));$('change').textContent=`${data.length.toLocaleString()} candles · ${days} days history`;$('historyInfo').textContent=`${days}+ days · ${data.length.toLocaleString()} candles`;}
 Object.values(lwcCharts).forEach(item=>{try{item.series.setData(data);item.chart.timeScale().fitContent()}catch(e){}});
 applyCurrentPivotToCharts();
 $('mode').textContent=mode==='live'?'LIVE MARKET':'LIVE RETRY'; $('mode').style.color=mode==='live'?'var(--green)':'var(--amber)'; $('chartStatus').textContent=mode==='live'?'LIVE MARKET':'RETRYING';
}
function setTf(v){
 interval=v;
 liveCandle=null;
 document.querySelectorAll('[data-interval]').forEach(b=>b.classList.toggle('active',b.dataset.interval===v));
 if($('tfLabel'))$('tfLabel').textContent=({'1min':'1 MIN','5min':'5 MIN','15min':'15 MIN','30min':'30 MIN','1h':'1 HOUR','4h':'4 HOUR','1day':'1 DAY'})[v]||v;
 mountTradingView('chart', interval); if($('chartSection').classList.contains('active')) setTimeout(()=>mountTradingView('chart2', interval),50); loadMain(true); setTimeout(()=>loadPivots(pivotInterval),250);
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
async function loadPivots(tf=pivotInterval){
  pivotInterval=tf;
  try{
    const d=await api(`/api/v1/pivots/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(tf)}`);
    const p=d.timeframes?.[tf]||{};
    $('pivotFilter').textContent=tfName(tf);
    $('pivotSource').textContent=`${tfName(tf)} Pivot · source: ${tfName(p.source_timeframe||tf)}${p.warning?' · '+p.warning:''}`;
    $('levels').innerHTML=[['R3',p.r3,'res'],['R2',p.r2,'res'],['R1',p.r1,'res'],['Pivot',p.pivot,'piv'],['S1',p.s1,'sup'],['S2',p.s2,'sup'],['S3',p.s3,'sup']].map(x=>`<div class="row"><span>${x[0]}</span><b class="${x[2]}">${fmt(x[1])}</b></div>`).join('');
    window.__selectedPivot=p; applyCurrentPivotToCharts();
  }catch(e){
    $('pivotSource').textContent='Pivot yuklanmadi: '+e.message;
  }
}
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
function renderAnalysis(d){const s=d.setup||{},ta=d.technical||{};$('signalMain').textContent=d.direction||'WAIT';$('signalMain').className='signal-main '+((d.direction||'WAIT').toLowerCase()==='buy'?'buy':(d.direction||'').toLowerCase()==='sell'?'sell':'wait');$('signalReason').textContent=d.headline||s.reason||'—';$('entry').textContent=fmt(s.entry);$('sl').textContent=fmt(s.stop_loss);$('tp1').textContent=fmt((s.take_profit||[])[0]);$('tp2').textContent=fmt((s.take_profit||[])[1]);$('bias').textContent=d.levels?.bias||s.pivot_filter||'—';$('pivotFilter').textContent=d.levels?.bias||'—';const p=d.levels||{};$('levels').innerHTML=[['R3',p.r3,'res'],['R2',p.r2,'res'],['R1',p.r1,'res'],['Pivot',p.pivot,'piv'],['S1',p.s1,'sup'],['S2',p.s2,'sup'],['S3',p.s3,'sup']].map(x=>`<div class="row"><span>${x[0]}</span><b class="${x[2]}">${fmt(x[1])}</b></div>`).join('');$('rsi').textContent=fmt(ta.rsi);$('atr').textContent=fmt(ta.atr);$('rsiState').textContent=ta.rsi_state||'—';$('taTrend').textContent=ta.trend||'—';$('taState').textContent=d.interval?.toUpperCase()||interval;$('taSummary').textContent=ta.summary||'—';const ai=d.ai||{};$('aiMode').textContent=ai.mode||'—';$('aiSummary').textContent=ai.summary||'—';$('confidence').textContent=ai.confidence!=null?ai.confidence+'%':'—';$('aiBias').textContent=ai.bias||'—';$('aiAdvice').textContent=ai.advice||'—';}
function updateCountdown(){const ts=countdownData?.close_timestamp; if(!ts)return;$('countdown').textContent=fmtDuration(Math.max(0,ts*1000-Date.now())); const close=new Date(ts*1000); $('closeTime').textContent='Close time: '+close.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});}function fmtDuration(ms){let s=Math.floor(ms/1000),h=Math.floor(s/3600);s%=3600;let m=Math.floor(s/60);s%=60;return h?`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`}
async function loadSessions(){try{const d=await api('/api/v1/sessions');const html=d.sessions.map(x=>`<div class="session ${x.open?'open':''}"><b>${x.name}</b><div class="sub">${x.local_time||''}</div><div class="status ${x.open?'up':'muted'}">${x.open?'OPEN':'CLOSED'}</div></div>`).join('');$('sessions').innerHTML=html;$('sessions2').innerHTML=html;$('sessionClock').textContent=d.utc_time||'—';$('sessionClock2').textContent=d.utc_time||'—'}catch(e){}}
async function loadCalendar(){try{const d=await api('/api/v1/calendar?days=7');const source=d.provider?` · Source: ${d.provider}`:'';if(!d.events?.length){$('calendar').innerHTML=`<div class="mini">${d.warning||'HIGH IMPACT eventlar topilmadi.'}</div>`;return}$('calendar').innerHTML=`<div class="mini" style="margin-bottom:8px">USD · HIGH IMPACT${source} · ${d.events.length} event</div>`+d.events.map(x=>`<div class="calendar-item"><div><span class="tag">HIGH IMPACT</span> · ${x.country||'USD'} · ${x.time||''}</div><b>${x.event||'Economic event'}</b><div class="mini">Forecast: ${x.forecast??x.estimate??'—'} · Previous: ${x.previous??'—'} · Actual: ${x.actual??'—'}</div></div>`).join('')}catch(e){$('calendar').innerHTML=`<div class="mini">Calendar ma’lumoti hozircha mavjud emas: ${e.message}</div>`}}
async function loadMtf(){try{const d=await api(`/api/v1/multi-timeframe/${encodeURIComponent(symbol)}`);$('mtfOverall').textContent=d.overall||'—';$('mtfGrid').innerHTML=(d.frames||[]).map(x=>`<div class="metric"><small>${x.interval}</small><b class="${(x.trend||'').toLowerCase()==='bullish'?'buy':(x.trend||'').toLowerCase()==='bearish'?'sell':''}">${x.trend||'—'}</b><div class="mini">RSI ${x.rsi!=null?fmt(x.rsi):'—'}</div></div>`).join('')}catch(e){}}
async function loadStats(){if(!token){$('totalSignals').textContent='0';$('completedSignals').textContent='0';$('wins').textContent='0';$('losses').textContent='0';$('winrate').textContent='0%';return}try{const d=await api('/api/v1/signals/analytics');$('totalSignals').textContent=d.total_signals;$('completedSignals').textContent=d.completed_trades;$('wins').textContent=d.wins;$('losses').textContent=d.losses;$('winrate').textContent=d.winrate+'%'}catch(e){}}
async function loadHistory(){if(!token){$('history').innerHTML='<tr><td colspan="7">Kirish kerak.</td></tr>';return}try{const d=await api('/api/v1/signals/history?limit=50');$('history').innerHTML=(d.items||[]).map(x=>`<tr><td>${new Date(x.created_at).toLocaleString()}</td><td>${x.interval}</td><td class="${x.direction==='BUY'?'buy':x.direction==='SELL'?'sell':''}">${x.direction}</td><td>${fmt(x.entry)}</td><td>${(x.tp||[]).map(fmt).join(' / ')||'—'}</td><td>${fmt(x.sl)}</td><td class="outcome-${x.outcome==='TP HIT'?'tp':x.outcome==='SL HIT'?'sl':x.outcome==='OPEN'?'open':'amb'}">${x.outcome}</td></tr>`).join('')||'<tr><td colspan="7">Signal yo‘q.</td></tr>'}catch(e){$('history').innerHTML='<tr><td colspan="7">History yuklanmadi.</td></tr>'}}
function componentText(v){if(v==null)return '—';if(typeof v==='object'){if(v.type)return v.type+(v.low!=null?' · '+fmt(v.low)+'–'+fmt(v.high):'');if(v.support!=null)return 'S '+fmt(v.support)+' · R '+fmt(v.resistance);return JSON.stringify(v)}return String(v)}
function tfName(tf){return ({'1min':'1 MIN','5min':'5 MIN','15min':'15 MIN','30min':'30 MIN','1h':'1 HOUR','4h':'4 HOUR','1day':'1 DAY'})[tf]||tf;}
function advCard(tf,x){const sig=x.signal||'WAIT', cls=sig==='BUY'?'buy':sig==='SELL'?'sell':'wait', badge=sig==='BUY'?'badge-buy':sig==='SELL'?'badge-sell':'badge-wait';const c=x.components||{};return `<div class="advanced-card ${cls}"><div class="advanced-head"><div><div class="mini">${tfName(tf)}</div><div class="advanced-signal ${badge}">${sig}</div></div><span class="pill">${x.confidence||0}%</span></div><div class="mini" style="margin-top:4px">Score ${x.score??0} · ${x.setup||'—'}</div><div class="grid4" style="margin-top:9px"><div class="metric"><small>Entry</small><b>${fmt(x.entry)}</b></div><div class="metric"><small>SL</small><b>${fmt(x.stop_loss)}</b></div><div class="metric"><small>TP1</small><b>${fmt((x.take_profit||[])[0])}</b></div><div class="metric"><small>TP2</small><b>${fmt((x.take_profit||[])[1])}</b></div></div><div class="component-grid"><div class="component"><small>ICT</small><b>${componentText(c['ICT'])}</b></div><div class="component"><small>SNR</small><b>${componentText(c['SNR'])}</b></div><div class="component"><small>SNR Malaysia</small><b>${componentText(c['SNR Malaysia'])}</b></div><div class="component"><small>Order Block</small><b>${componentText(c['Order Block'])}</b></div><div class="component"><small>FVG</small><b>${componentText(c['FVG'])}</b></div><div class="component"><small>Liquidity</small><b>${componentText(c['Liquidity'])}</b></div><div class="component"><small>Trend Line</small><b>${componentText(c['Trend Line'])}</b></div><div class="component"><small>Global Trend</small><b>${componentText(c['Global Trend Line'])}</b></div><div class="component"><small>BOS</small><b>${componentText(c['BOS'])}</b></div><div class="component"><small>CHOCH</small><b>${componentText(c['CHOCH'])}</b></div><div class="component"><small>Internal</small><b>${componentText(c['Internal Structure'])}</b></div><div class="component"><small>RSI / ATR</small><b>${fmt(x.rsi)} / ${fmt(x.atr)}</b></div></div><div class="advanced-actions"><div class="mini">${x.reason||'—'}</div>${sig==='BUY'||sig==='SELL'?`<button class="btn" data-save-advanced="${tf}">Saqlash</button>`:''}</div></div>`}
async function loadAdvancedSignals(){if(!token){showToast('Avval tizimga kiring');$('authModal').classList.add('show');return}$('advancedStatus').textContent='7 timeframe hisoblanmoqda…';$('advancedGrid').innerHTML='<div class="card">Signal hisoblanmoqda...</div>';try{const d=await api(`/api/v1/signals/advanced/${encodeURIComponent(symbol)}`);const order=['1min','5min','15min','30min','1h','4h','1day'];$('advancedGrid').innerHTML=order.map(tf=>advCard(tf,d.timeframes?.[tf]||{})).join('');$('advancedStatus').textContent=`${symbol} · ${new Date(d.generated_at).toLocaleString()} · har bir timeframe alohida`; }catch(e){$('advancedStatus').textContent=e.message;$('advancedGrid').innerHTML='<div class="card">Signal yuklanmadi.</div>'}}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-save-advanced]');if(!b)return;const tf=b.dataset.saveAdvanced;b.disabled=true;try{await api(`/api/v1/signals/save-advanced?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(tf)}`,{method:'POST'});showToast(tfName(tf)+' signal saqlandi');loadStats();if($('historySection').classList.contains('active'))loadHistory()}catch(err){showToast(err.message)}finally{b.disabled=false}});
function openSection(id){document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));$(id).classList.add('active');document.querySelectorAll('.nav button').forEach(b=>b.classList.toggle('active',b.dataset.section===id));const titles={overview:'Market Overview',chartSection:'Live Chart',analysisSection:'Technical Analysis',mtfSection:'Multi-Timeframe Analysis',aiSection:'AI Smart Analysis',signalSection:'Signal Lab',calendarSection:'Economic Calendar',sessionsSection:'Market Sessions',historySection:'Signal History'};$('pageTitle').textContent=titles[id]||'Trading SaaS';if(id==='chartSection'){setTimeout(()=>mountTradingView('chart2',interval),50);setTimeout(()=>window.dispatchEvent(new Event('resize')),150);}if(id==='overview'){setTimeout(()=>mountTradingView('chart',interval),50);}if(id==='analysisSection')loadAnalysisOnly().catch(()=>{});if(id==='aiSection')loadAISmart(aiInterval);if(id==='signalSection')loadSelectedSignal(signalInterval);if(id==='calendarSection')loadCalendar();if(id==='sessionsSection')loadSessions();if(id==='mtfSection')loadMtf();if(id==='historySection')loadHistory()}

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
  const wsFresh = marketWS && marketWS.readyState===WebSocket.OPEN && (Date.now()-lastTickTs < 20000);
  if(wsFresh){
    $('mode').textContent='LIVE STREAM'; $('mode').style.color='var(--green)'; $('chartStatus').textContent='LIVE';
    return true;
  }
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
   marketWS.onclose=()=>{ $('chartStatus').textContent='RECONNECTING'; $('mode').textContent='RECONNECTING'; setTimeout(()=>{if(document.visibilityState!=='hidden')connectMarketStream()},2500)};
   marketWS.onerror=()=>{ $('chartStatus').textContent='STREAM ERROR'; try{marketWS.close()}catch{} setTimeout(()=>{if(document.visibilityState!=='hidden')connectMarketStream()},1200) };
 }catch(e){showToast('Real-time stream could not start')}
}
function setAuth(mode){authMode=mode;$('authTitle').textContent=mode==='login'?'Kirish':'Ro‘yxatdan o‘tish';$('authSubmit').textContent=mode==='login'?'Kirish':'Ro‘yxatdan o‘tish';$('authSwitch').textContent=mode==='login'?'Hisobingiz yo‘qmi? Ro‘yxatdan o‘tish':'Hisobingiz bormi? Kirish';$('email').placeholder=mode==='login'?'Login yoki elektron pochta':'Elektron pochta';$('password').required=mode==='login';$('password').style.display=mode==='login'?'block':'none';$('password').value='';$('authMsg').textContent=mode==='register'?'Email kiriting — login va parol avtomatik yaratiladi.':''}
$('timeframes').addEventListener('click',e=>{const b=e.target.closest('[data-interval]');if(b)setTf(b.dataset.interval)});document.querySelectorAll('.tfbar').forEach(bar=>bar.addEventListener('click',e=>{const b=e.target.closest('[data-interval]');if(b)setTf(b.dataset.interval)}));document.querySelectorAll('.nav button').forEach(b=>b.addEventListener('click',()=>openSection(b.dataset.section)));$('saveSignal').onclick=saveSignal;$('refreshAdvanced').onclick=loadAdvancedSignals;$('refreshStats').onclick=loadStats;$('refreshCalendar').onclick=loadCalendar;$('refreshHistory').onclick=loadHistory;$('authBtn').onclick=()=>{ setAuth('login'); $('authMsg').textContent=''; $('authModal').classList.add('show'); setTimeout(()=>$('email').focus(),50); }; $('authSwitch').onclick=()=>setAuth(authMode==='login'?'register':'login');async function logoutUser(){await api('/api/auth/logout',{method:'POST'}).catch(()=>{});token='';localStorage.removeItem('trading_token');$('plan').textContent='Guest';$('authBtn').textContent='Kirish';loadStats();loadHistory();$('authModal').classList.add('show');$('authMsg').textContent='Tizimdan chiqildi. Qayta kirish talab qilinadi.';showToast('Tizimdan chiqildi')};$('authForm').onsubmit=async e=>{e.preventDefault();$('authMsg').textContent='Tekshirilmoqda…';try{const path=authMode==='login'?'/api/auth/login':'/api/auth/register';const payload=authMode==='login'?{username:$('email').value,password:$('password').value}:{email:$('email').value};const d=await api(path,{method:'POST',body:JSON.stringify(payload)});token=d.token;localStorage.setItem('trading_token',token);$('plan').textContent=d.user?.plan||'free';$('authBtn').textContent='Chiqish'; if(authMode==='register' && d.credentials){ $('authMsg').textContent=(d.email_message||'Hisob yaratildi')+' Login: '+d.credentials.login+' | Parol: '+d.credentials.password; } else { $('authMsg').textContent=''; } $('authModal').classList.remove('show');showToast(authMode==='login'?'Muvaffaqiyatli kirdingiz':'Hisob yaratildi');loadStats();loadHistory()}catch(err){$('authMsg').textContent=err.message}};
(async()=>{try{if(token){try{const me=await api('/api/auth/me');$('plan').textContent=me.plan||'free';$('authBtn').textContent='Chiqish'}catch(_){token='';localStorage.removeItem('trading_token')}}if(!token){$('authModal').classList.add('show');$('authBtn').textContent='Kirish'}const nd=await nodeMarketHealth(); if(nd?.ok) $('change').textContent='Cloud market gateway ready'; else window.__NODE_MARKET_DISABLED=true; const d=await api('/api/health');try{const md=await api('/api/market/diagnostics');if(md.live_ready){const ok=Object.entries(md.providers||{}).filter(([,v])=>v.ok).map(([k])=>k.toUpperCase()).join(' + ');$('mode').textContent='LIVE '+(ok||'READY');$('mode').style.color='var(--green)'}else{$('mode').textContent=md?.providers?.realmarketapi?.ok?'LIVE CHECK':'MARKET CHECK';$('mode').style.color='var(--amber)';$('change').textContent=Object.entries(md.providers||{}).map(([k,v])=>k+': '+(v.error||'not configured')).join(' | ')}}catch(_){}mountTradingView('chart', interval);await loadMain(true);await Promise.all([loadStats(),loadHistory(),loadSessions(),loadMtf()]);await quoteHeartbeat();setInterval(async()=>{await quoteHeartbeat();if($('historySection').classList.contains('active'))loadHistory();if($('overview').classList.contains('active'))loadStats()},8000);setInterval(async()=>{loadAnalysisOnly().catch(()=>{})},15000);setInterval(loadSessions,30000);setInterval(updateCountdown,250);setInterval(()=>{if($('calendarSection').classList.contains('active'))loadCalendar()},60000);}catch(e){showToast(e.message)}})();
