/**
 * Stock Analyzer — メインアプリケーションロジック
 */

// ===== State =====
const API_BASE = '';
const cache = new Map();
const CACHE_TTL = 5 * 60 * 1000;

let currentSymbol = null;
let priceChart = null;
let rsiChartInstance = null;
let currentPeriod = '3mo';
let currentChartHistory = [];
let currentChartCurrency = null;

// Stats History
const statsHistory = [];
const HISTORY_MAX_LEN = 20;
let hitRateChartInstance = null;
let endpointChartInstance = null;
let responseTimeChartInstance = null;

// 為替レート
let exchangeRateUSDJPY = null;

// リストビュー（アカウントに1:1対応）
let listItems = [];
let sortKey = 'symbol';
let sortAsc = true;

// アカウント
let currentUser = null;
let currentListId = null;

// 削除確認（2段階）
let pendingDeleteSymbol = null;
let pendingDeleteTimer = null;

// タグフィルター
let activeTagFilter = null;
let tagEditSymbol = null;

// ===== Init =====
(async function init() {
    const saved = localStorage.getItem('stockAnalyzerUser');
    if (saved) {
        try {
            currentUser = JSON.parse(saved);
            updateAccountUI();
            // ログイン済みなら自動でリスト読み込み
            loadDefaultList();
        } catch { /* ignore */ }
    }
    
    // 為替レートの初期取得
    await fetchExchangeRate();
    
    // 統計情報の定期取得を開始
    fetchStats();
    setInterval(fetchStats, 5000);
})();

// ===== View Switch =====
function switchView(view) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(b => {
        if (b.id === 'btn-detail-view' || b.id === 'btn-list-view' || b.id === 'btn-stats-view') {
            b.classList.remove('active');
        }
    });

    if (view === 'detail') {
        document.getElementById('detail-view').classList.add('active');
        document.getElementById('btn-detail-view').classList.add('active');
    } else if (view === 'stats') {
        document.getElementById('stats-view').classList.add('active');
        document.getElementById('btn-stats-view').classList.add('active');
        // If switched to stats view, manually trigger stats fetch to update dashboard
        fetchStats();
    } else {
        document.getElementById('list-view').classList.add('active');
        document.getElementById('btn-list-view').classList.add('active');
    }
}

// ===== API Helper =====
async function fetchAPI(endpoint, options = {}) {
    const cacheKey = endpoint + JSON.stringify(options);

    if (!options.method || options.method === 'GET') {
        const cached = cache.get(cacheKey);
        if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
            return cached.data;
        }
    }

    const res = await fetch(`${API_BASE}${endpoint}`, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();

    if (!options.method || options.method === 'GET') {
        cache.set(cacheKey, { data, timestamp: Date.now() });
    }
    fetchStats(); // リクエスト後に統計を更新
    return data;
}

// ===== System Stats =====
async function fetchStats() {
    try {
        const res = await fetch(`${API_BASE}/stats`);
        if (!res.ok) return;
        const data = await res.json();
        
        // 既存のステータスバーを更新
        document.getElementById('stat-api-calls').textContent = data.api_calls;
        document.getElementById('stat-cache-hits').textContent = data.cache_hits;
        document.getElementById('stat-hit-rate').textContent = data.hit_rate_percent.toFixed(1) + '%';
        
        const bar = document.getElementById('stats-bar');
        if (data.total_requests > 0) {
            bar.classList.remove('hidden');
        }

        // Stats HistoryとDashboardの更新
        const now = new Date();
        data.timestamp = now.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        
        statsHistory.push(data);
        if (statsHistory.length > HISTORY_MAX_LEN) {
            statsHistory.shift();
        }

        // Dashboard Viewが開かれている場合、ダッシュボードを更新
        if (document.getElementById('stats-view').classList.contains('active')) {
            updateStatsDashboard(data);
        }

    } catch {
        // ignore errors for stats fetching
    }
}

function updateStatsDashboard(data) {
    // Uptimes
    const minutes = Math.floor(data.uptime_seconds / 60);
    const seconds = data.uptime_seconds % 60;
    document.getElementById('dash-uptime').textContent = `${minutes}m ${seconds}s`;

    // Metrics
    document.getElementById('dash-server-requests').textContent = data.server_requests || 0;
    document.getElementById('dash-cache-hits').textContent = data.cache_hits || 0;
    document.getElementById('dash-avg-time').textContent = (data.avg_response_time_ms || 0).toFixed(1);
    
    document.getElementById('dash-errors').textContent = data.server_errors || 0;
    document.getElementById('dash-error-rate').textContent = ` (${(data.error_rate_percent || 0).toFixed(1)}%)`;

    // Charts
    updateCharts(data);
}

function updateCharts(data) {
    const isDark = true;
    const textColor = '#94a3b8';
    const gridColor = 'rgba(255,255,255,0.05)';

    // Hit Rate (Pie Chart)
    const hitCtx = document.getElementById('hitRateChart');
    if (hitCtx) {
        if (!hitRateChartInstance) {
            hitRateChartInstance = new Chart(hitCtx, {
                type: 'doughnut',
                data: {
                    labels: ['Cache Hits', 'API Calls'],
                    datasets: [{
                        data: [data.cache_hits, data.api_calls],
                        backgroundColor: ['#10b981', '#3b82f6'],
                        borderWidth: 0,
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { position: 'bottom', labels: { color: textColor } } }
                }
            });
        } else {
            hitRateChartInstance.data.datasets[0].data = [data.cache_hits, data.api_calls];
            hitRateChartInstance.update();
        }
    }

    // Endpoints (Bar Chart)
    const epCtx = document.getElementById('endpointChart');
    if (epCtx && data.top_endpoints) {
        const labels = data.top_endpoints.map(e => e.endpoint.substring(0, 15) + (e.endpoint.length > 15 ? '...' : ''));
        const counts = data.top_endpoints.map(e => e.count);
        
        if (!endpointChartInstance) {
            endpointChartInstance = new Chart(epCtx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Hits',
                        data: counts,
                        backgroundColor: '#6366f1',
                        borderRadius: 4,
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: textColor, font: { size: 10 }, maxRotation: 45, minRotation: 45 }, grid: { display: false } },
                        y: { ticks: { color: textColor, precision: 0 }, grid: { color: gridColor, drawBorder: false }, beginAtZero: true }
                    }
                }
            });
        } else {
            endpointChartInstance.data.labels = labels;
            endpointChartInstance.data.datasets[0].data = counts;
            endpointChartInstance.update();
        }
    }

    // Response Time (Line Chart) over Time
    const rtCtx = document.getElementById('responseTimeChart');
    if (rtCtx) {
        const labels = statsHistory.map(h => h.timestamp);
        const avgTimes = statsHistory.map(h => h.avg_response_time_ms || 0);
        
        if (!responseTimeChartInstance) {
            responseTimeChartInstance = new Chart(rtCtx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Avg Response Time (ms)',
                        data: avgTimes,
                        borderColor: '#f59e0b',
                        backgroundColor: 'rgba(245, 158, 11, 0.1)',
                        fill: true,
                        tension: 0.4,
                        borderWidth: 2,
                        pointRadius: 2,
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    animation: { duration: 0 }, // Disable animation for smoother over-time updates
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: textColor, maxTicksLimit: 6 }, grid: { display: false } },
                        y: { ticks: { color: textColor }, grid: { color: gridColor, drawBorder: false }, beginAtZero: true }
                    }
                }
            });
        } else {
            responseTimeChartInstance.data.labels = labels;
            responseTimeChartInstance.data.datasets[0].data = avgTimes;
            responseTimeChartInstance.update();
        }
    }
}

// ===== Exchange Rate =====
async function fetchExchangeRate() {
    try {
        const res = await fetchAPI('/forex/usdjpy', { method: 'GET' });
        exchangeRateUSDJPY = res.rate;
    } catch (err) {
        console.warn('Failed to fetch exchange rate:', err);
    }
}

// ===== Search =====
function quickSearch(symbol) {
    document.getElementById('search-input').value = symbol;
    searchStock();
}

async function searchStock() {
    const input = document.getElementById('search-input');
    const symbol = input.value.trim().toUpperCase();
    if (!symbol) return;

    currentSymbol = symbol;
    showSection('loading');
    document.getElementById('loading-text').textContent = `${symbol} のデータを取得中...`;

    try {
        const [price, profile, indicators] = await Promise.all([
            fetchAPI(`/stock/${symbol}`),
            fetchAPI(`/stock/${symbol}/profile`),
            fetchAPI(`/stock/${symbol}/indicators`),
        ]);

        renderStockHeader(price, profile);
        renderProfile(profile);
        renderIndicators(indicators);

        showSection('stock-detail');
        loadChart(symbol, currentPeriod, profile.currency);
        loadFinancials(symbol, profile);
        loadNews(symbol);
    } catch (err) {
        showError('データ取得エラー', err.message);
    }
}

function showSection(name) {
    ['welcome-section', 'loading-section', 'error-section', 'stock-detail'].forEach(id => {
        document.getElementById(id).classList.add('hidden');
    });
    if (name === 'loading') document.getElementById('loading-section').classList.remove('hidden');
    else if (name === 'error') document.getElementById('error-section').classList.remove('hidden');
    else if (name === 'stock-detail') document.getElementById('stock-detail').classList.remove('hidden');
    else document.getElementById('welcome-section').classList.remove('hidden');
}

function showError(title, message) {
    document.getElementById('error-title').textContent = title;
    document.getElementById('error-message').textContent = message;
    showSection('error');
}

// ===== Render: Stock Header =====
function renderStockHeader(price, profile) {
    document.getElementById('company-name').textContent = profile.name || price.symbol;
    document.getElementById('ticker-badge').textContent = price.symbol;

    const meta = [];
    if (profile.sector) meta.push(profile.sector);
    if (profile.industry) meta.push(profile.industry);
    if (profile.country) meta.push(profile.country);
    document.getElementById('stock-meta').textContent = meta.join(' • ');

    const currency = profile.currency || 'USD';
    document.getElementById('price-display').textContent = formatCurrency(price.price, currency);
    document.getElementById('price-timestamp').textContent = `最終更新: ${formatTimestamp(price.timestamp)}`;
}

// ===== Render: Profile =====
function renderProfile(profile) {
    const body = document.getElementById('profile-body');
    let html = '';

    const rows = [
        ['セクター', profile.sector],
        ['業種', profile.industry],
        ['国', profile.country],
        ['時価総額', profile.market_cap ? formatLargeNumber(profile.market_cap, profile.currency) : null],
        ['従業員数', profile.employees ? profile.employees.toLocaleString() + '人' : null],
        ['通貨', profile.currency],
    ];

    if (profile.website) {
        rows.push(['ウェブサイト', `<a href="${profile.website}" target="_blank" style="color:var(--accent-blue);text-decoration:none;">${new URL(profile.website).hostname}</a>`]);
    }

    rows.forEach(([label, value]) => {
        if (value != null) {
            html += `<div class="data-row"><span class="data-label">${label}</span><span class="data-value">${value}</span></div>`;
        }
    });

    if (profile.summary) {
        html += `<div class="company-summary">${profile.summary}</div>`;
    }

    body.innerHTML = html || '<p style="color:var(--text-muted)">データなし</p>';
}

function getMixIndexRating(value) {
    if (value == null) return null;
    if (value < 22.5) return 'good';
    if (value < 50) return 'neutral';
    return 'bad';
}

function getRatingSymbol(rating) {
    if (rating === 'good') return '◎';
    if (rating === 'neutral') return '○';
    return '△';
}

function getMarketCapCategory(marketCap, currency) {
    if (marketCap == null) return null;

    let marketCapUsd = null;
    if (!currency || currency === 'USD') {
        marketCapUsd = marketCap;
    } else if (currency === 'JPY' && exchangeRateUSDJPY) {
        marketCapUsd = marketCap / exchangeRateUSDJPY;
    }

    if (marketCapUsd == null) return null;
    if (marketCapUsd < 50_000_000) return 'Nano';
    if (marketCapUsd < 300_000_000) return 'Micro';
    if (marketCapUsd < 2_000_000_000) return 'Small';
    if (marketCapUsd < 10_000_000_000) return 'Mid';
    if (marketCapUsd < 200_000_000_000) return 'Large';
    return 'Mega';
}

// ===== Render: Indicators =====
function renderIndicators(data) {
    const body = document.getElementById('indicators-body');
    let html = '';

    const indicators = [
        ['ROE', data.roe, '%', v => v > 15 ? 'good' : v > 8 ? 'neutral' : 'bad', '高いほど良い'],
        ['ROA', data.roa, '%', v => v > 10 ? 'good' : v > 5 ? 'neutral' : 'bad', '高いほど良い'],
        ['PBR', data.pbr, '倍', v => v < 1 ? 'good' : v < 3 ? 'neutral' : 'bad', '低いほど割安'],
        ['PER', data.per, '倍', v => v < 15 ? 'good' : v < 30 ? 'neutral' : 'bad', '低いほど割安'],
        ['EPS', data.eps, '', null, '1株あたり利益'],
        ['ミックス指数', data.mix_index, '', v => getMixIndexRating(v), 'PER×PBR（22.5以下が割安）'],
        ['配当利回り', data.dividend_yield, '%', v => v > 3 ? 'good' : v > 1 ? 'neutral' : 'bad', '高いほど良い'],
        ['利益率', data.profit_margin, '%', v => v > 20 ? 'good' : v > 10 ? 'neutral' : 'bad', '高いほど良い'],
        ['D/Eレシオ', data.debt_to_equity, '', v => v < 50 ? 'good' : v < 150 ? 'neutral' : 'bad', '低いほど財務健全'],
    ];

    indicators.forEach(([label, value, unit, ratingFn, tooltip]) => {
        const displayValue = value != null ? `${value}${unit}` : '—';
        let badge = '';
        if (value != null && ratingFn) {
            const rating = ratingFn(value);
            const ratingLabel = rating === 'good' ? '◎' : rating === 'neutral' ? '○' : '△';
            badge = `<span class="indicator-badge ${rating}">${ratingLabel}</span>`;
        }
        html += `
            <div class="data-row" title="${tooltip || ''}">
                <span class="data-label">${label}</span>
                <span class="data-value ${value != null && ratingFn ? ratingFn(value) === 'good' ? 'positive' : ratingFn(value) === 'bad' ? 'negative' : '' : ''}">
                    ${displayValue} ${badge}
                </span>
            </div>`;
    });

    body.innerHTML = html;
}

// ===== Load: Financials =====
async function loadFinancials(symbol, profile) {
    const body = document.getElementById('financials-body');
    body.innerHTML = '<div class="skeleton-lines"><div></div><div></div><div></div></div>';

    try {
        const data = await fetchAPI(`/stock/${symbol}/financials`);
        let html = '';
        const rows = [
            ['売上高', data.revenue ? formatLargeNumber(data.revenue, profile?.currency) : null],
            ['純利益', data.net_income ? formatLargeNumber(data.net_income, profile?.currency) : null],
            ['EPS', data.eps != null ? data.eps.toFixed(2) : null],
            ['PER', data.pe_ratio != null ? data.pe_ratio.toFixed(2) + '倍' : null],
        ];
        rows.forEach(([label, value]) => {
            html += `<div class="data-row"><span class="data-label">${label}</span><span class="data-value">${value || '—'}</span></div>`;
        });
        body.innerHTML = html || '<p style="color:var(--text-muted)">データなし</p>';
    } catch (err) {
        body.innerHTML = `<p style="color:var(--accent-rose)">取得失敗: ${err.message}</p>`;
    }
}

// ===== Load: News =====
async function loadNews(symbol) {
    const body = document.getElementById('news-body');
    body.innerHTML = '<div class="skeleton-lines"><div></div><div></div><div></div></div>';

    try {
        const data = await fetchAPI(`/stock/${symbol}/news`);
        if (!data.news || data.news.length === 0) {
            body.innerHTML = '<p style="color:var(--text-muted)">ニュースが見つかりませんでした</p>';
            return;
        }
        let html = '<div class="news-list">';
        data.news.forEach(article => {
            const dateStr = article.published_at ? formatNewsDate(article.published_at) : '';
            html += `
                <a href="${article.url}" target="_blank" rel="noopener" class="news-item">
                    <div class="news-bullet"></div>
                    <div class="news-item-content">
                        <h4>${escapeHtml(article.title)}</h4>
                        ${dateStr ? `<span class="news-date">${dateStr}</span>` : ''}
                    </div>
                </a>`;
        });
        html += '</div>';
        body.innerHTML = html;
    } catch (err) {
        body.innerHTML = `<p style="color:var(--accent-rose)">取得失敗: ${err.message}</p>`;
    }
}

// ===== Indicators & Chart Helper =====
function updateChartVisibility() {
    if (currentChartHistory.length > 0) {
        renderChart(currentChartHistory, currentChartCurrency);
    }
}

// ===== Chart =====
async function loadChart(symbol, period, currency) {
    const periodMap = {
        '1mo': { months: 1 },
        '3mo': { months: 3 },
        '6mo': { months: 6 },
        '1y':  { months: 12 },
        '2y':  { months: 24 },
    };

    const p = periodMap[period] || periodMap['3mo'];
    const endDate = new Date();
    const startDate = new Date();
    
    let interval = '1d';
    if (period === '10y') {
        startDate.setFullYear(startDate.getFullYear() - 10);
        interval = '1mo'; // 10年は月次
    } else {
        startDate.setMonth(startDate.getMonth() - p.months);
        interval = p.months > 12 ? '1wk' : '1d';
    }

    const startStr = startDate.toISOString().split('T')[0];
    const endStr = endDate.toISOString().split('T')[0];

    try {
        const data = await fetchAPI(`/stock/${symbol}/history?start_date=${startStr}&end_date=${endStr}&interval=${interval}`);
        currentChartHistory = data.history;
        currentChartCurrency = currency;
        renderChart(data.history, currency);
    } catch (err) {
        console.error('Chart load error:', err);
    }
}

function renderChart(history, currency) {
    const ctx = document.getElementById('price-chart').getContext('2d');
    if (priceChart) priceChart.destroy();

    const rsiCtx = document.getElementById('rsi-chart').getContext('2d');
    if (rsiChartInstance) rsiChartInstance.destroy();

    let closes = history.map(h => h.close);
    
    // 円換算（USDの場合のみ）
    if ((!currency || currency === 'USD') && exchangeRateUSDJPY) {
        closes = closes.map(c => c * exchangeRateUSDJPY);
    }

    const labels = history.map(h => h.date);
    
    const showSma25 = document.getElementById('toggle-sma25').checked;
    const showSma50 = document.getElementById('toggle-sma50').checked;
    const showSma75 = document.getElementById('toggle-sma75').checked;
    const showSma200 = document.getElementById('toggle-sma200').checked;
    const showRSI = document.getElementById('toggle-rsi').checked;

    document.getElementById('rsi-container').classList.toggle('hidden', !showRSI);

    const datasets = [];
    
    const isUp = closes.length >= 2 && closes[closes.length - 1] >= closes[0];
    const lineColor = isUp ? '#10b981' : '#f43f5e';
    const fillColor = isUp ? 'rgba(16, 185, 129, 0.08)' : 'rgba(244, 63, 94, 0.08)';

    datasets.push({
        label: '終値',
        data: closes,
        borderColor: lineColor,
        backgroundColor: fillColor,
        fill: true,
        tension: 0.3,
        borderWidth: 2,
        pointRadius: 0,
        pointHitRadius: 10,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: lineColor,
        order: 1
    });

    const getIndicatorData = (key) => {
        let values = history.map(h => h[key]);
        if ((!currency || currency === 'USD') && exchangeRateUSDJPY) {
            // 値段に関する指標は為替レートを乗算
            values = values.map(v => v !== null && v !== undefined ? v * exchangeRateUSDJPY : null);
        }
        return values;
    };

    if (showSma25) datasets.push({ label: 'SMA 25', data: getIndicatorData("sma_25"), borderColor: '#3b82f6', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false, order: 2 });
    if (showSma50) datasets.push({ label: 'SMA 50', data: getIndicatorData("sma_50"), borderColor: '#f59e0b', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false, order: 3 });
    if (showSma75) datasets.push({ label: 'SMA 75', data: getIndicatorData("sma_75"), borderColor: '#8b5cf6', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false, order: 4 });
    if (showSma200) datasets.push({ label: 'SMA 200', data: getIndicatorData("sma_200"), borderColor: '#ec4899', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false, order: 5 });

    priceChart = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    titleColor: '#94a3b8',
                    bodyColor: '#f1f5f9',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    padding: 12,
                    cornerRadius: 8,
                    titleFont: { size: 12 },
                    bodyFont: { size: 13, weight: '500' },
                    callbacks: {
                        label: ctx => {
                            const val = ctx.parsed.y;
                            const dsLabel = ctx.dataset.label;
                            let formatted = val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                            if ((!currency || currency === 'USD') && exchangeRateUSDJPY) {
                                formatted = `¥${val.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
                            }
                            return `  ${dsLabel}: ${formatted}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
                    ticks: { color: '#64748b', font: { size: 11 }, maxTicksLimit: 8, maxRotation: 0 },
                    border: { display: false },
                },
                y: {
                    position: 'right',
                    grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
                    ticks: { color: '#64748b', font: { size: 11 }, callback: v => v.toLocaleString() },
                    border: { display: false },
                }
            }
        }
    });

    if (showRSI) {
        const rsiData = history.map(h => h.rsi_14);
        rsiChartInstance = new Chart(rsiCtx, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'RSI (14)',
                    data: rsiData,
                    borderColor: '#a855f7',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    pointHitRadius: 10,
                    pointHoverRadius: 5,
                    pointHoverBackgroundColor: '#a855f7',
                    tension: 0.3,
                    fill: {
                        target: { value: 30 },
                        below: 'rgba(168, 85, 247, 0.1)'
                    }
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(17, 24, 39, 0.95)',
                        titleColor: '#94a3b8',
                        bodyColor: '#f1f5f9',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1,
                        padding: 12,
                        cornerRadius: 8,
                        titleFont: { size: 12 },
                        bodyFont: { size: 13, weight: '500' },
                        callbacks: {
                            label: ctx => `  RSI: ${ctx.parsed.y.toFixed(1)}`
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { display: false },
                        border: { display: false },
                    },
                    y: {
                        position: 'right',
                        min: 0,
                        max: 100,
                        grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
                        ticks: { color: '#64748b', font: { size: 10 }, stepSize: 30 },
                        border: { display: false },
                    }
                }
            }
        });
    }
}

function changePeriod(period) {
    currentPeriod = period;
    document.querySelectorAll('.period-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.period === period);
    });
    
    // 現在のprofileからcurrencyを取得する（レンダリング時に必要）
    // NOTE: quick hackとしてUIから取得するか、キャッシュから取得します
    const currentCurrency = document.getElementById('price-display').textContent.includes('¥') ? 'USD' : 'JPY'; // 雑な判定だが実用上は機能する
    if (currentSymbol) loadChart(currentSymbol, period, currentCurrency);
}

// ===== Default List (1:1対応) =====
async function loadDefaultList() {
    if (!currentUser) return;

    try {
        const data = await fetchAPI(`/user/${currentUser.id}/default-list`);
        currentListId = data.id;

        // 既存リストをクリアして読み込み
        listItems = [];
        renderListTable();

        for (const item of data.items) {
            const entry = { symbol: item.symbol, loading: true, tags: item.tags || [] };
            listItems.push(entry);
            renderListTable();
            loadListItemData(item.symbol, item.tags);
        }
    } catch (err) {
        console.warn('Default list load failed:', err);
    }
}

async function loadListItemData(symbol, tags) {
    try {
        const [price, profile, indicators, memo] = await Promise.all([
            fetchAPI(`/stock/${symbol}`),
            fetchAPI(`/stock/${symbol}/profile`),
            fetchAPI(`/stock/${symbol}/indicators`),
            fetchStockMemo(symbol),
        ]);

            const idx = listItems.findIndex(i => i.symbol === symbol);
        if (idx >= 0) {
            listItems[idx] = {
                symbol,
                loading: false,
                name: profile.name,
                price: price.price,
                currency: profile.currency,
                market_cap: profile.market_cap,
                mix_index: indicators.mix_index,
                dividend_yield: indicators.dividend_yield,
                tags: tags || [],
                memo,
            };
            renderListTable();
        }
    } catch (err) {
        const idx = listItems.findIndex(i => i.symbol === symbol);
        if (idx >= 0) {
            listItems[idx].loading = false;
            listItems[idx].name = '(取得失敗)';
            renderListTable();
        }
    }
}

async function fetchStockMemo(symbol) {
    if (!currentUser) return null;
    try {
        const data = await fetchAPI(`/user/${currentUser.id}/memo/${symbol}`);
        return data.memo || null;
    } catch (err) {
        console.warn('Memo fetch failed:', err);
        return null;
    }
}

async function editStockMemo(symbol) {
    if (!currentUser) {
        showToast('メモ機能はログインが必要です', 'warning');
        return;
    }

    const item = listItems.find(i => i.symbol === symbol);
    const currentMemo = item?.memo || '';
    const input = window.prompt(`${symbol} のメモを入力`, currentMemo);
    if (input === null) return;

    const memo = input.trim() === '' ? null : input.trim();

    try {
        const saved = await fetchAPI(`/user/${currentUser.id}/memo/${symbol}`, {
            method: 'PUT',
            body: JSON.stringify({ memo }),
        });
        if (item) {
            item.memo = saved.memo || null;
            renderListTable();
        }
        showToast('メモを保存しました', 'success');
    } catch (err) {
        showToast(`メモ保存に失敗しました: ${err.message}`, 'error');
    }
}

// ===== List View =====
function quickAddToList(symbol) {
    document.getElementById('list-add-input').value = symbol;
    addToList();
}

async function addToList() {
    const input = document.getElementById('list-add-input');
    const symbol = input.value.trim().toUpperCase();
    if (!symbol) return;
    input.value = '';

    if (listItems.find(item => item.symbol === symbol)) return;

    const item = { symbol, loading: true, tags: [] };
    listItems.push(item);
    renderListTable();

    // サーバーにも追加（ログイン中のみ）
    if (currentUser && currentListId) {
        try {
            await fetchAPI(`/user/${currentUser.id}/lists/${currentListId}/items`, {
                method: 'POST',
                body: JSON.stringify({ symbol, tags: [] }),
            });
        } catch (err) {
            console.warn('Server add failed:', err);
        }
    }

    try {
        const [price, profile, indicators, memo] = await Promise.all([
            fetchAPI(`/stock/${symbol}`),
            fetchAPI(`/stock/${symbol}/profile`),
            fetchAPI(`/stock/${symbol}/indicators`),
            fetchStockMemo(symbol),
        ]);

        const idx = listItems.findIndex(i => i.symbol === symbol);
        if (idx >= 0) {
            listItems[idx] = {
                symbol,
                loading: false,
                name: profile.name,
                price: price.price,
                currency: profile.currency,
                market_cap: profile.market_cap,
                mix_index: indicators.mix_index,
                dividend_yield: indicators.dividend_yield,
                tags: listItems[idx].tags || [],
                memo,
            };
            renderListTable();
        }
    } catch (err) {
        listItems = listItems.filter(i => i.symbol !== symbol);
        renderListTable();
        // サーバーからも削除
        if (currentUser && currentListId) {
            try {
                await fetchAPI(`/user/${currentUser.id}/lists/${currentListId}/items/${symbol}`, { method: 'DELETE' });
            } catch { /* ignore */ }
        }
        showToast(`${symbol} の取得に失敗しました`, 'error');
    }
}

async function removeFromList(symbol) {
    listItems = listItems.filter(i => i.symbol !== symbol);
    if (pendingDeleteSymbol === symbol) {
        pendingDeleteSymbol = null;
    }
    if (pendingDeleteTimer) {
        clearTimeout(pendingDeleteTimer);
        pendingDeleteTimer = null;
    }
    renderListTable();

    // サーバーからも削除
    if (currentUser && currentListId) {
        try {
            await fetchAPI(`/user/${currentUser.id}/lists/${currentListId}/items/${symbol}`, { method: 'DELETE' });
        } catch (err) {
            console.warn('Server remove failed:', err);
        }
    }
}

function requestRemoveFromList(symbol) {
    if (pendingDeleteSymbol === symbol) {
        removeFromList(symbol);
        return;
    }

    pendingDeleteSymbol = symbol;
    if (pendingDeleteTimer) {
        clearTimeout(pendingDeleteTimer);
    }
    pendingDeleteTimer = setTimeout(() => {
        pendingDeleteSymbol = null;
        pendingDeleteTimer = null;
        renderListTable();
    }, 4000);

    renderListTable();
}

function sortTable(key) {
    if (sortKey === key) {
        sortAsc = !sortAsc;
    } else {
        sortKey = key;
        sortAsc = true;
    }
    renderListTable();
}

function getFilteredItems() {
    if (!activeTagFilter) return listItems;
    return listItems.filter(item => item.tags && item.tags.includes(activeTagFilter));
}

function getAllTags() {
    const tagSet = new Set();
    listItems.forEach(item => {
        if (item.tags) item.tags.forEach(t => tagSet.add(t));
    });
    return [...tagSet].sort();
}

function updateFilterButtonState() {
    const btn = document.getElementById('btn-filter');
    const label = document.getElementById('filter-btn-label');
    const filterBar = document.getElementById('active-filter-bar');

    if (activeTagFilter) {
        btn.classList.add('active');
        label.textContent = `フィルタ: ${activeTagFilter}`;
        // アクティブフィルタバーを表示
        filterBar.classList.remove('hidden');
        const tagEl = document.getElementById('active-filter-tag');
        const color = getTagColor(activeTagFilter);
        tagEl.innerHTML = `<span class="tag-chip small" style="--tag-hue:${color}">${escapeHtml(activeTagFilter)}</span>`;
    } else {
        btn.classList.remove('active');
        label.textContent = 'フィルタ';
        filterBar.classList.add('hidden');
    }
}

function renderListTable() {
    const emptyEl = document.getElementById('list-empty');
    const tableEl = document.getElementById('list-table-section');

    if (listItems.length === 0) {
        emptyEl.classList.remove('hidden');
        tableEl.classList.add('hidden');
        updateFilterButtonState();
        return;
    }

    emptyEl.classList.add('hidden');
    tableEl.classList.remove('hidden');
    updateFilterButtonState();

    const filtered = getFilteredItems();
    const sorted = [...filtered].sort((a, b) => {
        if (a.loading) return 1;
        if (b.loading) return -1;
        let va = a[sortKey];
        let vb = b[sortKey];
        if (va == null) return 1;
        if (vb == null) return -1;
        if (typeof va === 'string') return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        return sortAsc ? va - vb : vb - va;
    });

    // ヘッダーの矢印更新
    document.querySelectorAll('#comparison-table th.sortable').forEach(th => {
        const key = th.dataset.sort;
        th.classList.toggle('sort-active', key === sortKey);
        const arrow = th.querySelector('.sort-arrow');
        if (key === sortKey) {
            arrow.textContent = sortAsc ? ' ▲' : ' ▼';
        } else {
            arrow.textContent = '';
        }
    });

    const tbody = document.getElementById('comparison-tbody');
    let html = '';

    sorted.forEach(item => {
        if (item.loading) {
            const isPendingDelete = pendingDeleteSymbol === item.symbol;
            html += `
                <tr class="row-loading">
                    <td class="table-ticker">${item.symbol}</td>
                    <td colspan="7" style="color:var(--text-muted)">読み込み中...</td>
                    <td><button class="btn-remove ${isPendingDelete ? 'confirm' : ''}" onclick="event.stopPropagation(); requestRemoveFromList('${item.symbol}')">${isPendingDelete ? 'OK?' : '削除'}</button></td>
                </tr>`;
            return;
        }

        let tagsHtml = '';
        if (item.tags && item.tags.length > 0) {
            item.tags.forEach(tag => {
                const color = getTagColor(tag);
                tagsHtml += `<span class="tag-chip small" style="--tag-hue:${color}">${escapeHtml(tag)}</span>`;
            });
        }
        tagsHtml += `<button class="btn-tag-edit" onclick="event.stopPropagation(); openTagModal('${item.symbol}')" title="タグ編集">🏷️</button>`;

        const memoPreview = item.memo
            ? escapeHtml(item.memo.length > 24 ? `${item.memo.slice(0, 24)}...` : item.memo)
            : '<span class="memo-empty">未入力</span>';
        const memoTitle = item.memo ? escapeAttr(item.memo) : '';
        const marketCapCategory = getMarketCapCategory(item.market_cap, item.currency);
        const mixRating = getMixIndexRating(item.mix_index);
        const mixBadge = mixRating ? `<span class="indicator-badge ${mixRating}">${getRatingSymbol(mixRating)}</span>` : '';
        const isPendingDelete = pendingDeleteSymbol === item.symbol;

        html += `
            <tr onclick="goToDetail('${item.symbol}')">
                <td class="table-ticker">${item.symbol}</td>
                <td class="table-company">${escapeHtml(item.name || '—')}</td>
                <td class="numeric">${item.price != null ? formatCurrency(item.price, item.currency) : '—'}</td>
                <td class="table-market-cap" title="${item.market_cap != null ? escapeAttr(formatLargeNumber(item.market_cap, item.currency)) : ''}">${marketCapCategory || '—'}</td>
                <td class="numeric">${item.mix_index != null ? item.mix_index.toFixed(2) : '—'} ${mixBadge}</td>
                <td class="numeric">${item.dividend_yield != null ? item.dividend_yield.toFixed(2) + '%' : '—'}</td>
                <td class="table-tags" onclick="event.stopPropagation()">${tagsHtml}</td>
                <td class="table-memo" onclick="event.stopPropagation()"><button class="btn-memo" onclick="event.stopPropagation(); editStockMemo('${item.symbol}')">📝</button><span class="memo-preview" title="${memoTitle}">${memoPreview}</span></td>
                <td><button class="btn-remove ${isPendingDelete ? 'confirm' : ''}" onclick="event.stopPropagation(); requestRemoveFromList('${item.symbol}')">${isPendingDelete ? 'OK?' : '削除'}</button></td>
            </tr>`;
    });

    tbody.innerHTML = html;
}

function goToDetail(symbol) {
    document.getElementById('search-input').value = symbol;
    switchView('detail');
    searchStock();
}

// ===== Filter Modal =====
function openFilterModal() {
    const allTags = getAllTags();
    const container = document.getElementById('filter-tags-container');

    if (allTags.length === 0) {
        container.innerHTML = '<p class="filter-empty-note">タグが設定された銘柄がありません。<br>銘柄行の 🏷️ ボタンからタグを追加できます。</p>';
    } else {
        let html = '<div class="filter-tag-list">';
        allTags.forEach(tag => {
            const color = getTagColor(tag);
            const isActive = tag === activeTagFilter;
            const count = listItems.filter(i => i.tags && i.tags.includes(tag)).length;
            html += `<button class="filter-tag-item ${isActive ? 'active' : ''}" onclick="selectFilterTag('${escapeAttr(tag)}')" style="--tag-hue:${color}">
                <span class="filter-tag-name">${escapeHtml(tag)}</span>
                <span class="filter-tag-count">${count}件</span>
            </button>`;
        });
        html += '</div>';
        container.innerHTML = html;
    }

    document.getElementById('filter-modal-overlay').classList.remove('hidden');
}

function closeFilterModal() {
    document.getElementById('filter-modal-overlay').classList.add('hidden');
}

function selectFilterTag(tag) {
    activeTagFilter = activeTagFilter === tag ? null : tag;

    // モーダル内のアクティブ状態を更新
    document.querySelectorAll('.filter-tag-item').forEach(el => {
        const nameEl = el.querySelector('.filter-tag-name');
        if (nameEl && nameEl.textContent === tag) {
            el.classList.toggle('active', activeTagFilter === tag);
        } else {
            el.classList.remove('active');
        }
    });

    renderListTable();
}

function clearTagFilter() {
    activeTagFilter = null;
    renderListTable();
}

// ===== Tag Management =====
function openTagModal(symbol) {
    tagEditSymbol = symbol;
    document.getElementById('tag-modal-symbol').textContent = symbol;
    document.getElementById('tag-input').value = '';
    renderCurrentTags();
    document.getElementById('tag-modal-overlay').classList.remove('hidden');
}

function closeTagModal() {
    document.getElementById('tag-modal-overlay').classList.add('hidden');
    tagEditSymbol = null;
}

function renderCurrentTags() {
    const container = document.getElementById('tag-current-tags');
    const item = listItems.find(i => i.symbol === tagEditSymbol);
    if (!item || !item.tags || item.tags.length === 0) {
        container.innerHTML = '<span class="tag-empty-note">タグがありません</span>';
        return;
    }

    let html = '';
    item.tags.forEach(tag => {
        const color = getTagColor(tag);
        html += `<span class="tag-chip editable" style="--tag-hue:${color}">
            ${escapeHtml(tag)}
            <button class="tag-remove-btn" onclick="removeTag('${escapeAttr(tag)}')" title="削除">✕</button>
        </span>`;
    });
    container.innerHTML = html;
}

function addTagFromInput() {
    const input = document.getElementById('tag-input');
    const tag = input.value.trim();
    if (!tag) return;
    input.value = '';
    addTagToItem(tagEditSymbol, tag);
}

function addPresetTag(tag) {
    addTagToItem(tagEditSymbol, tag);
}

function addTagToItem(symbol, tag) {
    const item = listItems.find(i => i.symbol === symbol);
    if (!item) return;
    if (!item.tags) item.tags = [];
    if (item.tags.includes(tag)) return;

    item.tags.push(tag);
    renderCurrentTags();
    renderListTable();
    syncTagsToServer(symbol, item.tags);
}

function removeTag(tag) {
    const item = listItems.find(i => i.symbol === tagEditSymbol);
    if (!item || !item.tags) return;
    item.tags = item.tags.filter(t => t !== tag);
    renderCurrentTags();
    renderListTable();
    syncTagsToServer(tagEditSymbol, item.tags);
}

async function syncTagsToServer(symbol, tags) {
    if (!currentUser || !currentListId) return;
    try {
        await fetchAPI(`/user/${currentUser.id}/lists/${currentListId}/items/${symbol}/tags`, {
            method: 'PUT',
            body: JSON.stringify({ tags }),
        });
    } catch (err) {
        console.warn('Tag sync failed:', err);
    }
}

function getTagColor(tag) {
    let hash = 0;
    for (let i = 0; i < tag.length; i++) {
        hash = tag.charCodeAt(i) + ((hash << 5) - hash);
    }
    return Math.abs(hash % 360);
}

// ===== Account Management =====
function toggleAccountMenu() {
    const menu = document.getElementById('account-menu');
    menu.classList.toggle('hidden');

    if (!menu.classList.contains('hidden')) {
        setTimeout(() => {
            document.addEventListener('click', closeAccountMenuOnOutside, { once: true });
        }, 10);
    }
}

function closeAccountMenuOnOutside(e) {
    const section = document.querySelector('.account-section');
    if (!section.contains(e.target)) {
        document.getElementById('account-menu').classList.add('hidden');
    }
}

function updateAccountUI() {
    const btnLabel = document.getElementById('account-btn-label');
    const menuUser = document.getElementById('account-menu-user');
    const menuGuest = document.getElementById('account-menu-guest');
    const accountBtn = document.getElementById('account-btn');

    if (currentUser) {
        btnLabel.textContent = currentUser.username;
        menuUser.classList.remove('hidden');
        menuGuest.classList.add('hidden');
        document.getElementById('account-menu-username').textContent = `👤 ${currentUser.username}`;
        accountBtn.classList.add('logged-in');
    } else {
        btnLabel.textContent = 'ログイン';
        menuUser.classList.add('hidden');
        menuGuest.classList.remove('hidden');
        accountBtn.classList.remove('logged-in');
    }
    document.getElementById('account-menu').classList.add('hidden');
}

// ===== Auth Modal =====
let authMode = 'login';

function openAuthModal(mode) {
    authMode = mode;
    document.getElementById('account-menu').classList.add('hidden');
    document.getElementById('auth-modal-overlay').classList.remove('hidden');
    document.getElementById('auth-username').value = '';
    document.getElementById('auth-password').value = '';
    document.getElementById('auth-error').classList.add('hidden');

    if (mode === 'login') {
        document.getElementById('auth-modal-title').textContent = 'ログイン';
        document.getElementById('auth-submit-btn').textContent = 'ログイン';
        document.getElementById('auth-toggle-text').textContent = 'アカウントをお持ちでない方は';
        document.getElementById('auth-toggle-link').textContent = '新規登録';
    } else {
        document.getElementById('auth-modal-title').textContent = '新規登録';
        document.getElementById('auth-submit-btn').textContent = '登録';
        document.getElementById('auth-toggle-text').textContent = '既にアカウントをお持ちの方は';
        document.getElementById('auth-toggle-link').textContent = 'ログイン';
    }

    setTimeout(() => document.getElementById('auth-username').focus(), 100);
}

function closeAuthModal() {
    document.getElementById('auth-modal-overlay').classList.add('hidden');
}

function toggleAuthMode(e) {
    e.preventDefault();
    openAuthModal(authMode === 'login' ? 'register' : 'login');
}

async function submitAuth() {
    const username = document.getElementById('auth-username').value.trim();
    const password = document.getElementById('auth-password').value;
    const errorEl = document.getElementById('auth-error');

    if (!username || !password) {
        errorEl.textContent = 'ユーザー名とパスワードを入力してください';
        errorEl.classList.remove('hidden');
        return;
    }

    const submitBtn = document.getElementById('auth-submit-btn');
    submitBtn.disabled = true;
    submitBtn.textContent = '処理中...';

    try {
        const endpoint = authMode === 'login' ? '/user/login' : '/user/register';
        const user = await fetchAPI(endpoint, {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });

        currentUser = user;
        localStorage.setItem('stockAnalyzerUser', JSON.stringify(user));
        updateAccountUI();
        closeAuthModal();
        showToast(authMode === 'login' ? 'ログインしました' : 'アカウントを作成しました', 'success');

        // ログイン/登録直後にデフォルトリストを読み込み
        await loadDefaultList();
    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove('hidden');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = authMode === 'login' ? 'ログイン' : '登録';
    }
}

function logoutUser() {
    currentUser = null;
    currentListId = null;
    listItems = [];
    activeTagFilter = null;
    localStorage.removeItem('stockAnalyzerUser');
    updateAccountUI();
    renderListTable();
    showToast('ログアウトしました', 'info');
}

// ===== Toast Notifications =====
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
    toast.innerHTML = `<span class="toast-icon">${icons[type] || 'ℹ'}</span><span class="toast-message">${escapeHtml(message)}</span>`;

    container.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('toast-hide');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ===== Formatting Utilities =====
function formatCurrency(value, currency) {
    if (value == null) return '—';
    try {
        let displayValue = value;
        let displayCurrency = currency || 'USD';

        // USDの場合は円換算する
        if (displayCurrency === 'USD' && exchangeRateUSDJPY) {
            displayValue = value * exchangeRateUSDJPY;
            displayCurrency = 'JPY';
        }

        const locale = displayCurrency === 'JPY' ? 'ja-JP' : 'en-US';
        return new Intl.NumberFormat(locale, {
            style: 'currency',
            currency: displayCurrency,
            minimumFractionDigits: displayCurrency === 'JPY' ? 0 : 2,
            maximumFractionDigits: displayCurrency === 'JPY' ? 0 : 2,
        }).format(displayValue);
    } catch {
        return value.toLocaleString();
    }
}

function formatLargeNumber(value, currency) {
    if (value == null) return '—';
    
    let displayValue = value;
    let isJPY = currency === 'JPY';

    // USDの場合は円換算
    if ((!currency || currency === 'USD') && exchangeRateUSDJPY) {
        displayValue = value * exchangeRateUSDJPY;
        isJPY = true;
    }

    const abs = Math.abs(displayValue);
    
    if (isJPY) {
        if (abs >= 1e12) return '¥' + (displayValue / 1e12).toFixed(2) + '兆';
        if (abs >= 1e8)  return '¥' + (displayValue / 1e8).toFixed(2) + '億';
        if (abs >= 1e4)  return '¥' + (displayValue / 1e4).toFixed(2) + '万';
        return '¥' + displayValue.toLocaleString();
    } else {
        if (abs >= 1e12) return '$' + (displayValue / 1e12).toFixed(2) + 'T';
        if (abs >= 1e9)  return '$' + (displayValue / 1e9).toFixed(2) + 'B';
        if (abs >= 1e6)  return '$' + (displayValue / 1e6).toFixed(2) + 'M';
        if (abs >= 1e3)  return '$' + (displayValue / 1e3).toFixed(1) + 'K';
        return '$' + displayValue.toLocaleString();
    }
}

function formatTimestamp(ts) {
    try {
        const date = new Date(ts);
        return date.toLocaleString('ja-JP');
    } catch {
        return ts;
    }
}

function formatNewsDate(dateStr) {
    try {
        const date = new Date(dateStr);
        if (isNaN(date.getTime())) return dateStr;
        return date.toLocaleDateString('ja-JP', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch {
        return dateStr;
    }
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escapeAttr(str) {
    return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// ===== Event Listeners =====
document.getElementById('search-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') searchStock();
});

document.getElementById('list-add-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') addToList();
});

document.getElementById('tag-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') addTagFromInput();
});

document.getElementById('auth-password').addEventListener('keydown', e => {
    if (e.key === 'Enter') submitAuth();
});
