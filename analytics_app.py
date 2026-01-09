"""
Standalone wBAN Analytics App
Run with: python analytics_app.py
"""
import json
import os
from flask import Flask, jsonify, render_template_string
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

ANALYTICS_FILE = "wban_analytics_data.json"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>wBAN Cross-Chain Analytics</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.3.1/dist/css/bootstrap.min.css">
    <style>
        :root {
            --bg-primary: #f8f9fa;
            --bg-secondary: #ffffff;
            --text-primary: #212529;
            --text-secondary: #6c757d;
            --accent: #fbdd11;
            --accent-dark: #e6c900;
            --border-color: #dee2e6;
        }
        body.dark-mode {
            --bg-primary: #1a1a2e;
            --bg-secondary: #16213e;
            --text-primary: #eaeaea;
            --text-secondary: #b8b8b8;
            --border-color: #2a2a4a;
        }
        body {
            background-color: var(--bg-primary);
            color: var(--text-primary);
            transition: background-color 0.3s, color 0.3s;
        }
        .card {
            background-color: var(--bg-secondary);
            border-color: var(--border-color);
        }
        .card-header {
            background-color: var(--accent);
            color: #212529;
            font-weight: bold;
        }
        body.dark-mode .card-header { background-color: var(--accent-dark); }
        .table { color: var(--text-primary); }
        .table th { border-top: none; border-bottom: 2px solid var(--border-color); }
        .table td { border-color: var(--border-color); }
        .stat-value {
            font-size: 1.5rem;
            font-weight: bold;
            color: var(--accent-dark);
        }
        body.dark-mode .stat-value { color: var(--accent); }
        .stat-label { font-size: 0.9rem; color: var(--text-secondary); }
        .rank-badge {
            display: inline-block;
            width: 24px; height: 24px; line-height: 24px;
            text-align: center; border-radius: 50%;
            font-weight: bold; font-size: 0.8rem;
        }
        .rank-1 { background-color: #ffd700; color: #000; }
        .rank-2 { background-color: #c0c0c0; color: #000; }
        .rank-3 { background-color: #cd7f32; color: #fff; }
        .rank-other { background-color: var(--text-secondary); color: #fff; }
        .summary-card { border-left: 4px solid var(--accent); }
        .progress { height: 20px; background-color: var(--border-color); }
        .progress-bar { background-color: var(--accent); }
        .volume-bar { height: 8px; border-radius: 4px; margin-top: 5px; }
        .navbar { background-color: var(--bg-secondary) !important; border-bottom: 1px solid var(--border-color); }
        .toggle-switch { cursor: pointer; }
        .timestamp { font-size: 0.85rem; color: var(--text-secondary); }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-light">
        <div class="container">
            <a class="navbar-brand" href="/">wBAN Analytics</a>
            <span class="toggle-switch" onclick="toggleDarkMode()">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
                </svg>
            </span>
        </div>
    </nav>

    <div class="container mt-4">
        <div id="content">
            <!-- Summary -->
            <div class="row mb-4">
                <div class="col-md-4 mb-3">
                    <div class="card summary-card h-100">
                        <div class="card-body text-center">
                            <div class="stat-label">wBAN Price</div>
                            <div class="stat-value" id="wban-price">-</div>
                        </div>
                    </div>
                </div>
                <div class="col-md-4 mb-3">
                    <div class="card summary-card h-100">
                        <div class="card-body text-center">
                            <div class="stat-label">Total Liquidity</div>
                            <div class="stat-value" id="total-liquidity">-</div>
                        </div>
                    </div>
                </div>
                <div class="col-md-4 mb-3">
                    <div class="card summary-card h-100">
                        <div class="card-body text-center">
                            <div class="stat-label">Data Generated</div>
                            <div class="timestamp" id="generated-at">-</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 1 Month -->
            <div class="card mb-4">
                <div class="card-header">Past 1 Month Activity</div>
                <div class="card-body">
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <div class="stat-label">Total Swaps</div>
                            <div class="stat-value" id="total-swaps-1m">-</div>
                        </div>
                        <div class="col-md-6">
                            <div class="stat-label">Total Volume</div>
                            <div class="stat-value" id="total-volume-1m">-</div>
                        </div>
                    </div>
                    <table class="table table-striped">
                        <thead><tr><th>Rank</th><th>Chain</th><th>Swaps</th><th>Volume (wBAN)</th><th>Volume (USD)</th><th>%</th></tr></thead>
                        <tbody id="table-1m"></tbody>
                    </table>
                </div>
            </div>

            <!-- 3 Months -->
            <div class="card mb-4">
                <div class="card-header">Past 3 Months Activity</div>
                <div class="card-body">
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <div class="stat-label">Total Swaps</div>
                            <div class="stat-value" id="total-swaps-3m">-</div>
                        </div>
                        <div class="col-md-6">
                            <div class="stat-label">Total Volume</div>
                            <div class="stat-value" id="total-volume-3m">-</div>
                        </div>
                    </div>
                    <table class="table table-striped">
                        <thead><tr><th>Rank</th><th>Chain</th><th>Swaps</th><th>Volume (wBAN)</th><th>Volume (USD)</th><th>%</th></tr></thead>
                        <tbody id="table-3m"></tbody>
                    </table>
                </div>
            </div>

            <!-- Liquidity -->
            <div class="card mb-4">
                <div class="card-header">Current Liquidity by Chain</div>
                <div class="card-body">
                    <table class="table table-striped">
                        <thead><tr><th>Rank</th><th>Chain</th><th>wBAN in Pool</th><th>Liquidity (USD)</th><th>%</th></tr></thead>
                        <tbody id="table-liquidity"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <footer class="text-center py-4"><small class="text-muted">wBAN Analytics | Data from blockchain</small></footer>

    <script>
        const data = {{ data | tojson }};

        function fmt(n, d=0) { return n ? n.toLocaleString('en-US', {minimumFractionDigits: d, maximumFractionDigits: d}) : 'N/A'; }
        function fmtUSD(n) { return n ? '$' + fmt(n, 2) : 'N/A'; }
        function badge(r) {
            let c = r === 1 ? 'rank-1' : r === 2 ? 'rank-2' : r === 3 ? 'rank-3' : 'rank-other';
            return `<span class="rank-badge ${c}">${r}</span>`;
        }
        function bar(p) {
            return `<div class="progress volume-bar"><div class="progress-bar" style="width:${Math.min(p,100)}%"></div></div><small>${fmt(p,1)}%</small>`;
        }

        // Summary
        document.getElementById('wban-price').textContent = '$' + (data.wban_price_usd || 0).toFixed(6);
        let totalLiq = Object.values(data.chains).reduce((s, c) => s + (c.liquidity?.usd || 0), 0);
        document.getElementById('total-liquidity').textContent = fmtUSD(totalLiq);
        document.getElementById('generated-at').textContent = data.generated_at ? new Date(data.generated_at).toLocaleString() : '-';

        // 1 Month
        document.getElementById('total-swaps-1m').textContent = fmt(data.totals['1_month'].swap_count);
        document.getElementById('total-volume-1m').textContent = fmt(data.totals['1_month'].volume_wban) + ' wBAN';
        let chains1m = Object.entries(data.chains).map(([k,v]) => ({id:k, ...v})).sort((a,b) => b['1_month'].swap_count - a['1_month'].swap_count);
        document.getElementById('table-1m').innerHTML = chains1m.map((c, i) => {
            let pct = data.totals['1_month'].swap_count ? (c['1_month'].swap_count / data.totals['1_month'].swap_count) * 100 : 0;
            return `<tr><td>${badge(i+1)}</td><td>${c.name}</td><td>${fmt(c['1_month'].swap_count)}</td><td>${fmt(c['1_month'].volume_wban)}</td><td>${fmtUSD(c['1_month'].volume_usd)}</td><td>${bar(pct)}</td></tr>`;
        }).join('');

        // 3 Months
        document.getElementById('total-swaps-3m').textContent = fmt(data.totals['3_months'].swap_count);
        document.getElementById('total-volume-3m').textContent = fmt(data.totals['3_months'].volume_wban) + ' wBAN';
        let chains3m = Object.entries(data.chains).map(([k,v]) => ({id:k, ...v})).sort((a,b) => b['3_months'].swap_count - a['3_months'].swap_count);
        document.getElementById('table-3m').innerHTML = chains3m.map((c, i) => {
            let pct = data.totals['3_months'].swap_count ? (c['3_months'].swap_count / data.totals['3_months'].swap_count) * 100 : 0;
            return `<tr><td>${badge(i+1)}</td><td>${c.name}</td><td>${fmt(c['3_months'].swap_count)}</td><td>${fmt(c['3_months'].volume_wban)}</td><td>${fmtUSD(c['3_months'].volume_usd)}</td><td>${bar(pct)}</td></tr>`;
        }).join('');

        // Liquidity
        let chainsLiq = Object.entries(data.chains).map(([k,v]) => ({id:k, ...v})).filter(c => c.liquidity?.usd).sort((a,b) => b.liquidity.usd - a.liquidity.usd);
        document.getElementById('table-liquidity').innerHTML = chainsLiq.map((c, i) => {
            let pct = totalLiq ? (c.liquidity.usd / totalLiq) * 100 : 0;
            return `<tr><td>${badge(i+1)}</td><td>${c.name}</td><td>${fmt(c.liquidity.wban)}</td><td>${fmtUSD(c.liquidity.usd)}</td><td>${bar(pct)}</td></tr>`;
        }).join('');

        function toggleDarkMode() {
            document.body.classList.toggle('dark-mode');
            localStorage.setItem('darkMode', document.body.classList.contains('dark-mode'));
        }
        if (localStorage.getItem('darkMode') === 'true') document.body.classList.add('dark-mode');
    </script>
</body>
</html>
"""

def load_analytics():
    try:
        with open(ANALYTICS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"error": "No data. Run 'python wban_analytics.py' first.", "chains": {}, "totals": {"1_month": {}, "3_months": {}}}

@app.route("/")
def index():
    data = load_analytics()
    return render_template_string(HTML_TEMPLATE, data=data)

@app.route("/api/data")
def api_data():
    return jsonify(load_analytics())

if __name__ == "__main__":
    host = os.getenv("ANALYTICS_HOST", "127.0.0.1")
    port = int(os.getenv("ANALYTICS_PORT", 5001))
    print(f"wBAN Analytics running at http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
