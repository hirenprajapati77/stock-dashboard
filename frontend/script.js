const IS_LOCAL_FILE = window.location.protocol === 'file:';
// Use relative paths for API calls to avoid CORS/hostname issues when served from the same origin
const API_BASE = ""; 
const hostname = window.location.hostname;
const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1';
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


function isIntelligenceModeActive() {
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
                list.innerHTML = '<p class="text-xs text-gray-500">No stocks currently match all 9 strict growth criteria.</p>';
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
        const symbol = symbolInput ? symbolInput.value.toUpperCase() : "RELIANCE";
        const tfSelector = document.getElementById('tf-selector');
        const tf = tfSelector ? tfSelector.value : '1D';
        const stratSelector = document.getElementById('strategy-selector');
        const strategy = stratSelector ? stratSelector.value : 'SR';

        console.log(`[Fetch] ${symbol} @ ${tf} | Strategy: ${strategy} (Background: ${isBackground})`);

        const response = await fetch(`${API_URL}?symbol=${encodeURIComponent(symbol)}&tf=${tf}&strategy=${strategy}&_=${Date.now()}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        if (data && data.meta) {
            window.lastReceivedData = data;
            
            // Update live indicator based on source
            const liveIndicator = document.getElementById('live-indicator');
            if (liveIndicator) {
                if (data.source === 'fallback') {
                    liveIndicator.innerHTML = '<span class="w-1.5 h-1.5 bg-yellow-500 rounded-full"></span> CACHED';
                    liveIndicator.className = 'flex items-center gap-1 text-[9px] text-yellow-500 font-bold';
                    liveIndicator.title = "Yahoo rate limit reached. Showing last cached data.";
                } else {
                    liveIndicator.innerHTML = '<span class="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse"></span> LIVE';
                    liveIndicator.className = 'flex items-center gap-1 text-[9px] text-blue-400 font-bold';
                    liveIndicator.title = "Live data from Yahoo Finance";
                }
            }

            updateUI(data);
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

    } catch (err) {
        console.error("Strategy UI update error:", err);
    }
}

function formatVal(v) {
    if (v === undefined || v === null) return '—';
    if (typeof v === 'number') return v.toFixed(2);
    return v;
}

function updateUI(data) {
    try {
        // Hide error message if it exists
        const errDiv = document.getElementById('chart-error-msg');
        if (errDiv) errDiv.classList.add('hidden');
        const tvChart = document.getElementById('tv-chart');
        if (tvChart) tvChart.classList.remove('hidden');

        const symbolMap = { 'INR': '₹', 'USD': '$', 'EUR': '€', 'GBP': '£' };
        const currencySym = (data.meta && data.meta.currency) ? (symbolMap[data.meta.currency] || data.meta.currency + ' ') : '₹';

        const formatWithCurrency = (val) => {
            if (val === undefined || val === null || val === '—') return '—';
            if (typeof val === 'number') return `${currencySym}${val.toFixed(2)}`;
            // If it's a string that looks like a number, try to parse it
            const num = parseFloat(val);
            if (!isNaN(num)) return `${currencySym}${num.toFixed(2)}`;
            return `${currencySym}${val}`;
        };

        // 1. Meta & Summary
        const cmpEl = document.getElementById('cmp');
        if (cmpEl) cmpEl.textContent = formatWithCurrency(data.meta.cmp);

        const verTag = document.getElementById('ver-tag');
        if (verTag) verTag.textContent = "v1.5.0 Intelligence Layer";

        const syncTime = document.getElementById('sync-time');
        if (syncTime && data.meta.last_update) syncTime.textContent = `Last updated: ${data.meta.last_update}`;

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
            if (el) el.textContent = formatWithCurrency(val);
        };
        setVal('nearest-support', data.summary.nearest_support);
        setVal('nearest-resistance', data.summary.nearest_resistance);
        setVal('stop-loss', data.summary.stop_loss);
        const rrEl = document.getElementById('risk-reward');
        if (rrEl) rrEl.textContent = data.summary.risk_reward || '—';

        const signalEl = document.getElementById('trade-signal');
        const signalReasonEl = document.getElementById('trade-signal-reason');
        const signal = (data.summary && data.summary.trade_signal) ? data.summary.trade_signal : 'HOLD';
        if (signalEl) {
            signalEl.textContent = signal;
            signalEl.className = `px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wider ${signal === 'BUY'
                ? 'bg-green-600/20 text-green-300 border border-green-500/40'
                : signal === 'SELL'
                    ? 'bg-red-600/20 text-red-300 border border-red-500/40'
                    : 'bg-gray-800 text-gray-400 border border-gray-700'
                }`;
        }
        if (signalReasonEl) {
            signalReasonEl.textContent = (data.summary && data.summary.trade_signal_reason)
                ? data.summary.trade_signal_reason
                : 'Signal updates with EMA bias + structure.';
        }

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
        if (data.ai_analysis && data.ai_analysis.status === "success" && data.ai_analysis.priority) {
            const ai = data.ai_analysis;
            const pBadge = document.getElementById('ai-priority-badge');
            if (pBadge && ai.priority) {
                const level = ai.priority.level || 'NONE';
                pBadge.textContent = `PRIORITY: ${level}`;
                pBadge.className = `px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest ${level === 'HIGH' ? 'bg-indigo-600 text-white animate-pulse' :
                    level === 'MEDIUM' ? 'bg-indigo-900/40 text-indigo-200' : 'bg-gray-800 text-gray-500'
                    }`;
            }

            const bBadge = document.getElementById('ai-breakout-badge');
            if (bBadge && ai.breakout && ai.breakout.breakout_quality) {
                const qual = ai.breakout.breakout_quality;
                bBadge.textContent = qual.replace('_', ' ');
                bBadge.className = `text-[9px] font-bold px-1.5 py-0.5 rounded capitalize ${qual === 'LIKELY_GENUINE' ? 'bg-up text-up' :
                    qual === 'LIKELY_FAKE' ? 'bg-down text-down' : 'bg-gray-800 text-gray-400'
                    }`;
            }
            const bR = document.getElementById('ai-breakout-reason');
            if (bR && ai.breakout) bR.textContent = ai.breakout.reason || '';

            const rBadge = document.getElementById('ai-regime-badge');
            if (rBadge && ai.regime && ai.regime.market_regime) {
                const regime = ai.regime.market_regime;
                rBadge.textContent = regime.replace('_', ' ');
                rBadge.className = `text-[9px] font-bold px-1.5 py-0.5 rounded capitalize ${regime.startsWith('TRENDING') ? 'bg-blue-900/30 text-blue-400' : 'bg-gray-800 text-gray-400'
                    }`;
            }
            const rR = document.getElementById('ai-regime-reason');
            if (rR && ai.regime) rR.textContent = ai.regime.reason || '';
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
            // Auto-fit viewport to the new data range
            chart.timeScale().fitContent();
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

        // 8. Decision Strip (v2.0)
        updateDecisionStrip(data);

        // 9. Strategy Specific UI Toggles
        updateStrategyUI(data);

    } catch (e) {
        console.error("UI Update Error:", e);
    }
}

function updateDecisionStrip(data) {
    const strip = document.getElementById('decision-strip');
    const actionEl = document.getElementById('decision-action');
    const confEl = document.getElementById('decision-confidence');
    const entryEl = document.getElementById('strip-entry');
    const slEl = document.getElementById('strip-sl');
    const tgtEl = document.getElementById('strip-target');
    const rrEl = document.getElementById('strip-rr');
    const setupEl = document.getElementById('strip-setup');
    const reasonsEl = document.getElementById('decision-reasons');
    
    // New: Positives and Risks lists
    const posList = document.getElementById('positives-list');
    const riskList = document.getElementById('risks-list');

    if (!strip || !data.action) return;

    // 1. Action & Confidence
    actionEl.textContent = data.action;
    actionEl.className = `action-chip ${data.action.toLowerCase().replace(' ', '-')}`;
    
    // Pulse for STRONG actions
    if (data.action.includes('STRONG')) {
        actionEl.classList.add('animate-pulse', 'border-2');
        if (data.action.includes('BUY')) actionEl.classList.add('border-green-400');
        else actionEl.classList.add('border-red-400');
    }

    const score = data.score || data.confidence || 0;
    confEl.textContent = `${score}%`;
    
    // Dynamic color for confidence
    if (score >= 80) confEl.className = 'text-2xl font-black text-green-400 tracking-tighter shadow-green-500/20';
    else if (score >= 60) confEl.className = 'text-2xl font-black text-blue-400 tracking-tighter';
    else confEl.className = 'text-2xl font-black text-yellow-500 tracking-tighter';

    // 2. Execution Levels
    const symbolMap = { 'INR': '₹', 'USD': '$', 'EUR': '€', 'GBP': '£' };
    const currencySym = (data.meta && data.meta.currency) ? (symbolMap[data.meta.currency] || data.meta.currency + ' ') : '₹';
    
    entryEl.textContent = `${currencySym}${formatVal(data.meta.cmp)}`;
    slEl.textContent = `${currencySym}${formatVal(data.summary.stop_loss)}`;
    tgtEl.textContent = `${currencySym}${formatVal(data.summary.target)}`;
    
    if (rrEl) rrEl.textContent = `${(data.rr || data.summary.risk_reward || 0).toFixed(2)}x`;
    if (setupEl) setupEl.textContent = data.setupType || data.summary.setup_type || '---';

    // 3. Reason Tags (Main Strip)
    if (reasonsEl) {
        reasonsEl.innerHTML = (data.reasonTags || []).slice(0, 4).map(tag => 
            `<span class="reason-tag">${tag}</span>`
        ).join('');
    }

    // 4. Positives & Risks Detailed Lists (Decision Logic v2.0)
    const factors = data.confidenceFactors || [];
    if (posList && riskList) {
        const positives = factors.filter(f => f.positive);
        const risks = factors.filter(f => !f.positive);

        posList.innerHTML = positives.length > 0 
            ? positives.map(f => `
                <li class="flex items-center justify-between text-[11px]">
                    <span class="text-gray-300 font-medium">${f.label}</span>
                    <span class="text-green-400 font-bold font-mono">${f.value}</span>
                </li>
            `).join('')
            : '<li class="text-[10px] text-gray-500 italic">No major positives identified.</li>';

        riskList.innerHTML = risks.length > 0
            ? risks.map(f => `
                <li class="flex items-center justify-between text-[11px]">
                    <span class="text-gray-400 font-medium">${f.label}</span>
                    <span class="text-red-400 font-bold font-mono">${f.value}</span>
                </li>
            `).join('')
            : '<li class="text-[10px] text-gray-500 italic">No critical risks flagged.</li>';
    }
}

window.renderTopPicks = function(hits) {
    const section = document.getElementById('top-picks-section');
    const container = document.getElementById('top-picks-container');
    if (!section || !container) return;

    // Filter: Score > 70 AND RR >= 2 (as per requirements)
    const topPicks = hits.filter(h => {
        const score = h.score || h.confidence || 0;
        const rr = h.rr || h.risk_reward || 0;
        return score >= 70 && rr >= 2.0;
    }).sort((a,b) => (b.score || b.confidence || 0) - (a.score || a.confidence || 0))
      .slice(0, 3);

    if (topPicks.length === 0) {
        section.classList.add('hidden');
        return;
    }

    section.classList.remove('hidden');
    container.innerHTML = topPicks.map(p => {
        const score = p.score || p.confidence || 0;
        const rr = p.rr || p.risk_reward || 0;
        return `
            <div class="glass p-4 rounded-2xl border border-indigo-500/30 hover:border-indigo-500 transition-all cursor-pointer"
                 onclick="window.fetchDataForSymbol('${p.symbol}', { fromIntelligence: true })">
                <div class="flex justify-between items-start">
                    <div>
                        <h4 class="text-sm font-bold text-white">${p.symbol}</h4>
                        <p class="text-[9px] text-gray-400 font-mono uppercase">${p.sector || 'Sector'}</p>
                    </div>
                    <div class="text-right">
                        <span class="text-[10px] font-black text-indigo-400">${score}% CONF</span>
                    </div>
                </div>
                <div class="mt-3 flex justify-between items-end">
                    <div class="flex flex-col">
                        <span class="text-[8px] text-gray-500 uppercase font-black tracking-widest">Risk Reward</span>
                        <span class="text-lg font-black text-white mono">${rr.toFixed(2)}x</span>
                    </div>
                    <div class="flex flex-col text-right">
                         <span class="text-[8px] text-gray-500 uppercase font-black tracking-widest">Action</span>
                         <span class="text-[10px] font-bold text-green-400 uppercase">${p.action || 'BUY'}</span>
                    </div>
                </div>
            </div>
        `;
    }).join('');
};

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
    if (!candlestickSeries) return;

    // Clear existing primitives
    levelsLayer.forEach(line => {
        candlestickSeries.removePriceLine(line);
    });
    levelsLayer = [];

    // 1. Draw Execution Overlays (Entry, SL, Target)
    if (fullData && fullData.summary) {
        const s = fullData.summary;
        const cmp = fullData.meta.cmp;

        // Entry (Blue)
        levelsLayer.push(candlestickSeries.createPriceLine({
            price: cmp,
            color: '#3b82f6',
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: 'ENTRY (CMP)',
        }));

        // Stop Loss (Red)
        if (s.stop_loss) {
            levelsLayer.push(candlestickSeries.createPriceLine({
                price: s.stop_loss,
                color: '#f6465d',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: 'STOP LOSS',
            }));
        }

        // Target (Green)
        if (s.target) {
            levelsLayer.push(candlestickSeries.createPriceLine({
                price: s.target,
                color: '#00c076',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: 'TARGET (T1)',
            }));
        }
    }

    if (!levels) return;

    // Helper to draw
    const addLine = (lv, color, isResistance) => {
        // 1. ZONE Logic
        if (lv.timeframe === 'ZONE') {
            // Draw simple boundary lines
            // Top
            const l1 = candlestickSeries.createPriceLine({
                price: lv.price_high || lv.price,
                color: color, // Green/Red
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: isResistance ? 'SUPPLY' : 'DEMAND',
            });
            levelsLayer.push(l1);

            // Bottom
            if (lv.price_low && lv.price_low !== lv.price_high) {
                const l2 = candlestickSeries.createPriceLine({
                    price: lv.price_low,
                    color: color,
                    lineWidth: 2,
                    lineStyle: LightweightCharts.LineStyle.Solid,
                    axisLabelVisible: false, // Only label one side to reduce clutter
                    title: '',
                });
                levelsLayer.push(l2);
            }
            return;
        }

        // 2. SWING Logic (Thicker lines)
        const isSwing = lv.timeframe === '1D' || lv.timeframe === '1W' || lv.timeframe === '1M';
        const lineWidth = isSwing ? 2 : 1;
        const lineStyle = isSwing ? LightweightCharts.LineStyle.Solid : LightweightCharts.LineStyle.Dashed;

        // 3. Simple Level
        const line = candlestickSeries.createPriceLine({
            price: lv.price,
            color: color, // Blue/Green etc
            lineWidth: lineWidth,
            lineStyle: lineStyle,
            axisLabelVisible: true,
            title: lv.timeframe || '',
        });
        levelsLayer.push(line);
    };

    const showMTF = document.getElementById('mtf-toggle').checked;

    // Add MTF Resistance (Dashed)
    if (showMTF && levels.mtf) {
        levels.mtf.resistances.forEach(lv => addLine(lv, '#00c076', true));
        levels.mtf.supports.forEach(lv => addLine(lv, '#3b82f6', false));
    }

    // Add Primary Support (Solid)
    if (levels.primary) {
        levels.primary.supports.forEach(lv => addLine(lv, '#3b82f6', false));
        levels.primary.resistances.forEach(lv => addLine(lv, '#dc2626', true)); // Red for resistance
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
        initChart();
        fetchData();

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
            window.marketIntelligence = intelligenceApp;
        }

        // Toggle Handlers
        const std = document.getElementById('standard-dashboard');
        const rot = document.getElementById('rotation-section');
        const intel = document.getElementById('intelligence-section');
        const rotTog = document.getElementById('rotation-toggle');
        const intelTog = document.getElementById('view-intelligence');
        const dashTog = document.getElementById('view-dashboard');
        const scrTog = document.getElementById('screener-toggle');

        // Rotation Toggle Logic
        if (rotTog) {
            rotTog.addEventListener('change', (e) => {
                if (e.target.checked) {
                    rot.classList.remove('hidden');
                    std.classList.add('hidden');
                    intel.classList.add('hidden');
                    scrTog.checked = false;
                    document.getElementById('screener-toggle').dispatchEvent(new Event('change'));
                    fetchRotation();
                    if (rotationApp) rotationApp.resize();
                    updateViewToggleButtons('rotation');
                } else {
                    rot.classList.add('hidden');
                    // Default back to dashboard
                    std.classList.remove('hidden');
                    updateViewToggleButtons('dashboard');
                }
            });
        }

        // View Mode Toggle Helper
        function updateViewToggleButtons(mode) {
            if (dashTog && intelTog) {
                if (mode === 'intelligence') {
                    dashTog.classList.replace('bg-blue-600', 'text-gray-400');
                    dashTog.classList.replace('text-white', 'hover:bg-gray-800');
                    intelTog.classList.replace('text-gray-400', 'bg-blue-600');
                    intelTog.classList.replace('hover:bg-gray-800', 'text-white');
                } else if (mode === 'dashboard') {
                    intelTog.classList.replace('bg-blue-600', 'text-gray-400');
                    intelTog.classList.replace('text-white', 'hover:bg-gray-800');
                    dashTog.classList.replace('text-gray-400', 'bg-blue-600');
                    dashTog.classList.replace('hover:bg-gray-800', 'text-white');
                } else {
                    // Both off for rotation if needed, but keeping them as is visually
                    intelTog.classList.replace('bg-blue-600', 'text-gray-400');
                    intelTog.classList.replace('text-white', 'hover:bg-gray-800');
                    dashTog.classList.replace('bg-blue-600', 'text-gray-400');
                    dashTog.classList.replace('text-white', 'hover:bg-gray-800');
                }
            }
        }

        // Dashboard Button Logic
        if (dashTog) {
            dashTog.addEventListener('click', () => {
                std.classList.remove('hidden');
                intel.classList.add('hidden');
                rot.classList.add('hidden');
                if (rotTog) rotTog.checked = false;
                scrTog.checked = false;
                updateViewToggleButtons('dashboard');
                // document.getElementById('screener-toggle').dispatchEvent(new Event('change'));
                fetchData(true);
            });
        }

        // Intelligence Button Logic
        if (intelTog) {
            intelTog.addEventListener('click', () => {
                intel.classList.remove('hidden');
                std.classList.add('hidden');
                rot.classList.add('hidden');
                if (rotTog) rotTog.checked = false;
                scrTog.checked = false;
                // document.getElementById('screener-toggle').dispatchEvent(new Event('change'));
                updateViewToggleButtons('intelligence');
                fetchIntelligence();
            });
        }

        // Autocomplete Logic
        const searchInput = document.getElementById('symbol-input');
        const resultsDiv = document.getElementById('search-results');
        let searchTimeout;
        let selectedIndex = -1;

        searchInput.addEventListener('focus', () => {
            searchInput.select();
        });

        searchInput.addEventListener('input', function (e) {
            const query = e.target.value.trim();
            clearTimeout(searchTimeout);
            selectedIndex = -1;

            if (query.length < 1) {
                resultsDiv.classList.add('hidden');
                resultsDiv.innerHTML = '';
                return;
            }

            searchTimeout = setTimeout(async () => {
                try {
                    const res = await fetch(`${SEARCH_URL}?q=${encodeURIComponent(query)}`);
                    if (!res.ok) throw new Error(`Search failed: ${res.status}`);
                    const results = await res.json();

                    resultsDiv.innerHTML = '';
                    if (results && results.length > 0) {
                        resultsDiv.classList.remove('hidden');
                        results.forEach((item, index) => {
                            const div = document.createElement('div');
                            div.className = "px-4 py-2 hover:bg-gray-800 cursor-pointer flex justify-between items-center border-b border-gray-700/50 last:border-0 search-item transition-colors";
                            div.dataset.index = index;
                            div.innerHTML = `
                                <div>
                                    <span class="font-bold text-sm text-white">${item.symbol}</span>
                                    <p class="text-[10px] text-gray-500 truncate w-40">${item.shortname}</p>
                                </div>
                                <span class="text-[9px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400 font-mono">${item.exchange}</span>
                            `;
                            div.onclick = (event) => {
                                event.stopPropagation();
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
                    console.error("[Search] error:", err);
                    resultsDiv.classList.add('hidden');
                }
            }, 300);
        });

        // Hide search results when clicking outside
        document.addEventListener('click', (e) => {
            if (!searchInput.contains(e.target) && !resultsDiv.contains(e.target)) {
                resultsDiv.classList.add('hidden');
            }
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

        // No-op for redundant listener cleanup

        document.getElementById('tf-selector').addEventListener('change', () => {
            const isRotationActive = document.getElementById('rotation-toggle').checked;
            if (isRotationActive) {
                fetchRotation();
            } else if (isIntelligenceModeActive()) {
                fetchIntelligence();
            } else {
                fetchData();
            }
        });
        // Timeframe Dropdown (TradingView-style)
        const tfDropBtn = document.getElementById('tf-dropdown-btn');
        const tfDropMenu = document.getElementById('tf-dropdown-menu');
        const tfDropLabel = document.getElementById('tf-dropdown-label');
        const tfSelectorHidden = document.getElementById('tf-selector');

        if (tfDropBtn && tfDropMenu) {
            // Toggle open/close
            tfDropBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                tfDropMenu.classList.toggle('open');
            });

            // Close when clicking outside
            document.addEventListener('click', () => tfDropMenu.classList.remove('open'));
            tfDropMenu.addEventListener('click', (e) => e.stopPropagation());

            // Handle option click
            const tfOptions = tfDropMenu.querySelectorAll('.tf-option');
            const setActiveTfOption = (tf) => {
                tfOptions.forEach(opt => {
                    if (opt.dataset.tf === tf) {
                        opt.classList.add('active');
                    } else {
                        opt.classList.remove('active');
                    }
                });
                if (tfDropLabel) tfDropLabel.textContent = tf;
            };

            tfOptions.forEach(opt => {
                opt.addEventListener('click', () => {
                    const tf = opt.dataset.tf;
                    // Sync hidden selector and fire change
                    if (tfSelectorHidden) {
                        tfSelectorHidden.value = tf;
                        tfSelectorHidden.dispatchEvent(new Event('change'));
                    }
                    setActiveTfOption(tf);
                    tfDropMenu.classList.remove('open');
                    // Refresh intelligence if active
                    if (isIntelligenceModeActive()) {
                        fetchIntelligence();
                    }
                });
            });

            // Initialise from selector's default value
            if (tfSelectorHidden) {
                setActiveTfOption(tfSelectorHidden.value || '15m');
            }
        }
        // Legacy intraday-tf-toggle kept as empty div for backwards compat, no-op
        document.getElementById('mtf-toggle').addEventListener('change', () => {
            // Re-render chart levels without re-fetching
            if (window.lastReceivedData) {
                drawLevelsOnChart(window.lastReceivedData.levels, window.lastReceivedData);
            }
        });
        document.getElementById('search-btn').addEventListener('click', () => {
            resultsDiv.classList.add('hidden');
            fetchData();
        });
        document.getElementById('symbol-input').addEventListener('keypress', function (e) {
            if (e.key === 'Enter') {
                resultsDiv.classList.add('hidden');
                fetchData();
            }
        });

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

let marketStatus = { open: true, lastCheck: 0 };

async function fetchIntelligence(overrideTf = null) {
    try {
        const tfSelector = document.getElementById('tf-selector');
        const defaultTf = tfSelector ? tfSelector.value : '1D';
        const tf = overrideTf || defaultTf;
        const now = Date.now();

        // 0. Cache Check
        const cacheKey = `intel_cache_${tf}`;
        const cached = localStorage.getItem(cacheKey);
        if (cached) {
            const cacheObj = JSON.parse(cached);
            const age = now - cacheObj.timestamp;
            // Market closed: cache lasts 1 hour. Market open: cache lasts 20 seconds.
            const ttl = marketStatus.open ? 20000 : 3600000;
            
            if (age < ttl) {
                console.log(`%c[Intelligence] Serving ${tf} from cache (age: ${Math.round(age/1000)}s)`, "color: #10b981; font-weight: bold;");
                applyIntelligenceData(cacheObj.data);
                return;
            }
        }

        console.log(`%c[Intelligence] Fetching live data for ${tf}...`, "color: #3b82f6; font-weight: bold;");

        // 1. Fetch data in parallel
        const [hitsRes, sectorRes, summaryRes, earlyRes, perfRes, tradePerfRes] = await Promise.all([
            fetch(`${API_BASE}/api/v1/momentum-hits?tf=${tf}&t=${now}`).catch(e => { console.error("Hits fetch error", e); return null; }),
            fetch(`${ROTATION_URL}?tf=${tf}&t=${now}`).catch(e => { console.error("Sector fetch error", e); return null; }),
            fetch(`${API_BASE}/api/v1/market-summary?tf=${tf}&t=${now}`).catch(e => { console.error("Summary fetch error", e); return null; }),
            fetch(`${EARLY_SETUPS_URL}?tf=${tf}&limit=5&t=${now}`).catch(e => { console.error("Early setups fetch error", e); return null; }),
            fetch(`${SIGNAL_PERF_URL}?tf=${tf}&t=${now}`).catch(e => { console.error("Signal performance fetch error", e); return null; }),
            fetch(`${TRADE_PERF_URL}?t=${now}`).catch(e => { console.error("Trade performance fetch error", e); return null; })
        ]);

        // 2. Parse responses carefully
        let hitsData = { data: [], source: 'live' };
        let sectorData = { data: {}, source: 'live' };
        let summaryData = null;
        let summarySource = 'live';
        let earlyData = { data: [], source: 'live' };
        let perfData = null;
        let tradePerfData = null;

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
        }

        const allData = {
            hitsData,
            sectorData,
            summaryData,
            summarySource,
            earlyData,
            perfData,
            tradePerfData
        };

        // 3. Save to Cache
        localStorage.setItem(`intel_cache_${tf}`, JSON.stringify({
            timestamp: now,
            data: allData
        }));

        // 4. Update Intelligence Dashboard
        applyIntelligenceData(allData);

    } catch (e) {
        console.error("Critical failure in fetchIntelligence", e);
    }
}

function applyIntelligenceData(allData) {
    try {
        const { hitsData, sectorData, summaryData, summarySource, earlyData, perfData, tradePerfData } = allData;
        
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
        console.error("Critical failure in applyIntelligenceData", e);
    }
}
window.fetchIntelligence = fetchIntelligence;

// --- Fyers Integration ---
async function checkFyersStatus() {
    try {
        const res = await fetch('/api/v1/fyers/status');
        const data = await res.json();
        
        marketStatus.open = !!data.market_open;
        marketStatus.lastCheck = Date.now();

        const dot = document.getElementById('fyers-status-dot');
        const text = document.getElementById('fyers-status-text');
        const btn = document.getElementById('fyers-login-btn');
        
        if (data.logged_in) {
            if (dot) dot.className = "w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]";
            if (text) text.textContent = "Online";
            if (text) text.className = "text-[10px] font-bold text-green-400 uppercase tracking-widest hidden lg:inline";
            if (btn) btn.classList.add('hidden');
        } else {
            if (dot) dot.className = "w-2 h-2 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)]";
            if (text) text.textContent = "Offline";
            if (text) text.className = "text-[10px] font-bold text-red-400 uppercase tracking-widest hidden lg:inline";
            if (btn) btn.classList.remove('hidden');
        }
    } catch (e) {
        console.error("Failed to check Fyers status", e);
    }
}

function loginToFyers() {
    window.location.href = '/api/v1/fyers/login';
}

window.loginToFyers = loginToFyers;

// Check on load
document.addEventListener('DOMContentLoaded', () => {
    checkFyersStatus();
    // Poll every 30 seconds for faster updates after login
    setInterval(checkFyersStatus, 30000);
});
