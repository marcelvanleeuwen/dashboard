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
    # runonflux.com project: op CoinGecko is dit id 'zelcash' (naam: Flux)
    "flux": {"symbol": "FLUX", "name": "Flux", "gecko_id": "zelcash"},
}

# Simpele cache om API rate-limits op te vangen
CACHE_TTL_PRICE = 20   # seconden
CACHE_TTL_HISTORY = 300  # 5 min
price_cache = {}
history_cache = {}  # key: f"{coin}:{days}:{currency}"

HTML = """
<!doctype html>
<html lang="nl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Crypto Prijs Checker v3</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg: #0f172a;
      --text: #e2e8f0;
      --card: #111827;
      --muted: #94a3b8;
      --chart-bg: #0b1220;
      --border: #334155;
      --btn: #2563eb;
      --line: #38bdf8;
      --line-fill: rgba(56,189,248,.15);
      --shadow: rgba(0,0,0,.3);
    }

    body.light {
      --bg: #f1f5f9;
      --text: #0f172a;
      --card: #ffffff;
      --muted: #475569;
      --chart-bg: #f8fafc;
      --border: #cbd5e1;
      --btn: #1d4ed8;
      --line: #0284c7;
      --line-fill: rgba(2,132,199,.12);
      --shadow: rgba(15,23,42,.08);
    }

    body {
      font-family: system-ui, Arial, sans-serif;
      margin: 2rem;
      background: var(--bg);
      color: var(--text);
      transition: background .2s ease, color .2s ease;
    }
    .card {
      max-width: 1280px;
      width: min(96vw, 1280px);
      padding: 1.5rem;
      border-radius: 16px;
      background: var(--card);
      box-shadow: 0 10px 25px var(--shadow);
      transition: background .2s ease;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1rem;
      flex-wrap: wrap;
    }
    .top-right {
      display: flex;
      align-items: center;
      gap: .75rem;
      margin-left: auto;
      flex-wrap: wrap;
      justify-content: flex-end;
      min-width: 620px;
    }
    .label { color: var(--muted); font-size: .95rem; }
    .price { font-size: 2.1rem; font-weight: 700; margin: .4rem 0 .5rem; }
    .row { margin: .35rem 0; }
    .muted { color: var(--muted); font-size: .9rem; }
    .good { color: #22c55e; font-weight: 700; }
    .bad { color: #ef4444; font-weight: 700; }
    .warn { color: #f59e0b; font-size: .9rem; }
    .status-wrap { display: flex; align-items: center; gap: .5rem; margin-top: .25rem; }
    .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    .dot.live { background: #22c55e; box-shadow: 0 0 0 3px rgba(34,197,94,.2); }
    .dot.fallback { background: #f59e0b; box-shadow: 0 0 0 3px rgba(245,158,11,.2); }
    .controls { margin-top: 1rem; display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; }
    .btn {
      display: inline-block;
      padding: .55rem .9rem;
      border-radius: 10px;
      background: var(--btn);
      color: white;
      text-decoration: none;
      border: none;
      cursor: pointer;
    }
    .btn.theme-btn { padding: .45rem .75rem; margin-left: auto; }
    .coin-select {
      background: var(--chart-bg);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: .5rem .65rem;
      min-width: 120px;
    }
    canvas { margin-top: 1rem; background: var(--chart-bg); border-radius: 12px; padding: .5rem; }
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div>
        <div class="label" id="title">Crypto prijs (live)</div>
        <div class="price" id="price">Laden...</div>
      </div>
      <div class="top-right">
        <div>
          <label class="muted" for="coin" id="coinLabel">Munt:&nbsp;</label>
          <select id="coin" class="coin-select" onchange="onCoinChange()">
            <option value="bitcoin">Bitcoin (BTC)</option>
            <option value="ethereum">Ethereum (ETH)</option>
            <option value="solana">Solana (SOL)</option>
            <option value="presearch">Presearch (PRE)</option>
            <option value="flux">Flux (FLUX)</option>
          </select>
        </div>
        <div>
          <label class="muted" for="range" id="rangeLabel">Periode:&nbsp;</label>
          <select id="range" class="coin-select" onchange="onRangeChange()">
            <option value="1" id="rangeOpt1">24 uur</option>
            <option value="7" id="rangeOpt7">Week</option>
            <option value="30" id="rangeOpt30">Maand</option>
          </select>
        </div>
        <div>
          <label class="muted" for="lang" id="langLabel">Taal:&nbsp;</label>
          <select id="lang" class="coin-select" onchange="onLangChange()">
            <option value="nl">Nederlands</option>
            <option value="en">English</option>
          </select>
        </div>
        <div>
          <label class="muted" for="currency" id="currencyLabel">Grafiek valuta:&nbsp;</label>
          <select id="currency" class="coin-select" onchange="onCurrencyChange()">
            <option value="eur">EUR (€)</option>
            <option value="usd">USD ($)</option>
          </select>
        </div>
      </div>
    </div>

    <div class="row"><span id="changeLabel">24u verandering:</span> <strong id="change">-</strong></div>
    <div class="row muted"><span id="updatedLabel">Laatst geüpdatet:</span> <span id="updated">-</span></div>
    <div class="status-wrap">
      <span id="statusDot" class="dot live"></span>
      <span id="statusText" class="muted">Live</span>
    </div>
    <div class="warn" id="status"></div>

    <canvas id="coinChart" height="120"></canvas>

    <div class="controls">
      <button class="btn" onclick="refreshNow()" id="refreshBtn">Nu verversen</button>
      <span class="muted" id="autoRefreshText">Auto-refresh: prijs elke 30s, grafiek elke 2 min</span>
      <button class="btn theme-btn" onclick="toggleTheme()" id="themeBtn">🌙 Dark</button>
    </div>
  </div>

  <script>
    let chart;
    let currentCoin = 'bitcoin';
    let currentRange = '1';
    let currentLang = 'nl';
    let currentCurrency = 'eur';

    const I18N = {
      nl: {
        coinLabel: 'Munt:',
        rangeLabel: 'Periode:',
        langLabel: 'Taal:',
        currencyLabel: 'Grafiek valuta:',
        range1: '24 uur',
        range7: 'Week',
        range30: 'Maand',
        titleSuffix: 'prijs (live)',
        changeLabel: '24u verandering:',
        updatedLabel: 'Laatst geüpdatet:',
        live: 'Live',
        fallback: 'Fallback',
        fallbackWarn: '⚠ API rate-limit, toon laatst bekende data',
        refreshBtn: 'Nu verversen',
        autoRefresh: 'Auto-refresh: prijs elke 30s, grafiek elke 2 min',
        chart24: '24u',
        chart7: '7d',
        chart30: '30d',
        dark: '🌙 Dark',
        light: '☀️ Light'
      },
      en: {
        coinLabel: 'Coin:',
        rangeLabel: 'Range:',
        langLabel: 'Language:',
        currencyLabel: 'Chart currency:',
        range1: '24 hours',
        range7: 'Week',
        range30: 'Month',
        titleSuffix: 'price (live)',
        changeLabel: '24h change:',
        updatedLabel: 'Last updated:',
        live: 'Live',
        fallback: 'Fallback',
        fallbackWarn: '⚠ API rate limit, showing last known data',
        refreshBtn: 'Refresh now',
        autoRefresh: 'Auto refresh: price every 30s, chart every 2 min',
        chart24: '24h',
        chart7: '7d',
        chart30: '30d',
        dark: '🌙 Dark',
        light: '☀️ Light'
      }
    };

    function getTheme() {
      return localStorage.getItem('theme') || 'dark';
    }

    function getLang() {
      return localStorage.getItem('lang') || 'nl';
    }

    function t(key) {
      return (I18N[currentLang] && I18N[currentLang][key]) || I18N.nl[key] || key;
    }

    function applyLang(lang) {
      currentLang = (lang === 'en') ? 'en' : 'nl';
      document.getElementById('lang').value = currentLang;
      document.documentElement.lang = currentLang;

      document.getElementById('coinLabel').textContent = t('coinLabel') + ' ';
      document.getElementById('rangeLabel').textContent = t('rangeLabel') + ' ';
      document.getElementById('langLabel').textContent = t('langLabel') + ' ';
      document.getElementById('currencyLabel').textContent = t('currencyLabel') + ' ';
      document.getElementById('rangeOpt1').textContent = t('range1');
      document.getElementById('rangeOpt7').textContent = t('range7');
      document.getElementById('rangeOpt30').textContent = t('range30');
      document.getElementById('changeLabel').textContent = t('changeLabel');
      document.getElementById('updatedLabel').textContent = t('updatedLabel');
      document.getElementById('refreshBtn').textContent = t('refreshBtn');
      document.getElementById('autoRefreshText').textContent = t('autoRefresh');

      applyTheme(getTheme());
    }

    function applyTheme(theme) {
      const isLight = theme === 'light';
      document.body.classList.toggle('light', isLight);
      const btn = document.getElementById('themeBtn');
      btn.textContent = isLight ? t('light') : t('dark');
    }

    function toggleTheme() {
      const next = getTheme() === 'dark' ? 'light' : 'dark';
      localStorage.setItem('theme', next);
      applyTheme(next);
      if (chart) loadChart();
    }

    function formatPrice(v) {
      const n = Number(v || 0);
      let digits = 2;
      if (n !== 0 && Math.abs(n) < 1) digits = 6;
      if (n !== 0 && Math.abs(n) < 0.01) digits = 8;
      return new Intl.NumberFormat('nl-NL', {
        minimumFractionDigits: 2,
        maximumFractionDigits: digits
      }).format(n);
    }

    function setChange(change) {
      const el = document.getElementById('change');
      const val = Number(change);
      el.textContent = `${val.toFixed(2)}%`;
      el.className = val >= 0 ? 'good' : 'bad';
    }

    function displayName(coin) {
      const names = {
        bitcoin: 'Bitcoin (BTC)',
        ethereum: 'Ethereum (ETH)',
        solana: 'Solana (SOL)',
        presearch: 'Presearch (PRE)',
        flux: 'Flux (FLUX)'
      };
      return names[coin] || coin;
    }

    async function loadPrice() {
      const res = await fetch(`/api/price?coin=${currentCoin}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);

      document.getElementById('title').textContent = `${displayName(currentCoin)} ${t('titleSuffix')}`;

      const primaryIsUsd = currentCurrency === 'usd';
      const primarySymbol = primaryIsUsd ? '$' : '€';
      const secondarySymbol = primaryIsUsd ? '€' : '$';
      const primaryValue = primaryIsUsd ? data.usd : data.eur;
      const secondaryValue = primaryIsUsd ? data.eur : data.usd;

      document.getElementById('price').innerHTML = `${primarySymbol} ${formatPrice(primaryValue)} <span class="muted">/ ${secondarySymbol} ${formatPrice(secondaryValue)}</span>`;
      setChange(data.change_24h);
      document.getElementById('updated').textContent = data.updated;

      const dot = document.getElementById('statusDot');
      const txt = document.getElementById('statusText');
      if (data.stale) {
        dot.className = 'dot fallback';
        txt.textContent = t('fallback');
        document.getElementById('status').textContent = t('fallbackWarn');
      } else {
        dot.className = 'dot live';
        txt.textContent = t('live');
        document.getElementById('status').textContent = '';
      }
    }

    async function loadChart() {
      const res = await fetch(`/api/history?coin=${currentCoin}&days=${currentRange}&currency=${currentCurrency}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);

      const labels = data.points.map(p => p.time);
      const values = data.points.map(p => p.price);
      const symbol = currentCurrency === 'usd' ? '$' : '€';
      const currencyCode = currentCurrency.toUpperCase();

      if (chart) chart.destroy();

      const styles = getComputedStyle(document.body);
      const line = styles.getPropertyValue('--line').trim();
      const fill = styles.getPropertyValue('--line-fill').trim();
      const muted = styles.getPropertyValue('--muted').trim();

      chart = new Chart(document.getElementById('coinChart'), {
        type: 'line',
        data: {
          labels,
          datasets: [{
            label: `${displayName(currentCoin)} / ${currencyCode} (${currentRange === '30' ? t('chart30') : (currentRange === '7' ? t('chart7') : t('chart24'))})`,
            data: values,
            borderColor: line,
            backgroundColor: fill,
            fill: true,
            tension: 0.25,
            pointRadius: 0
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          scales: {
            x: { ticks: { color: muted, maxTicksLimit: 8 } },
            y: {
              ticks: {
                color: muted,
                callback: (value) => `${symbol} ${formatPrice(value)}`
              }
            }
          },
          plugins: {
            legend: { labels: { color: muted } },
            tooltip: {
              callbacks: {
                label: (ctx) => `${displayName(currentCoin)}: ${symbol} ${formatPrice(ctx.parsed.y)}`
              }
            }
          }
        }
      });
    }

    async function refreshNow() {
      try {
        await Promise.all([loadPrice(), loadChart()]);
      } catch (e) {
        console.error(e);
      }
    }

    async function onCoinChange() {
      currentCoin = document.getElementById('coin').value;
      await refreshNow();
    }

    async function onRangeChange() {
      currentRange = document.getElementById('range').value;
      await loadChart();
    }

    async function onCurrencyChange() {
      currentCurrency = document.getElementById('currency').value;
      localStorage.setItem('chartCurrency', currentCurrency);
      await Promise.all([loadPrice(), loadChart()]);
    }

    async function onLangChange() {
      const lang = document.getElementById('lang').value;
      localStorage.setItem('lang', lang);
      applyLang(lang);
      await refreshNow();
    }

    applyLang(getLang());
    currentCurrency = localStorage.getItem('chartCurrency') || 'eur';
    document.getElementById('currency').value = currentCurrency;
    refreshNow();
    setInterval(loadPrice, 30000);
    setInterval(loadChart, 120000);
  </script>
</body>
</html>
"""


def validate_coin(coin: str) -> str:
    return coin if coin in COINS else "bitcoin"


def fetch_price_from_coinbase(coin: str):
    symbol = COINS[coin]["symbol"]

    def _spot(pair: str):
        u = f"https://api.coinbase.com/v2/prices/{pair}/spot"
        rr = requests.get(u, timeout=8)
        rr.raise_for_status()
        return float(rr.json()["data"]["amount"])

    eur = _spot(f"{symbol}-EUR")
    usd = _spot(f"{symbol}-USD")
    return eur, usd


def fetch_price_from_cryptocompare(coin: str):
    symbol = COINS[coin]["symbol"]
    u = f"https://min-api.cryptocompare.com/data/price?fsym={symbol}&tsyms=EUR,USD"
    rr = requests.get(u, timeout=8)
    rr.raise_for_status()
    d = rr.json()
    if "EUR" not in d or "USD" not in d:
        raise ValueError("Cryptocompare gaf geen EUR/USD terug")
    return float(d["EUR"]), float(d["USD"])


def fetch_price(coin: str):
    coin = validate_coin(coin)
    now = time.time()

    # Verse cache gebruiken
    if coin in price_cache and (now - price_cache[coin]["ts"]) < CACHE_TTL_PRICE:
        cached = dict(price_cache[coin]["data"])
        cached["stale"] = False
        return cached

    gecko_id = COINS[coin]["gecko_id"]
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        f"?ids={gecko_id}&vs_currencies=eur,usd&include_24hr_change=true"
    )

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()[gecko_id]
        result = {
            "coin": coin,
            "symbol": COINS[coin]["symbol"],
            "name": COINS[coin]["name"],
            "eur": data["eur"],
            "usd": data["usd"],
            "change_24h": data.get("eur_24h_change", 0),
            "updated": datetime.now(timezone.utc).astimezone().strftime("%d-%m-%Y %H:%M:%S"),
            "stale": False,
        }
        price_cache[coin] = {"ts": now, "data": result}
        return result
    except requests.HTTPError:
        # Bij rate limit: terugvallen op laatst bekende data
        if coin in price_cache:
            cached = dict(price_cache[coin]["data"])
            cached["stale"] = True
            return cached

        # Fallback bron(nen) zodat prijs zichtbaar blijft
        for fallback in (fetch_price_from_cryptocompare, fetch_price_from_coinbase):
            try:
                eur, usd = fallback(coin)
                return {
                    "coin": coin,
                    "symbol": COINS[coin]["symbol"],
                    "name": COINS[coin]["name"],
                    "eur": eur,
                    "usd": usd,
                    "change_24h": 0,
                    "updated": datetime.now(timezone.utc).astimezone().strftime("%d-%m-%Y %H:%M:%S"),
                    "stale": True,
                }
            except Exception:
                pass

        # Laatste fallback
        return {
            "coin": coin,
            "symbol": COINS[coin]["symbol"],
            "name": COINS[coin]["name"],
            "eur": 0,
            "usd": 0,
            "change_24h": 0,
            "updated": datetime.now(timezone.utc).astimezone().strftime("%d-%m-%Y %H:%M:%S"),
            "stale": True,
        }


def fetch_history(coin: str, days: int = 1, currency: str = "eur"):
    coin = validate_coin(coin)
    days = 30 if days == 30 else (7 if days == 7 else 1)
    currency = "usd" if str(currency).lower() == "usd" else "eur"
    now = time.time()
    cache_key = f"{coin}:{days}:{currency}"

    if cache_key in history_cache and (now - history_cache[cache_key]["ts"]) < CACHE_TTL_HISTORY:
        return history_cache[cache_key]["points"]

    gecko_id = COINS[coin]["gecko_id"]
    url = f"https://api.coingecko.com/api/v3/coins/{gecko_id}/market_chart?vs_currency={currency}&days={days}"

    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        prices = r.json().get("prices", [])

        target_points = 24 if days == 1 else (42 if days == 7 else 60)
        if len(prices) > target_points:
            step = max(1, len(prices) // target_points)
            prices = prices[::step]

        points = []
        for ts, price in prices:
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).astimezone()
            if abs(price) < 0.01:
                decimals = 8
            elif abs(price) < 0.1:
                decimals = 7
            elif abs(price) < 1:
                decimals = 6
            else:
                decimals = 2
            if days == 1:
                time_label = dt.strftime("%H:%M")
            elif days == 7:
                time_label = dt.strftime("%d-%m %H:%M")
            else:
                time_label = dt.strftime("%d-%m")
            points.append({"time": time_label, "price": round(price, decimals)})

        history_cache[cache_key] = {"ts": now, "points": points}
        return points
    except requests.HTTPError:
        if cache_key in history_cache:
            return history_cache[cache_key]["points"]
        return []


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/price")
def api_price():
    try:
        coin = validate_coin(request.args.get("coin", "bitcoin"))
        return jsonify(fetch_price(coin))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history")
def api_history():
    try:
        coin = validate_coin(request.args.get("coin", "bitcoin"))
        days = int(request.args.get("days", "1"))
        currency = request.args.get("currency", "eur")
        return jsonify({"coin": coin, "days": days, "currency": currency, "points": fetch_history(coin, days, currency)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
