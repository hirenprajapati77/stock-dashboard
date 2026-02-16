const IS_LOCAL_FILE = window.location.protocol === 'file:';
const API_BASE = IS_LOCAL_FILE ? "http://localhost:8000" : ""; // Use relative path if hosted, else localhost
const API_URL = `${API_BASE}/api/v1/dashboard`;
const AI_API_URL = `${API_BASE}/api/v2/ai-insights`;
const SCREENER_URL = `${API_BASE}/api/v1/screener`;
const SEARCH_URL = `${API_BASE}/api/v1/search`;
const ROTATION_URL = `${API_BASE}/api/v1/sector-rotation`;
const HITS_URL = `${API_BASE}/api/v1/momentum-hits`;

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
    const intelToggle = document.getElementById('intelligence-toggle');
    if (intelToggle) return !!intelToggle.checked;

    const intelligenceSection = document.getElementById('intelligence-section');
    return !!(intelligenceSection && !intelligenceSection.classList.contains('hidden'));
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
        }

        const symbolInput = document.getElementById('symbol-input');
        const symbol = symbolInput ? symbolInput.value.toUpperCase() : "RELIANCE";
        const tfSelector = document.getElementById('tf-selector');
        const tf = tfSelector ? tfSelector.value : '1D';

        console.log(`[Fetch] ${symbol} @ ${tf} (Background: ${isBackground})`);

        const response = await fetch(`${API_URL}?symbol=${encodeURIComponent(symbol)}&tf=${tf}&_=${Date.now()}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        if (data && data.meta) {
            window.lastReceivedData = data;
            updateUI(data);
        } else {
            throw new Error(data.message || "Malformed API response");
        }
    } catch (error) {
        console.error("Fetch failed:", error);

        if (!isBackground) {
            const chartParent = document.getElementById('chart-parent');
            if (chartParent) {
                // If we don't have a chart yet, show error in the area
                if (!chart || chartParent.innerHTML.includes('Failed to load data')) {
                    const tvChart = document.getElementById('tv-chart');
                    if (tvChart) tvChart.classList.add('hidden');

                    let errDiv = document.getElementById('chart-error-msg');
                    if (!errDiv) {
                        errDiv = document.createElement('div');
                        errDiv.id = 'chart-error-msg';
                        errDiv.className = 'absolute inset-0 flex flex-col items-center justify-center p-6 text-center bg-gray-900/50 z-20';
                        chartParent.appendChild(errDiv);
                    }
                    errDiv.classList.remove('hidden');
                    errDiv.innerHTML = `
                        <p class="text-red-500 font-bold mb-2">Sync Error</p>
                        <p class="text-[10px] text-gray-400 mb-4">${error.message}</p>
                        <button onclick="window.fetchData()" class="px-4 py-2 bg-indigo-600 rounded text-xs font-bold hover:bg-indigo-500">RETRY SYNC</button>
                     `;
                }
            }
        }
    } finally {
        if (loader && showLoader) {
            loader.classList.add('hidden');
            loader.style.display = 'none';
        }
    }
}
window.fetchData = fetchData;

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
            return `${currencySym}${val}`;
        };

        // 1. Meta & Summary
        const cmpEl = document.getElementById('cmp');
        if (cmpEl) cmpEl.textContent = formatWithCurrency(data.meta.cmp);

        const verTag = document.getElementById('ver-tag');
        if (verTag) verTag.textContent = "v1.4.2";

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
        setTxt('inside-candle', data.insights.inside_candle ? "YES" : "NO");
        setTxt('retest', data.insights.retest ? "CONFIRMED" : "NONE");
        setTxt('upside-pct', `+${data.insights.upside_pct}%`);

        const biasBadge = document.getElementById('bias-badge');
        if (biasBadge) {
            biasBadge.textContent = data.insights.ema_bias;
            biasBadge.className = `px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest ${data.insights.ema_bias === 'Bullish' ? 'bg-up text-up' :
                data.insights.ema_bias === 'Caution' ? 'bg-down text-down' : 'bg-gray-800 text-gray-400'
                }`;
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
        drawLevelsOnChart(data.levels);

    } catch (e) {
        console.error("UI Update Error:", e);
    }
}

function renderLevelList(containerId, levels, color, isMTF) {
    const list = document.getElementById(containerId);
    if (!list || !levels || !Array.isArray(levels)) return;

    const data = window.lastReceivedData;
    const symbolMap = { 'INR': '₹', 'USD': '$', 'EUR': '€', 'GBP': '£' };
    const currencySym = (data && data.meta && data.meta.currency) ? (symbolMap[data.meta.currency] || data.meta.currency + ' ') : '₹';

    levels.forEach((level, index) => {
        const div = document.createElement('div');
        div.className = `flex items-center justify-between p-3 rounded-xl bg-gray-900 border ${isMTF ? 'border-gray-800/50 opacity-70' : 'border-gray-800'} hover:border-gray-700 transition-all cursor-default scale-95 origin-left`;
        div.title = `Price: ${level.price}\nTimeframe: ${level.timeframe}\nTouches: ${level.touches}\nScore: ${level.confidence || 0}`;
        div.innerHTML = `
            <div>
                <p class="text-[9px] text-gray-500 font-medium">${isMTF ? 'MTF' : 'L' + (index + 1)}</p>
                <p class="font-bold mono text-sm ${isMTF ? 'text-gray-400' : 'text-white'}">${currencySym}${level.price.toFixed(2)}</p>
            </div>
            <div class="text-right">
                <span class="text-[9px] font-bold px-1.5 py-0.5 rounded bg-gray-800 text-gray-500 uppercase">${level.timeframe}</span>
                <p class="text-[9px] text-gray-600 mt-1">${level.touches}T</p>
            </div>
        `;
        list.appendChild(div);
    });
}

function drawLevelsOnChart(levels) {
    // Clear old lines
    if (levelsLayer && levelsLayer.length > 0) {
        levelsLayer.forEach(line => {
            candlestickSeries.removePriceLine(line);
        });
        levelsLayer = [];
    }

    if (!levels) return;

    const showMTF = document.getElementById('mtf-toggle').checked;

    // Add Primary Resistance (Solid)
    levels.primary.resistances.forEach(lv => {
        const line = candlestickSeries.createPriceLine({
            price: lv.price,
            color: '#00c076',
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Solid,
            axisLabelVisible: true,
            title: lv.timeframe,
        });
        levelsLayer.push(line);
    });

    // Add MTF Resistance (Dashed)
    if (showMTF) {
        levels.mtf.resistances.forEach(lv => {
            const line = candlestickSeries.createPriceLine({
                price: lv.price,
                color: '#00c076',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: '', // Removed title from axis to declutter
            });
            levelsLayer.push(line);
        });
    }

    // Add Primary Support (Solid)
    levels.primary.supports.forEach(lv => {
        const line = candlestickSeries.createPriceLine({
            price: lv.price,
            color: '#3b82f6',
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Solid,
            axisLabelVisible: true,
            title: lv.timeframe,
        });
        levelsLayer.push(line);
    });

    // Add MTF Support (Dashed)
    if (showMTF) {
        levels.mtf.supports.forEach(lv => {
            const line = candlestickSeries.createPriceLine({
                price: lv.price,
                color: '#3b82f6',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: '', // Removed title from axis to declutter
            });
            levelsLayer.push(line);
        });
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

        // Intelligence Toggle Logic
        if (intelTog) {
            intelTog.addEventListener('change', (e) => {
                if (e.target.checked) {
                    intel.classList.remove('hidden');
                    std.classList.add('hidden');
                    rot.classList.add('hidden');
                    if (rotTog) rotTog.checked = false;
                    scrTog.checked = false;
                    document.getElementById('screener-toggle').dispatchEvent(new Event('change'));
                    fetchIntelligence();
                } else {
                    intel.classList.add('hidden');
                    if (!rotTog || !rotTog.checked) std.classList.remove('hidden');
                }
            });
        }

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
            const setActive = (activeTf) => {
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
        const tf = document.getElementById('tf-selector').value;
        const now = Date.now();

        // Fetch in parallel
        const [hitsRes, sectorRes] = await Promise.all([
            fetch(`${API_BASE}/api/v1/momentum-hits?tf=${tf}&t=${now}`),
            fetch(`${ROTATION_URL}?tf=${tf}&t=${now}`)
        ]);

        const [hitsData, sectorData] = await Promise.all([
            hitsRes.json(),
            sectorRes.json().catch(() => ({ data: {} })) // Guard JSON parse
        ]);

        if (intelligenceApp) {
            if (hitsData && hitsData.data) {
                intelligenceApp.updateHits(hitsData.data);
            }
            if (sectorData && sectorData.data) {
                window.lastSectorData = sectorData.data;
                intelligenceApp.updateSectors(sectorData.data);
            }
        }
    } catch (e) {
        console.error("Failed to fetch intelligence data", e);
    }
}
window.fetchIntelligence = fetchIntelligence;
