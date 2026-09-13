'use strict';

try { require('dotenv').config(); } catch {}

const http = require('http');
const WebSocket = require('ws');
const { URL } = require('url');

const PORT = Number(process.env.NODE_MARKET_PORT || 3001);
const HOST = process.env.NODE_MARKET_HOST || '0.0.0.0';
const TWELVE_KEY = (process.env.TWELVE_DATA_API_KEY || '').trim();
const REAL_KEY = (process.env.REALMARKET_API_KEY || '').trim();
const REAL_BASE = (process.env.REALMARKET_API_BASE || 'https://api.realmarketapi.com').replace(/\/$/, '');
const CORS = process.env.NODE_CORS_ORIGIN || '*';
const PRICE_CACHE_TTL_MS = Number(process.env.NODE_PRICE_CACHE_TTL_MS || 30000);
const PRICE_REST_COOLDOWN_MS = Number(process.env.NODE_PRICE_REST_COOLDOWN_MS || 15000);
const MARKET_PROVIDER = (process.env.MARKET_PROVIDER || 'auto').trim().toLowerCase();
const REAL_WS_ENABLED = String(process.env.REALMARKET_WS_ENABLED || 'true').toLowerCase() !== 'false';
const priceCache = new Map();
const priceFetchAt = new Map();

function json(res, status, body) {
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'access-control-allow-origin': CORS,
    'access-control-allow-headers': 'content-type',
    'cache-control': 'no-store'
  });
  res.end(JSON.stringify(body));
}

function cleanSymbol(s) {
  return String(s || 'XAU/USD').trim() || 'XAU/USD';
}

function tdInterval(interval) {
  const map = { '1min':'1min','5min':'5min','15min':'15min','30min':'30min','1h':'1h','4h':'4h','1day':'1day' };
  return map[interval] || '1min';
}

async function twelvePrice(symbol) {
  const cached = priceCache.get(symbol);
  const now = Date.now();
  if (cached && now - cached.receivedAt <= PRICE_CACHE_TTL_MS) {
    return { price: cached.price, provider: cached.provider || 'twelvedata-stream-cache', timestamp: Math.floor(cached.timestamp || now / 1000) };
  }
  if (!TWELVE_KEY) throw new Error('TWELVE_DATA_API_KEY is not configured');
  const lastTry = priceFetchAt.get(symbol) || 0;
  if (now - lastTry < PRICE_REST_COOLDOWN_MS) {
    if (cached) return { price: cached.price, provider: cached.provider || 'twelvedata-cache', timestamp: Math.floor(cached.timestamp || now / 1000) };
    throw new Error('Twelve Data REST cooldown active; waiting for WebSocket tick');
  }
  priceFetchAt.set(symbol, now);
  const u = new URL('https://api.twelvedata.com/price');
  u.searchParams.set('symbol', symbol);
  u.searchParams.set('apikey', TWELVE_KEY);
  const r = await fetch(u);
  const d = await r.json().catch(() => ({}));
  if (!r.ok || d.status === 'error' || d.code) throw new Error(d.message || `Twelve Data HTTP ${r.status}`);
  const price = Number(d.price);
  if (!Number.isFinite(price)) throw new Error('Invalid Twelve Data price');
  const item = { price, provider: 'twelvedata-rest', timestamp: Date.now()/1000, receivedAt: Date.now() };
  priceCache.set(symbol, item);
  return { price, provider: 'twelvedata-rest', timestamp: Math.floor(item.timestamp) };
}

async function twelveCandles(symbol, interval, outputsize=5000) {
  if (!TWELVE_KEY) throw new Error('TWELVE_DATA_API_KEY is not configured');
  const u = new URL('https://api.twelvedata.com/time_series');
  u.searchParams.set('symbol', symbol);
  u.searchParams.set('interval', tdInterval(interval));
  u.searchParams.set('outputsize', String(Math.min(Math.max(Number(outputsize)||500, 1), 5000)));
  u.searchParams.set('order', 'ASC');
  u.searchParams.set('apikey', TWELVE_KEY);
  const r = await fetch(u);
  const d = await r.json();
  if (!r.ok || d.status === 'error' || !Array.isArray(d.values)) throw new Error(d.message || `Twelve Data HTTP ${r.status}`);
  const candles = d.values.map(v => ({
    time: Math.floor(Date.parse(v.datetime.replace(' ', 'T') + (/[zZ]|[+-]\d\d:?\d\d$/.test(v.datetime) ? '' : 'Z'))/1000),
    open: Number(v.open), high: Number(v.high), low: Number(v.low), close: Number(v.close), volume: v.volume == null ? undefined : Number(v.volume)
  })).filter(x => Number.isFinite(x.time) && [x.open,x.high,x.low,x.close].every(Number.isFinite));
  return { provider: 'twelvedata', symbol, interval, candles };
}

function rmSymbol(symbol) {
  return cleanSymbol(symbol).replace('/', '');
}

async function realPrice(symbol, interval='1min') {
  if (!REAL_KEY) throw new Error('REALMARKET_API_KEY is not configured');
  const u = new URL(`${REAL_BASE}/api/v1/price`);
  u.searchParams.set('apiKey', REAL_KEY);
  u.searchParams.set('symbolCode', rmSymbol(symbol));
  u.searchParams.set('timeFrame', rmTimeframe(interval));
  const r = await fetch(u, { headers: { Accept: 'application/json' } });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.message || d.Message || `RealMarketAPI HTTP ${r.status}`);
  const raw = d.ClosePrice ?? d.closePrice ?? d.Price ?? d.price ?? d.Last ?? d.last ?? d.Bid ?? d.bid ?? d.value;
  const price = Number(raw);
  if (!Number.isFinite(price)) throw new Error('Invalid RealMarketAPI price response');
  const tsRaw = d.OpenTime ?? d.openTime ?? d.Timestamp ?? d.timestamp;
  const ts = tsRaw ? (Number.isFinite(Number(tsRaw)) ? Number(tsRaw) : Math.floor(new Date(tsRaw).getTime()/1000)) : Math.floor(Date.now()/1000);
  return { price, provider: 'realmarketapi-rest', timestamp: Number.isFinite(ts) ? ts : Math.floor(Date.now()/1000) };
}

function rmTimeframe(interval) {
  const map = { '1min':'M1','5min':'M5','15min':'M15','30min':'M30','1h':'H1','4h':'H4','1day':'D1' };
  return map[interval] || 'M1';
}

function extractRealPrice(m) {
  const raw = m.ClosePrice ?? m.closePrice ?? m.price ?? m.Price ?? m.Last ?? m.last ?? m.Bid ?? m.bid ?? m.value;
  const price = Number(raw);
  if (!Number.isFinite(price)) return null;
  const rawTs = m.OpenTime ?? m.openTime ?? m.timestamp ?? m.Timestamp ?? m.ts;
  let ts = Math.floor(Date.now()/1000);
  if (rawTs != null) {
    const n = Number(rawTs);
    ts = Number.isFinite(n) ? (n > 1e12 ? Math.floor(n/1000) : Math.floor(n)) : Math.floor(new Date(rawTs).getTime()/1000);
  }
  return { price, timestamp: Number.isFinite(ts) ? ts : Math.floor(Date.now()/1000) };
}

const upstream = new Map();

function startRealMarketStream(symbol, interval, localClients) {
  if (!REAL_KEY || !REAL_WS_ENABLED) return null;
  const key = `rm|${symbol}|${interval}`;
  if (upstream.has(key)) return upstream.get(key);
  let closedByUs = false;
  let retry = 1000;
  let ws;
  const state = { stop(){ closedByUs = true; try { ws?.close(); } catch {} } };
  const connect = () => {
    if (closedByUs) return;
    const url = `${REAL_BASE.replace(/^http/, 'ws')}/price?apiKey=${encodeURIComponent(REAL_KEY)}&symbolCode=${encodeURIComponent(rmSymbol(symbol))}&timeFrame=${encodeURIComponent(rmTimeframe(interval))}`;
    ws = new WebSocket(url);
    ws.on('open', () => {
      retry = 1000;
      for (const c of localClients) c.sendSafe({type:'stream-status', status:'connected', provider:'realmarketapi'});
    });
    ws.on('message', raw => {
      let m; try { m = JSON.parse(raw.toString()); } catch { return; }
      const p = extractRealPrice(m);
      if (!p) return;
      const receivedAt = Date.now();
      priceCache.set(symbol, { price:p.price, timestamp:p.timestamp, receivedAt, provider:'realmarketapi-websocket' });
      for (const c of localClients) c.sendSafe({type:'tick', symbol, price:p.price, timestamp:p.timestamp, provider:'realmarketapi-websocket'});
    });
    ws.on('close', () => {
      for (const c of localClients) c.sendSafe({type:'stream-status', status:'reconnecting', provider:'realmarketapi'});
      if (!closedByUs) { const d = retry + Math.floor(Math.random()*500); retry=Math.min(retry*2,30000); setTimeout(connect,d); }
    });
    ws.on('error', err => { for (const c of localClients) c.sendSafe({type:'stream-error', provider:'realmarketapi', message:err?.message||'WebSocket error'}); });
  };
  connect(); upstream.set(key,state); return state;
}

function startTwelveStream(symbol, interval, localClients) {
  if (!TWELVE_KEY) return null;
  const key = `td|${symbol}|${interval}`;
  if (upstream.has(key)) return upstream.get(key);
  let closedByUs = false;
  let retry = 1000;
  let ws;
  const state = { stop(){ closedByUs = true; try { ws?.close(); } catch {} } };
  const connect = () => {
    if (closedByUs) return;
    const url = `wss://ws.twelvedata.com/v1/quotes/price?apikey=${encodeURIComponent(TWELVE_KEY)}`;
    ws = new WebSocket(url);
    ws.on('open', () => {
      retry = 1000;
      ws.send(JSON.stringify({ action:'subscribe', params:{ symbols: symbol }}));
      state.timer = setInterval(() => { try { ws.send(JSON.stringify({action:'heartbeat'})); } catch {} }, 10000);
      for (const c of localClients) c.sendSafe({type:'stream-status', status:'connected', provider:'twelvedata'});
    });
    ws.on('message', raw => {
      let m; try { m = JSON.parse(raw.toString()); } catch { return; }
      if (m.event === 'price' || m.event === 'PRICE' || (m.type === 'price' && m.price != null) || m.price != null) {
        const price = Number(m.price ?? m.close ?? m.data?.price ?? m.data?.close);
        const ts = Number(m.timestamp ?? m.ts ?? m.data?.timestamp ?? m.data?.ts) || Math.floor(Date.now()/1000);
        if (!Number.isFinite(price)) return;
        const receivedAt = Date.now();
        priceCache.set(symbol, { price, timestamp: ts, receivedAt, provider:'twelvedata-websocket' });
        for (const c of localClients) c.sendSafe({type:'tick', symbol, price, timestamp:ts, provider:'twelvedata-websocket'});
      }
    });
    ws.on('close', () => {
      if (state.timer) clearInterval(state.timer);
      for (const c of localClients) c.sendSafe({type:'stream-status', status:'reconnecting', provider:'twelvedata'});
      if (!closedByUs) { const d=retry+Math.floor(Math.random()*500); retry=Math.min(retry*2,30000); setTimeout(connect,d); }
    });
    ws.on('error', err => { for (const c of localClients) c.sendSafe({type:'stream-error', provider:'twelvedata', message:err?.message||'WebSocket error'}); });
  };
  connect(); upstream.set(key,state); return state;
}

function preferredStreamProviders() {
  if (MARKET_PROVIDER === 'realmarketapi' || MARKET_PROVIDER === 'realmarket') return ['realmarketapi','twelvedata'];
  if (MARKET_PROVIDER === 'twelvedata') return ['twelvedata','realmarketapi'];
  return ['realmarketapi','twelvedata'];
}

class Client {
  constructor(ws) { this.ws = ws; this.stream = null; }
  sendSafe(msg) { if (this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg)); }
  close() { try { this.stream?.clients.delete(this); } catch {}; try { this.ws.close(); } catch {} }
}

const clients = new Set();
const wss = new WebSocket.Server({ noServer:true });
wss.on('connection', (ws, req) => {
  const u = new URL(req.url, `http://${req.headers.host}`);
  const symbol = cleanSymbol(u.searchParams.get('symbol'));
  const interval = u.searchParams.get('interval') || '1min';
  const client = new Client(ws);
  clients.add(client);
  client.symbol = symbol; client.interval = interval;
  client.sendSafe({type:'hello', provider: preferredStreamProviders()[0]});
  const provider = preferredStreamProviders()[0];
  if (provider === 'realmarketapi' && REAL_KEY && REAL_WS_ENABLED) {
    const key = `rm|${symbol}|${interval}`;
    let pool = clientPools.get(key); if (!pool) { pool = new Set(); clientPools.set(key,pool); }
    pool.add(client); client.pool=pool;
    client.sendSafe({type:'stream-status',status:'connecting',provider:'realmarketapi'});
    startRealMarketStream(symbol, interval, pool);
  } else if (TWELVE_KEY) {
    const key = `td|${symbol}|${interval}`;
    let pool = clientPools.get(key); if (!pool) { pool = new Set(); clientPools.set(key,pool); }
    pool.add(client); client.pool=pool;
    client.sendSafe({type:'stream-status',status:'connecting',provider:'twelvedata'});
    startTwelveStream(symbol, interval, pool);
  } else {
    client.sendSafe({type:'stream-status',status:'unavailable',provider:'none',message:'No market streaming API key configured'});
  }
  ws.on('close', () => { clients.delete(client); if (client.pool) client.pool.delete(client); });
});

const clientPools = new Map();

const server = http.createServer(async (req,res) => {
  try {
    const u = new URL(req.url, `http://${req.headers.host}`);
    if (req.method === 'OPTIONS') { res.writeHead(204, {'access-control-allow-origin':CORS,'access-control-allow-headers':'content-type'}); return res.end(); }
    if (u.pathname === '/health') return json(res,200,{ok:true,node:true,twelvedata:!!TWELVE_KEY,realmarketapi:!!REAL_KEY});
    if (u.pathname === '/market/price') {
      const symbol = cleanSymbol(u.searchParams.get('symbol'));
      const interval = u.searchParams.get('interval') || '1min';
      let q; const errs=[];
      // Prefer a cached WebSocket tick first; avoid wasting REST quota.
      const cached = priceCache.get(symbol);
      if (cached && Date.now() - cached.receivedAt <= PRICE_CACHE_TTL_MS) q = { price:cached.price, provider:cached.provider, timestamp:Math.floor(cached.timestamp) };
      for (const p of preferredStreamProviders()) {
        if (q) break;
        try {
          if (p==='realmarketapi') q=await realPrice(symbol, interval);
          else if (p==='twelvedata') q=await twelvePrice(symbol);
        } catch(e) { errs.push(`${p}: ${e.message}`); }
      }
      if (!q) return json(res,503,{ok:false,error:'Live price unavailable',details:errs});
      return json(res,200,{ok:true,...q});
    }
    if (u.pathname === '/market/candles') {
      const symbol=cleanSymbol(u.searchParams.get('symbol'));
      const interval=u.searchParams.get('interval')||'1min';
      const outputsize=Math.min(Number(u.searchParams.get('outputsize')||2000),5000);
      let out;
      const errs=[];
      try { out=await twelveCandles(symbol,interval,outputsize); } catch(e) { errs.push(`twelvedata: ${e.message}`); }
      if (!out) return json(res,503,{ok:false,error:'Live candle history unavailable',details:errs});
      return json(res,200,{ok:true,...out});
    }
    if (u.pathname === '/market/status') return json(res,200,{ok:true,twelvedata:!!TWELVE_KEY,realmarketapi:!!REAL_KEY,connections:wss.clients.size});
    json(res,404,{ok:false,error:'Not found'});
  } catch (e) { json(res,500,{ok:false,error:e.message}); }
});

server.on('upgrade',(req,socket,head)=>{
  const u=new URL(req.url,`http://${req.headers.host}`);
  if(!u.pathname.startsWith('/ws/market')){socket.destroy();return;}
  wss.handleUpgrade(req,socket,head,ws=>wss.emit('connection',ws,req));
});

server.listen(PORT,HOST,()=>console.log(`Node market gateway listening on http://${HOST}:${PORT}`));
