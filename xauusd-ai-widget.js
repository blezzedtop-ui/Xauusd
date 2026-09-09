
(() => {
  const s = document.currentScript;
  const api = s.dataset.api || "/api/market";
  const aiApi = s.dataset.aiApi || "/api/ai-analysis";
  const targetId = s.dataset.target || "xauusd-ai-widget";
  const refreshMs = Number(s.dataset.refresh || 30000);
  const target = document.getElementById(targetId);
  if (!target) return;

  target.innerHTML = `
    <div class="xai-card">
      <div class="xai-head">
        <div><div class="xai-title">XAUUSD M30 AI Signal</div><div class="xai-sub">10 Price Action Strategies + OpenAI</div></div>
        <div class="xai-live" id="xai-status">CONNECTING</div>
      </div>
      <div class="xai-grid">
        <div><span>Signal</span><b id="xai-signal">NO TRADE</b></div>
        <div><span>AI Signal</span><b id="xai-ai-signal">—</b></div>
        <div><span>Confidence</span><b id="xai-confidence">—</b></div>
        <div><span>Strategy</span><b id="xai-strategy">—</b></div>
        <div><span>Entry</span><b id="xai-entry">—</b></div>
        <div><span>SL</span><b id="xai-sl">—</b></div>
        <div><span>TP</span><b id="xai-tp">—</b></div>
        <div><span>R:R</span><b id="xai-rr">—</b></div>
      </div>
      <div class="xai-section"><span>Market Bias</span><div id="xai-bias">—</div></div>
      <div class="xai-section"><span>Structure</span><div id="xai-structure">—</div></div>
      <div class="xai-section"><span>Reason</span><div id="xai-reason">—</div></div>
      <div class="xai-section"><span>Risk</span><div id="xai-risk">—</div></div>
    </div>
    <style>
      .xai-card{font-family:Arial,sans-serif;background:#10172b;color:#e9eefc;border:1px solid #293452;border-radius:14px;padding:16px;max-width:760px}
      .xai-head{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:14px}
      .xai-title{font-size:19px;font-weight:800}.xai-sub{font-size:12px;color:#8996b6;margin-top:4px}
      .xai-live{font-size:10px;padding:6px 8px;border:1px solid #33405f;border-radius:7px}
      .xai-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
      .xai-grid>div{background:#0b1020;border-radius:10px;padding:10px}
      .xai-grid span,.xai-section>span{display:block;font-size:10px;color:#8d9aba;text-transform:uppercase;margin-bottom:6px}
      .xai-grid b{font-size:15px}.xai-section{border-top:1px solid #26304a;margin-top:12px;padding-top:12px;font-size:13px;line-height:1.45}
      .xai-buy{color:#60e39b!important}.xai-sell{color:#ff8ea0!important}.xai-neutral{color:#cbd4eb!important}
      @media(max-width:620px){.xai-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    </style>
  `;

  const $ = id => document.getElementById(id);
  const fmt = v => v == null ? "—" : Number(v).toFixed(2);
  const paint = (el, v) => { el.textContent = v || "—"; el.className = v==="BUY"?"xai-buy":v==="SELL"?"xai-sell":"xai-neutral"; };

  async function refresh(){
    try{
      const [mr, ar] = await Promise.all([
        fetch(api,{cache:"no-store"}), fetch(aiApi,{cache:"no-store"})
      ]);
      if(!mr.ok || !ar.ok) throw new Error("API request failed");
      const m = await mr.json(), a = await ar.json(), sig=m.signal||{}, ai=a.ai||{};
      paint($("xai-signal"),sig.signal);
      paint($("xai-ai-signal"),ai.final_signal);
      $("xai-confidence").textContent=ai.confidence==null?"—":ai.confidence+"%";
      $("xai-strategy").textContent=sig.strategy||"—";
      $("xai-entry").textContent=fmt(sig.entry); $("xai-sl").textContent=fmt(sig.sl);
      $("xai-tp").textContent=fmt(sig.tp); $("xai-rr").textContent=sig.rr==null?"—":Number(sig.rr).toFixed(2);
      $("xai-bias").textContent=ai.market_bias||"—"; $("xai-structure").textContent=ai.structure||ai.error||"—";
      $("xai-reason").textContent=Array.isArray(ai.reasons)?ai.reasons.join(" · "):"—";
      $("xai-risk").textContent=Array.isArray(ai.risks)?ai.risks.join(" · "):"—";
      $("xai-status").textContent="LIVE";
    }catch(e){ $("xai-status").textContent="ERROR"; console.error(e); }
  }
  refresh(); setInterval(refresh,refreshMs);
})();
