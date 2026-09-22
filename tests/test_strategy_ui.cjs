/* DOM integration test; fake API only. Run: NODE_PATH=<jsdom install>/node_modules node tests/test_strategy_ui.cjs */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM,VirtualConsole}=require('jsdom');
const root=path.resolve(__dirname,'..');
const vc=new VirtualConsole();const errors=[];vc.on('jsdomError',e=>errors.push(e.message));
const dom=new JSDOM(fs.readFileSync(path.join(root,'index.html'),'utf8'),{url:'https://signalx.test',runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:vc});
const w=dom.window;const requests=[];
w.localStorage.setItem('trading_token','fake-test-session');
w.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){},addListener(){},removeListener(){}});
w.scrollTo=()=>{};w.HTMLElement.prototype.scrollTo=function(){};w.HTMLElement.prototype.scrollIntoView=function(){};
w.ResizeObserver=class{observe(){} disconnect(){} unobserve(){}};
w.setInterval=()=>1;w.clearInterval=()=>{};
const modules=[['ict-ai-pro','ICT AI Pro','ictSection'],['snr','SNR','msaiStrategySection'],['ai-analysis','AI Analysis','smartAnalysisSection'],['trend','Trend','trendChannelSection'],['trendline','Trend liniya','trendLineSection'],['technical','Technical Analysis','analysisSection'],['classic','Classic Trade','classicSection'],['ob','OB Trade','smcSection'],['fibonacci','Fibonacci Trade','fibonacciSection']];
const catalog={items:modules.map(([module_id,source,section])=>({module_id,source,section,interval:'5min',target_rr:2,name:source+' independent rules',rules:'Closed candle + independent AI'})),can_configure:true,autotrade_enabled:false,transport:'legacy'};
const cs=Array.from({length:80},(_,i)=>({time:1800000000-(80-i)*300,open:100+i*.01,high:100.1+i*.01,low:99.9+i*.01,close:100.05+i*.01}));
w.fetch=async(raw,opt={})=>{
 const u=new URL(raw);requests.push({path:u.pathname,method:opt.method||'GET',body:opt.body});let data={};
 if(u.pathname==='/api/v1/strategies')data=catalog;
 else if(u.pathname.startsWith('/api/v1/strategies/')){
  const mid=u.pathname.split('/')[4],m=catalog.items.find(x=>x.module_id===mid);assert(m,'unknown module request');
  if(u.pathname.endsWith('/config')){const body=JSON.parse(opt.body);Object.assign(m,body);data={ok:true};}
  else if(u.pathname.endsWith('/record'))data={saved:true,signal_id:'TEST-'+mid,queued:false};
  else data={module_id:mid,source:m.source,symbol:'XAU/USD',interval:'5min',higher_interval:'30min',signal:'BUY',state:'READY',entry:100,stop_loss:99,take_profit:[102],risk_reward:2,candle_time:cs.at(-1).time,event_id:'EVENT-'+mid,provider:'tradingview',candles:cs,evidence:{closed:true},ai_validation:{mode:'groq',confidence:90,agreement:90,reasoning:'Offline fixture'}};
 } else if(u.pathname==='/api/auth/me')data={user:{role:'admin',is_admin:true}};
 else if(u.pathname.startsWith('/api/v1/candles/'))data={mode:'live',candles:cs,candle:{close_timestamp:1800000300}};
 else if(u.pathname.startsWith('/api/v1/quote/'))data={mode:'live',price:100,change:0};
 else if(u.pathname.startsWith('/api/v1/pivots/'))data={pivots:{p:100,r1:101,r2:102,s1:99,s2:98}};
 else if(u.pathname==='/api/v2/signal-history/stats')data={overall:{},by_module:{},by_day:{}};
 else if(u.pathname==='/api/v2/signal-history')data={items:[],count:0,total_count:0};
 else if(u.pathname==='/api/v1/mt5/gateway/accounts')data={accounts:[]};
 return {ok:true,status:200,json:async()=>data};
};
for(const script of [...w.document.scripts]){
 const src=script.getAttribute('src');
 if(src&&['config.js','app.js','assets/strategy-suite.js'].includes(src.split('?')[0]))w.eval(fs.readFileSync(path.join(root,src.split('?')[0]),'utf8'));
 else if(!src)w.eval(script.textContent);
}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 await sleep(30);
 assert.equal(w.document.querySelectorAll('.sidebar .nav button[data-section]').length,13);
 for(const [mid,name,section] of modules){
  w.document.querySelector(`[data-section="${section}"]`).click();
  await w.SignalXSuite.load(mid);await sleep(5);
  const el=w.document.getElementById(section);
  assert(el.classList.contains('active'),name+' opens');
  assert.equal(w.document.querySelectorAll('.section.active').length,1);
  assert.equal(el.querySelector('h2').textContent,name);
  assert(el.querySelector('svg[aria-label]'),name+' has real-candle plot');
  assert(el.textContent.includes('TEST-'+mid),name+' has own History ID');
  assert.equal(el.querySelector('[name=target_rr]').min,'1');
  assert.equal(el.querySelector('[name=target_rr]').max,'');
  assert.equal(el.querySelector('[name=target_rr]').step,'any');
 }
 const form=w.document.querySelector('[data-sx9-config="snr"]');form.elements.target_rr.value='1.05';
 form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await sleep(20);
 assert(requests.some(r=>r.path==='/api/v1/strategies/snr/config'&&JSON.parse(r.body).target_rr===1.05));
 const filters=[...w.document.querySelector('#historyV2Module').options].map(x=>x.value).filter(Boolean);
 assert.deepEqual(filters,modules.map(x=>x[1]));
 assert(!requests.some(r=>/^\/api\/v1\/(smc|msai-strategy|ict-ai-pro|ai-signals|new-strategy)\//.test(r.path)),'No retired signal API used');
 assert.equal(errors.filter(x=>!x.includes('navigation')).length,0,errors.join('\n'));
 dom.window.close();console.log('PASS: 13 navigation links; 9 isolated module panels, plots and History IDs; arbitrary RR save; exact History filters; no legacy signal API.');
})().catch(e=>{dom.window.close();console.error(e);process.exitCode=1;});
