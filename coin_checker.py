from flask import Flask, jsonify, render_template_string, request
import requests
from datetime import datetime, timezone
import time

app = Flask(__name__)

COINS = {
    "bitcoin": {"symbol": "BTC", "name": "Bitcoin", "gecko_id": "bitcoin"},
    "ethereum": {"symbol": "ETH", "name": "Ethereum", "gecko_id": "ethereum"},
    "solana": {"symbol": "SOL", "name": "Solana", "gecko_id": "solana"},
    "presearch": {"symbol": "PRE", "name": "Presearch", "gecko_id": "presearch"},
    "flux": {"symbol": "FLUX", "name": "Flux", "gecko_id": "zelcash"},
}

CACHE_TTL_PRICE = 20
CACHE_TTL_HISTORY = 300
price_cache = {}
history_cache = {}
ohlc_cache = {}
volume_cache = {}

HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Crypto Price Checker</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
  <style>
    :root {
      --bg: #0f172a; --text: #e2e8f0; --card: #111827; --muted: #94a3b8;
      --chart-bg: #0b1220; --border: #334155; --btn: #2563eb;
      --line: #38bdf8; --line-fill: rgba(56,189,248,.15); --shadow: rgba(0,0,0,.3);
    }
    body.light {
      --bg: #f1f5f9; --text: #0f172a; --card: #ffffff; --muted: #475569;
      --chart-bg: #f8fafc; --border: #cbd5e1; --btn: #1d4ed8;
      --line: #0284c7; --line-fill: rgba(2,132,199,.12); --shadow: rgba(15,23,42,.08);
    }
    body { font-family: system-ui, Arial; margin: 2rem; background: var(--bg); color: var(--text); }
    .card { max-width: 1280px; width: min(96vw,1280px); padding: 1.5rem; border-radius: 16px; background: var(--card); box-shadow: 0 10px 25px var(--shadow); }
    .header { display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; flex-wrap:wrap; }
    .top-right { display:flex; flex-direction:column; gap:.55rem; align-items:flex-end; }
    .top-right-controls { display:flex; gap:.7rem; flex-wrap:wrap; justify-content:flex-end; }
    .label,.muted { color: var(--muted); }
    .price { font-size:2.1rem; font-weight:700; margin:.4rem 0 .5rem; }
    .coin-select { background: var(--chart-bg); color: var(--text); border:1px solid var(--border); border-radius:10px; padding:.5rem .65rem; min-width:120px; }
    .btn { padding:.55rem .9rem; border-radius:10px; background:var(--btn); color:#fff; border:none; cursor:pointer; }
    .controls { margin-top:1rem; display:flex; gap:.6rem; align-items:center; }
    .theme-btn { margin-left:auto; }
    .dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
    .live { background:#22c55e; box-shadow:0 0 0 3px rgba(34,197,94,.2); }
    .fallback { background:#f59e0b; box-shadow:0 0 0 3px rgba(245,158,11,.2); }
    .status-wrap { display:flex; gap:.5rem; align-items:center; }
    .top20-wrap { margin-bottom:.7rem; padding:.45rem .6rem; background:var(--chart-bg); border:1px solid var(--border); border-radius:10px; display:flex; align-items:center; gap:.8rem; white-space:nowrap; }
    .top20-fixed { font-weight:600; color:var(--muted); flex:0 0 auto; }
    .top20-scroll { overflow:hidden; flex:1; }
    .top20-track { display:inline-flex; gap:0; min-width:max-content; animation: ticker-scroll 90s linear infinite; will-change: transform; }
    .top20-wrap:hover .top20-track { animation-play-state: paused; }
    .top20-item { display:inline-block; margin-right:1rem; font-size:.92rem; }
    .top20-symbol { color:var(--muted); margin-right:.2rem; }
    @keyframes ticker-scroll { from { transform: translateX(0); } to { transform: translateX(-50%); } }
    canvas { margin-top:1rem; background:var(--chart-bg); border-radius:12px; padding:.5rem; }
  </style>
</head>
<body>
  <div class="card">
    <div class="top20-wrap" id="top20Row"><span class="top20-fixed" id="top20Label">Top 20:</span><div class="top20-scroll"><div class="top20-track">Laden...</div></div></div>
    <div class="header">
      <div>
        <div class="label" id="title">Crypto prijs (live)</div>
        <div class="price" id="price">Laden...</div>
      </div>
      <div class="top-right">
        <div class="top-right-controls">
          <div><label class="muted" id="coinLabel">Munt:</label><br><select id="coin" class="coin-select" onchange="onCoinChange()"><option value="bitcoin">Bitcoin (BTC)</option><option value="ethereum">Ethereum (ETH)</option><option value="solana">Solana (SOL)</option><option value="presearch">Presearch (PRE)</option><option value="flux">Flux (FLUX)</option></select></div>
          <!-- range verplaatst naar boven de lijn grafiek -->
          <div><label class="muted" id="currencyLabel">Grafiek valuta:</label><br><select id="currency" class="coin-select" onchange="onCurrencyChange()"><option value="eur">EUR (€)</option><option value="usd">USD ($)</option></select></div>
        </div>
      </div>
    </div>

    <div><span id="changeLabel">24u verandering:</span> <strong id="change">-</strong></div>
    <div class="muted"><span id="updatedLabel">Laatst geüpdatet:</span> <span id="updated">-</span></div>
    <div class="status-wrap"><span id="statusDot" class="dot live"></span><span id="statusText" class="muted">Live</span></div>
    <!-- debug label verwijderd -->

    <div style="margin-top:.9rem; display:flex; justify-content:center; align-items:end;">
      <div>
        <label class="muted" id="rangeLabel">Periode:</label><br>
        <select id="range" class="coin-select" onchange="onRangeChange()"><option value="1" id="range1">24 uur</option><option value="7" id="range7">Week</option><option value="30" id="range30">Maand</option></select>
      </div>
    </div>

    <canvas id="lineChart" height="120"></canvas>
    <div style="margin-top:.9rem; display:flex; justify-content:center; align-items:end;">
      <div>
        <label class="muted" id="candleRangeLabel">Range:</label><br>
        <select id="candleRange" class="coin-select" onchange="onCandleRangeChange()">
          <option value="1h" id="candleRange1h">1 uur</option>
          <option value="4h" id="candleRange4h">4 uur</option>
        </select>
      </div>
    </div>
    <div id="candleChart"></div>
    <div id="candleVolumeChart" style="margin-top:.35rem;"></div>

    <div class="controls">
      <button class="btn" id="refreshBtn" onclick="refreshNow()">Nu verversen</button>
      <span class="muted" id="autoText">Auto-refresh: prijs elke 30s, grafiek elke 2 min</span>
      <button class="btn theme-btn" id="themeBtn" onclick="toggleTheme()">🌙 Dark</button>
    </div>
    <div class="muted" id="volumeHint" style="margin-top:.8rem; font-size:.88rem; text-align:center;">© Marcel</div>
  </div>

<script>
let lineChart, candleChart, candleVolumeChart;
let currentCoin='bitcoin', currentRange='1', currentCurrency='eur', currentLang='en', currentCandleRange='4h';
let top20Data = [];

const I18N = {
  nl: { coin:'Munt:', range:'Periode:', currency:'Grafiek valuta:', lang:'Taal:', type:'Grafiek type:', line:'Lijn', candle:'Candlestick', r4:'4 uur', r1h:'1 uur', r1:'24 uur', r7:'Week', r30:'Maand', title:'prijs (live)', ch:'24u verandering:', up:'Laatst geüpdatet:', ref:'Nu verversen', auto:'Auto-refresh: prijs elke 2,5 min, grafiek elke 5 min', live:'Live', fallback:'Fallback', dark:'🌙 Dark', light:'☀️ Light', c4h:'4 uur candles', cRange:'Range:', cTime:'Tijd:', local:'Lokale tijd', utc:'UTC', top20:'Top 50:' },
  en: { coin:'Coin:', range:'Range:', currency:'Chart currency:', lang:'Language:', type:'Chart type:', line:'Line', candle:'Candlestick', r4:'4 hours', r1h:'1 hour', r1:'24 hours', r7:'Week', r30:'Month', title:'price (live)', ch:'24h change:', up:'Last updated:', ref:'Refresh now', auto:'Auto refresh: price every 2.5 min, chart every 5 min', live:'Live', fallback:'Fallback', dark:'🌙 Dark', light:'☀️ Light', c4h:'4h candles', cRange:'Range:', cTime:'Time:', local:'Local time', utc:'UTC', top20:'Top 50:' }
};

const t = (k)=> (I18N[currentLang]||I18N.en)[k] || k;

function applyLang() {
  document.documentElement.lang = currentLang;
  document.getElementById('coinLabel').textContent=t('coin');
  document.getElementById('rangeLabel').textContent=t('range');
  document.getElementById('currencyLabel').textContent=t('currency');
  // chart type verwijderd
  // 4h range verwijderd
  document.getElementById('range1').textContent=t('r1');
  document.getElementById('range7').textContent=t('r7');
  document.getElementById('range30').textContent=t('r30');
  document.getElementById('changeLabel').textContent=t('ch');
  document.getElementById('updatedLabel').textContent=t('up');
  document.getElementById('refreshBtn').textContent=t('ref');
  document.getElementById('autoText').textContent=t('auto');
  // candle titel verwijderd
  document.getElementById('candleRangeLabel').textContent=t('cRange');
  document.getElementById('candleRange1h').textContent=t('r1h');
  document.getElementById('candleRange4h').textContent=t('r4');
  document.getElementById('top20Label').textContent=t('top20');
  renderTop20();
  applyTheme(localStorage.getItem('theme')||'dark');
}

function applyTheme(mode){
  document.body.classList.toggle('light', mode==='light');
  document.getElementById('themeBtn').textContent = mode==='light' ? t('light') : t('dark');
}
function toggleTheme(){ const n=(localStorage.getItem('theme')||'dark')==='dark'?'light':'dark'; localStorage.setItem('theme',n); applyTheme(n); loadChart(); }

function formatPrice(v){
  const n=Number(v||0);
  let d=2; if(n!==0 && Math.abs(n)<1)d=6; if(n!==0 && Math.abs(n)<0.01)d=8;
  return new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:d}).format(n);
}

function formatCompact(v){
  const n = Number(v||0);
  const abs = Math.abs(n);
  if (abs >= 1e12) return `${(n/1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(n/1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(n/1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(n/1e3).toFixed(2)}K`;
  return n.toFixed(2);
}

// RSI helper removed (not used)
function displayName(coin){
  const n={bitcoin:'Bitcoin (BTC)',ethereum:'Ethereum (ETH)',solana:'Solana (SOL)',presearch:'Presearch (PRE)',flux:'Flux (FLUX)'};
  return n[coin]||coin;
}

function renderTop20(){
  const row = document.getElementById('top20Row');
  const symbol = currentCurrency==='usd' ? '$' : '€';
  const label = row.querySelector('#top20Label');
  if (label) label.textContent = t('top20');
  const scroll = row.querySelector('.top20-scroll');
  if(!scroll) return;
  if(!top20Data.length){
    scroll.innerHTML = `<div class="top20-track">...</div>`;
    return;
  }
  const line = top20Data.map(c =>
    `<span class="top20-item"><span class="top20-symbol">${(c.symbol||'').toUpperCase()}</span>${symbol} ${formatPrice(c.current_price)}</span>`
  ).join('');
  scroll.innerHTML = `<div class="top20-track">${line}${line}</div>`;
}

async function loadTop20(){
  try {
    const r = await fetch(`https://api.coingecko.com/api/v3/coins/markets?vs_currency=${currentCurrency}&order=market_cap_desc&per_page=100&page=1&sparkline=false`);
    const d = await r.json();
    if(Array.isArray(d)) {
      const stableSymbols = new Set(['usdt','usdc','dai','fdusd','tusd','usde','usds','usdd','pyusd','gusd','eurs','usdp','rlusd']);
      const stableIds = new Set(['tether','usd-coin','dai','first-digital-usd','true-usd','ethena-usde','usds','usdd','paypal-usd','gemini-dollar','stasis-eurs','pax-dollar','rlusd']);
      top20Data = d.filter(c => !stableSymbols.has((c.symbol||'').toLowerCase()) && !stableIds.has((c.id||'').toLowerCase())).slice(0,50);
    }
    renderTop20();
  } catch(_) {
    renderTop20();
  }
}

async function loadPrice(){
  const r=await fetch(`/api/price?coin=${currentCoin}`); const d=await r.json(); if(d.error) throw new Error(d.error);
  const usd=currentCurrency==='usd';
  const a=usd?d.usd:d.eur;
  const sa=usd?'$':'€';
  document.getElementById('title').textContent = `${displayName(currentCoin)} ${t('title')}`;
  document.getElementById('price').textContent = `${sa} ${formatPrice(a)}`;
  document.getElementById('change').textContent = `${Number(d.change_24h||0).toFixed(2)}%`;
  document.getElementById('change').className = Number(d.change_24h||0)>=0 ? 'good' : 'bad';
  document.getElementById('updated').textContent = d.updated;
  document.getElementById('statusDot').className = `dot ${d.stale?'fallback':'live'}`;
  document.getElementById('statusText').textContent = d.stale ? t('fallback') : t('live');
}

async function loadChart(){
  if(lineChart){lineChart.destroy(); lineChart=null;}
  if(candleChart){candleChart.destroy(); candleChart=null;}
  if(candleVolumeChart){candleVolumeChart.destroy(); candleVolumeChart=null;}

  const lineCanvas=document.getElementById('lineChart');
  const candleDiv=document.getElementById('candleChart');
  const candleVolumeDiv=document.getElementById('candleVolumeChart');
  const styles=getComputedStyle(document.body);
  const muted=styles.getPropertyValue('--muted').trim();
  const line=styles.getPropertyValue('--line').trim();
  const fill=styles.getPropertyValue('--line-fill').trim();
  const lineSymbol=currentCurrency==='usd'?'$':'€';
  const candleSymbol=currentCurrency==='usd'?'$':'€';

  const r=await fetch(`/api/history?coin=${currentCoin}&days=${currentRange}&currency=${currentCurrency}`); const d=await r.json(); if(d.error) throw new Error(d.error);
  const labels=(d.points||[]).map(p=>p.time), values=(d.points||[]).map(p=>p.price);
  lineChart = new Chart(lineCanvas, {
    type:'line',
    data:{ labels, datasets:[{ label:`${displayName(currentCoin)} / ${currentCurrency.toUpperCase()}`, data:values, borderColor:line, backgroundColor:fill, fill:true, tension:.25, pointRadius:0 }]},
    options:{ responsive:true, maintainAspectRatio:true, scales:{ x:{ ticks:{ color:muted, maxTicksLimit:8 } }, y:{ ticks:{ color:muted, callback:(v)=>`${lineSymbol} ${formatPrice(v)}` } } }, plugins:{ legend:{ labels:{ color:muted } } } }
  });

  const ohlcDays = currentCandleRange==='1h' ? '1' : '4h';
  let d2;
  let convertUsdToEur = 1;

  // Probeer eerst geselecteerde currency; fallback naar USD zodat candle chart altijd zichtbaar blijft.
  let r2=await fetch(`/api/ohlc?coin=${currentCoin}&days=${ohlcDays}&currency=${currentCurrency}`);
  d2=await r2.json();
  if(d2.error){
    r2=await fetch(`/api/ohlc?coin=${currentCoin}&days=${ohlcDays}&currency=usd`);
    d2=await r2.json();
    if(d2.error) throw new Error(d2.error);
    if(currentCurrency==='eur'){
      try {
        const rp=await fetch(`/api/price?coin=${currentCoin}`);
        const dp=await rp.json();
        const usd=Number(dp.usd), eur=Number(dp.eur);
        if(Number.isFinite(usd) && usd>0 && Number.isFinite(eur) && eur>0){
          convertUsdToEur = eur / usd;
        }
      } catch(_) {}
    }
  }

  const bucketMs = currentCandleRange==='1h' ? (1 * 3600 * 1000) : (4 * 3600 * 1000);
  const candleLimit = currentCandleRange==='1h' ? 24 : 18;

  const byBucket = new Map();
  for (const p of (d2.points||[])) {
    const ts = Math.floor(Number(p.ts) / bucketMs) * bucketMs;
    const o = Number(p.open) * convertUsdToEur;
    const h = Number(p.high) * convertUsdToEur;
    const l = Number(p.low) * convertUsdToEur;
    const cClose = Number(p.close) * convertUsdToEur;
    if (!byBucket.has(ts)) {
      byBucket.set(ts, { x: ts, y:[o, h, l, cClose] });
    } else {
      const c = byBucket.get(ts);
      c.y[1] = Math.max(Number(c.y[1]), h);
      c.y[2] = Math.min(Number(c.y[2]), l);
      c.y[3] = cClose;
    }
  }

  let candles = Array.from(byBucket.values()).sort((a,b)=>a.x-b.x);
  const nowBucket = Math.floor(Date.now() / bucketMs) * bucketMs;

  // Voeg live candle toe (of update lopende candle) zodat de laatste candle altijd zichtbaar is.
  try {
    const rp=await fetch(`/api/price?coin=${currentCoin}`);
    const dp=await rp.json();
    const live = Number(currentCurrency==='usd' ? dp.usd : dp.eur);
    if (Number.isFinite(live) && live > 0 && candles.length > 0) {
      const last = candles[candles.length - 1];
      if (last.x === nowBucket) {
        last.y[1] = Math.max(Number(last.y[1]), live);
        last.y[2] = Math.min(Number(last.y[2]), live);
        last.y[3] = live;
      } else {
        const open = Number(last.y[3]);
        candles.push({ x: nowBucket, y:[open, Math.max(open, live), Math.min(open, live), live] });
      }
    }
  } catch (_) {}

  const cutoff = nowBucket - ((candleLimit - 1) * bucketMs);
  candles = candles.filter(c => c.x >= cutoff);
  const visibleCandles = candles.slice(-candleLimit);
  const xCats = visibleCandles.map((c)=>{
    const dt = new Date(c.x);
    const dd = String(dt.getUTCDate()).padStart(2,'0');
    const hh = String(dt.getUTCHours()).padStart(2,'0');
    return currentCandleRange==='1h' ? `${hh}:00` : `${dd} ${hh}:00`;
  });

  const series = visibleCandles.map((c, i)=>({ x: xCats[i], y: c.y }));

  candleChart = new ApexCharts(candleDiv, {
    chart:{ type:'candlestick', height:320, toolbar:{show:false}, zoom:{enabled:false}, animations:{enabled:false}, background:'transparent' },
    series:[{ name:`${displayName(currentCoin)} ${currentCurrency.toUpperCase()} ${currentCandleRange}`, data: series }],
    xaxis:{ type:'category', tickPlacement:'on', labels:{ style:{ colors: muted }, rotate:0, hideOverlappingLabels:false } },
    yaxis:{ labels:{ minWidth: 72, style:{ colors: muted }, formatter:(v)=>`${candleSymbol} ${formatPrice(v)}` } },
    theme:{ mode: document.body.classList.contains('light') ? 'light':'dark' }
  });
  candleChart.render();

  // Volume per candle (zelfde buckets als candlesticks)
  let volVals = [];
  const volCats = xCats;

  try {
    const rv = await fetch(`/api/volume?coin=${currentCoin}&range=${currentCandleRange}&currency=${currentCurrency}`);
    const dv = await rv.json();
    const vMap = new Map((dv.points||[]).map(p => [Number(p.ts), Number(p.volume)]));
    volVals = visibleCandles.map(c => (vMap.get(Number(c.x)) || 0));
  } catch (e) {
    // Fallback: benader volume met candle range, zodat chart niet leeg is.
    volVals = visibleCandles.map(c => Math.abs(Number(c.y[1]) - Number(c.y[2])));
  }

  candleVolumeChart = new ApexCharts(candleVolumeDiv, {
    chart:{ type:'bar', height:160, toolbar:{show:false}, zoom:{enabled:false}, animations:{enabled:false}, background:'transparent' },
    dataLabels:{ enabled:false },
    series:[{ name:'Volume', data: volVals }],
    xaxis:{ categories: volCats, labels:{ style:{ colors: muted }, rotate:0, hideOverlappingLabels:false } },
    yaxis:{ labels:{ minWidth: 72, style:{ colors: muted }, formatter:(v)=> formatCompact(v) } },
    plotOptions:{ bar:{ columnWidth:'70%' } },
    colors:['#94a3b8'],
    legend:{ show:false },
    theme:{ mode: document.body.classList.contains('light') ? 'light':'dark' }
  });
  candleVolumeChart.render();
}

async function refreshNow(){ try{ await Promise.all([loadPrice(),loadChart(),loadTop20()]); }catch(e){ console.error(e); } }
async function onCoinChange(){ currentCoin=document.getElementById('coin').value; await refreshNow(); }
async function onRangeChange(){ currentRange=document.getElementById('range').value; await loadChart(); }
async function onCurrencyChange(){ currentCurrency=document.getElementById('currency').value; localStorage.setItem('chartCurrency',currentCurrency); await refreshNow(); }
async function onCandleRangeChange(){ currentCandleRange=document.getElementById('candleRange').value; localStorage.setItem('candleRange',currentCandleRange); await loadChart(); }

currentCurrency=localStorage.getItem('chartCurrency')||'eur';
currentCandleRange=localStorage.getItem('candleRange')||'1h';
document.getElementById('currency').value=currentCurrency;
document.getElementById('candleRange').value=currentCandleRange;
applyLang();
refreshNow();
setInterval(loadPrice,150000);
setInterval(loadChart,300000);
setInterval(loadTop20,300000);
</script>
</body>
</html>
"""


def validate_coin(coin: str) -> str:
    return coin if coin in COINS else "bitcoin"


def normalize_range(days):
    r = str(days).lower()
    if r == "4h":
        return "4h", 1
    if r == "7":
        return "7", 7
    if r == "30":
        return "30", 30
    return "1", 1


def fetch_price_from_cryptocompare(coin: str):
    symbol = COINS[coin]["symbol"]
    u = f"https://min-api.cryptocompare.com/data/price?fsym={symbol}&tsyms=EUR,USD"
    rr = requests.get(u, timeout=8)
    rr.raise_for_status()
    d = rr.json()
    if "EUR" not in d or "USD" not in d:
        raise ValueError("No EUR/USD")
    return float(d["EUR"]), float(d["USD"])


def fetch_price_from_coinbase(coin: str):
    symbol = COINS[coin]["symbol"]

    def spot(pair):
        rr = requests.get(f"https://api.coinbase.com/v2/prices/{pair}/spot", timeout=8)
        rr.raise_for_status()
        return float(rr.json()["data"]["amount"])

    return spot(f"{symbol}-EUR"), spot(f"{symbol}-USD")


def fetch_price(coin: str):
    coin = validate_coin(coin)
    now = time.time()

    if coin in price_cache and (now - price_cache[coin]["ts"]) < CACHE_TTL_PRICE:
        cached = dict(price_cache[coin]["data"])
        cached["stale"] = False
        return cached

    gecko_id = COINS[coin]["gecko_id"]
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={gecko_id}&vs_currencies=eur,usd&include_24hr_change=true"

    try:
        rr = requests.get(url, timeout=10)
        rr.raise_for_status()
        data = rr.json()[gecko_id]
        out = {
            "coin": coin,
            "symbol": COINS[coin]["symbol"],
            "name": COINS[coin]["name"],
            "eur": data["eur"],
            "usd": data["usd"],
            "change_24h": data.get("eur_24h_change", 0),
            "updated": datetime.now(timezone.utc).astimezone().strftime("%d-%m-%Y %H:%M:%S"),
            "stale": False,
        }
        price_cache[coin] = {"ts": now, "data": out}
        return out
    except requests.HTTPError:
        if coin in price_cache:
            c = dict(price_cache[coin]["data"])
            c["stale"] = True
            return c
        for fallback in (fetch_price_from_cryptocompare, fetch_price_from_coinbase):
            try:
                eur, usd = fallback(coin)
                return {
                    "coin": coin, "symbol": COINS[coin]["symbol"], "name": COINS[coin]["name"],
                    "eur": eur, "usd": usd, "change_24h": 0,
                    "updated": datetime.now(timezone.utc).astimezone().strftime("%d-%m-%Y %H:%M:%S"),
                    "stale": True,
                }
            except Exception:
                pass
        return {
            "coin": coin, "symbol": COINS[coin]["symbol"], "name": COINS[coin]["name"],
            "eur": 0, "usd": 0, "change_24h": 0,
            "updated": datetime.now(timezone.utc).astimezone().strftime("%d-%m-%Y %H:%M:%S"),
            "stale": True,
        }


def aggregate_4h(rows):
    if not rows:
        return []
    bucket_ms = 4 * 3600 * 1000
    out, cur = [], None
    for ts, o, h, l, c in rows:
        b = (int(ts) // bucket_ms) * bucket_ms
        if cur is None or cur[0] != b:
            if cur is not None:
                out.append(cur)
            cur = [b, float(o), float(h), float(l), float(c)]
        else:
            cur[2] = max(cur[2], float(h))
            cur[3] = min(cur[3], float(l))
            cur[4] = float(c)
    if cur is not None:
        out.append(cur)
    return out


def fetch_history(coin: str, days="1", currency: str = "eur"):
    coin = validate_coin(coin)
    range_key, gecko_days = normalize_range(days)
    currency = "usd" if str(currency).lower() == "usd" else "eur"
    cache_key = f"{coin}:{range_key}:{currency}"

    if cache_key in history_cache and (time.time() - history_cache[cache_key]["ts"]) < CACHE_TTL_HISTORY:
        return history_cache[cache_key]["points"]

    gecko_id = COINS[coin]["gecko_id"]
    rr = requests.get(f"https://api.coingecko.com/api/v3/coins/{gecko_id}/market_chart?vs_currency={currency}&days={gecko_days}", timeout=15)
    rr.raise_for_status()
    prices = rr.json().get("prices", [])

    if range_key == "4h":
        cutoff = int((time.time() - 3 * 24 * 3600) * 1000)
        prices = [p for p in prices if p[0] >= cutoff]

    target = 24 if range_key in ("1", "4h") else (42 if range_key == "7" else 60)
    if len(prices) > target:
        step = max(1, len(prices) // target)
        prices = prices[::step]

    points = []
    for ts, price in prices:
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).astimezone()
        if range_key == "1":
            lbl = d.strftime("%H:%M")
        elif range_key == "4h":
            lbl = d.strftime("%d-%m %H:%M")
        elif range_key == "7":
            lbl = d.strftime("%d-%m %H:%M")
        else:
            lbl = d.strftime("%d-%m")
        points.append({"time": lbl, "price": float(price)})

    history_cache[cache_key] = {"ts": time.time(), "points": points}
    return points


def fetch_ohlc(coin: str, days="1", currency: str = "eur"):
    coin = validate_coin(coin)
    range_key, gecko_days = normalize_range(days)
    currency = "usd" if str(currency).lower() == "usd" else "eur"
    cache_key = f"{coin}:{range_key}:{currency}"

    if cache_key in ohlc_cache and (time.time() - ohlc_cache[cache_key]["ts"]) < CACHE_TTL_HISTORY:
        return ohlc_cache[cache_key]["points"]

    gecko_id = COINS[coin]["gecko_id"]
    # CoinGecko OHLC ondersteunt geen 3 dagen; haal 7 dagen op en neem laatste 18 candles.
    ohlc_days = 7 if range_key == "4h" else gecko_days
    rr = requests.get(f"https://api.coingecko.com/api/v3/coins/{gecko_id}/ohlc?vs_currency={currency}&days={ohlc_days}", timeout=15)
    rr.raise_for_status()
    rows = rr.json()

    if range_key == "4h":
        rows = aggregate_4h(rows)
        rows = rows[-18:]  # exact 3 dagen * 6 candles

    points = [{"ts": int(ts), "open": float(o), "high": float(h), "low": float(l), "close": float(c)} for ts, o, h, l, c in rows]
    ohlc_cache[cache_key] = {"ts": time.time(), "points": points}
    return points


def fetch_volume(coin: str, range_key="4h", currency: str = "eur"):
    coin = validate_coin(coin)
    rk = "1h" if str(range_key).lower() == "1h" else "4h"
    currency = "usd" if str(currency).lower() == "usd" else "eur"
    cache_key = f"{coin}:{rk}:{currency}"

    if cache_key in volume_cache and (time.time() - volume_cache[cache_key]["ts"]) < CACHE_TTL_HISTORY:
        return volume_cache[cache_key]["points"]

    gecko_id = COINS[coin]["gecko_id"]
    days = 2 if rk == "1h" else 7
    bucket_ms = 3600 * 1000 if rk == "1h" else 4 * 3600 * 1000
    limit = 24 if rk == "1h" else 18

    rr = requests.get(f"https://api.coingecko.com/api/v3/coins/{gecko_id}/market_chart?vs_currency={currency}&days={days}", timeout=15)
    rr.raise_for_status()
    rows = rr.json().get("total_volumes", [])

    buckets = {}
    for ts, vol in rows:
        b = (int(ts) // bucket_ms) * bucket_ms
        buckets[b] = buckets.get(b, 0.0) + float(vol)

    points = [{"ts": int(ts), "volume": float(v)} for ts, v in sorted(buckets.items())][-limit:]
    volume_cache[cache_key] = {"ts": time.time(), "points": points}
    return points


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/price")
def api_price():
    try:
        return jsonify(fetch_price(request.args.get("coin", "bitcoin")))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history")
def api_history():
    try:
        coin = request.args.get("coin", "bitcoin")
        days = request.args.get("days", "1")
        currency = request.args.get("currency", "eur")
        return jsonify({"coin": coin, "days": days, "currency": currency, "points": fetch_history(coin, days, currency)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ohlc")
def api_ohlc():
    try:
        coin = request.args.get("coin", "bitcoin")
        days = request.args.get("days", "1")
        currency = request.args.get("currency", "eur")
        return jsonify({"coin": coin, "days": days, "currency": currency, "points": fetch_ohlc(coin, days, currency)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/volume")
def api_volume():
    try:
        coin = request.args.get("coin", "bitcoin")
        range_key = request.args.get("range", "4h")
        currency = request.args.get("currency", "eur")
        return jsonify({"coin": coin, "range": range_key, "currency": currency, "points": fetch_volume(coin, range_key, currency)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
