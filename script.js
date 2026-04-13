const IS_LOCAL_FILE = window.location.protocol === 'file:';
const API_BASE = IS_LOCAL_FILE ? "http://localhost:8000" : ""; // Use relative path if hosted, else localhost
const API_URL = `${API_BASE}/api/v1/dashboard`;
const AI_API_URL = `${API_BASE}/api/v2/ai-insights`;
const SCREENER_URL = `${API_BASE}/api/v1/screener`;
const SEARCH_URL = `${API_BASE}/api/v1/search`;
const ROTATION_URL = `${API_BASE}/api/v1/sector-rotation`;
const HITS_URL = `${API_BASE}/api/v1/momentum-hits`;
const EARLY_SETUPS_URL = `${API_BASE}/api/v1/early-setups`;
const SIGNAL_PERF_URL = `${API_BASE}/api/v1/signal-performance`;
const TRADE_PERF_URL = `${API_BASE}/api/v1/trade-performance`;

// Safety check for file protocol only if backend isn't running locally for it
if (IS_LOCAL_FILE) {
    console.warn("Running from file protocol. Ensure backend is running at http://localhost:8000");
}

let chart, candlestickSeries;
let levelsLayer = [];
let rotationApp; // Added for sector rotation
let intelligenceApp; // Added for market intelligence
let fetchController = null; // To abort previous fetches
window.currentMarketStatus = null;
window.loginToFyers = function() {
    console.log("Initiating Fyers Login...");
    const width = 600, height = 700;
    const left = (window.innerWidth / 2) - (width / 2);
    const top = (window.innerHeight / 2) - (height / 2);
    window.open(`${API_BASE}/api/v1/fyers/login`, 'FyersLogin', `width=${width},height=${height},top=${top},left=${left}`);
};

async function checkFyersStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/v1/fyers/status`);
        const result = await res.json();
        const dot = document.getElementById('fyers-status-dot');
        const text = document.getElementById('fyers-status-text');
        
        if (result.status === 'success' && result.data.is_connected) {
            if (dot) dot.className = 'w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.7)]';
            if (text) text.textContent = 'Online';
            
            // Update button if exists
            const loginBtn = document.getElementById('fyers-login-btn');
            if (loginBtn) {
                loginBtn.textContent = 'ONLINE';
                loginBtn.classList.remove('text-blue-400');
                loginBtn.classList.add('text-green-400');
            }
        } else {
            if (dot) dot.className = 'w-2 h-2 rounded-full bg-gray-600';
            if (text) text.textContent = 'Offline';
            const loginBtn = document.getElementById('fyers-login-btn');
            if (loginBtn) {
                loginBtn.textContent = 'CONNECT';
                loginBtn.classList.add('text-blue-400');
                loginBtn.classList.remove('text-green-400');
            }
        }
    } catch (e) {
        console.error('Fyers status check failed', e);
    }
}
async function checkMarketStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/v1/market-status`);
        const result = await res.json();
        if (result.status === 'success') {
            window.currentMarketStatus = result.data;
            applyMarketStatusState(result.data);
        }
    } catch (e) { console.error('Market status fetch failed', e); }
}

function applyMarketStatusState(ms) {
    const banner = document.getElementById('market-status-banner');
    if (!banner) return;
    
    if (ms.mode !== 'OPEN') {
        banner.classList.remove('hidden');
        const title = document.getElementById('market-status-title');
        const desc = document.getElementById('market-status-desc');
        const icon = document.getElementById('market-status-icon');
        const time = document.getElementById('market-status-time');
        
        if (ms.mode === 'CLOSED') {
            banner.className = 'glass rounded-xl border border-orange-500/50 bg-orange-950/20 p-3 mb-4 flex items-center justify-between animate-in fade-in duration-500';
            title.className = 'text-xs font-bold uppercase tracking-widest text-orange-400';
            title.textContent = 'MARKET CLOSED';
            icon.textContent = '🌙';
        } else if (ms.mode === 'PRE_MARKET') {
            banner.className = 'glass rounded-xl border border-blue-500/50 bg-blue-950/20 p-3 mb-4 flex items-center justify-between animate-in fade-in duration-500';
            title.className = 'text-xs font-bold uppercase tracking-widest text-blue-400';
            title.textContent = 'PRE-MARKET';
            icon.textContent = '🌅';
        } else if (ms.mode === 'POST_MARKET') {
            banner.className = 'glass rounded-xl border border-purple-500/50 bg-purple-950/20 p-3 mb-4 flex items-center justify-between animate-in fade-in duration-500';
            title.className = 'text-xs font-bold uppercase tracking-widest text-purple-400';
            title.textContent = 'POST-MARKET';
            icon.textContent = '🌆';
        }
        
        desc.textContent = ms.message + ' - Showing last session data';
        time.textContent = 'Status as of: ' + new Date(ms.last_updated).toLocaleTimeString();
    } else {
        banner.classList.add('hidden');
    }
}


function isIntelligenceModeActive() {
    const intelToggle = document.getElementById('intelligence-toggle');
    if (intelToggle) return !!intelToggle.checked;

    const intelligenceSection = document.getElementById('intelligence-section');
    return !!(intelligenceSection && !intelligenceSection.classList.contains('hidden'));
}

// Quick Filter State
window.activeQuickFilters = {
    leaders: false,
    smart: false,
    momentum: false,
    early: false
};

window.toggleQuickFilter = function (filterName) {
    if (window.activeQuickFilters[filterName] !== undefined) {
        window.activeQuickFilters[filterName] = !window.activeQuickFilters[filterName];

        // Update UI Button states
        const btn = document.getElementById(`filter-${filterName}`);
        if (btn) {
            if (window.activeQuickFilters[filterName]) {
                btn.classList.add('bg-gray-800', 'border-gray-600', 'text-white');
                if (filterName === 'leaders') btn.classList.add('border-green-500/50', 'text-green-400');
                if (filterName === 'smart') btn.classList.add('border-blue-500/50', 'text-blue-400');
                if (filterName === 'momentum') btn.classList.add('border-indigo-500/50', 'text-indigo-400');
            } else {
                btn.className = `flex-1 py-1.5 rounded-lg border border-gray-800 bg-gray-900/50 text-[9px] font-black text-gray-500 uppercase transition-all`;
                if (filterName === 'leaders') btn.classList.add('hover:border-green-500/50', 'hover:text-green-400');
                if (filterName === 'smart') btn.classList.add('hover:border-blue-500/50', 'hover:text-blue-400');
                if (filterName === 'momentum') btn.classList.add('hover:border-indigo-500/50', 'hover:text-indigo-400');
            }
        }

        // Trigger table re-render
        if (window.intelligenceApp) {
            window.intelligenceApp._renderHitsTable();
        }
    }
}

function initChart() {
    const chartContainer = document.getElementById('tv-chart');
    console.log('Initializing chart, container:', chartContainer);
    console.log('Container dimensions:', chartContainer.clientWidth, 'x', chartContainer.clientHeight);

    chart = LightweightCharts.createChart(chartContainer, {
        layout: {
            background: { color: '#0b0e11' },
            textColor: '#d1d4dc',
        },
        grid: {
            vertLines: { color: '#1f2937' },
            horzLines: { color: '#1f2937' },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
        },
        rightPriceScale: {
            borderColor: '#374151',
        },
        timeScale: {
            borderColor: '#374151',
            timeVisible: true,
            secondsVisible: false,
        },
    });

    candlestickSeries = chart.addCandlestickSeries({
        upColor: '#00c076',
        downColor: '#f6465d',
        borderVisible: false,
        wickUpColor: '#00c076',
        wickDownColor: '#f6465d',
    });

    console.log('Chart initialized successfully');

    window.addEventListener('resize', () => {
        chart.resize(chartContainer.clientWidth, chartContainer.clientHeight);
    });
}


// 5. Screener Logic
document.getElementById('screener-toggle').addEventListener('change', function (e) {
    const panel = document.getElementById('screener-panel');
    if (e.target.checked) {
        panel.classList.remove('hidden');
        runScreener();
    } else {
        panel.classList.add('hidden');
    }
});

async function runScreener() {
    const list = document.getElementById('screener-list');
    const count = document.getElementById('screener-count');

    list.innerHTML = '<p class="text-xs text-indigo-400/60 animate-pulse">Running 9-point fundamental check on Nifty 10...</p>';
    count.textContent = 'SCANNING...';

    try {
        const response = await fetch(`${SCREENER_URL}?_=${Date.now()}`);
        const data = await response.json();

        if (data.status === 'success') {
            count.textContent = `${data.count} MATCH(ES)`;
            list.innerHTML = '';

            if (data.matches.length === 0) {
                const isClosed = window.currentMarketStatus && window.currentMarketStatus.mode === 'CLOSED';
                list.innerHTML = `<p class="text-xs text-gray-500">${isClosed ? 'No live data (market closed). Awaiting next session.' : 'No stocks currently match all 9 strict growth criteria.'}</p>`;
                return;
            }

            data.matches.forEach(stock => {
                const card = document.createElement('div');
                card.className = "min-w-[180px] bg-gray-900 border border-indigo-500/30 p-3 rounded-xl hover:border-indigo-400 transition-all cursor-pointer";
                card.onclick = () => {
                    document.getElementById('symbol-input').value = stock.symbol;
                    fetchData(stock.symbol, document.getElementById('tf-selector').value);
                };

                card.innerHTML = `
                    <div class="flex justify-between items-start mb-2">
                        <span class="font-bold text-sm text-white">${stock.symbol}</span>
                        <span class="text-[10px] text-up font-bold">MATCH</span>
                    </div>
                    <div class="space-y-1">
                        <div class="flex justify-between text-[10px]">
                            <span class="text-gray-500">Sales Gr</span>
                            <span class="text-indigo-300 font-bold">${stock.sales_growth}</span>
                        </div>
                        <div class="flex justify-between text-[10px]">
                            <span class="text-gray-500">PEG</span>
                            <span class="text-white font-mono">${stock.peg}</span>
                        </div>
                        <div class="flex justify-between text-[10px]">
                            <span class="text-gray-500">D/E</span>
                            <span class="text-white font-mono">${stock.debt_equity}</span>
                        </div>
                    </div>
                `;
                list.appendChild(card);
            });
        }
    } catch (error) {
        console.error("Screener error:", error);
        count.textContent = 'ERROR';
        list.innerHTML = '<p class="text-xs text-down">Failed to connect to screener service.</p>';
    }
}
async function fetchData(isBackground = false) {
    const loader = document.getElementById('loading-overlay');
    const showLoader = isBackground !== true;

    try {
        if (loader && showLoader) {
            loader.classList.remove('hidden');
            loader.style.display = 'flex';

            // Centralized Safeguard: Hide loader after 15s if it hangs
            if (window._loaderTimeout) clearTimeout(window._loaderTimeout);
            window._loaderTimeout = setTimeout(() => {
                if (loader && !loader.classList.contains('hidden')) {
                    console.warn("[UI] Loader safeguard triggered after 15s timeout.");
                    loader.classList.add('hidden');
                    loader.style.display = 'none';
                }
            }, 15000);
        }

        const symbolInput = document.getElementById('symbol-input');
        let symbol = symbolInput ? symbolInput.value.trim().toUpperCase() : "NIFTY50";
        if (!symbol) symbol = "NIFTY50"; // Fallback to avoid empty ticker error
        
        const tfSelector = document.getElementById('tf-selector');
        const tf = tfSelector ? tfSelector.value : '15m';
        const stratSelector = document.getElementById('strategy-selector');
        const strategy = stratSelector ? stratSelector.value : 'SR';

        console.log(`[Fetch] ${symbol} @ ${tf} | Strategy: ${strategy} (Background: ${isBackground})`);

        const response = await fetch(`${API_URL}?symbol=${encodeURIComponent(symbol)}&tf=${tf}&strategy=${strategy}&_=${Date.now()}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        if (data && data.meta) {
            window.lastReceivedData = data;
            
            // Update live indicator based on specific source
            const liveIndicator = document.getElementById('live-indicator');
            if (liveIndicator) {
                if (data.source === 'fyers') {
                    liveIndicator.innerHTML = '<span class="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></span> FYERS LIVE';
                    liveIndicator.className = 'flex items-center gap-1 text-[9px] text-green-400 font-bold';
                    liveIndicator.title = "Real-time data from Fyers API";
                } else if (data.source === 'yahoo') {
                    liveIndicator.innerHTML = '<span class="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse"></span> YAHOO LIVE';
                    liveIndicator.className = 'flex items-center gap-1 text-[9px] text-blue-400 font-bold';
                    liveIndicator.title = "Live data from Yahoo Finance";
                } else if (data.source === 'cache' || data.source === 'fallback') {
                    liveIndicator.innerHTML = '<span class="w-1.5 h-1.5 bg-yellow-500 rounded-full"></span> OFFLINE CACHE';
                    liveIndicator.className = 'flex items-center gap-1 text-[9px] text-yellow-500 font-bold';
                    liveIndicator.title = "Rate limit reached or offline. Showing last cached data.";
                }
            }

            updateUI(data, isBackground);
            if (data.market_status) {
                window.currentMarketStatus = data.market_status;
                applyMarketStatusState(data.market_status);
            }
        } else {
            throw new Error(data.message || "Malformed API response");
        }
    } catch (error) {
        console.error("Fetch failed:", error);

        const isRateLimit = error.message.includes("Rate Limit") || error.message.includes("Too Many Requests") || error.message.includes("No data found");
        
        // Show error UI if NOT background, OR if it's a critical rate limit error
        if (!isBackground || isRateLimit) {
            const chartParent = document.getElementById('chart-parent');
            if (chartParent) {
                // If we don't have a chart yet, or it's a rate limit error, show/update error area
                if (!chart || chartParent.innerHTML.includes('Failed to load data') || isRateLimit) {
                    const tvChart = document.getElementById('tv-chart');
                    if (tvChart && isRateLimit) tvChart.classList.add('hidden'); // Hide chart area for rate limit message

                    let errDiv = document.getElementById('chart-error-msg');
                    if (!errDiv) {
                        errDiv = document.createElement('div');
                        errDiv.id = 'chart-error-msg';
                        errDiv.className = 'absolute inset-0 flex flex-col items-center justify-center p-6 text-center bg-gray-900/80 z-50 rounded-2xl border border-yellow-500/30';
                        chartParent.appendChild(errDiv);
                    }
                    errDiv.classList.remove('hidden');
                    
                    errDiv.innerHTML = `
                        <div class="flex flex-col items-center gap-3">
                            <span class="text-3xl">${isRateLimit ? '⏳' : '❌'}</span>
                            <p class="${isRateLimit ? 'text-yellow-500' : 'text-red-500'} font-bold text-lg">${isRateLimit ? 'Yahoo Finance Cooldown' : 'Sync Error'}</p>
                            <p class="text-xs text-gray-400 max-w-[280px]">${isRateLimit ? 'The data provider is temporarily limiting requests. This usually resolves in 2-5 minutes.' : error.message}</p>
                            <button onclick="window.fetchData()" class="mt-2 px-6 py-2 bg-indigo-600 rounded-xl text-xs font-bold hover:bg-indigo-500 transition-all shadow-lg">RETRY SYNC</button>
                        </div>
                    `;
                }
            }
        }
    } finally {
        // ALWAYS try to hide loader in finally if it was showing
        if (loader) {
            loader.classList.add('hidden');
            loader.style.display = 'none';
        }
    }
}
window.fetchData = fetchData;

function updateStrategyUI(data) {
    try {
        const strategy = data.meta.strategy || 'SR';
        const strat = data.strategy || {};
        const metrics = strat.additionalMetrics || {};
        const tech = data.technical || {};
        const insights = data.insights || {};
        const summary = data.summary || {};

        console.log(`[UI] Updating decision metrics panel`);

        // Update Positives
        const adxVal = parseFloat(insights.adx || metrics.adx || 0);
        const adxText = adxVal > 25 ? 'Strong Trend' : adxVal > 15 ? 'Moderate' : 'Weak';
        document.getElementById('metric-adx').textContent = `${adxVal.toFixed(1)} (${adxText})`;
        document.getElementById('metric-adx').className = `text-sm font-bold ${adxVal > 25 ? 'text-up' : 'text-white'}`;

        const volRatio = parseFloat(insights.volRatio || metrics.volRatio || 1);
        document.getElementById('metric-volume').textContent = `${volRatio.toFixed(2)}x ${volRatio > 1.2 ? 'Spike' : 'Normal'}`;
        document.getElementById('metric-volume').className = `text-sm font-bold ${volRatio > 1.2 ? 'text-up' : 'text-white'}`;

        const setupText = (insights.retest ? 'Retest' : '') + (insights.retest && tech.isBreakout ? ' + ' : '') + (tech.isBreakout ? 'Breakout' : '');
        document.getElementById('metric-setup').textContent = setupText || 'No Setup';
        document.getElementById('metric-setup').className = `text-sm font-bold ${setupText ? 'text-up' : 'text-gray-500'}`;

        const s0 = summary.nearest_support;
        const cmp = data.meta.cmp;
        const distS = s0 ? ((cmp - s0) / cmp * 100).toFixed(1) : '--';
        document.getElementById('metric-sr').textContent = s0 ? `${distS}% from S` : 'No Level';
        document.getElementById('metric-sr').className = `text-sm font-bold ${parseFloat(distS) < 2 ? 'text-up' : 'text-white'}`;

        // Update Risks
        const mo = (tech.momentumStrength || 'WEAK').toUpperCase();
        document.getElementById('metric-momentum').textContent = mo;
        document.getElementById('metric-momentum').className = `text-sm font-bold ${mo === 'STRONG' ? 'text-white' : 'text-down'}`;

        const vola = tech.volHigh ? 'High Volatility' : 'Stable';
        document.getElementById('metric-vola').textContent = vola;
        document.getElementById('metric-vola').className = `text-sm font-bold ${tech.volHigh ? 'text-down' : 'text-white'}`;

        const sector = (data.sector_info?.state || 'NEUTRAL').toUpperCase();
        document.getElementById('metric-sector').textContent = sector;
        document.getElementById('metric-sector').className = `text-sm font-bold ${['LEADING', 'IMPROVING'].includes(sector) ? 'text-white' : 'text-down'}`;

        const regime = summary.market_regime || 'UNKNOWN';
        document.getElementById('metric-regime').textContent = regime.replace('_', ' ');
        document.getElementById('metric-regime').className = `text-sm font-bold ${regime === 'RISK_ON' ? 'text-white' : 'text-down'}`;

        // Update Swing Metrics
        if (strategy === 'SWING') {
            document.getElementById('swing-structure').textContent = metrics.marketStructure || 'NEUTRAL';
            document.getElementById('swing-ema').textContent = insights.ema_bias || 'NEUTRAL';
            document.getElementById('swing-htf').textContent = metrics.htfTrend || 'NEUTRAL';
            document.getElementById('swing-pullback').textContent = metrics.pullbackPct ? `${metrics.pullbackPct}%` : 'NO';
        }

        // Update Dynamic Metrics Panels
        const dynPanels = document.getElementById('strategy-dynamic-panels');
        if (dynPanels) {
            const hasDynamicData = strategy === 'FIBONACCI' || strategy === 'DEMAND_SUPPLY';
            dynPanels.style.display = hasDynamicData ? 'grid' : 'none';
            dynPanels.classList.remove('hidden'); // Ensure hidden class is removed if toggling display

            if (hasDynamicData) {
                const c1T = document.getElementById('strat-card-1-title');
                const c1V = document.getElementById('strat-card-1-val');
                const c2T = document.getElementById('strat-card-2-title');
                const c2V = document.getElementById('strat-card-2-val');
                const c3T = document.getElementById('strat-card-3-title');
                const c3V = document.getElementById('strat-card-3-val');

                if (strategy === 'FIBONACCI') {
                    if(c1T) c1T.textContent = 'Retracement';
                    if(c1V) c1V.textContent = metrics.retracementDepth || '--';
                    if(c2T) c2T.textContent = 'Golden Pocket';
                    if(c2V) c2V.textContent = metrics.goldenPocket ? 'YES' : 'NO';
                    if(c2V) c2V.className = metrics.goldenPocket ? 'text-lg font-bold text-yellow-400' : 'text-lg font-bold text-gray-400';
                    if(c3T) c3T.textContent = 'Trend';
                    if(c3V) c3V.textContent = metrics.is_uptrend ? 'BULL' : 'BEAR';
                    if(c3V) c3V.className = metrics.is_uptrend ? 'text-lg font-bold uppercase tracking-widest text-green-400' : 'text-lg font-bold uppercase tracking-widest text-red-400';
                } else if (strategy === 'DEMAND_SUPPLY') {
                    if(c1T) c1T.textContent = 'Departure';
                    if(c1V) c1V.textContent = metrics.departureStrength || 'STRONG';
                    if(c2T) c2T.textContent = 'Zone Range';
                    if(c2V) c2V.textContent = metrics.zoneRange || '--';
                    if(c2V) c2V.className = 'text-lg font-bold text-gray-300';
                    if(c3T) c3T.textContent = 'Vol Spike';
                    if(c3V) c3V.textContent = metrics.volExpansion || 'NONE';
                    if(c3V) c3V.className = 'text-lg font-bold uppercase tracking-widest text-white';
                }
            }
        }

    } catch (err) {
        console.error("Strategy UI update error:", err);
    }
}

function formatVal(v) {
    if (v === undefined || v === null) return '—';
    if (typeof v === 'number') return v.toFixed(2);
    return v;
}

function formatWithCurrency(val, currency = 'INR') {
    if (val === undefined || val === null || val === '—' || val === '---') return '—';
    const symbolMap = { 'INR': '₹', 'USD': '$', 'EUR': '€', 'GBP': '£' };
    const currencySym = symbolMap[currency] || '₹';
    
    if (typeof val === 'number') return `${currencySym}${val.toFixed(2)}`;
    const num = parseFloat(val);
    if (!isNaN(num)) return `${currencySym}${num.toFixed(2)}`;
    return `${currencySym}${val}`;
}

function updateUI(data, isBackground = false) {
    try {
        // Hide error message if it exists
        const errDiv = document.getElementById('chart-error-msg');
        if (errDiv) errDiv.classList.add('hidden');
        const tvChart = document.getElementById('tv-chart');
        if (tvChart) tvChart.classList.remove('hidden');

        // 1. Meta & Summary
        const cmpEl = document.getElementById('cmp');
        if (cmpEl) cmpEl.textContent = formatWithCurrency(data.meta.cmp, data.meta.currency);

        const verTag = document.getElementById('ver-tag');
        if (verTag) verTag.textContent = "v1.5.0 Intelligence Layer";

        // Sync Time
        const syncTime = document.getElementById('sync-time');
        if (syncTime && data.meta.last_update) syncTime.textContent = `${data.meta.last_update}`;

        // Pulse indicators only if price changed
        const liveInd = document.getElementById('live-indicator');
        const lastCmp = window.lastCmpValue || 0;
        const currentCmp = data.meta.cmp;

        if (liveInd && cmpEl && currentCmp !== lastCmp) {
            liveInd.classList.add('text-blue-300');
            cmpEl.classList.add('text-blue-400');
            setTimeout(() => {
                liveInd.classList.remove('text-blue-300');
                cmpEl.classList.remove('text-blue-400');
            }, 500);
            window.lastCmpValue = currentCmp; // Update tracker
        }

        // Update Price Change %
        if (data.ohlcv && data.ohlcv.length > 1) {
            const prevClose = data.ohlcv[data.ohlcv.length - 2].close;
            const change = ((data.meta.cmp - prevClose) / prevClose) * 100;
            const changeEl = document.getElementById('price-change');
            if (changeEl) {
                changeEl.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`;
                changeEl.className = `text-xs font-medium ${change >= 0 ? 'text-up' : 'text-down'}`;
            }
        }

        // Summary details
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = formatWithCurrency(val, data.meta.currency);
        };
        setVal('nearest-support', data.summary.nearest_support);
        setVal('nearest-resistance', data.summary.nearest_resistance);
        setVal('stop-loss', data.summary.stop_loss);
        const rrEl = document.getElementById('risk-reward');
        if (rrEl) rrEl.textContent = data.summary.risk_reward || '—';

        // 8. Hero Strip
        updateHeroDecisionStrip(data);

        // 2. Insights
        const setTxt = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };

        if (data.insights) {
            setTxt('inside-candle', data.insights.inside_candle ? "YES" : "NO");
            setTxt('retest', data.insights.retest ? "CONFIRMED" : "NONE");
            
            const upside = data.insights.upside_pct;
            if (upside !== undefined && upside !== null) {
                setTxt('upside-pct', `+${upside}%`);
            } else {
                setTxt('upside-pct', '0.00%');
            }

            const biasBadge = document.getElementById('bias-badge');
            if (biasBadge) {
                biasBadge.textContent = data.insights.ema_bias || 'NEUTRAL';
                biasBadge.className = `px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest ${data.insights.ema_bias === 'Bullish' ? 'bg-up text-up' :
                    data.insights.ema_bias === 'Caution' ? 'bg-down text-down' : 'bg-gray-800 text-gray-400'
                    }`;
            }
        }

        // 3. AI Insights
        if (data.ai_analysis && data.ai_analysis.status === "success") {
            const ai = data.ai_analysis;
            const pBadge = document.getElementById('ai-priority-badge');
            if (pBadge) {
                pBadge.textContent = `PRIORITY: ${ai.priority.level}`;
                pBadge.className = `px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest ${ai.priority.level === 'HIGH' ? 'bg-indigo-600 text-white animate-pulse' :
                    ai.priority.level === 'MEDIUM' ? 'bg-indigo-900/40 text-indigo-200' : 'bg-gray-800 text-gray-500'
                    }`;
            }

            const bBadge = document.getElementById('ai-breakout-badge');
            if (bBadge) {
                bBadge.textContent = ai.breakout.breakout_quality.replace('_', ' ');
                bBadge.className = `text-[9px] font-bold px-1.5 py-0.5 rounded capitalize ${ai.breakout.breakout_quality === 'LIKELY_GENUINE' ? 'bg-up text-up' :
                    ai.breakout.breakout_quality === 'LIKELY_FAKE' ? 'bg-down text-down' : 'bg-gray-800 text-gray-400'
                    }`;
            }
            const bR = document.getElementById('ai-breakout-reason');
            if (bR) bR.textContent = ai.breakout.reason;

            const rBadge = document.getElementById('ai-regime-badge');
            if (rBadge) {
                rBadge.textContent = ai.regime.market_regime.replace('_', ' ');
                rBadge.className = `text-[9px] font-bold px-1.5 py-0.5 rounded capitalize ${ai.regime.market_regime.startsWith('TRENDING') ? 'bg-blue-900/30 text-blue-400' : 'bg-gray-800 text-gray-400'
                    }`;
            }
            const rR = document.getElementById('ai-regime-reason');
            if (rR) rR.textContent = ai.regime.reason;
        }

        // 4. Levels
        const sL = document.getElementById('support-list');
        const rL = document.getElementById('resistance-list');
        if (sL && rL) {
            sL.innerHTML = '';
            rL.innerHTML = '';
            renderLevelList('support-list', data.levels.primary.supports, 'blue', false);
            renderLevelList('support-list', data.levels.mtf.supports, 'blue', true);
            renderLevelList('resistance-list', data.levels.primary.resistances, 'green', false);
            renderLevelList('resistance-list', data.levels.mtf.resistances, 'green', true);
        }

        // 5. Chart
        if (data.ohlcv && data.ohlcv.length > 0 && candlestickSeries) {
            candlestickSeries.setData(data.ohlcv);
            
            // Only auto-fit if it's NOT a background refresh
            if (!isBackground) {
                chart.timeScale().fitContent();
            }
            
            // Enable time labels for intraday timeframes, hide for daily+
            const tf = document.getElementById('tf-selector').value;
            const isIntraday = ['5m', '15m', '75m', '1H', '2H', '4H'].includes(tf);
            chart.applyOptions({
                timeScale: { timeVisible: isIntraday, secondsVisible: false }
            });
        }

        // 6. Fundamentals
        const fundCard = document.getElementById('fundamentals-card');
        if (data.fundamentals && fundCard) {
            fundCard.classList.remove('hidden');
            const f = data.fundamentals;
            const sectorEl = document.getElementById('fund-sector');
            if (sectorEl) sectorEl.textContent = f.sector || '—';

            const mcapEl = document.getElementById('fund-mcap');
            if (mcapEl) mcapEl.textContent = f.market_cap || '—';

            const peEl = document.getElementById('fund-pe');
            if (peEl) {
                peEl.textContent = f.pe_ratio || '—';
                if (f.pe_ratio) {
                    peEl.className = `text-sm font-bold ${f.pe_ratio < 20 ? 'text-up' : f.pe_ratio > 50 ? 'text-down' : 'text-white'}`;
                }
            }

            setTxt('fund-roe', f.roe ? `${f.roe}%` : '—');
            setTxt('fund-div', f.dividend_yield ? `${f.dividend_yield}%` : '—');
            setTxt('fund-52h', f['52w_high'] || '—');
            setTxt('fund-52l', f['52w_low'] || '—');

            const rB = document.getElementById('fund-range-bar');
            if (rB && f['52w_high'] && f['52w_low']) {
                let p = ((data.meta.cmp - f['52w_low']) / (f['52w_high'] - f['52w_low'])) * 100;
                rB.style.width = `${Math.max(0, Math.min(100, p))}%`;
            }
        } else if (fundCard) {
            fundCard.classList.add('hidden');
        }

        // 7. Finally draw levels on chart
        window.lastReceivedData = data;
        drawLevelsOnChart(data.levels, data);


        // 9. Strategy Specific UI Toggles
        updateStrategyUI(data);

    } catch (e) {
        console.error("UI Update Error:", e);
    }
}

function updateHeroDecisionStrip(data) {
    const heroStrip = document.getElementById('hero-decision-strip');
    if (!heroStrip || !data.summary) return;
    
    heroStrip.classList.remove('hidden');
    
    // Action Badge
    const action = data.action || 'WATCH';
    const actionBadge = document.getElementById('hero-action-badge');
    const badgeSpan = actionBadge.querySelector('span');
    const badgeIcon = actionBadge.querySelector('i');
    
    badgeSpan.textContent = action;
    actionBadge.className = 'decision-badge';
    
    if (action.includes('BUY') || action.includes('ENTRY')) {
        actionBadge.classList.add('decision-buy');
        badgeIcon.className = 'fas fa-check-circle';
    } else if (action === 'WAIT' || action.includes('HOLD')) {
        actionBadge.classList.add('decision-no-trade');
        badgeIcon.className = 'fas fa-times-circle';
    } else {
        actionBadge.classList.add('decision-watch');
        badgeIcon.className = 'fas fa-eye';
    }

    // POWER HEADER INTEGRATION (Keep metrics persistent in Navigation Bar)
    const currency = data.meta?.currency || 'INR';
    const hPrice = document.getElementById('hero-price');
    if (hPrice) hPrice.textContent = formatWithCurrency(data.meta.cmp, currency);
    
    // Fallback: If no setup entry, use current market price for Entry visibility
    const hEntry = document.getElementById('hero-entry');
    const hSl = document.getElementById('hero-sl');
    const hTarget = document.getElementById('hero-target');
    const hRR = document.getElementById('hero-rr');

    if (hEntry) hEntry.textContent = formatWithCurrency(data.setup?.entry || data.summary?.entry_price || data.meta.cmp, currency);
    if (hSl) hSl.textContent = formatWithCurrency(data.setup?.sl || data.summary?.stop_loss, currency);
    if (hTarget) hTarget.textContent = formatWithCurrency(data.setup?.target || data.summary?.target_price || data.summary?.target, currency);
    if (hRR) hRR.textContent = (data.setup?.rr || data.summary?.risk_reward || 0).toFixed(2);
}

function renderLevelList(containerId, levels, color, isMTF) {
    const list = document.getElementById(containerId);
    if (!list || !levels || !Array.isArray(levels)) return;

    const data = window.lastReceivedData;
    const symbolMap = { 'INR': '₹', 'USD': '$', 'EUR': '€', 'GBP': '£' };
    const currencySym = (data && data.meta && data.meta.currency) ? (symbolMap[data.meta.currency] || data.meta.currency + ' ') : '₹';

    levels.forEach((level, index) => {
        const div = document.createElement('div');
        div.className = `flex items-center justify-between px-2 py-1 rounded-lg bg-gray-900/60 border ${isMTF ? 'border-gray-800/30 opacity-60' : 'border-gray-800/50'} hover:border-gray-700 transition-all cursor-default`;

        const labelText = level.timeframe === 'ZONE' ? 'Z' : (isMTF ? level.timeframe || 'MTF' : level.timeframe || ('L' + (index + 1)));
        const timeframeLabel = level.timeframe || '—';

        div.title = `Price: ${level.price}\nTimeframe: ${timeframeLabel}\nTouches: ${level.touches || 0}`;
        div.innerHTML = `
            <span class="text-[9px] font-bold px-1 py-0.5 rounded text-[10px] bg-gray-800 text-gray-400 uppercase">${labelText}</span>
            <span class="font-bold mono text-[11px] ${isMTF ? 'text-gray-500' : 'text-white'}">${currencySym}${formatVal(level.price)}</span>
        `;
        list.appendChild(div);
    });
}

function drawLevelsOnChart(levels, fullData = null) {
    if (!candlestickSeries || !chart) return;

    // Clear existing primitives
    levelsLayer.forEach(line => {
        try { candlestickSeries.removePriceLine(line); } catch(e) {}
    });
    
    // Remove zone area series if they exist
    if (window.targetZoneSeries) { chart.removeSeries(window.targetZoneSeries); window.targetZoneSeries = null; }
    if (window.stopZoneSeries) { chart.removeSeries(window.stopZoneSeries); window.stopZoneSeries = null; }
    
    // Remove existing floating tags
    const existingTags = document.querySelectorAll('.chart-tag');
    existingTags.forEach(t => t.remove());

    levelsLayer = [];

    const action = fullData ? (fullData.action || 'WAIT') : 'WAIT';
    const isNoTrade = action === 'WAIT' || action === 'HOLD' || (fullData && !fullData.summary.stop_loss);
    
    const noTradeOverlay = document.getElementById('no-trade-overlay');
    if (noTradeOverlay) noTradeOverlay.style.display = isNoTrade ? 'flex' : 'none';

    // 1. Chart Header Action Tag (Primary Feedback)
    const headerAction = document.getElementById('chart-header-action');
    if (headerAction && fullData) {
        const isEntry = action.includes('BUY') || action.includes('ENTRY');
        headerAction.innerHTML = `
            <div class="px-3 py-1 bg-white/5 border border-white/5 rounded-lg flex items-center gap-2">
                <span class="${isEntry ? 'text-green-400' : 'text-amber-400'} animate-pulse text-[10px]">●</span>
                <span class="text-[9px] font-black text-white tracking-widest uppercase">${action}</span>
            </div>
        `;
        headerAction.classList.remove('hidden');
    }

    // 2. Draw Execution Overlays (Entry, SL, Target)
    if (fullData && fullData.summary && !isNoTrade) {
        const s = fullData.summary;
        const entry = fullData.meta.cmp;
        const sl = parseFloat(s.stop_loss);
        const tgt = parseFloat(s.target);

        if (entry && sl && tgt) {
            // SL (Red - Solid)
            levelsLayer.push(candlestickSeries.createPriceLine({
                price: sl,
                color: '#EF4444',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: 'STOP LOSS',
            }));

            // Target (Green - Solid)
            levelsLayer.push(candlestickSeries.createPriceLine({
                price: tgt,
                color: '#22C55E',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: 'TARGET',
            }));

            // EXECUTION ZONES (Shaded Areas)
            const ohlcv = fullData.ohlcv || [];
            if (ohlcv.length > 0) {
                // Profit Zone
                window.targetZoneSeries = chart.addAreaSeries({
                    topColor: 'rgba(34, 197, 94, 0.15)',
                    bottomColor: 'rgba(34, 197, 94, 0.02)',
                    lineColor: 'transparent',
                    lineWidth: 0,
                    priceLineVisible: false,
                    lastValueVisible: false,
                });
                window.targetZoneSeries.setData(ohlcv.map(d => ({ time: d.time, value: tgt })));
                window.targetZoneSeries.applyOptions({ baseValue: { type: 'price', price: entry } });

                // Risk Zone
                window.stopZoneSeries = chart.addAreaSeries({
                    topColor: 'rgba(239, 68, 68, 0.12)',
                    bottomColor: 'rgba(239, 68, 68, 0.05)',
                    lineColor: 'transparent',
                    lineWidth: 0,
                    priceLineVisible: false,
                    lastValueVisible: false,
                });
                window.stopZoneSeries.setData(ohlcv.map(d => ({ time: d.time, value: entry })));
                window.stopZoneSeries.applyOptions({ baseValue: { type: 'price', price: sl } });
            }
        }
    }

    if (!levels) return;

    const cmp = fullData ? fullData.meta.cmp : 0;
    const strategy = fullData?.meta?.strategy || 'SR';

    // Helper to add lines
    const addLine = (lv, color, title = '', dashed = true) => {
        levelsLayer.push(candlestickSeries.createPriceLine({
            price: lv.price,
            color: color,
            lineWidth: 1,
            lineStyle: dashed ? LightweightCharts.LineStyle.Dashed : LightweightCharts.LineStyle.Solid,
            axisLabelVisible: true,
            title: title || lv.timeframe || '',
        }));
    };

    // MODE-BASED FILTERING (Rule: One Mode = One Visual)
    if (strategy === 'SR') {
        const primarySupports = (levels.primary?.supports || []).filter(l => l.timeframe !== 'ZONE');
        const primaryResists = (levels.primary?.resistances || []).filter(l => l.timeframe !== 'ZONE');

        // Take 2 nearest each
        primarySupports.sort((a,b) => Math.abs(a.price - cmp) - Math.abs(b.price - cmp))
            .slice(0, 2).forEach(lv => addLine(lv, '#3B82F6', 'SUP'));
            
        primaryResists.sort((a,b) => Math.abs(a.price - cmp) - Math.abs(b.price - cmp))
            .slice(0, 2).forEach(lv => addLine(lv, '#94A3B8', 'RES'));
    } 
    else if (strategy === 'DEMAND_SUPPLY') {
        const demand = (levels.primary?.supports || []).filter(l => l.timeframe === 'ZONE');
        const supply = (levels.primary?.resistances || []).filter(l => l.timeframe === 'ZONE');

        demand.forEach(lv => addLine(lv, 'rgba(34, 197, 94, 0.5)', 'DEMAND', false));
        supply.forEach(lv => addLine(lv, 'rgba(239, 68, 68, 0.5)', 'SUPPLY', false));
    }
    else if (strategy === 'FIBONACCI') {
        // In FIB mode, data structure changed to levels.primary
        const supports = levels.primary?.supports || [];
        const resistances = levels.primary?.resistances || [];
        
        // Show only key ratios: 38.2, 50, 61.8 (0.382, 0.5, 0.618)
        const keyRatios = [0.382, 0.5, 0.618];
        
        [...supports, ...resistances]
            .filter(l => keyRatios.includes(l.ratio))
            .forEach(l => addLine(l, '#A855F7', l.label, true));
    }
}

// Rotation Data Fetching
async function fetchRotation() {
    try {
        const tf = document.getElementById('tf-selector').value;
        const res = await fetch(`${ROTATION_URL}?tf=${tf}&t=${Date.now()}`);
        const result = await res.json();
        if (result.status === 'success' && rotationApp) {
            rotationApp.setData(result.data, result.alerts);
        }
    } catch (e) {
        console.error("Failed to fetch rotation data", e);
    }
}

// Initialize
window.onload = function () {
    try {
        if (typeof LightweightCharts === 'undefined') {
            throw new Error("Charting library not found. Please check your internet connection.");
        }
        checkMarketStatus();
        initChart();
        fetchData();

        // Check for Fyers login success in URL
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('fyers_login') === 'success') {
            console.log("Fyers login success detected, refreshing status and data...");
            checkFyersStatus();
            fetchData();
            
            // Clean up URL
            setTimeout(() => {
                const newUrl = window.location.pathname + window.location.search.replace(/[?&]fyers_login=success(&|$)/, '$1').replace(/[?&]$/, '');
                window.history.replaceState({}, document.title, newUrl);
            }, 2000);
        }

        // Global key listener for ESC to exit fullscreen
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && document.body.classList.contains('chart-fullscreen')) {
                window.toggleFullscreenChart();
            }
        });

        // Force chart resize after a short delay to ensure container has proper dimensions
        setTimeout(() => {
            if (chart) {
                const chartContainer = document.getElementById('tv-chart');
                chart.resize(chartContainer.clientWidth, chartContainer.clientHeight);
            }
        }, 100);

        // Initialize Rotation App
        if (typeof RotationDashboard !== 'undefined') {
            rotationApp = new RotationDashboard('rotation-canvas');
        }

        // Initialize Intelligence App
        if (typeof MarketIntelligence !== 'undefined') {
            intelligenceApp = new MarketIntelligence('momentum-hits-body', 'sector-intelligence-list');
            window.intelligenceApp = intelligenceApp;
        }

        // Toggle Handlers
        const std = document.getElementById('standard-dashboard');
        const rot = document.getElementById('rotation-section');
        const intel = document.getElementById('intelligence-section');
        const rotTog = document.getElementById('rotation-toggle');
        const intelTog = document.getElementById('intelligence-toggle');
        const scrTog = document.getElementById('screener-toggle');

        // Rotation Toggle Logic
        if (rotTog) {
            rotTog.addEventListener('change', (e) => {
                if (e.target.checked) {
                    rot.classList.remove('hidden');
                    std.classList.add('hidden');
                    intel.classList.add('hidden');
                    if (intelTog) intelTog.checked = false;
                    scrTog.checked = false;
                    document.getElementById('screener-toggle').dispatchEvent(new Event('change'));
                    fetchRotation();
                    if (rotationApp) rotationApp.resize();
                } else {
                    rot.classList.add('hidden');
                    if (!intelTog || !intelTog.checked) std.classList.remove('hidden');
                }
            });
        }

        // Navigation Logic (Dashboard vs Intelligence)
        const btnDash = document.getElementById('view-dashboard');
        const btnIntel = document.getElementById('view-intelligence');
        
        const setNavActive = (mode) => {
            if (mode === 'intel') {
                btnIntel.classList.add('bg-blue-600', 'text-white');
                btnIntel.classList.remove('text-gray-400', 'hover:bg-gray-800');
                btnDash.classList.remove('bg-blue-600', 'text-white');
                btnDash.classList.add('text-gray-400', 'hover:bg-gray-800');
                
                intel.classList.remove('hidden');
                std.classList.add('hidden');
                if (rot) rot.classList.add('hidden');
                if (rotTog) rotTog.checked = false;
                scrTog.checked = false;
                document.getElementById('screener-toggle').dispatchEvent(new Event('change'));
                fetchIntelligence();
            } else {
                btnDash.classList.add('bg-blue-600', 'text-white');
                btnDash.classList.remove('text-gray-400', 'hover:bg-gray-800');
                btnIntel.classList.remove('bg-blue-600', 'text-white');
                btnIntel.classList.add('text-gray-400', 'hover:bg-gray-800');
                
                std.classList.remove('hidden');
                intel.classList.add('hidden');
                if (rot) rot.classList.add('hidden');
            }
        };

        if (btnDash) btnDash.addEventListener('click', () => setNavActive('dash'));
        if (btnIntel) btnIntel.addEventListener('click', () => setNavActive('intel'));

        // Autocomplete Logic
        const searchInput = document.getElementById('symbol-input');
        const resultsDiv = document.getElementById('search-results');
        let searchTimeout;
        let selectedIndex = -1;

        searchInput.addEventListener('input', function (e) {
            const query = e.target.value.trim();
            clearTimeout(searchTimeout);
            selectedIndex = -1;

            if (query.length < 1) {
                resultsDiv.classList.add('hidden');
                return;
            }

            searchTimeout = setTimeout(async () => {
                try {
                    const res = await fetch(`${SEARCH_URL}?q=${query}`);
                    const results = await res.json();

                    resultsDiv.innerHTML = '';
                    if (results.length > 0) {
                        resultsDiv.classList.remove('hidden');
                        results.forEach((item, index) => {
                            const div = document.createElement('div');
                            div.className = "px-4 py-2 hover:bg-gray-800 cursor-pointer flex justify-between items-center border-b border-gray-800 last:border-0 search-item";
                            div.dataset.index = index;
                            div.innerHTML = `
                                <div>
                                    <span class="font-bold text-sm text-white">${item.symbol}</span>
                                    <p class="text-[10px] text-gray-500 truncate w-32">${item.shortname}</p>
                                </div>
                                <span class="text-[9px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400">${item.exchange}</span>
                            `;
                            div.onclick = () => {
                                searchInput.value = item.symbol;
                                resultsDiv.classList.add('hidden');
                                fetchData();
                            };
                            resultsDiv.appendChild(div);
                        });
                    } else {
                        resultsDiv.classList.add('hidden');
                    }
                } catch (err) {
                    console.error("Search error:", err);
                }
            }, 300);
        });

        searchInput.addEventListener('keydown', function (e) {
            const items = resultsDiv.getElementsByClassName('search-item');
            if (resultsDiv.classList.contains('hidden') || items.length === 0) return;

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                selectedIndex = (selectedIndex + 1) % items.length;
                updateSelection(items);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                selectedIndex = (selectedIndex - 1 + items.length) % items.length;
                updateSelection(items);
            } else if (e.key === 'Enter') {
                if (selectedIndex >= 0) {
                    e.preventDefault();
                    items[selectedIndex].click();
                }
            }
        });

        function updateSelection(items) {
            for (let i = 0; i < items.length; i++) {
                if (i === selectedIndex) {
                    items[i].classList.add('bg-blue-900/40');
                    items[i].classList.add('border-blue-500/50');
                    items[i].scrollIntoView({ block: 'nearest' });
                } else {
                    items[i].classList.remove('bg-blue-900/40');
                    items[i].classList.remove('border-blue-500/50');
                }
            }
        }

        // Close dropdown when clicking outside
        document.addEventListener('click', function (e) {
            if (!searchInput.contains(e.target) && !resultsDiv.contains(e.target)) {
                resultsDiv.classList.add('hidden');
            }
        });

        document.getElementById('tf-selector').addEventListener('change', () => {
            const tfSelector = document.getElementById('tf-selector');
            if (window.updateTfChips) window.updateTfChips(tfSelector.value);
            
            const isRotationActive = document.getElementById('rotation-toggle').checked;
            if (isRotationActive) {
                fetchRotation();
            } else if (isIntelligenceModeActive()) {
                fetchIntelligence();
            } else {
                fetchData();
            }
        });
        // Intraday chip group (5m / 15m) – drives tf-selector for Intelligence flows
        const intradayGroup = document.getElementById('intraday-tf-toggle');
        if (intradayGroup) {
            const tfSelector = document.getElementById('tf-selector');
            const buttons = intradayGroup.querySelectorAll('button[data-tf]');
            window.updateTfChips = (activeTf) => {
                buttons.forEach(btn => {
                    if (btn.dataset.tf === activeTf) {
                        btn.classList.add('bg-blue-600', 'text-white', 'shadow-[0_0_8px_rgba(37,99,235,0.7)]');
                        btn.classList.remove('text-gray-300', 'hover:bg-gray-800');
                    } else {
                        btn.classList.remove('bg-blue-600', 'text-white', 'shadow-[0_0_8px_rgba(37,99,235,0.7)]');
                        btn.classList.add('text-gray-300', 'hover:bg-gray-800');
                    }
                });
            };
            const setActive = window.updateTfChips;
            buttons.forEach(btn => {
                btn.addEventListener('click', () => {
                    const tf = btn.dataset.tf;
                    if (tfSelector) {
                        tfSelector.value = tf;
                        tfSelector.dispatchEvent(new Event('change'));
                    }
                    setActive(tf);
                    // When user explicitly chooses intraday chip, ensure Intelligence panel refreshes
                    if (isIntelligenceModeActive()) {
                        fetchIntelligence();
                    }
                });
            });
            // Initialise chip state from selector's default
            if (tfSelector) {
                setActive(tfSelector.value);
            }
        }
        document.getElementById('mtf-toggle').addEventListener('change', () => {
            // Re-render chart levels without re-fetching
            if (window.lastReceivedData) {
                drawLevelsOnChart(window.lastReceivedData.levels);
            }
        });
        const searchBtn = document.getElementById('search-btn');
        if (searchBtn) {
            searchBtn.addEventListener('click', (e) => {
                e.preventDefault();
                resultsDiv.classList.add('hidden');
                fetchData();
            });
        }

        const symbolInput = document.getElementById('symbol-input');
        if (symbolInput) {
            symbolInput.addEventListener('keypress', function (e) {
                if (e.key === 'Enter') {
                    resultsDiv.classList.add('hidden');
                    fetchData();
                }
            });
        }

        setInterval(() => {
            const rotToggle = document.getElementById('rotation-toggle');
            const isRotationActive = rotToggle && rotToggle.checked;
            const isIntelligenceActive = isIntelligenceModeActive();

            if (isRotationActive) {
                fetchRotation();
            } else if (isIntelligenceActive) {
                fetchIntelligence();
            } else {
                fetchData(true);
            }
        }, 10000); // reduced frequency for expensive intelligence calls (10s)

        document.getElementById('strategy-selector').addEventListener('change', () => {
            fetchData();
        });
    } catch (e) {
        console.error("Init error:", e);
        const chartParent = document.getElementById('chart-parent');
        if (chartParent) {
            chartParent.innerHTML = `
                <div class="h-full w-full flex flex-col items-center justify-center p-6 text-center text-red-500">
                    <p class="font-bold">Initialization Error</p>
                    <p class="text-sm">${e.message}</p>
                </div>
            `;
        }
    }
};

async function fetchIntelligence() {
    try {
        const tfSelector = document.getElementById('tf-selector');
        const tf = tfSelector ? tfSelector.value : '15m';
        const now = Date.now();

        // 1. Fetch data in parallel
        const [hitsRes, sectorRes, summaryRes, earlyRes, perfRes, tradePerfRes, watchlistRes] = await Promise.all([
            fetch(`${API_BASE}/api/v1/momentum-hits?tf=${tf}&t=${now}`).catch(e => { console.error("Hits fetch error", e); return null; }),
            fetch(`${ROTATION_URL}?tf=${tf}&t=${now}`).catch(e => { console.error("Sector fetch error", e); return null; }),
            fetch(`${API_BASE}/api/v1/market-summary?tf=${tf}&t=${now}`).catch(e => { console.error("Summary fetch error", e); return null; }),
            fetch(`${EARLY_SETUPS_URL}?tf=${tf}&limit=5&t=${now}`).catch(e => { console.error("Early setups fetch error", e); return null; }),
            fetch(`${SIGNAL_PERF_URL}?tf=${tf}&t=${now}`).catch(e => { console.error("Signal performance fetch error", e); return null; }),
            fetch(`${TRADE_PERF_URL}?t=${now}`).catch(e => { console.error("Trade performance fetch error", e); return null; }),
            fetch(`${API_BASE}/api/v1/next-session-watchlist?tf=${tf}&t=${now}`).catch(e => { console.error("Watchlist fetch error", e); return null; })
        ]);

        // 2. Parse responses carefully
        let hitsData = { data: [], source: 'live' };
        let sectorData = { data: {}, source: 'live' };
        let summaryData = null;
        let summarySource = 'live';
        let earlyData = { data: [], source: 'live' };
        let perfData = null;
        let tradePerfData = null;
        let watchlistData = null;

        if (hitsRes && hitsRes.ok) {
            hitsData = await hitsRes.json();
        } else if (hitsRes) {
            console.error(`Hits API error: ${hitsRes.status}`);
            hitsData.source = 'error';
        }

        if (sectorRes && sectorRes.ok) {
            sectorData = await sectorRes.json();
        } else if (sectorRes) {
            console.error(`Sector API error: ${sectorRes.status}`);
            sectorData.source = 'error';
        }

        if (summaryRes && summaryRes.ok) {
            const summaryJson = await summaryRes.json();
            if (summaryJson.status === 'success') {
                summaryData = summaryJson.data;
                summarySource = summaryJson.source || 'live';
            }
        } else if (summaryRes) {
            console.error(`Market Summary API error: ${summaryRes.status}`);
        }

        if (earlyRes && earlyRes.ok) {
            earlyData = await earlyRes.json();
        } else if (earlyRes) {
            console.error(`Early Setups API error: ${earlyRes.status}`);
            earlyData.source = 'error';
        }

        if (perfRes && perfRes.ok) {
            const perfJson = await perfRes.json();
            if (perfJson.status === 'success') perfData = perfJson.data;
        } else if (perfRes) {
            console.error(`Signal Performance API error: ${perfRes.status}`);
        }

        if (tradePerfRes && tradePerfRes.ok) {
            const tradePerfJson = await tradePerfRes.json();
            if (tradePerfJson.status === 'success') tradePerfData = tradePerfJson.data;
        } else if (tradePerfRes) {
            console.error(`Trade Performance API error: ${tradePerfRes.status}`);
        }

        if (watchlistRes && watchlistRes.ok) {
            const wlJson = await watchlistRes.json();
            if (wlJson.status === 'success') watchlistData = wlJson.data;
        } else if (watchlistRes) {
            console.error(`Watchlist API error: ${watchlistRes.status}`);
        }

        // 3. Update Intelligence Dashboard instance
        if (intelligenceApp) {
            if (hitsData && hitsData.data) {
                intelligenceApp.updateHits(hitsData.data, hitsData.source || 'live');
            }
            if (earlyData && earlyData.data && typeof intelligenceApp.updateEarlySetups === 'function') {
                intelligenceApp.updateEarlySetups(earlyData.data, earlyData.source || 'live');
            }
            if (perfData && typeof intelligenceApp.updateSignalPerformance === 'function') {
                intelligenceApp.updateSignalPerformance(perfData);
            }
            if (tradePerfData && typeof intelligenceApp.updateTradePerformance === 'function') {
                intelligenceApp.updateTradePerformance(tradePerfData);
            }
            if (watchlistData && typeof intelligenceApp.updateWatchlist === 'function') {
                intelligenceApp.updateWatchlist(watchlistData);
            }
            if (sectorData && sectorData.data && Object.keys(sectorData.data).length > 0) {
                window.lastSectorData = sectorData.data;
                intelligenceApp.updateSectors(sectorData.data, sectorData.alerts || [], sectorData.source || 'live');

                // Also update the Shining Sectors UX card if available
                if (window.renderActionableSectors) {
                    window.renderActionableSectors(sectorData.data);
                }
                if (summaryData) {
                    intelligenceApp.updateMarketSummary(summaryData, summarySource);
                }
            } else if (sectorData) {
                // Handle empty but valid responses (e.g., fallback)
                intelligenceApp.updateSectors(sectorData.data || {}, sectorData.alerts || [], sectorData.source || 'live');
            }
        }
    } catch (e) {
        console.error("Critical failure in fetchIntelligence", e);
    }
}
window.fetchIntelligence = fetchIntelligence;

// --- Professional UX Toggles ---
window.toggleFullscreenChart = function() {
    document.body.classList.toggle('chart-fullscreen');
    setTimeout(() => {
        if (chart) {
            const container = document.getElementById('tv-chart');
            chart.resize(container.clientWidth, container.clientHeight);
            chart.timeScale().fitContent();
        }
    }, 100);
};

window.toggleLevelsPanel = function() {
    const sidebar = document.getElementById('levels-sidebar');
    if (sidebar) {
        sidebar.classList.toggle('collapsed');
        sidebar.classList.toggle('mobile-show');
        setTimeout(() => {
            if (chart) {
                const container = document.getElementById('tv-chart');
                chart.resize(container.clientWidth, container.clientHeight);
            }
        }, 310); // Match CSS transition
    }
};

window.setActiveTimeframe = function(tf) {
    const selector = document.getElementById('tf-selector');
    if (selector) {
        selector.value = tf;
        
        // Update UI buttons
        document.querySelectorAll('.tf-group button').forEach(btn => {
            if (btn.dataset.tfBtn === tf) btn.classList.add('active');
            else btn.classList.remove('active');
        });
        
        // Update chart display
        const tfLabel = document.getElementById('chart-tf-label');
        if (tfLabel) {
            const names = { '5m': '5 MIN', '15m': '15 MIN', '1H': 'HOURLY', '1D': 'DAILY', '1W': 'WEEKLY' };
            tfLabel.textContent = names[tf] || tf.toUpperCase();
        }
        
        fetchData();
    }
};

// Check on load
document.addEventListener('DOMContentLoaded', () => {
    checkFyersStatus();
    // Poll every 30 seconds for faster updates after login
    setInterval(checkFyersStatus, 30000);
});
