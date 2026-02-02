const IS_LOCAL_FILE = window.location.protocol === 'file:';
const API_BASE = IS_LOCAL_FILE ? "http://localhost:8000" : ""; // Use relative path if hosted, else localhost
export const API_URL = `${API_BASE}/api/v1/dashboard`;
export const AI_API_URL = `${API_BASE}/api/v2/ai-insights`;
export const SCREENER_URL = `${API_BASE}/api/v1/screener`;
export const SEARCH_URL = `${API_BASE}/api/v1/search`;

// Safety check for file protocol only if backend isn't running locally for it
if (IS_LOCAL_FILE) {
    console.warn("Running from file protocol. Ensure backend is running at http://localhost:8000");
}

let chart, candlestickSeries;
let levelsLayer = [];

function initChart() {
    const chartContainer = document.getElementById('tv-chart');
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
        const response = await fetch(SCREENER_URL);
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
async function fetchData() {
    const loader = document.getElementById('loading-overlay');

    try {
        if (loader) loader.classList.remove('hidden');

        const symbolInput = document.getElementById('symbol-input');
        const symbol = symbolInput.value.toUpperCase() || "RELIANCE";
        const tf = document.getElementById('tf-selector').value;
        const response = await fetch(`${API_URL}?symbol=${encodeURIComponent(symbol)}&tf=${tf}`);
        const data = await response.json();

        if (data.meta) {
            updateUI(data);
        } else {
            throw new Error(data.message || "Invalid response from server");
        }
    } catch (error) {
        console.error("Fetch error:", error);
        // Show non-destructive error toast or badge if we already have a chart
        const chartParent = document.getElementById('chart-parent');
        if (!chart || chartParent.innerHTML.includes('Failed to load data')) {
            chartParent.innerHTML = `
                <div class="h-full w-full flex flex-col items-center justify-center p-6 text-center">
                    <p class="text-red-500 font-bold mb-2">Failed to load data</p>
                    <code class="text-xs bg-gray-800 p-2 rounded text-left w-full overflow-auto max-h-40">
                        ${error.message}<br>
                        Is the backend running on port 8000?
                    </code>
                    <button onclick="fetchData()" class="mt-4 px-4 py-2 bg-blue-600 rounded text-sm font-bold hover:bg-blue-500">Retry</button>
                </div>
            `;
        } else {
            console.warn("Background update failed, keeping current data.");
        }
    } finally {
        if (loader) loader.classList.add('hidden');
    }
}

function updateUI(data) {
    // 1. Meta & Summary
    document.getElementById('cmp').textContent = `₹${data.meta.cmp}`;
    document.getElementById('nearest-support').textContent = data.summary.nearest_support ? `₹${data.summary.nearest_support}` : '—';
    document.getElementById('nearest-resistance').textContent = data.summary.nearest_resistance ? `₹${data.summary.nearest_resistance}` : '—';
    document.getElementById('stop-loss').textContent = data.summary.stop_loss ? `₹${data.summary.stop_loss}` : '—';
    document.getElementById('risk-reward').textContent = data.summary.risk_reward || '—';

    // 2. Insights
    document.getElementById('inside-candle').textContent = data.insights.inside_candle ? "YES" : "NO";
    document.getElementById('retest').textContent = data.insights.retest ? "CONFIRMED" : "NONE";
    document.getElementById('upside-pct').textContent = `+${data.insights.upside_pct}%`;

    const biasBadge = document.getElementById('bias-badge');
    biasBadge.textContent = data.insights.ema_bias;
    biasBadge.className = `px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest ${data.insights.ema_bias === 'Bullish' ? 'bg-up text-up' :
        data.insights.ema_bias === 'Caution' ? 'bg-down text-down' : 'bg-gray-800 text-gray-400'
        }`;

    // 3. AI Insights (Unified from dashboard response)
    if (data.ai_analysis && data.ai_analysis.status === "success") {
        const ai = data.ai_analysis;
        // Priority
        const pBadge = document.getElementById('ai-priority-badge');
        pBadge.textContent = `PRIORITY: ${ai.priority.level}`;
        pBadge.className = `px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest ${ai.priority.level === 'HIGH' ? 'bg-indigo-600 text-white animate-pulse' :
            ai.priority.level === 'MEDIUM' ? 'bg-indigo-900/40 text-indigo-200' : 'bg-gray-800 text-gray-500'
            }`;

        // Breakout
        const bBadge = document.getElementById('ai-breakout-badge');
        bBadge.textContent = ai.breakout.breakout_quality;
        bBadge.className = `text-[9px] font-bold px-1.5 py-0.5 rounded capitalize ${ai.breakout.breakout_quality === 'LIKELY_GENUINE' ? 'bg-up text-up' :
            ai.breakout.breakout_quality === 'LIKELY_FAKE' ? 'bg-down text-down' : 'bg-gray-800 text-gray-400'
            }`;
        document.getElementById('ai-breakout-reason').textContent = ai.breakout.reason;

        // Regime
        const rBadge = document.getElementById('ai-regime-badge');
        rBadge.textContent = ai.regime.market_regime.replace('_', ' ');
        rBadge.className = `text-[9px] font-bold px-1.5 py-0.5 rounded capitalize ${ai.regime.market_regime.startsWith('TRENDING') ? 'bg-blue-900/30 text-blue-400' : 'bg-gray-800 text-gray-400'
            }`;
        document.getElementById('ai-regime-reason').textContent = ai.regime.reason;

        // Reliability
        const adj = ai.reliability ? ai.reliability.ai_adjustment : 0;
        const relText = document.getElementById('ai-reliability-adjustment');
        relText.textContent = `Score Mod: ${adj > 0 ? '+' : ''}${adj}`;
        relText.className = `text-[10px] font-bold mono ${adj > 0 ? 'text-up' : adj < 0 ? 'text-down' : 'text-gray-400'}`;
        relText.title = ai.reliability ? ai.reliability.reason : "No adjustments";
    }

    // 4. Clear and Render Level Lists (Primary + MTF)
    const supportList = document.getElementById('support-list');
    const resistanceList = document.getElementById('resistance-list');
    supportList.innerHTML = '';
    resistanceList.innerHTML = '';

    renderLevelList('support-list', data.levels.primary.supports, 'blue', false);
    renderLevelList('support-list', data.levels.mtf.supports, 'blue', true);

    renderLevelList('resistance-list', data.levels.primary.resistances, 'green', false);
    renderLevelList('resistance-list', data.levels.mtf.resistances, 'green', true);

    // 5. Render Chart Data
    if (data.ohlcv && data.ohlcv.length > 0) {
        candlestickSeries.setData(data.ohlcv);
    }

    // 6. Fundamental Health UI
    const fundCard = document.getElementById('fundamentals-card');
    if (data.fundamentals) {
        fundCard.classList.remove('hidden');
        const f = data.fundamentals;

        document.getElementById('fund-sector').textContent = f.sector || '—';
        document.getElementById('fund-mcap').textContent = f.market_cap || '—';
        document.getElementById('fund-pe').textContent = f.pe_ratio || '—';

        // Color code PE
        const peEl = document.getElementById('fund-pe');
        if (f.pe_ratio) {
            peEl.className = `text-sm font-bold ${f.pe_ratio < 20 ? 'text-up' : f.pe_ratio > 50 ? 'text-down' : 'text-white'}`;
        } else {
            peEl.className = 'text-sm font-bold text-white';
        }

        document.getElementById('fund-roe').textContent = f.roe ? `${f.roe}%` : '—';
        document.getElementById('fund-div').textContent = f.dividend_yield ? `${f.dividend_yield}%` : '—';

        const high = f['52w_high'] || 0;
        const low = f['52w_low'] || 0;
        const cmp = data.meta.cmp;

        document.getElementById('fund-52h').textContent = high || '—';
        document.getElementById('fund-52l').textContent = low || '—';

        if (high && low && high > low) {
            let pct = ((cmp - low) / (high - low)) * 100;
            pct = Math.max(0, Math.min(100, pct));

            const bar = document.getElementById('fund-range-bar');
            bar.style.width = `${pct}%`;
            bar.className = 'h-full rounded-full transition-all duration-500 ' +
                (pct > 80 ? 'bg-down' : pct < 20 ? 'bg-up' : 'bg-blue-600');
        }
    } else {
        if (fundCard) fundCard.classList.add('hidden');
    }

    // Draw Levels on Chart
    window.lastReceivedData = data; // Cache for toggle
    drawLevelsOnChart(data.levels);
}

function renderLevelList(containerId, levels, color, isMTF) {
    const container = document.getElementById(containerId);

    levels.forEach((level, index) => {
        const div = document.createElement('div');
        div.className = `flex items-center justify-between p-3 rounded-xl bg-gray-900 border ${isMTF ? 'border-gray-800/50 opacity-70' : 'border-gray-800'} hover:border-gray-700 transition-all cursor-default scale-95 origin-left`;
        div.title = `Price: ${level.price}\nTimeframe: ${level.timeframe}\nTouches: ${level.touches}\nScore: ${level.confidence || 0}`;
        div.innerHTML = `
            <div>
                <p class="text-[9px] text-gray-500 font-medium">${isMTF ? 'MTF' : 'L' + (index + 1)}</p>
                <p class="font-bold mono text-sm ${isMTF ? 'text-gray-400' : 'text-white'}">₹${level.price.toFixed(2)}</p>
            </div>
            <div class="text-right">
                <span class="text-[9px] font-bold px-1.5 py-0.5 rounded bg-gray-800 text-gray-500 uppercase">${level.timeframe}</span>
                <p class="text-[9px] text-gray-600 mt-1">${level.touches}T</p>
            </div>
        `;
        container.appendChild(div);
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

// Initialize
window.onload = function () {
    try {
        if (typeof LightweightCharts === 'undefined') {
            throw new Error("Charting library not found. Please check your internet connection.");
        }
        initChart();
        fetchData();

        // Autocomplete Logic
        const searchInput = document.getElementById('symbol-input');
        const resultsDiv = document.getElementById('search-results');
        let searchTimeout;

        searchInput.addEventListener('input', function (e) {
            const query = e.target.value.trim();
            clearTimeout(searchTimeout);

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
                        results.forEach(item => {
                            const div = document.createElement('div');
                            div.className = "px-4 py-2 hover:bg-gray-800 cursor-pointer flex justify-between items-center border-b border-gray-800 last:border-0";
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

        // Close dropdown when clicking outside
        document.addEventListener('click', function (e) {
            if (!searchInput.contains(e.target) && !resultsDiv.contains(e.target)) {
                resultsDiv.classList.add('hidden');
            }
        });

        document.getElementById('tf-selector').addEventListener('change', fetchData);
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

        setInterval(fetchData, 10000); // Auto-sync every 10s
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
