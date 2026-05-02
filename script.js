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

// ==========================================
// GLOBAL TRADING STATE
// ==========================================
const appState = {
    tradingMode: 'AUTO', // 'AUTO', 'EQUITY', 'OPTIONS'
    resolvedMode: 'EQUITY'
};

function setTradingMode(mode) {
    appState.tradingMode = mode;
    
    // Update UI active states
    ['mode-auto', 'mode-equity', 'mode-options'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) {
            btn.classList.remove('bg-indigo-600', 'text-white');
            btn.classList.add('text-gray-500', 'hover:bg-gray-800');
        }
    });
    
    const activeBtn = document.getElementById(`mode-${mode.toLowerCase()}`);
    if (activeBtn) {
        activeBtn.classList.remove('text-gray-500', 'hover:bg-gray-800');
        activeBtn.classList.add('bg-indigo-600', 'text-white');
    }
    
    // Refresh UI if we have data
    if (window.lastDashboardData) {
        updateUI(window.lastDashboardData);
    }
}

function resolveMode(userMode, data) {
    if (userMode === 'EQUITY') return 'EQUITY';
    if (userMode === 'OPTIONS') return 'OPTIONS';
    
    // AUTO Mode: Decide based on data
    const d = data?.decision || {};
    const opt = d.option_selector || data.options || {};
    const hasOption = !!(opt.strike || data.options?.strike);
    const confidence = data?.score || d?.meta_score || 0;

    // AUTO Prioritization: Promote to Options if setup is high-confidence
    if (userMode === 'AUTO') {
        if (hasOption && confidence > 60) return 'OPTIONS';
        return 'EQUITY';
    }
    
    return hasOption ? 'OPTIONS' : 'EQUITY';
}

function switchView(view) {
    const dashboard = document.getElementById('standard-dashboard');
    const intelligence = document.getElementById('execution-edge-panel');
    const scanner = document.getElementById('top-trades-panel');
    
    const btnDash = document.getElementById('view-dashboard');
    const btnIntel = document.getElementById('view-intelligence');

    if (view === 'dashboard') {
        dashboard?.classList.remove('hidden');
        intelligence?.classList.add('hidden');
        scanner?.classList.add('hidden');
        
        btnDash?.classList.add('bg-blue-600', 'text-white');
        btnDash?.classList.remove('text-gray-400', 'hover:bg-gray-800');
        
        btnIntel?.classList.remove('bg-blue-600', 'text-white');
        btnIntel?.classList.add('text-gray-400', 'hover:bg-gray-800');
    } else {
        dashboard?.classList.add('hidden');
        intelligence?.classList.remove('hidden');
        scanner?.classList.remove('hidden');
        
        btnIntel?.classList.add('bg-blue-600', 'text-white');
        btnIntel?.classList.remove('text-gray-400', 'hover:bg-gray-800');
        
        btnDash?.classList.remove('bg-blue-600', 'text-white');
        btnDash?.classList.add('text-gray-400', 'hover:bg-gray-800');
        
        // Trigger chart resize when switching to intelligence
        setTimeout(() => {
            if (window.chart) window.chart.resize();
        }, 100);
    }
    
    console.log(`[UI] Switched to ${view.toUpperCase()} mode`);
}

// Expose to window for HTML onclick handlers
window.switchView = switchView;
window.setTradingMode = setTradingMode;

// ==========================================
// TRADING ASSISTANT MEMORY MODULE
// ==========================================
function isMarketOpen() {
    const now = new Date();
    // Indian Market Hours (9:15 AM - 3:30 PM IST)
    // Convert current time to IST
    const istOffset = 5.5 * 60; // IST is UTC+5.5
    const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
    const istTime = new Date(utc + (istOffset * 60000));
    
    const day = istTime.getDay(); // 0 = Sun, 6 = Sat
    const hours = istTime.getHours();
    const minutes = istTime.getMinutes();
    const totalMinutes = hours * 60 + minutes;

    // Weekend check
    if (day === 0 || day === 6) return false;

    // NSE Equity: 09:15 (555) to 15:30 (930)
    return totalMinutes >= 555 && totalMinutes <= 930;
}

function getATMStrike(symbol, price) {
    if (!price || price <= 0) return null;
    
    let step = 100;
    const sym = symbol.toUpperCase();
    
    if (sym.includes("NIFTY50") || sym.includes("NIFTY")) {
        step = 50;
    } else if (sym.includes("BANKNIFTY")) {
        step = 100;
    } else if (sym.includes("FINNIFTY")) {
        step = 50;
    } else {
        // For stocks, we assume a 10 step for large caps, 5 for others
        step = price > 1000 ? 10 : 5;
    }
    
    return Math.round(price / step) * step;
}

const TradingAssistant = {
    version: 1,
    state: {
        alerts: [],
        outcomes: [],
        watchlist: []
    },
    
    init() {
        try {
            const stored = localStorage.getItem('tradingAssistant');
            if (stored) {
                const parsed = JSON.parse(stored);
                if (parsed.version === this.version) {
                    this.state = parsed;
                } else {
                    this.state = { version: this.version, alerts: [], outcomes: [], watchlist: [] };
                    this.save();
                }
            }
        } catch (e) {
            console.warn("Could not load Trading Assistant state", e);
        }
        
        this.renderAll();
    },
    
    save() {
        try {
            this.state.version = this.version;
            localStorage.setItem('tradingAssistant', JSON.stringify(this.state));
            this.renderAll();
        } catch (e) {
            console.warn("Could not save Trading Assistant state", e);
        }
    },
    
    addAlert(symbol, type) {
        if (!this.state.alerts.find(a => a.symbol === symbol)) {
            this.state.alerts.push({ symbol, type, timestamp: Date.now() });
            this.save();
            showToast(`🔔 Alert set for ${symbol}`, 'success');
        } else {
            showToast(`Alert already exists for ${symbol}`, 'warning');
        }
    },
    
    removeAlert(symbol) {
        this.state.alerts = this.state.alerts.filter(a => a.symbol !== symbol);
        this.save();
    },
    
    addOutcome(symbol, entry, sl) {
        if (!this.state.outcomes.find(o => o.symbol === symbol && o.status === "RUNNING")) {
            this.state.outcomes.push({ symbol, entry, sl, targets: [], status: "RUNNING" });
            this.save();
            showToast(`🚀 Trade logged: ${symbol}`, 'success');
        }
    },
    
    cycleOutcomeStatus(symbol) {
        const trade = this.state.outcomes.find(o => o.symbol === symbol && o.status === "RUNNING");
        if (trade) {
            trade.status = "TARGET HIT";
        } else {
            const tradeT = this.state.outcomes.find(o => o.symbol === symbol && o.status === "TARGET HIT");
            if (tradeT) {
                tradeT.status = "SL HIT";
            } else {
                const tradeS = this.state.outcomes.find(o => o.symbol === symbol && o.status === "SL HIT");
                if (tradeS) tradeS.status = "RUNNING";
            }
        }
        this.save();
    },
    
    removeOutcome(symbol, status) {
        this.state.outcomes = this.state.outcomes.filter(o => !(o.symbol === symbol && o.status === status));
        this.save();
    },
    
    toggleWatchlist(symbol, e) {
        if (e) e.stopPropagation();
        if (this.state.watchlist.includes(symbol)) {
            this.state.watchlist = this.state.watchlist.filter(s => s !== symbol);
        } else {
            this.state.watchlist.push(symbol);
        }
        this.save();
        if (typeof loadTopTrades === 'function') loadTopTrades();
    },
    
    isPinned(symbol) {
        return this.state.watchlist.includes(symbol);
    },
    
    renderAll() {
        this.renderAlerts();
        this.renderOutcomes();
        this.renderWatchlist();
    },
    
    renderAlerts() {
        const list = document.getElementById('ta-alerts-list');
        if (!list) return;
        if (this.state.alerts.length === 0) {
            list.innerHTML = '<div class="text-[10px] text-gray-500 italic text-center py-2">No active alerts.</div>';
            return;
        }
        
        list.innerHTML = this.state.alerts.map(a => `
            <div class="flex items-center justify-between bg-gray-900/50 p-2 rounded border border-gray-800">
                <div class="flex items-center gap-2 cursor-pointer hover:text-blue-400 transition-colors" onclick="document.getElementById('symbol-input').value='${a.symbol}'; fetchData(false);">
                    <span class="text-xs font-bold text-white">${a.symbol}</span>
                    <span class="text-[9px] text-gray-500 uppercase tracking-widest">${a.type}</span>
                </div>
                <button onclick="TradingAssistant.removeAlert('${a.symbol}')" class="text-gray-500 hover:text-red-400 transition-colors px-1"><i class="fas fa-times text-[10px]"></i></button>
            </div>
        `).join('');
    },
    
    renderOutcomes() {
        const list = document.getElementById('ta-outcomes-list');
        if (!list) return;
        if (this.state.outcomes.length === 0) {
            list.innerHTML = '<div class="text-[10px] text-gray-500 italic text-center py-2">No active trades.</div>';
            return;
        }
        
        list.innerHTML = this.state.outcomes.map(o => {
            let statusBadge = '';
            if (o.status === "RUNNING") statusBadge = '<span class="text-[10px] font-bold text-yellow-400 bg-yellow-400/10 px-1.5 py-0.5 rounded cursor-pointer" onclick="TradingAssistant.cycleOutcomeStatus(\''+o.symbol+'\')">RUNNING ⏳</span>';
            else if (o.status === "TARGET HIT") statusBadge = '<span class="text-[10px] font-bold text-green-400 bg-green-400/10 px-1.5 py-0.5 rounded cursor-pointer" onclick="TradingAssistant.cycleOutcomeStatus(\''+o.symbol+'\')">TARGET HIT ✅</span>';
            else statusBadge = '<span class="text-[10px] font-bold text-red-400 bg-red-400/10 px-1.5 py-0.5 rounded cursor-pointer" onclick="TradingAssistant.cycleOutcomeStatus(\''+o.symbol+'\')">SL HIT ❌</span>';
            
            return `
            <div class="flex items-center justify-between bg-gray-900/50 p-2 rounded border border-gray-800">
                <span class="text-xs font-bold text-white cursor-pointer hover:text-blue-400" onclick="document.getElementById('symbol-input').value='${o.symbol}'; fetchData(false);">${o.symbol}</span>
                <div class="flex items-center gap-2">
                    ${statusBadge}
                    <button onclick="TradingAssistant.removeOutcome('${o.symbol}', '${o.status}')" class="text-gray-600 hover:text-gray-400 transition-colors ml-1 px-1"><i class="fas fa-times text-[10px]"></i></button>
                </div>
            </div>
            `;
        }).join('');
    },
    
    renderWatchlist() {
        const list = document.getElementById('ta-watchlist-list');
        if (!list) return;
        if (this.state.watchlist.length === 0) {
            list.innerHTML = '<div class="text-[10px] text-gray-500 italic w-full text-center py-1">Pin symbols from the scanner.</div>';
            return;
        }
        
        list.innerHTML = this.state.watchlist.map(sym => `
            <div class="bg-gray-800/80 hover:bg-gray-700 px-2 py-1 rounded text-[10px] font-bold text-white cursor-pointer flex items-center gap-1 group transition-colors">
                <span onclick="document.getElementById('symbol-input').value='${sym}'; fetchData(false);">${sym}</span>
                <i class="fas fa-times text-gray-500 group-hover:text-red-400 ml-1 opacity-0 group-hover:opacity-100 transition-opacity" onclick="TradingAssistant.toggleWatchlist('${sym}')"></i>
            </div>
        `).join('');
    }
};

function toggleTrackingPanel() {
    const body = document.getElementById('tracking-panel-body');
    const icon = document.getElementById('tracking-panel-icon');
    if (body.classList.contains('hidden')) {
        body.classList.remove('hidden');
        icon.classList.remove('rotate-180');
    } else {
        body.classList.add('hidden');
        icon.classList.add('rotate-180');
    }
}

function toggleIntelligenceSidebar() {
    const sidebar = document.querySelector('.intelligence-sidebar');
    const wrapper = document.querySelector('.chart-layout-wrapper');
    if (sidebar && wrapper) {
        sidebar.classList.toggle('hidden');
        if (sidebar.classList.contains('hidden')) {
            wrapper.style.gridTemplateColumns = '1fr';
        } else {
            wrapper.style.gridTemplateColumns = '1fr 320px';
        }
        // Resize chart after transition
        setTimeout(() => {
            if (chart) {
                const container = document.getElementById('tv-chart');
                chart.resize(container.clientWidth, container.clientHeight);
            }
        }, 310);
    }
}

function toggleChartFullscreen() {
    document.body.classList.toggle('chart-fullscreen');
    // Resize chart
    setTimeout(() => {
        if (chart) {
            const container = document.getElementById('tv-chart');
            chart.resize(container.clientWidth, container.clientHeight);
        }
    }, 100);
}

window.toggleTrackingModeColumn = function() {
    const analysisCol = document.getElementById('analysis-column');
    const trackingCol = document.getElementById('tracking-column');
    const btn = document.getElementById('toggle-tracking-btn');
    
    if (analysisCol && trackingCol) {
        trackingCol.classList.toggle('hidden');
        if (trackingCol.classList.contains('hidden')) {
            analysisCol.classList.remove('lg:col-span-9');
            analysisCol.classList.add('lg:col-span-12');
            btn.classList.remove('text-gray-400');
            btn.classList.add('bg-blue-900/40', 'text-blue-400');
        } else {
            analysisCol.classList.remove('lg:col-span-12');
            analysisCol.classList.add('lg:col-span-9');
            btn.classList.remove('bg-blue-900/40', 'text-blue-400');
            btn.classList.add('text-gray-400');
        }
        
        // Resize chart and other elements
        setTimeout(() => {
            if (chart) {
                const container = document.getElementById('tv-chart');
                chart.resize(container.clientWidth, container.clientHeight);
            }
        }, 310);
    }
};
// Safety check for file protocol only if backend isn't running locally for it
if (IS_LOCAL_FILE) {
    console.warn("Running from file protocol. Ensure backend is running at http://localhost:8000");
}

let chart, candlestickSeries, volumeSeries, volumeEmaSeries;
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
        const statusDot = document.getElementById('fyers-status-dot');
        const loginBtn = document.getElementById('fyers-login-btn');

        // Backend returns { status: "success", data: { is_connected: bool, ... } }
        const isConnected = result?.data?.is_connected || result?.logged_in || false;

        if (isConnected) {
            if (statusDot) {
                statusDot.className = 'w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]';
            }
            if (loginBtn) {
                loginBtn.textContent = 'ONLINE';
                loginBtn.className = 'text-[9px] font-bold text-green-400 uppercase tracking-widest';
                loginBtn.onclick = null; // Prevent re-login if already connected
            }
        } else {
            if (statusDot) statusDot.className = 'w-2 h-2 rounded-full bg-gray-600';
            if (loginBtn) {
                loginBtn.textContent = 'CONNECT';
                loginBtn.className = 'text-[9px] font-bold text-blue-400 uppercase tracking-widest hover:text-blue-300';
                loginBtn.onclick = () => window.loginToFyers();
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

    volumeSeries = chart.addHistogramSeries({
        color: '#26a69a',
        priceFormat: {
            type: 'volume',
        },
        priceScaleId: 'volume',
    });

    chart.priceScale('volume').applyOptions({
        scaleMargins: {
            top: 0.8,
            bottom: 0,
        },
        visible: false,
    });

    volumeEmaSeries = chart.addLineSeries({
        color: '#ff9800',
        lineWidth: 1,
        priceScaleId: 'volume',
    });

    console.log('Chart initialized successfully');

    window.addEventListener('resize', () => {
        chart.resize(chartContainer.clientWidth, chartContainer.clientHeight);
    });
}


// 5. Screener Logic
document.getElementById('screener-toggle').addEventListener('change', function (e) {
    const topTradesPanel = document.getElementById('top-trades-panel');
    const legacyScreenerPanel = document.getElementById('screener-panel');
    
    if (e.target.checked) {
        if (topTradesPanel) {
            topTradesPanel.classList.remove('hidden');
            loadTopTrades(); // Trigger the scan immediately
        }
        // Keep legacy hidden for now to reduce clutter as per feedback
        if (legacyScreenerPanel) legacyScreenerPanel.classList.add('hidden');
    } else {
        if (topTradesPanel) topTradesPanel.classList.add('hidden');
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

        const errLower = error.message.toLowerCase();
        const isRateLimit = errLower.includes("rate limit") || 
                           errLower.includes("too many requests") || 
                           errLower.includes("no data found") || 
                           errLower.includes("rate-limited");
        
        // Show error UI if NOT background, OR if it's a critical rate limit error
        if (!isBackground || isRateLimit) {
            // Update chart labels even on error so user knows which symbol failed
            const symbolInput = document.getElementById('symbol-input');
            const symbol = symbolInput ? symbolInput.value.trim().toUpperCase() : "ERROR";
            const tf = document.getElementById('tf-selector')?.value || '15m';
            
            const sLab = document.getElementById('chart-symbol-label');
            const tfLab = document.getElementById('chart-tf-label');
            const hasData = !!window.lastReceivedData;
            
            if (sLab) sLab.textContent = symbol;
            if (tfLab) tfLab.textContent = `${tf} - ${hasData ? 'CACHED' : 'SYNC ERROR'}`;


            // If we have existing data and it's a background update or rate limit, 
            // DON'T show the giant blocking overlay. Just update status indicator.

            
            if (hasData && (isBackground || isRateLimit)) {
                console.warn(`Data sync rate-limited for ${symbol}. Keeping existing data visible.`);
                const liveIndicator = document.getElementById('live-indicator');
                if (liveIndicator) {
                    liveIndicator.innerHTML = '<span class="w-1.5 h-1.5 bg-orange-500 rounded-full animate-pulse"></span> COOLDOWN';
                    liveIndicator.className = 'flex items-center gap-1 text-[9px] text-orange-500 font-bold';
                    liveIndicator.title = "Data provider is rate-limiting. Using existing data until sync recovers.";
                }
                return; // Exit without showing blocking error
            }

            const chartParent = document.getElementById('chart-parent');
            if (chartParent) {
                // Determine Provider name for branding
                const loginBtn = document.getElementById('fyers-login-btn');
                const providerName = (loginBtn && loginBtn.textContent === 'ONLINE') ? 'Fyers' : 'Yahoo Finance';

                const tvChart = document.getElementById('tv-chart');
                if (tvChart && isRateLimit) tvChart.classList.add('hidden'); 

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
                        <p class="${isRateLimit ? 'text-yellow-500' : 'text-red-500'} font-bold text-lg">${isRateLimit ? providerName + ' Cooldown' : 'Sync Error'}</p>
                        <p class="text-xs text-gray-400 max-w-[280px]">${isRateLimit ? 'The data provider is temporarily limiting requests. This usually resolves in 2-5 minutes.' : error.message}</p>
                        <button onclick="window.fetchData()" class="mt-2 px-6 py-2 bg-indigo-600 rounded-xl text-xs font-bold hover:bg-indigo-500 transition-all shadow-lg">RETRY SYNC</button>
                    </div>
                `;
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

        // Toggle specific strategy panels
        const swingPanel = document.getElementById('strategy-swing-metrics');
        const zonesPanel = document.getElementById('strategy-zones-metrics');
        
        if (swingPanel) swingPanel.style.display = strategy === 'SWING' ? 'grid' : 'none';
        if (zonesPanel) zonesPanel.style.display = strategy === 'DEMAND_SUPPLY' ? 'grid' : 'none';

        // Update Swing Metrics
        if (strategy === 'SWING') {
            document.getElementById('swing-structure').textContent = metrics.structure || 'NEUTRAL';
            document.getElementById('swing-ema').textContent = metrics.emaAlignment ? 'ALIGNED' : 'NOT ALIGNED';
            document.getElementById('swing-htf').textContent = metrics.htfTrend || 'NEUTRAL';
            document.getElementById('swing-pullback').textContent = metrics.pullback ? 'YES' : 'NO';
        }

        // Update Dynamic Metrics Panels
        const dynPanels = document.getElementById('strategy-dynamic-panels');
        if (dynPanels) {
            const hasDynamicData = strategy === 'FIBONACCI' || strategy === 'DEMAND_SUPPLY';
            dynPanels.style.display = hasDynamicData ? 'grid' : 'none';
            if (hasDynamicData) dynPanels.classList.remove('hidden'); 

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
}

let scanInterval;

function toggleAutoScan(enabled) {
    if (enabled) {
        scanInterval = setInterval(loadTopTrades, 30000);
    } else {
        clearInterval(scanInterval);
    }
}

function formatNarrative(vm) {
    const text = vm.narrative || "";
    let title = "📊 Market Insight";
    let bullets = [];
    let action = vm.nextAction || "Observe";

    if (vm.executionSignal === "REJECT") {
        title = "🚫 No Trade Setup";
    } else if (vm.executionSignal === "WATCH") {
        title = "🟡 Setup Forming";
    } else if (vm.executionSignal === "EXECUTE") {
        title = "🟢 Trade Ready";
    }

    bullets = text.split(/\.\s+|\.$/).filter(t => t.trim()).slice(0, 3);
    return { title, bullets, action };
}

function toViewModel(data) {
    const d = data?.decision || {};
    const marketOpen = isMarketOpen();
    const opt = d.option_selector || data.options || {};
    
    let executionSignal = "REJECT";
    if (d?.execution_signal) {
        executionSignal = d.execution_signal;
    } else if (d?.final_decision) {
        executionSignal = d.final_decision; // Standardized V5 signal (EXECUTE/WATCH/WAIT/REJECT)
    } else if (d?.setup_state === "FORMING") {
        executionSignal = "WATCH";
    } else if (["STRONG BUY", "BUY"].includes(data?.action)) {
        executionSignal = "EXECUTE";
    } else if (["WATCHLIST", "MONITOR", "WATCH"].includes(data?.action)) {
        executionSignal = "WATCH";
    }

    // Standardize signals to V5 Terminology
    if (executionSignal === "BUY") executionSignal = "EXECUTE";
    if (executionSignal === "HOLD") executionSignal = "WAIT";

    // SESSION ECHO: If market is closed, reconstruct the last valid signal based on score
    if (!marketOpen && (executionSignal === "REJECT" || executionSignal === "NONE")) {
        const score = data?.score || d?.meta_score || 0;
        if (score >= 75) {
            executionSignal = "EXECUTE";
        } else if (score >= 60) {
            executionSignal = "WATCH";
        } else {
            executionSignal = "REJECT";
        }
    }

    // Resolve Mode
    const mode = resolveMode(appState.tradingMode, data);
    appState.resolvedMode = mode;

    let narrative = "-";
    if (d?.narrative) {
        narrative = d.narrative;
    } else if (data?.ai_analysis?.breakout?.reason) {
        narrative = data.ai_analysis.breakout.reason;
    } else if (data?.summary?.trade_signal_reason) {
        narrative = data.summary.trade_signal_reason;
    }

    let entryType = "-";
    let nextAction = "-";
    if (executionSignal === "EXECUTE") {
        entryType = marketOpen ? "CONFIRMED" : "PREVIOUS";
        nextAction = marketOpen ? "BUY" : "STUDY";
    } else if (executionSignal === "WATCH") {
        entryType = marketOpen ? "OBSERVE" : "PREP";
        nextAction = marketOpen ? "WAIT" : "WATCH";
    } else {
        entryType = "NONE";
        nextAction = "SKIP";
    }

    // OI Interpretation
    const getOIState = (val) => {
        if (!val) return "NEUTRAL (Balanced)";
        const v = val.toUpperCase();
        if (v.includes("LONG BUILDUP")) return "LONG BUILDUP (Strong)";
        if (v.includes("SHORT COVERING")) return "SHORT COVERING (Bullish)";
        if (v.includes("SHORT BUILDUP")) return "SHORT BUILDUP (Weak)";
        if (v.includes("LONG UNWINDING")) return "LONG UNWINDING (Caution)";
        return `${v} (Steady)`;
    };

    // PCR Interpretation
    const getPCRState = (val) => {
        if (!val) return "—";
        const v = parseFloat(val);
        if (v > 1.25) return `${v} (Strong Bullish)`;
        if (v > 1.05) return `${v} (Bullish)`;
        if (v < 0.75) return `${v} (Strong Bearish)`;
        if (v < 0.95) return `${v} (Bearish)`;
        return `${v} (Balanced)`;
    };

    const riskLevel = data?.score >= 60 ? "LOW" : "HIGH";
    const premium = parseFloat(opt.premium_entry || opt.premium || 0);
    const lotSize = parseInt(opt.lot_size || (data?.meta?.symbol?.includes('NIFTY') ? 50 : 25));

    // Smart Strike Mapping (ATM Suggestion)
    let strike = opt.strike;
    let type = opt.type;
    let isSuggested = false;
    
    if (!strike || strike === "--") {
        const atm = getATMStrike(data?.meta?.symbol || "NIFTY", data?.meta?.cmp);
        if (atm) {
            strike = atm;
            isSuggested = true;
            const bias = data.insights?.ema_bias || d?.market_context?.market_bias || "";
            type = bias.toUpperCase().includes("BULL") ? "CE" : (bias.toUpperCase().includes("BEAR") ? "PE" : "CE");
        }
    }

    return {
        mode: mode,
        symbol: data?.meta?.symbol || "NIFTY",
        underlyingPrice: data?.meta?.cmp || 0,
        narrative: !marketOpen && narrative.includes("volume") ? "Market is currently closed. Analyzed levels remain valid for the next session." : narrative,
        executionSignal: executionSignal,
        setupState: d?.setup_state || data?.action || "-",
        marketTrend: d?.market_regime?.regime || data?.summary?.trade_signal || "-",
        marketBias: d?.market_regime?.trend_intensity || data?.summary?.trade_signal_reason || "-",
        regime: d?.market_regime?.regime || data?.summary?.market_regime || "UNKNOWN",
        entryType: entryType,
        nextAction: nextAction,
        liquidity: marketOpen ? (data?.volume_ratio ? `VOL ${data.volume_ratio}x` : "NORMAL") : "OFF-HOURS",
        
        // Stock Microstructure (EQUITY)
        volumeSurge: data?.volume_ratio ? `${data.volume_ratio}x ${data.volume_ratio >= 1.5 ? 'Institutional Accumulation' : 'Session Growth'}` : "NORMAL",
        intradayVol: data?.intraday_volume_ratio ? `${data.intraday_volume_ratio}x Candle` : "NORMAL",
        trendIntensity: d?.market_regime?.trend_intensity || data?.ai_analysis?.regime?.trend_intensity || "STABLE",
        relativeStrength: data?.insights?.relative_strength || "NEUTRAL",
        
        // Options Fields (OPTIONS)
        strike: strike || "--",
        optionType: type || "CE",
        expiry: opt.expiry || "28 APR",
        strikeType: isSuggested ? "ATM Suggestion" : (opt.strike_type || "ATM"),
        strategy: opt.strategy || (isSuggested ? "ATM MOMENTUM" : "STRATEGY"),
        premium: premium,
        premiumSL: parseFloat(opt.premium_sl || 0),
        premiumT1: parseFloat(opt.premium_target1 || opt.premium_targets?.[0] || 0),
        premiumT2: parseFloat(opt.premium_target2 || opt.premium_targets?.[1] || 0),
        lotSize: lotSize,
        maxLoss: premium * lotSize,
        oiState: getOIState(data.insights?.oi_buildup || opt.oi_buildup || d?.microstructure?.oi_buildup),
        pcr: getPCRState(data.insights?.pcr || opt.pcr || d?.microstructure?.pcr),
        isSuggestedStrike: isSuggested,
        
        allocation: (data?.score >= 75 || d?.meta_score >= 75) ? "100%" : ((data?.score >= 60 || d?.meta_score >= 60) ? "50%" : "MINIMAL"),
        riskLevel: riskLevel,
        riskRuin: d?.risk_of_ruin?.risk_level || "MEDIUM",
        riskReward: data?.rr || d?.risk_of_ruin?.risk_reward || "N/A",
        score: d?.meta_score || data?.score || 0
    };
}

function updateHeroDecisionStrip(data, vm) {
    const hPrice = document.getElementById('hero-price');
    const hEntry = document.getElementById('hero-entry');
    const hSL = document.getElementById('hero-sl');
    const hTarget = document.getElementById('hero-target');
    const hRR = document.getElementById('hero-rr');
    
    const hPriceLabel = document.getElementById('hero-price-label');
    const hEntryLabel = document.getElementById('hero-entry-label');
    const hSLLabel = document.getElementById('hero-sl-label');
    const hTargetLabel = document.getElementById('hero-target-label');

    if (hPrice) hPrice.textContent = formatWithCurrency(data.meta.cmp, data.meta.currency);
    
    if (vm.mode === 'OPTIONS') {
        if (hPriceLabel) hPriceLabel.textContent = "PREMIUM CMP";
        if (hEntryLabel) hEntryLabel.textContent = "PREM ENTRY";
        if (hSLLabel) hSLLabel.textContent = "PREM SL";
        if (hTargetLabel) hTargetLabel.textContent = "PREM TARGET";
        
        const fmtPrem = (val) => val > 0 ? `₹${formatVal(val)}` : "AWAITING...";
        if (hEntry) hEntry.textContent = fmtPrem(vm.premium);
        if (hSL) hSL.textContent = fmtPrem(vm.premiumSL);
        if (hTarget) hTarget.textContent = fmtPrem(vm.premiumT1);
        if (hRR) hRR.textContent = data.rr || "N/A";
    } else {
        if (hPriceLabel) hPriceLabel.textContent = "CURRENT PRICE";
        if (hEntryLabel) hEntryLabel.textContent = "ENTRY";
        if (hSLLabel) hSLLabel.textContent = "STOP LOSS";
        if (hTargetLabel) hTargetLabel.textContent = "TARGET";
        
        if (hEntry) hEntry.textContent = formatWithCurrency(data.decision.entry_price || data.meta.cmp, data.meta.currency);
        if (hSL) hSL.textContent = formatWithCurrency(data.decision.stop_loss || data.summary.stop_loss, data.meta.currency);
        if (hTarget) hTarget.textContent = formatWithCurrency(data.decision.target_price, data.meta.currency);
        if (hRR) hRR.textContent = data.rr || "0.00";
    }
    
    // Action Badge Sync
    const heroSignal = document.getElementById('hero-signal-badge');
    if (heroSignal) {
        heroSignal.textContent = vm.executionSignal;
        const color = getExecutionState(vm);
        heroSignal.className = `mt-0.5 px-4 py-0.5 rounded text-[10px] font-black tracking-widest border border-current uppercase ${
            color === 'green' ? 'bg-green-900/30 text-green-400' : 
            color === 'yellow' ? 'bg-yellow-900/30 text-yellow-400' :
            color === 'indigo' ? 'bg-indigo-900/30 text-indigo-400' : 'bg-red-900/30 text-red-400'
        }`;
    }
}

function getExecutionState(vm) {
    if (vm.executionSignal === "EXECUTE") return "green";
    if (vm.executionSignal === "WATCH" || vm.setupState === "FORMING") return "yellow";
    if (vm.executionSignal === "CLOSED") return "indigo";
    return "red";
}

function renderScore(vm) {
    const scoreBadge = document.getElementById('ee-score-badge');
    if (!scoreBadge || !vm.score) {
        if (scoreBadge) scoreBadge.classList.add('hidden');
        return;
    }
    
    scoreBadge.classList.remove('hidden');
    scoreBadge.innerText = `Score: ${vm.score}`;
    
    // Use semantic CSS classes from style.css (refactored from inline Tailwind)
    scoreBadge.className = 'score-badge';
    if (vm.score >= 85)      scoreBadge.classList.add('score-badge-high');
    else if (vm.score >= 65) scoreBadge.classList.add('score-badge-mid');
    else                     scoreBadge.classList.add('score-badge-low');
}

let previousSignalState = null;

function updateExecutionEdge(data) {
    const panel = document.getElementById('execution-edge-panel');
    if (!panel) return;

    if (!data || !data.action) {
        panel.classList.add('hidden');
        return;
    }

    panel.classList.remove('hidden');
    const vm = toViewModel(data);

    // Toast logic
    if (previousSignalState === "FORMING" && vm.executionSignal === "EXECUTE") {
        const sym = vm.symbol || 'Trade';
        showToast(`🚀 ${sym} execution triggered!`, 'success');
    }
    previousSignalState = vm.executionSignal !== "-" ? vm.executionSignal : vm.setupState;

    // Narrative & Summary
    const narrativeEl = document.getElementById('ee-narrative');
    if (narrativeEl) {
        const formatted = formatNarrative(vm);
        // Simplified view for primary card: just bullets
        narrativeEl.innerHTML = `
            <ul class="space-y-1">
                ${formatted.bullets.slice(0, 2).map(b => `<li class="flex items-center gap-2"><span class="w-1 h-1 bg-blue-500 rounded-full"></span>${b.trim()}</li>`).join('')}
            </ul>
        `;
    }

    // Analysis Tab Title
    const analysisTxt = document.getElementById('ee-analysis-text');
    if (analysisTxt) {
        const formatted = formatNarrative(vm);
        analysisTxt.innerHTML = `<strong>${formatted.title}</strong><br/>${formatted.bullets.join('<br/>• ')}`;
    }
    
    const undLabel = document.getElementById('ee-underlying-label');
    if (undLabel) undLabel.textContent = vm.symbol;
    
    const undPrice = document.getElementById('ee-underlying-price');
    if (undPrice) undPrice.textContent = formatVal(vm.underlyingPrice);

    // Execution State Badge
    const stateColor = getExecutionState(vm);
    const badgeEl = document.getElementById('ee-execution-badge');
    if (badgeEl) {
        badgeEl.innerText = vm.executionSignal !== "-" ? vm.executionSignal : (vm.setupState !== "-" ? vm.setupState : "WAITING");
        badgeEl.className = `px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest border shadow-lg ${
            stateColor === "green" ? "bg-green-900/30 text-green-400 border-green-500/50" :
            stateColor === "yellow" ? "bg-yellow-900/30 text-yellow-400 border-yellow-500/50" :
            stateColor === "indigo" ? "bg-indigo-900/30 text-indigo-400 border-indigo-500/50" :
            "bg-red-900/30 text-red-400 border-red-500/50"
        }`;
    }
    
    renderScore(vm);

    // DUAL MODE RENDERING
    const optionsGrid = document.getElementById('ee-options-grid');
    const optionLabel = document.getElementById('ee-option-label');
    const optionRisk = document.getElementById('ee-option-risk');
    
    const microTitle = document.getElementById('micro-title');
    const microL1 = document.getElementById('micro-label-1');
    const microL2 = document.getElementById('micro-label-2');
    const microL3 = document.getElementById('micro-label-3');
    const microV1 = document.getElementById('ee-micro-val-1');
    const microV2 = document.getElementById('ee-micro-val-2');
    const microV3 = document.getElementById('ee-micro-val-3');
    
    if (vm.mode === 'OPTIONS') {
        optionsGrid?.classList.remove('hidden');
        optionLabel?.classList.remove('hidden');
        optionRisk?.classList.remove('hidden');
        
        if (optionLabel) {
            optionLabel.innerHTML = `
                <span class="flex items-center gap-1.5">
                    <span class="text-indigo-400 text-[9px] font-black">F&O</span>
                    <span class="px-2 py-0.5 rounded border ${vm.optionType === 'CE' ? 'bg-green-500/20 text-green-400 border-green-500/30' : 'bg-red-500/20 text-red-400 border-red-500/30'}">
                        ${vm.strike} ${vm.optionType}
                    </span>
                </span>
            `;
            optionLabel.className = "flex items-center px-1 text-[10px] font-black";
        }
        
        // Set premium values
        const fmtPrem = (val) => val > 0 ? `₹${formatVal(val)}` : "Awaiting...";
        document.getElementById('ee-premium-entry').textContent = fmtPrem(vm.premium);
        document.getElementById('ee-premium-sl').textContent = fmtPrem(vm.premiumSL);
        document.getElementById('ee-premium-t1').textContent = fmtPrem(vm.premiumT1);
        document.getElementById('ee-premium-t2').textContent = fmtPrem(vm.premiumT2);
        
        // Risk
        document.getElementById('ee-lot-size').textContent = vm.lotSize;
        const maxLossEl = document.getElementById('ee-max-loss');
        if (vm.premium > 0) {
            maxLossEl.textContent = `₹${formatVal(vm.maxLoss)}`;
            maxLossEl.className = "text-xs font-black text-red-400";
        } else {
            maxLossEl.textContent = "---";
            maxLossEl.className = "text-xs font-black text-gray-500";
        }
        
        // Microstructure (F&O)
        if (microTitle) microTitle.textContent = "F&O Microstructure";
        if (microL1) microL1.textContent = "OI Build-up";
        if (microL2) microL2.textContent = "PCR Ratio";
        if (microL3) microL3.textContent = "Option Strat";
        if (microV1) microV1.textContent = vm.oiState;
        if (microV2) microV2.textContent = vm.pcr;
        
        // Populate Analysis tab specific fields
        const oiAnalysis = document.getElementById('ee-micro-val-1-analysis');
        const pcrAnalysis = document.getElementById('ee-micro-val-2-analysis');
        if (oiAnalysis) oiAnalysis.textContent = vm.oiState;
        if (pcrAnalysis) pcrAnalysis.textContent = vm.pcr;

        if (microV3) {
            microV3.textContent = vm.strategy;
            microV3.className = `text-[9px] font-black px-1.5 py-0.5 rounded ${
                vm.strategy.includes('MOMENTUM') ? 'bg-indigo-500/20 text-indigo-400' : 'bg-blue-500/20 text-blue-400'
            }`;
        }
    } else {
        optionsGrid?.classList.add('hidden');
        optionLabel?.classList.add('hidden');
        optionRisk?.classList.add('hidden');
        
        // Microstructure (EQUITY)
        if (microTitle) microTitle.textContent = "Stock Microstructure";
        if (microL1) microL1.textContent = "Volume Surge";
        if (microL2) microL2.textContent = "Trend Intensity";
        if (microL3) microL3.textContent = "Relative Strength";
        
        if (microV1) {
            microV1.textContent = vm.volumeSurge;
            const volVal = parseFloat(vm.volumeSurge);
            if (volVal >= 2.0) microV1.className = "text-[9px] font-black px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30 animate-pulse uppercase";
            else if (volVal >= 1.3) microV1.className = "text-[9px] font-black px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-400 border border-orange-500/30 uppercase";
            else microV1.className = "text-[9px] font-black px-1.5 py-0.5 rounded bg-gray-800 text-gray-400 uppercase";
        }
        
        if (microV2) {
            const intensity = vm.trendIntensity.toUpperCase();
            microV2.textContent = intensity;
            if (intensity.includes("VERTICAL") || intensity.includes("STRONG")) {
                microV2.className = "text-[9px] font-black px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30";
            } else {
                microV2.className = "text-[9px] font-black px-1.5 py-0.5 rounded bg-gray-800 text-gray-400";
            }
        }

        if (microV3) {
            microV3.textContent = vm.relativeStrength;
            const rs = vm.relativeStrength.toUpperCase();
            if (rs.includes("STRONG")) microV3.className = "text-[9px] font-black px-1.5 py-0.5 rounded bg-green-500/20 text-green-400 border border-green-500/30";
            else microV3.className = "text-[9px] font-black px-1.5 py-0.5 rounded bg-gray-800 text-gray-400";
        }
    }

    // Risk Panel
    const allocEl = document.getElementById('ee-allocation');
    if (allocEl) allocEl.textContent = vm.allocation;
    const ruinEl = document.getElementById('ee-risk-ruin');
    if (ruinEl) ruinEl.textContent = vm.riskRuin;

    // Safely update DOM elements
    const setTxt = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.innerText = val;
    };

    // Execution
    setTxt('ee-signal', vm.executionSignal);
    setTxt('ee-entry-type', vm.entryType);
    
    // Style next action
    const nextActionEl = document.getElementById('ee-next-action');
    if (nextActionEl) {
        nextActionEl.innerText = vm.nextAction;
        nextActionEl.className = "text-xs font-black px-2 py-0.5 rounded shadow-lg transition-colors";
        if (vm.executionSignal === "EXECUTE") nextActionEl.classList.add("bg-green-500/20", "text-green-400", "border", "border-green-500/30");
        else if (vm.executionSignal === "WATCH") nextActionEl.classList.add("bg-yellow-500/20", "text-yellow-400", "border", "border-yellow-500/30");
        else nextActionEl.classList.add("bg-red-500/10", "text-red-400", "border", "border-red-500/20");
    }

    // Market Context
    setTxt('ee-trend', vm.marketTrend);
    setTxt('ee-bias', vm.marketBias);
    setTxt('ee-regime', vm.regime.replace(/_/g, ' '));

    // Confidence Bar
    const confFill = document.getElementById('ee-confidence-fill');
    const confVal = document.getElementById('ee-confidence-val');
    if (confFill && confVal) {
        confFill.style.width = `${vm.score}%`;
        confVal.innerText = `${vm.score}%`;
        confFill.className = "h-full transition-all duration-1000";
        if (vm.score >= 80) confFill.classList.add("bg-green-500");
        else if (vm.score >= 60) confFill.classList.add("bg-yellow-500");
        else confFill.classList.add("bg-red-500");
    }

    updatePrimaryAction(vm);
}

function updatePrimaryAction(vm) {
    const btn = document.getElementById("primary-action-btn");
    if (!btn) return;
    
    btn.className = "px-6 py-2.5 rounded-xl font-black text-xs uppercase tracking-widest transition-all shadow-lg shrink-0 w-full sm:w-auto text-white";
    
    if (vm.executionSignal === "EXECUTE") {
        if (vm.mode === 'OPTIONS') {
            const isCall = vm.optionType === 'CE';
            btn.innerText = isCall ? "BUY CALL (CE)" : "BUY PUT (PE)";
            btn.className = `px-6 py-2.5 rounded-xl font-black text-xs uppercase tracking-widest transition-all shadow-lg shrink-0 w-full sm:w-auto text-white ${
                isCall ? 'bg-green-600 hover:bg-green-500' : 'bg-red-600 hover:bg-red-500'
            }`;
        } else {
            btn.innerText = "PLACE ORDER";
            btn.classList.add("bg-blue-600", "hover:bg-blue-500");
        }
        
        btn.onclick = () => {
            const sym = document.getElementById('symbol-input').value;
            const entry = vm.mode === 'OPTIONS' ? vm.premium : (document.getElementById('cmp').innerText || '0.00');
            const sl = vm.mode === 'OPTIONS' ? vm.premiumSL : (document.getElementById('stop-loss').innerText || '0.00');
            TradingAssistant.addOutcome(sym, entry, sl);
        };
    } else if (vm.executionSignal === "WATCH") {
        btn.innerText = "SET ALERT";
        btn.classList.add("bg-yellow-600", "hover:bg-yellow-500", "shadow-yellow-900/50");
        btn.onclick = () => {
            const sym = document.getElementById('symbol-input').value;
            TradingAssistant.addAlert(sym, "WATCH");
        };
    } else {
        btn.innerText = "SCAN NEXT";
        btn.classList.add("bg-gray-800", "hover:bg-gray-700");
        btn.onclick = () => loadTopTrades();
    }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    // Use semantic CSS classes from style.css (refactored from inline Tailwind)
    toast.className = `toast-base toast-${type}`;
    
    const icon = type === 'success' ? '\u2705' : type === 'warning' ? '\u26A0\uFE0F' : type === 'error' ? '\u274C' : '\u2139\uFE0F';
    toast.innerHTML = `<span class="text-base">${icon}</span> <span>${message}</span>`;
    
    container.appendChild(toast);
    
    requestAnimationFrame(() => {
        toast.classList.add('toast-show');
    });

    setTimeout(() => {
        toast.classList.remove('toast-show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

async function loadTopTrades() {
    const panel = document.getElementById('top-trades-panel');
    const list = document.getElementById('top-trades-list');
    if (!panel || !list) return;

    panel.classList.remove('hidden');
    list.innerHTML = '<div class="text-gray-500 text-xs italic px-2">Scanning market for top setups...</div>';

    try {
        const symbolsToScan = ["NSE:RELIANCE-EQ", "NSE:TCS-EQ", "NSE:INFY-EQ", "NSE:HDFCBANK-EQ", "NSE:ICICIBANK-EQ"];
        const results = [];
        
        await Promise.all(symbolsToScan.map(async (sym) => {
            try {
                const res = await fetch(`${API_URL}?symbol=${encodeURIComponent(sym)}&tf=15m&strategy=SR`);
                if (res.ok) {
                    const data = await res.json();
                    if (data && data.status === 'success') {
                        results.push({ symbol: sym, data: data });
                    }
                }
            } catch (e) { console.warn("Scan failed for", sym); }
        }));
        
        if (results.length === 0) {
            list.innerHTML = '<div class="text-red-400 text-xs font-bold px-2">Scan failed or no data available.</div>';
            return;
        }

        results.sort((a, b) => {
            const vmA = toViewModel(a.data);
            const vmB = toViewModel(b.data);
            
            const getPriority = (vm) => {
                if (vm.executionSignal === "EXECUTE") {
                    return vm.mode === 'OPTIONS' ? 100 : 80;
                }
                if (vm.executionSignal === "WATCH" || vm.setupState === "FORMING") return 60;
                if (vm.executionSignal === "CLOSED") return 40;
                return 20;
            };
            
            const pA = getPriority(vmA);
            const pB = getPriority(vmB);
            
            if (pA !== pB) return pB - pA;
            return vmB.score - vmA.score;
        });

        list.innerHTML = '';
        results.slice(0, 5).forEach(item => {
            const vm = toViewModel(item.data);
            const stateColor = getExecutionState(vm);
            
            const badgeIcon = stateColor === 'green' ? '🟢' : stateColor === 'yellow' ? '🟡' : (isMarketOpen() ? '🟢' : '🌙');
            const signalText = vm.executionSignal !== '-' ? vm.executionSignal : vm.setupState;
            const displaySignal = isMarketOpen() ? signalText : `${signalText} (OFF)`;
            
            const actionHint = vm.executionSignal === 'EXECUTE' ? 'Ready' : (vm.setupState === 'FORMING' ? 'Forming' : 'Analysis');
            
            const card = document.createElement('div');
            card.className = "min-w-[160px] bg-gray-900/50 border border-gray-800 p-3 rounded-xl hover:border-gray-600 hover:scale-105 transition-all duration-300 cursor-pointer group shrink-0";
            card.onclick = () => {
                document.getElementById('symbol-input').value = item.symbol;
                fetchData(false);
            };
            
            const optionBadge = vm.mode === 'OPTIONS' ? `
                <div class="mt-1 flex items-center gap-1">
                    <span class="px-1.5 py-0.5 rounded text-[8px] font-black ${vm.optionType === 'CE' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}">${vm.strike} ${vm.optionType}</span>
                    <span class="text-[8px] text-gray-600 font-bold">${vm.expiry}</span>
                </div>
            ` : '';

            card.innerHTML = `
                <div class="flex justify-between items-start mb-1">
                    <span class="font-bold text-xs text-white group-hover:text-blue-400 transition-colors">${item.symbol.replace('NSE:', '').replace('-EQ', '')}</span>
                    <div class="flex items-center gap-2 z-10">
                        <span class="text-[10px] font-bold text-gray-500">${vm.score}</span>
                    </div>
                </div>
                ${optionBadge}
                <div class="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-gray-400 mt-1">
                    <span>${badgeIcon}</span>
                    <span class="${stateColor === 'green' ? 'text-green-400' : stateColor === 'yellow' ? 'text-yellow-400' : 'text-indigo-400'}">${displaySignal}</span>
                </div>
                <div class="mt-1.5 text-[9px] text-gray-500 italic">
                    ${actionHint}
                </div>
            `;
            list.appendChild(card);
            
            if (vm.executionSignal === "EXECUTE") {
                if (TradingAssistant.isPinned(item.symbol) || TradingAssistant.state.alerts.find(a => a.symbol === item.symbol)) {
                    showToast(`🚀 EXECUTE Triggered for ${item.symbol}!`, 'success');
                } else {
                    showToast(`🚀 New setup found: ${item.symbol}`, 'success');
                }
            }
        });
        
    } catch (err) {
        console.error("Scanner error", err);
        list.innerHTML = '<div class="text-red-400 text-xs font-bold px-2">Error running scanner.</div>';
    }
}

function updateUI(data, isBackground = false) {
    try {
        // Update Market Status Banner
        const marketBanner = document.getElementById('market-status-banner');
        const marketTitle = document.getElementById('market-status-title');
        const marketDesc = document.getElementById('market-status-desc');
        const marketIcon = document.getElementById('market-status-icon');
        
        if (marketBanner) {
            if (isMarketOpen()) {
                marketBanner.classList.add('hidden');
            } else {
                marketBanner.classList.remove('hidden');
                if (marketTitle) marketTitle.textContent = "MARKET CLOSED";
                if (marketDesc) marketDesc.textContent = "Session ended. Showing final intelligence snapshot.";
                if (marketIcon) marketIcon.textContent = "🌙";
            }
        }

        // Hide error message if it exists
        const errDiv = document.getElementById('chart-error-msg');
        if (errDiv) errDiv.classList.add('hidden');
        const tvChart = document.getElementById('tv-chart');
        if (tvChart) tvChart.classList.remove('hidden');

        // 1. Meta & Summary
        const cmpEl = document.getElementById('cmp');
        if (cmpEl) cmpEl.textContent = formatWithCurrency(data.meta.cmp, data.meta.currency);

        const verTag = document.getElementById('ver-tag');
        if (verTag) verTag.textContent = "v1.6.0 F&O Terminal";

        // Sync Time & Symbol
        const syncTime = document.getElementById('sync-time');
        if (syncTime && data.meta.last_update) syncTime.textContent = `${data.meta.last_update}`;

        const sLabel = document.getElementById('chart-symbol-label');
        const tfLabel = document.getElementById('chart-tf-label');
        if (sLabel) sLabel.textContent = data.meta.symbol || 'NIFTY50';
        if (tfLabel) {
            const tf = data.meta.tf || data.meta.timeframe || '15m';
            const names = { '5m': '5 MIN', '15m': '15 MIN', '30m': '30 MIN', '45m': '45 MIN', '1H': 'HOURLY', '1D': 'DAILY', '1W': 'WEEKLY', '1M': 'MONTHLY' };
            const labelText = names[tf] || tf.toUpperCase();
            tfLabel.textContent = `${labelText} SESSION`;
        }


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

        // 8. Sync Intelligence ViewModel
        const vm = toViewModel(data);

        // 9. Execution Edge & Hero Strip Sync
        updateExecutionEdge(data);
        updateHeroDecisionStrip(data, vm);

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
                const bias = data.insights.ema_bias || 'NEUTRAL';
                biasBadge.textContent = bias;
                // Semantic CSS classes from style.css (refactored from inline Tailwind)
                const biasClass = bias === 'Bullish' ? 'bias-badge-bullish'
                    : bias === 'Caution' ? 'bias-badge-caution'
                    : 'bias-badge-neutral';
                biasBadge.className = `px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest ${biasClass}`;
            }
        }

        // 3. AI Insights
        if (data.ai_analysis && data.ai_analysis.status === "success") {
            const ai = data.ai_analysis;
            const pBadge = document.getElementById('ai-priority-badge');
            if (pBadge) {
                pBadge.textContent = `PRIORITY: ${ai.priority.level}`;
                // Semantic CSS classes from style.css (refactored from inline Tailwind)
                const priClass = ai.priority.level === 'HIGH' ? 'priority-badge-high'
                    : ai.priority.level === 'MEDIUM' ? 'priority-badge-medium'
                    : 'priority-badge-low';
                pBadge.className = `px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest ${priClass}`;
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

            // Volume & EMA logic
            if (volumeSeries && volumeEmaSeries) {
                const volumeData = data.ohlcv.map(d => ({
                    time: d.time,
                    value: (d.volume === null || d.volume === undefined || isNaN(d.volume)) ? 0 : Number(d.volume),
                    color: d.close >= d.open ? 'rgba(0, 192, 118, 0.5)' : 'rgba(246, 70, 93, 0.5)'
                }));
                console.log(`[Chart] Setting volume data: ${volumeData.length} points. Max vol: ${Math.max(...volumeData.map(d => d.value))}`);
                volumeSeries.setData(volumeData);

                // Calculate 20 EMA of volume
                if (volumeData.length > 0) {
                    const emaData = [];
                    const period = 20;
                    const k = 2 / (period + 1);
                    let prevEma = volumeData[0].value;
                    
                    for (let i = 0; i < volumeData.length; i++) {
                        const val = volumeData[i].value;
                        const ema = i === 0 ? val : (val - prevEma) * k + prevEma;
                        emaData.push({ time: volumeData[i].time, value: isNaN(ema) ? 0 : ema });
                        prevEma = ema;
                    }
                    volumeEmaSeries.setData(emaData);
                }
            }
            
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

        // 10. Update Execution Edge Panel
        updateExecutionEdge(data, vm);

    } catch (e) {
        console.error("UI Update Error:", e);
    }
}

// --- LAYERED UX LOGIC ---
function toggleEEDetails() {
    const panel = document.getElementById('ee-details-panel');
    const text = document.getElementById('ee-toggle-text');
    const icon = document.getElementById('ee-toggle-icon');
    const shimmer = document.getElementById('ee-details-shimmer');
    
    if (!panel) return;
    
    const isHidden = panel.classList.contains('hidden');
    if (isHidden) {
        panel.classList.remove('hidden');
        if (text) text.textContent = "Hide Details";
        if (icon) icon.className = "fas fa-chevron-up text-[8px]";
        
        // Show shimmer for a brief moment to simulate "Preparing Data"
        if (shimmer) {
            shimmer.classList.remove('hidden');
            setTimeout(() => {
                shimmer.classList.add('hidden');
            }, 600);
        }
    } else {
        panel.classList.add('hidden');
        if (text) text.textContent = "View Details";
        if (icon) icon.className = "fas fa-chevron-down text-[8px]";
    }
}

function switchEETab(tab) {
    const tabs = ['summary', 'analysis', 'risk'];
    tabs.forEach(t => {
        const content = document.getElementById(`ee-content-${t}`);
        const btn = document.getElementById(`ee-tab-${t}`);
        if (content) content.classList.add('hidden');
        if (btn) {
            btn.classList.remove('border-blue-500', 'text-white');
            btn.classList.add('border-transparent', 'text-gray-500');
        }
    });
    
    const activeContent = document.getElementById(`ee-content-${tab}`);
    const activeBtn = document.getElementById(`ee-tab-${tab}`);
    if (activeContent) activeContent.classList.remove('hidden');
    if (activeBtn) {
        activeBtn.classList.remove('border-transparent', 'text-gray-500');
        activeBtn.classList.add('border-blue-500', 'text-white');
    }
}

function updateHeroDecisionStrip(data, vm) {
    const heroStrip = document.getElementById('hero-decision-strip');
    if (!heroStrip || !data.summary || !vm) return;
    
    heroStrip.classList.remove('hidden');
    
    // Top-Level Action Badge in Nav Bar
    const actionBadge = document.getElementById('hero-action-badge');
    const badgeSpan = actionBadge ? actionBadge.querySelector('span') : null;
    const badgeIcon = actionBadge ? actionBadge.querySelector('i') : null;
    
    if (badgeSpan) {
        badgeSpan.textContent = vm.executionSignal;
        actionBadge.className = 'decision-badge';
        
        if (vm.executionSignal === "EXECUTE") {
            actionBadge.classList.add('decision-buy');
            if (badgeIcon) badgeIcon.className = 'fas fa-check-circle';
        } else if (vm.executionSignal === "WATCH") {
            actionBadge.classList.add('decision-watch');
            if (badgeIcon) badgeIcon.className = 'fas fa-eye';
        } else {
            actionBadge.classList.add('decision-no-trade');
            if (badgeIcon) badgeIcon.className = 'fas fa-times-circle';
        }
    }

    // POWER HEADER INTEGRATION (Keep metrics persistent in Navigation Bar)
    const currency = data.meta?.currency || 'INR';
    const hPrice = document.getElementById('hero-price');
    if (hPrice) hPrice.textContent = formatWithCurrency(data.meta.cmp, currency);
    
    const hEntry = document.getElementById('hero-entry');
    const hSl = document.getElementById('hero-sl');
    const hTarget = document.getElementById('hero-target');
    const hRR = document.getElementById('hero-rr');
    const hSignal = document.getElementById('hero-signal-badge');

    const side = data.summary?.side || data.strategy?.side || data.side || 'LONG';
    
    if (hSignal) {
        if (vm.executionSignal === "REJECT") {
            hSignal.textContent = 'WAIT';
            hSignal.className = 'mt-0.5 px-4 py-0.5 rounded text-[10px] font-black tracking-widest bg-gray-800 text-gray-500 uppercase';
        } else if (vm.executionSignal === "WATCH") {
            hSignal.textContent = 'OBSERVE';
            hSignal.className = 'mt-0.5 px-4 py-0.5 rounded text-[10px] font-black tracking-widest bg-yellow-900/40 text-yellow-500 border border-yellow-500/30 uppercase';
        } else {
            const label = side === 'LONG' ? 'BUY' : 'SELL';
            hSignal.textContent = label;
            hSignal.className = `mt-0.5 px-4 py-0.5 rounded text-[10px] font-black tracking-widest uppercase ${side === 'LONG' ? 'bg-green-600 text-white shadow-[0_0_10px_rgba(34,197,94,0.4)]' : 'bg-red-600 text-white shadow-[0_0_10px_rgba(239,68,68,0.4)]'}`;
        }
    }

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
        const side = fullData.summary?.side || fullData.strategy?.side || fullData.side || 'LONG';
        const isEntry = action.includes('BUY') || action.includes('ENTRY');
        const isAvoid = action.includes('AVOID') || action === 'WAIT' || action === 'HOLD';
        
        const displayAction = isAvoid ? action : `${side} | ${action}`;

        headerAction.innerHTML = `
            <div class="px-3 py-1 bg-white/5 border border-white/5 rounded-lg flex items-center gap-2">
                <span class="${isEntry ? 'text-green-400' : 'text-amber-400'} animate-pulse text-[10px]">●</span>
                <span class="text-[9px] font-black text-white tracking-widest uppercase">${displayAction}</span>
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
    else if (strategy === 'SWING') {
        const primarySupports = levels.primary?.supports || [];
        const primaryResists = levels.primary?.resistances || [];

        primarySupports.forEach(lv => addLine(lv, '#8B5CF6', 'SWING SUP')); // Purple color for Swing
        primaryResists.forEach(lv => addLine(lv, '#8B5CF6', 'SWING RES'));
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

        document.getElementById('tf-selector').addEventListener('change', () => {
            const tf = document.getElementById('tf-selector').value;
            // Sync buttons if it's 5m or 15m
            document.querySelectorAll('#intraday-tf-toggle button').forEach(btn => {
                if (btn.dataset.tf === tf) {
                    btn.classList.add('bg-blue-600', 'text-white');
                    btn.classList.remove('text-gray-400');
                } else {
                    btn.classList.remove('bg-blue-600', 'text-white');
                    btn.classList.add('text-gray-400');
                }
            });
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
        const tf = tfSelector ? tfSelector.value : '1D';
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
                // If Fyers is reported as inactive by backend, override source to 'expired'
                const effectiveSource = (hitsData.is_fyers_active === false) ? 'expired' : (hitsData.source || 'live');
                intelligenceApp.updateHits(hitsData.data, effectiveSource);
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
            const names = { '5m': '5 MIN', '15m': '15 MIN', '30m': '30 MIN', '45m': '45 MIN', '1H': 'HOURLY', '1D': 'DAILY', '1W': 'WEEKLY', '1M': 'MONTHLY' };
            tfLabel.textContent = names[tf] || tf.toUpperCase();
        }
        
        fetchData();
    }
};

// Handle messages from popups (Fyers Login)
window.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'fyers_auth') {
        console.log("Fyers auth message received:", event.data);
        if (event.data.status === 'success') {
            console.log("Fyers success received, waiting for session to settle...");
            // Add a small delay to ensure backend has flushed the token file
            setTimeout(() => {
                checkFyersStatus();
                fetchData();
            }, 500);
        } else {
            console.error("Fyers authentication failed:", event.data.message);
            alert("Fyers Authentication Failed: " + (event.data.message || "Unknown error"));
        }
    }
});

// Check on load
document.addEventListener('DOMContentLoaded', () => {
    TradingAssistant.init();
    checkFyersStatus();
    // Poll every 30 seconds for background refresh
    setInterval(checkFyersStatus, 30000);
});

