class MarketIntelligence {
    constructor(hitsTableId, sectorListId) {
        this.hitsBody = document.getElementById(hitsTableId);
        this.sectorList = document.getElementById(sectorListId);
        this.allHits = [];
        this.allSectors = {};
        this.activeSectorKey = null;
        this.isProView = false;
        this.summaryText = document.getElementById('market-summary-text');
        this.summaryBlock = document.getElementById('market-summary-block');
        this.summaryMode = 'evening'; // DEFAULTS TO EVENING WRAP
        this.summaryData = null;
        this.hitsSyncStatus = document.getElementById('hits-sync-status');
        this._initExplanationEvents();
    }

    updateSyncStatus(source) {
        if (!this.hitsSyncStatus) return;
        if (source === 'fallback' || source === 'cached') {
            this.hitsSyncStatus.innerHTML = `
                <span class="w-1.5 h-1.5 bg-yellow-500 rounded-full"></span>
                <span class="text-yellow-500 font-bold animate-pulse">CACHED DATA</span>
            `;
            this.hitsSyncStatus.title = "Displaying last available data due to rate limits.";
        } else if (source === 'error') {
            this.hitsSyncStatus.innerHTML = `
                <span class="w-1.5 h-1.5 bg-red-500 rounded-full"></span>
                <span class="text-red-500 font-bold">SYNC ERROR</span>
            `;
        } else {
            this.hitsSyncStatus.innerHTML = `
                <span class="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-pulse"></span>
                LIVE SYNC
            `;
            this.hitsSyncStatus.title = "Live data from Yahoo Finance";
        }
    }

    _initExplanationEvents() {
        const btnBeginner = document.getElementById('view-beginner');
        const btnPro = document.getElementById('view-pro');

        if (btnBeginner && btnPro) {
            btnBeginner.addEventListener('click', () => {
                this.isProView = false;
                btnBeginner.classList.add('bg-indigo-600', 'text-white');
                btnBeginner.classList.remove('text-gray-500');
                btnPro.classList.add('text-gray-500');
                btnPro.classList.remove('bg-indigo-600', 'text-white');
                this._updateExplanationView();
            });

            btnPro.addEventListener('click', () => {
                this.isProView = true;
                btnPro.classList.add('bg-indigo-600', 'text-white');
                btnPro.classList.remove('text-gray-500');
                btnBeginner.classList.add('text-gray-500');
                btnBeginner.classList.remove('bg-indigo-600', 'text-white');
                this._updateExplanationView();
            });
        }
    }

    updateHits(hits, source = 'live') {
        this.updateSyncStatus(source);
        if (!this.hitsBody) return;

        // 1. Store previous confidence scores before updating state
        this.prevConfidence = {};
        if (Array.isArray(this.allHits)) {
            this.allHits.forEach(hit => {
                const conf = this._calculateConfidence(hit);
                this.prevConfidence[hit.symbol] = conf.score;
            });
        }

        this.allHits = Array.isArray(hits) ? hits : [];
        this._renderHitsTable();
        if (window.renderTopPicks) {
            window.renderTopPicks(this.allHits);
        }
    }

    updateSectors(sectorData, alerts, source = 'live') {
        this.updateSyncStatus(source);
        if (!this.sectorList) return;
        this.lastSectorData = sectorData;
        this.allSectors = sectorData || {};

        if (!sectorData || Object.keys(sectorData).length === 0) {
            this.sectorList.innerHTML = '<div class="p-8 text-center text-gray-500 italic border border-gray-800 rounded-2xl">Awaiting sector rotation data...</div>';
            return;
        }

        // Regime Banner Logic (Consolidated v1.0)
        const sectorsArray = Object.values(sectorData);
        if (sectorsArray.length > 0) {
            const leadingCount = sectorsArray.filter(s => s && s.metrics && s.metrics.state === 'LEADING').length;
            const totalSectors = sectorsArray.length;
            const breadth = leadingCount / totalSectors;

            const banner = document.getElementById('market-regime-banner');
            const status = document.getElementById('regime-status');
            const desc = document.getElementById('regime-desc');

            if (banner && status && desc) {
                banner.classList.remove('hidden');
                if (breadth >= 0.4) {
                    status.textContent = "MARKET REGIME: RISK-ON";
                    status.className = "text-xs font-bold uppercase tracking-widest text-green-400";
                    desc.textContent = "Strong sector breadth. Momentum signals are likely to have high follow-through.";
                    banner.className = "glass rounded-xl border border-green-500/50 p-3 mb-4 flex items-center gap-3 animate-in fade-in duration-500 bg-green-500/5";
                } else if (breadth >= 0.2) {
                    status.textContent = "MARKET REGIME: NEUTRAL";
                    status.className = "text-xs font-bold uppercase tracking-widest text-blue-400";
                    desc.textContent = "Mixed participation. Focus on rotation into leading sectors.";
                    banner.className = "glass rounded-xl border border-blue-500/30 p-3 mb-4 flex items-center gap-3 animate-in fade-in duration-500";
                } else {
                    status.textContent = "MARKET REGIME: RISK-OFF";
                    status.className = "text-xs font-bold uppercase tracking-widest text-red-500";
                    desc.textContent = "Weak market breadth. Momentum signals should be traded with extreme caution.";
                    banner.className = "glass rounded-xl border border-red-500/50 p-3 mb-4 flex items-center gap-3 animate-in fade-in duration-500 bg-red-500/5";
                }
            }
        }

        const sectors = Object.entries(sectorData)
            .map(([name, data]) => ({ name, ...data }))
            .filter(s => s && s.metrics)
            .sort((a, b) => {
                const ap = this._statePriority(a.metrics.state);
                const bp = this._statePriority(b.metrics.state);
                if (bp !== ap) return bp - ap;
                return (b.metrics.momentumScore || 0) - (a.metrics.momentumScore || 0);
            });

        // SANITY CHECK: Too many leading sectors
        const leadingCount = sectors.filter(s => s.metrics.state === 'LEADING').length;
        if (leadingCount > 5) console.warn(`Too many LEADING sectors (${leadingCount}) — check RS logic scaling`);

        this.sectorList.innerHTML = sectors.map(sector => {
            const metrics = sector.metrics || {};
            const state = metrics.state || 'NEUTRAL';
            const stateMeta = this._stateMeta(state);
            const rsPercent = (sector.current?.rs || 0) * 100;
            const explanation = this._buildSectorExplanation(state, sector.current?.rs || 0, sector.current?.rm || 0);

            // Momentum Trend logic (NEW)
            const trend = metrics.momentumTrend || 'Stable';
            const trendIcon = trend === 'Strengthening' ? '↑' : (trend === 'Weakening' ? '↓' : '→');
            const trendColor = trend === 'Strengthening' ? 'text-green-400' : (trend === 'Weakening' ? 'text-red-400' : 'text-gray-500');

            // --- DEBUG OVERLAY CALCULATIONS (MUST-HAVE) ---
            const isDebug = new URLSearchParams(window.location.search).get('debug') === 'true';
            const sr = (metrics.sr || 0) * 100;
            const br = (metrics.br || 0) * 100;
            const rs = (sector.current?.rs || 0) * 100;
            const drs = (sector.current?.rm || 0) * 100;

            const debugPanel = isDebug ? `
                <div class="mt-3 p-3 bg-gray-900/80 rounded-xl border border-gray-700 font-mono text-[10px] leading-relaxed relative z-10">
                    <p class="text-gray-500 uppercase font-bold mb-1 tracking-widest text-[9px]">DEBUG — ${sector.name}</p>
                    <div class="grid grid-cols-2 gap-y-1">
                        <span class="text-gray-400">SR:</span> <span class="${sr >= 0 ? 'text-green-400' : 'text-red-400'}">${(sr >= 0 ? '+' : '') + sr.toFixed(2)}%</span>
                        <span class="text-gray-400">BR:</span> <span class="${br >= 0 ? 'text-green-400' : 'text-red-400'}">${(br >= 0 ? '+' : '') + br.toFixed(2)}%</span>
                        <span class="text-gray-400">RS:</span> <span class="${rs >= 0 ? 'text-green-400' : 'text-red-400'}">${(rs >= 0 ? '+' : '') + rs.toFixed(2)}%</span>
                        <span class="text-gray-400">ΔRS:</span> <span class="${drs >= 0 ? 'text-green-400' : 'text-red-400'}">${(drs >= 0 ? '+' : '') + drs.toFixed(2)}%</span>
                    </div>
                </div>
            ` : '';

            return `
                <div class="glass p-4 rounded-2xl border-l-4 ${stateMeta.borderClass} ${stateMeta.bgClass || ''} relative overflow-hidden group cursor-pointer"
                     data-sector-key="${sector.name}">
                    <div class="flex justify-between items-start relative z-10">
                        <div>
                            <h3 class="font-bold text-sm text-white">${sector.name ? sector.name.replace('NIFTY_', '').replace('_', ' ') : 'Unknown'}</h3>
                            <div class="flex items-center gap-3 mt-1">
                                <span class="text-[10px] font-bold ${stateMeta.textClass} uppercase tracking-tighter">${state}</span>
                                <span class="text-[10px] ${trendColor} font-bold" title="Momentum Trend: ${trend}">${trendIcon} ${trend.toUpperCase()}</span>
                                <span class="text-[10px] text-gray-400 font-mono">RS ${(rsPercent >= 0 ? '+' : '') + rsPercent.toFixed(2)}%</span>
                            </div>
                            <p class="text-[11px] text-gray-300 mt-2 leading-relaxed">${explanation}</p>
                        </div>
                        <div class="text-right">
                            <p class="text-[10px] text-gray-500 font-bold uppercase tracking-widest leading-none mb-1">Rank</p>
                            <p class="text-lg font-bold text-white mono">#${sector.rank || '—'}</p>
                        </div>
                    </div>
                    ${debugPanel}
                    <div class="mt-3 flex gap-1.5 text-[9px] relative z-10">
                        ${sector.commentary ? `<button class="px-2 py-0.5 bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-md hover:bg-indigo-500/20 transition-colors" data-action="ai-view" data-sector="${sector.name}">AI VIEW</button>` : ''}
                        <button class="px-2 py-0.5 bg-gray-800 text-gray-400 border border-gray-700 rounded-md hover:bg-gray-700 transition-colors" data-action="details" data-sector="${sector.name}">DETAILS</button>
                    </div>
                </div>
            `;
        }).join('');

        this.sectorList.querySelectorAll('[data-sector-key]').forEach((card) => {
            card.addEventListener('click', () => {
                const key = card.getAttribute('data-sector-key');
                if (window.focusSector && key) window.focusSector(key);
            });
        });

        this.sectorList.querySelectorAll('[data-action="ai-view"]').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const sectorName = btn.getAttribute('data-sector');
                if (window.showAICommentary && sectorName) window.showAICommentary(sectorName);
            });
        });

        this.sectorList.querySelectorAll('[data-action="details"]').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const sectorName = btn.getAttribute('data-sector');
                if (window.fetchDataForSymbol && sectorName) window.fetchDataForSymbol(sectorName, { fromIntelligence: true });
            });
        });

        this._renderHitsTable();

        if (window.renderActionableSectors) {
            window.renderActionableSectors(sectorData);
        }
    }

    updateEarlySetups(setups) {
        this.earlySetups = Array.isArray(setups) ? setups : [];
        this._renderEarlySetups();
    }

    updateWatchlist(data) {
        this.watchlistData = data || null;
        this._renderWatchlist();
    }

    _renderWatchlist() {
        if (!this.watchlistData) return;
        const card = document.getElementById('next-session-watchlist-card');
        if (!card) return;

        // If no data, hide it
        if (!this.watchlistData.strong_sectors && !this.watchlistData.breakout_candidates) {
            card.classList.add('hidden');
            return;
        }
        card.classList.remove('hidden');

        // Strong Sectors
        const strContainer = document.getElementById('wl-strong-sectors');
        if (strContainer) {
            const arr = this.watchlistData.strong_sectors || [];
            if (!arr.length) strContainer.innerHTML = '<span class="text-xs text-gray-500 italic">None currently</span>';
            else strContainer.innerHTML = arr.map(s => `<span class="px-2 py-0.5 bg-teal-500/10 text-teal-400 border border-teal-500/20 text-[10px] uppercase font-bold rounded">${s.replace('NIFTY_', '')}</span>`).join('');
        }

        // Avoid Sectors
        const avContainer = document.getElementById('wl-avoid-sectors');
        if (avContainer) {
            const arr = this.watchlistData.weak_sectors || [];
            if (!arr.length) avContainer.innerHTML = '<span class="text-xs text-gray-500 italic">None currently</span>';
            else avContainer.innerHTML = arr.map(s => `<span class="px-2 py-0.5 bg-red-500/10 text-red-400 border border-red-500/20 text-[10px] uppercase font-bold rounded">${s.replace('NIFTY_', '')}</span>`).join('');
        }

        // Breakout Candidates
        const boContainer = document.getElementById('wl-breakout-candidates');
        if (boContainer) {
            const arr = this.watchlistData.breakout_candidates || [];
            if (!arr.length) boContainer.innerHTML = '<span class="text-xs text-gray-500 italic">No clear setups found</span>';
            else {
                boContainer.innerHTML = arr.map(c => `
                    <div class="flex items-center justify-between text-xs border-b border-gray-800 pb-1 cursor-pointer hover:bg-gray-800/50 p-1 rounded" onclick="window.fetchDataForSymbol('${c.symbol}')">
                        <span class="font-bold text-white">${c.symbol}</span>
                        <div class="text-right">
                            <span class="text-teal-400 mono">₹${parseFloat(c.price).toFixed(2)}</span>
                            <span class="text-[9px] text-gray-500 block">${c.sector.replace('NIFTY_', '')}</span>
                        </div>
                    </div>
                `).join('');
            }
        }
    }

    updateSignalPerformance(data) {
        this.signalPerformance = data || null;
        this._renderSignalPerformance();
    }

    updateTradePerformance(data) {
        this.tradePerformance = data || null;
        this._renderTradePerformance();
    }

    _renderTradePerformance() {
        const data = this.tradePerformance || {};
        const setTxt = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };

        setTxt('trade-total', data.totalTrades ?? 0);
        setTxt('trade-win-rate', `${data.winRate ?? 0}%`);
        setTxt('trade-avg-r', `${(data.avgR ?? 0).toFixed ? (data.avgR ?? 0).toFixed(2) : data.avgR}R`);
        setTxt('trade-max-dd', `${(data.maxDrawdownR ?? 0).toFixed ? (data.maxDrawdownR ?? 0).toFixed(2) : data.maxDrawdownR}R`);
        setTxt('trade-profit-factor', (data.profitFactor ?? 0).toFixed ? (data.profitFactor ?? 0).toFixed(2) : data.profitFactor);

        const best = document.getElementById('trade-best-setups');
        const worst = document.getElementById('trade-worst-setups');

        if (best) {
            const rows = Array.isArray(data.bestSetups) ? data.bestSetups.slice(0, 3) : [];
            best.textContent = rows.length ? rows.map(r => `${r.symbol} (${Number(r.pnlR).toFixed(2)}R)`).join(' • ') : '—';
        }
        if (worst) {
            const rows = Array.isArray(data.worstSetups) ? data.worstSetups.slice(0, 3) : [];
            worst.textContent = rows.length ? rows.map(r => `${r.symbol} (${Number(r.pnlR).toFixed(2)}R)`).join(' • ') : '—';
        }
    }

    _renderSignalPerformance() {
        const data = this.signalPerformance || {};
        const setTxt = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };

        setTxt('perf-early', data.earlySetups ?? 0);
        setTxt('perf-entry', data.entryReady ?? 0);
        setTxt('perf-strong', data.strongEntry ?? 0);
        setTxt('perf-conv-early-entry', `${data.conversionRateEarlyToEntry ?? 0}%`);
        setTxt('perf-conv-entry-strong', `${data.conversionRateEntryToStrong ?? 0}%`);
        setTxt('perf-conv-early-entry-count', `${data.convertedToEntryReady ?? 0} converted`);
        setTxt('perf-conv-entry-strong-count', `${data.strongEntry ?? 0} strong`);

        const asof = document.getElementById('signal-performance-asof');
        if (asof) {
            const t = data.asOfTime || '--:--:--';
            asof.textContent = `As of ${t}`;
        }
    }

    _renderEarlySetups() {
        const card = document.getElementById('early-setup-card');
        const content = document.getElementById('early-setup-content');
        const countEl = document.getElementById('early-setup-count');
        if (!(card && content)) return;

        const setups = Array.isArray(this.earlySetups) ? this.earlySetups : [];
        if (!setups.length) {
            card.classList.add('hidden');
            if (countEl) countEl.textContent = 'Early Setups Today: 0';
            return;
        }

        card.classList.remove('hidden');
        if (countEl) countEl.textContent = `Early Setups Today: ${setups.length}`;
        content.innerHTML = setups.slice(0, 5).map(s => {
            const sector = (s.sector || '').toString().replace('NIFTY_', '').replace('_', ' ');
            const state = (s.sectorState || 'NEUTRAL').toString();
            const stateColor = state === 'LEADING' ? 'text-green-400' : (state === 'IMPROVING' ? 'text-blue-400' : 'text-gray-400');
            const details = s.details || {};
            const rangePct = details.rangePct ?? s.rangePct ?? '—';
            const volRatio = details.volRatio20 ?? s.volRatio ?? '—';
            const tooltip = (s.tooltip || 'Stock showing early accumulation with tight range and volume build-up. Potential breakout candidate.').toString().replace(/"/g, '&quot;');

            return `
                <div class="p-4 rounded-2xl border border-purple-500/20 bg-purple-500/5 hover:bg-purple-500/10 transition-colors cursor-pointer"
                     title="${tooltip}"
                     onclick="window.fetchDataForSymbol('${s.symbol}', { fromIntelligence: true })">
                    <div class="flex items-start justify-between">
                        <div>
                            <div class="flex items-center gap-2">
                                <span class="text-sm font-bold text-white">${s.symbol}</span>
                                <span class="text-[9px] font-black uppercase bg-purple-500/15 text-purple-300 border border-purple-500/25 px-2 py-0.5 rounded-full">EARLY SETUP</span>
                            </div>
                            <div class="mt-1 text-[10px] text-gray-400 font-mono">${sector} • <span class="${stateColor} font-bold">${state}</span></div>
                        </div>
                        <div class="text-right">
                            <div class="text-[10px] text-gray-500 uppercase font-bold">Price</div>
                            <div class="text-sm font-bold text-white mono">₹${s.price ?? '—'}</div>
                        </div>
                    </div>
                    <div class="mt-3 grid grid-cols-2 gap-2 text-[10px]">
                        <div class="bg-black/20 border border-gray-800 rounded-lg p-2">
                            <div class="text-gray-500 uppercase font-bold text-[9px]">Range</div>
                            <div class="text-white font-bold">${rangePct}%</div>
                        </div>
                        <div class="bg-black/20 border border-gray-800 rounded-lg p-2">
                            <div class="text-gray-500 uppercase font-bold text-[9px]">Vol Build</div>
                            <div class="text-white font-bold">${volRatio}x</div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    setSummaryMode(mode) {
        this.summaryMode = mode;
        this._renderSummary();

        // Update UI button states
        ['morning', 'evening', 'outlook'].forEach(m => {
            const btn = document.getElementById(`summary-mode-${m}`);
            if (btn) {
                if (m === mode) {
                    btn.classList.add('bg-indigo-600', 'text-white');
                    btn.classList.remove('text-gray-400', 'hover:text-white');
                } else {
                    btn.classList.remove('bg-indigo-600', 'text-white');
                    btn.classList.add('text-gray-400', 'hover:text-white');
                }
            }
        });

        // Update title
        const titleEl = document.getElementById('market-summary-title');
        if (titleEl) {
            const titles = { morning: 'Morning Context', evening: 'Today\'s Market Wrap', outlook: 'Tomorrow\'s Outlook' };
            titleEl.textContent = titles[mode] || 'AI Market Summary';
        }
    }

    updateMarketSummary(data) {
        if (!data) return;

        const summaryText = document.getElementById('market-summary-text');
        if (summaryText) {
            summaryText.textContent = data.summary || this._generateDailySummary(data);
        }

        // Corrected Breadth Calculation logic
        const sectorsData = this.lastSectorData || {};
        const sectors = Object.entries(sectorsData);
        const leading = sectors.filter(([name, info]) => info.metrics?.state === 'LEADING').map(([name, info]) => name.replace('NIFTY_', ''));
        const improving = sectors.filter(([name, info]) => info.metrics?.state === 'IMPROVING').map(([name, info]) => name.replace('NIFTY_', ''));
        const lagging = sectors.filter(([name, info]) => info.metrics?.state === 'LAGGING').map(([name, info]) => name.replace('NIFTY_', ''));

        const totalCount = sectors.length || 9; // Fallback to 9 if empty
        const breadth = data.breadthScore !== undefined ? (data.breadthScore > 1 ? data.breadthScore / 100 : data.breadthScore) : (leading.length / totalCount);
        const breadthPct = Math.round(breadth * 100);

        // Map Breadth to Regime based on user spec:
        // 0.4+ -> Risk On, 0.2-0.4 -> Neutral, <0.2 -> Risk Off
        let label = 'NEUTRAL';
        let color = 'text-yellow-500';
        let regimeStatus = 'NEUTRAL';

        if (breadth >= 0.4) {
            label = 'RISK ON';
            color = 'text-green-400';
            regimeStatus = 'BULLISH';
        } else if (breadth < 0.2) {
            label = 'RISK OFF (CRITICAL)';
            color = 'text-red-400';
            regimeStatus = 'BEARISH';
        }

        const scoreEl = document.getElementById('breadth-score');
        const statsEl = document.getElementById('breadth-stats');
        const labelsEl = document.getElementById('breadth-labels');
        const regimeEl = document.getElementById('breadth-regime');

        if (scoreEl) {
            scoreEl.textContent = `${breadthPct}%`;
            scoreEl.className = `text-4xl font-black ${color} tracking-tighter`;
        }
        if (statsEl) {
            statsEl.textContent = `${leading.length} / ${totalCount} SECTORS LEADING`;
        }
        if (regimeEl) {
            regimeEl.textContent = label;
            regimeEl.className = `text-[10px] font-bold px-2 py-0.5 rounded bg-gray-900 border border-gray-800 ${color}`;
        }

        // Detailed stats for Market Health
        if (labelsEl) {
            labelsEl.innerHTML = `
                <div class="flex gap-3 mt-2">
                    <div class="flex items-center gap-1.5">
                        <span class="w-1.5 h-1.5 rounded-full bg-green-400"></span>
                        <span class="text-[9px] text-gray-400 uppercase font-bold">${leading.length} Leading</span>
                    </div>
                    <div class="flex items-center gap-1.5">
                        <span class="w-1.5 h-1.5 rounded-full bg-blue-400"></span>
                        <span class="text-[9px] text-gray-400 uppercase font-bold">${improving.length} Improving</span>
                    </div>
                    <div class="flex items-center gap-1.5">
                        <span class="w-1.5 h-1.5 rounded-full bg-red-400"></span>
                        <span class="text-[9px] text-gray-400 uppercase font-bold">${lagging.length} Lagging</span>
                    </div>
                </div>
            `;
        }

        // Update Global Regime Banner if it exists
        const banner = document.getElementById('market-regime-banner');
        if (banner) {
            banner.textContent = `MARKET REGIME: ${label}`;
            banner.className = `px-3 py-1 rounded text-[10px] font-black tracking-widest uppercase ${regimeStatus === 'BULLISH' ? 'bg-green-600/20 text-green-400 border border-green-500/30' : (regimeStatus === 'BEARISH' ? 'bg-red-600/20 text-red-400 border border-red-500/30' : 'bg-yellow-600/10 text-yellow-500 border border-yellow-500/20')}`;
        }

        // Update Market Bias (NEW v1.3)
        const biasEl = document.getElementById('market-bias');
        if (biasEl) {
            const bias = breadth >= 0.4 ? 'BULLISH BIAS' : (breadth < 0.2 ? 'BEARISH BIAS' : 'NEUTRAL BIAS');
            const biasColor = breadth >= 0.4 ? 'text-green-400' : (breadth < 0.2 ? 'text-red-400' : 'text-indigo-400');
            biasEl.textContent = bias;
            biasEl.className = `text-[9px] font-black uppercase tracking-widest ${biasColor}`;
        }

        // Update Breadth Bar
        const bar = document.getElementById('breadth-bar');
        if (bar) {
            bar.style.width = `${breadthPct}%`;
            bar.className = `h-full transition-all duration-1000 ${breadth >= 0.4 ? 'bg-green-500' : (breadth >= 0.2 ? 'bg-yellow-500' : 'bg-red-500')}`;
        }

        // Original summary logic (kept for compatibility if needed elsewhere, but UI is now structured)
        if (!this.summaryText || !this.summaryBlock || !data) return;
        this.summaryData = data;

        // Auto-select mode based on IST time if not already manually toggled
        if (!this.userInteractedSummary) {
            const now = new Date();
            // Convert to IST (UTC+5:30)
            const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
            const ist = new Date(utc + (3600000 * 5.5));
            const hours = ist.getHours();
            const minutes = ist.getMinutes();
            const timeNum = hours * 100 + minutes;

            if (timeNum < 915) this.summaryMode = 'morning';
            else if (timeNum > 1545) this.summaryMode = 'evening'; // Wrap after market
            else this.summaryMode = 'evening'; // Default to intraday wrap

            // Initial UI state for buttons
            this.setSummaryMode(this.summaryMode);
        }

        this._renderSummary();
        this.summaryBlock.classList.remove('hidden');
    }

    _renderSummary() {
        if (!this.summaryData || !this.summaryText) return;

        let text = "";
        switch (this.summaryMode) {
            case 'morning': text = this._generatePreMarketSummary(this.summaryData); break;
            case 'outlook': text = this._generateTomorrowOutlook(this.summaryData); break;
            default: text = this._generateDailySummary(this.summaryData); break;
        }

        // Convert **bold** to <strong>bold</strong> to fix UI visibility issue
        const html = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        this.summaryText.innerHTML = html.split('\n\n').map(p => `<p class="mb-3 last:mb-0">${p}</p>`).join('');

        // Market Insight Line (Enhancement 5)
        if (this.summaryData && this.summaryData.leadingSectors && this.summaryData.leadingSectors.length > 0) {
            const leadingSectorsNames = this.summaryData.leadingSectors.map(s => s.name || s.sector || s).join(" and ");
            this.summaryText.innerHTML += `<p class="mt-4 pt-4 border-t border-indigo-500/20 text-indigo-300 font-medium">💡 <span class="text-white">Quick Insight:</span> Momentum is currently concentrated in ${leadingSectorsNames} sectors.</p>`;
        }

    }

    _generateDailySummary(data) {
        const lines = [];
        const isNeutralMarket = Math.abs(data.marketReturn) <= 0.2;
        const marketStrength = isNeutralMarket ? "NEUTRAL" : (data.marketReturn > 0 ? "POSITIVE" : "CAUTIOUS");

        if (marketStrength === "POSITIVE") {
            lines.push("The broader market closed higher, indicating a positive risk environment.");
        } else if (marketStrength === "CAUTIOUS") {
            lines.push("The broader market closed lower, reflecting cautious sentiment.");
        } else {
            lines.push("The broader market ended with minimal changes, suggesting a neutral bias.");
        }

        if (data.leadingSectors && data.leadingSectors.length) {
            const leadershipWord = isNeutralMarket ? "selective strength or relative leadership" : "Sector leadership";
            const sectorNames = data.leadingSectors.map(s => s.name || s.sector || s).join(", ");
            lines.push(`**${leadershipWord}** was observed in **${sectorNames}**, showing higher participation versus the broader market.`);
        }

        if (data.weakeningSectors && data.weakeningSectors.length) {
            const sectorNames = data.weakeningSectors.map(s => s.name || s.sector || s).join(", ");
            lines.push(`Momentum slowed in **${sectorNames}**, suggesting reduced follow-through.`);
        }

        if (data.improvingSectors && data.improvingSectors.length) {
            const sectorNames = data.improvingSectors.map(s => s.name || s.sector || s).join(", ");
            lines.push(`**${sectorNames}** are down in absolute terms but showing relative improvement versus the market despite broader weakness.`);
        }

        const strongStocks = (data.topStocks || []).filter(s => s.confidence >= 60);
        if (strongStocks.length) {
            const names = strongStocks.slice(0, 3).map(s => s.symbol).join(", ");
            lines.push(`Stocks showing the strongest alignment today include **${names}**, supported by sector strength and participation.`);
        }

        lines.push("Overall, market conditions favor selective opportunities aligned with strong sectors, while caution remains warranted in weakening areas.");
        return lines.join("\n\n");
    }

    _generatePreMarketSummary(data) {
        const lines = [];
        const prevMarketReturn = data.prevMarketReturn || 0;

        if (prevMarketReturn > 0) {
            lines.push("Markets ended the previous session on a positive note, indicating underlying strength.");
        } else {
            lines.push("Markets closed the previous session weak, suggesting cautious sentiment.");
        }

        if (data.globalCuesPositive || data.giftNiftyPositive) {
            lines.push("Global cues are supportive, which may aid early stability.");
        } else {
            lines.push("Global cues remain mixed, which may lead to a cautious open.");
        }

        if (data.leadingSectors && data.leadingSectors.length) {
            const sectorNames = data.leadingSectors.map(s => s.name || s.sector || s).join(", ");
            lines.push(`Strength was observed in **${sectorNames}**, which remain key sectors to track.`);
        }

        if (data.weakeningSectors && data.weakeningSectors.length) {
            const sectorNames = data.weakeningSectors.map(s => s.name || s.sector || s).join(", ");
            lines.push(`**${sectorNames}** showed signs of momentum fatigue and may remain selective.`);
        }

        lines.push("Traders may focus on stocks aligned with strong sectors while maintaining discipline in weaker areas.");
        return lines.join("\n\n");
    }

    _generateTomorrowOutlook(data) {
        const lines = [];

        if (data.leadingSectors && data.leadingSectors.length) {
            const sectorNames = data.leadingSectors.map(s => s.name || s.sector || s).join(", ");
            lines.push(`**${sectorNames}** continue to display relative strength and may remain in focus if momentum sustains.`);
        }

        if (data.improvingSectors && data.improvingSectors.length) {
            const sectorNames = data.improvingSectors.map(s => s.name || s.sector || s).join(", ");
            lines.push(`**${sectorNames}** are showing early improvement and may offer selective opportunities on confirmation.`);
        }

        if (data.weakeningSectors && data.weakeningSectors.length) {
            const sectorNames = data.weakeningSectors.map(s => s.name || s.sector || s).join(", ");
            lines.push(`Momentum in **${sectorNames}** is slowing, and follow-through may remain limited.`);
        }

        lines.push("Overall, continuation depends on sector participation and volume confirmation.");
        return lines.join("\n\n");
    }

    copySummaryToClipboard() {
        if (!this.summaryData) return;
        const data = this.summaryData;
        const activeTab = document.querySelector('.summary-tab.active');
        const mode = activeTab ? activeTab.dataset.mode : 'wrap';

        let text = "";
        const isNeutralMarket = Math.abs(data.marketReturn) <= 0.2;
        const marketStatus = isNeutralMarket ? "Neutral bias" : (data.marketReturn > 0 ? "Positive bias" : "Cautious bias");

        if (mode === 'morning') {
            text = `🧠 Pre-Market Focus\n`;
            text += `Strong sectors from previous session: ${data.leadingSectors.map(s => s.name || s.sector || s).join(", ")}\n`;
            if (data.weakeningSectors.length) text += `Weak areas: ${data.weakeningSectors.map(s => s.name || s.sector || s).join(", ")}\n`;
            text += `Track stocks aligned with strong sectors.`;
        } else {
            text = `🧠 Daily Market Snapshot\n\n`;
            text += `Market: ${marketStatus}\n`;
            text += `Leading Sectors: ${data.leadingSectors.map(s => s.name || s.sector || s).join(", ")}\n`;
            if (data.weakeningSectors.length) text += `Weakening: ${data.weakeningSectors.map(s => s.name || s.sector || s).join(", ")}\n`;

            const highConfidenceStocks = (data.topStocks || []).filter(s => s.confidence >= 60);
            if (highConfidenceStocks.length) {
                text += `\nTop Aligned Stocks:\n`;
                highConfidenceStocks.slice(0, 5).forEach(s => {
                    const tagline = s.entryTag === 'ENTRY_READY' ? 'ENTRY READY' : (s.entryTag === 'WAIT' ? 'WAIT' : s.entryTag);
                    text += `• ${s.symbol} (${tagline})\n`;
                });
            }

            text += `\nFocus on strength, stay selective ⚖️`;
        }

        navigator.clipboard.writeText(text).then(() => {
            const btn = document.getElementById('copy-summary-btn') || document.querySelector('[onclick*="copySummaryToClipboard"]');
            if (btn) {
                const originalHtml = btn.innerHTML;
                btn.innerHTML = '<span class="text-[9px] text-green-400 font-bold uppercase tracking-tighter">COPIED</span>';
                setTimeout(() => btn.innerHTML = originalHtml, 2000);
            }
        });
    }

    _buildSectorExplanation(state, rs, rm) {
        const mapping = {
            'LEADING': "Sector is rising and outperforming the broader market.",
            'WEAKENING': "Sector is still up but momentum is slowing.",
            'IMPROVING': "Sector is down in absolute terms but showing relative improvement versus the market.",
            'LAGGING': "Sector is underperforming the market with declining momentum.",
            'NEUTRAL': "Sector performance is mixed and lacks a clear relative-strength edge."
        };
        return mapping[state] || mapping['NEUTRAL'];
    }

    _statePriority(state) {
        return ({ LEADING: 5, IMPROVING: 4, WEAKENING: 3, NEUTRAL: 2, LAGGING: 1 })[state] || 0;
    }

    _stateMeta(state) {
        if (state === 'LEADING') return { textClass: 'text-green-400', borderClass: 'border-l-green-500', bgClass: 'bg-green-500/5' };
        if (state === 'IMPROVING') return { textClass: 'text-green-400', borderClass: 'border-l-green-500', bgClass: '' };
        if (state === 'LAGGING') return { textClass: 'text-red-500', borderClass: 'border-l-red-500', bgClass: 'bg-red-500/5' };
        if (state === 'WEAKENING') return { textClass: 'text-red-500', borderClass: 'border-l-red-500', bgClass: '' };
        return { textClass: 'text-gray-400', borderClass: 'border-l-gray-600', bgClass: '' };
    }

    // CONFIDENCE METER ENGINE v1.2 (LOCKED)
    _calculateConfidence(hit) {
        if (!hit) return { score: 0, factors: [] };

        // Prefer backend scoring if available (Decision Engine v2.0)
        // Corrected: Use numerical qualityScore if hit.confidence is a string (A,B,C,D)
        const backendScore = hit.technical?.qualityScore ?? hit.score;
        if (backendScore !== undefined && typeof backendScore === 'number') {
            return { 
                score: backendScore, 
                factors: hit.confidenceFactors || [] 
            };
        }

        const technical = hit.technical || {};
        const session = hit.session || {};
        const sectorState = hit.sectorState || "NEUTRAL";
        const stockActive = !!hit.stockActive;
        const volRatio = hit.volRatio || hit.volumeShocker || 0;
        const priceAboveVWAP = !!technical.aboveVWAP;
        const breakoutConfirmed = !!technical.isBreakout;
        const sessionTag = session.quality || "AVOID";
        const riskLevel = hit.riskLevel || "HIGH";

        let score = 0;
        const factors = [];

        // 1. Sector (30)
        if (sectorState === "LEADING") {
            score += 30;
            factors.push({ label: "Sector Strength (Leading)", value: "+30%", positive: true });
        } else if (sectorState === "IMPROVING") {
            score += 20;
            factors.push({ label: "Sector Improving", value: "+20%", positive: true });
        } else if (sectorState === "WEAKENING") {
            score += 10;
            factors.push({ label: "Sector Weakening", value: "+10%", positive: true });
        } else {
            factors.push({ label: "Sector Misaligned", value: "+0%", positive: false });
        }

        // 2. Stock (20)
        if (stockActive) {
            score += 20;
            factors.push({ label: "Stock Outperforming Sector", value: "+20%", positive: true });
        } else {
            factors.push({ label: "Stock Strength Weak", value: "+0%", positive: false });
        }

        // 3. Volume (15)
        if (volRatio >= 2) {
            score += 15;
            factors.push({ label: "Extremely High Volume", value: "+15%", positive: true });
        } else if (volRatio >= 1.5) {
            score += 10;
            factors.push({ label: "Healthy Volume Expansion", value: "+10%", positive: true });
        } else {
            factors.push({ label: "Sub-optimal Volume", value: "+0%", positive: false });
        }

        // 4. Price Structure (15)
        if (priceAboveVWAP) {
            score += 10;
            factors.push({ label: "Price Above VWAP", value: "+10%", positive: true });
        } else {
            factors.push({ label: "Price Below VWAP", value: "+0%", positive: false });
        }

        if (breakoutConfirmed) {
            score += 5;
            factors.push({ label: "Breakout Confirmed", value: "+5%", positive: true });
        } else {
            factors.push({ label: "No Confirmed Breakout", value: "+0%", positive: false });
        }

        // 5. Session (10)
        if (sessionTag === "BEST") {
            score += 10;
            factors.push({ label: "Optimal Session Window", value: "+10%", positive: true });
        } else if (sessionTag === "CAUTION") {
            score += 5;
            factors.push({ label: "Noisy Session Phase", value: "+5%", positive: true });
        } else {
            factors.push({ label: "Avoid Session Window", value: "+0%", positive: false });
        }

        // 6. Risk (10)
        if (riskLevel === "LOW") {
            score += 10;
            factors.push({ label: "Low Risk Setup", value: "+10%", positive: true });
        } else if (riskLevel === "MEDIUM") {
            score += 5;
            factors.push({ label: "Medium Risk Setup", value: "+5%", positive: true });
        } else {
            factors.push({ label: "High Risk Setup", value: "+0%", positive: false });
        }

        // HARD SAFETY RULES (LOCKED)
        if (sectorState === "LAGGING") {
            const prev = score;
            score = Math.min(score, 30);
            if (prev > 30) factors.push({ label: "SAFETY CAP: Sector Lagging", value: `-${prev - 30}%`, positive: false });
        }
        if (sessionTag === "AVOID") {
            const prev = score;
            score = Math.min(score, 40);
            if (prev > 40) factors.push({ label: "SAFETY CAP: Avoid Session", value: `-${prev - 40}%`, positive: false });
        }

        return { score: Math.max(0, Math.min(score, 100)), factors };
    }

    _getConfidenceLabel(score, asGrade = false) {
        if (asGrade) {
            if (score >= 85) return "A";
            if (score >= 70) return "B";
            if (score >= 55) return "C";
            return "D";
        }
        if (score >= 80) return "HIGH";
        if (score >= 60) return "MEDIUM";
        if (score >= 40) return "LOW";
        return "VERY LOW";
    }

    _renderConfidenceDots(score) {
        if (score >= 80) return "🟢🟢🟢🟢";
        if (score >= 60) return "🟢🟢🟢⚪";
        if (score >= 40) return "🟢🟢⚪⚪";
        return "🟢⚪⚪⚪";
    }

    // CONFIDENCE TREND ENGINE v1.3 (LOCKED)
    _calculateTrend(symbol, currentScore, sectorState) {
        const prevScore = this.prevConfidence[symbol];

        // Hard Safety Rule: No UP trend if sector is weakening/lagging
        if (sectorState === "WEAKENING" || sectorState === "LAGGING") {
            return { icon: "↓", label: "Weakening (Sector Pull)", color: "text-red-400" };
        }

        if (prevScore === undefined) return { icon: "→", label: "Stable", color: "text-gray-500" };

        const diff = currentScore - prevScore;
        if (diff >= 5) return { icon: "↑", label: "Improving", color: "text-green-400" };
        if (diff <= -5) return { icon: "↓", label: "Weakening", color: "text-red-400" };

        return { icon: "→", label: "Stable", color: "text-gray-500" };
    }

    // AUTO-EXPLANATION ENGINE v1.1 (LOCKED)
    _generateExplanation(hit, options = { short: false }) {
        if (!hit) return "";
        const technical = hit.technical || {};
        const session = hit.session || {};

        const data = {
            sectorState: hit.sectorState || "NEUTRAL",
            stockState: hit.stockActive ? "ACTIVE" : "WEAK",
            entryTag: hit.entryTag || "AVOID",
            priceAboveVWAP: !!technical.aboveVWAP,
            breakoutConfirmed: !!technical.isBreakout,
            volumeRatio: hit.volRatio || hit.volumeShocker || 0,
            sessionTag: session.quality || "AVOID",
            riskLevel: hit.riskLevel || "HIGH"
        };

        const lines = [];

        // Signal headline
        if (data.entryTag === "ENTRY_READY") {
            lines.push("Conditions are aligned for an actionable setup.");
        } else if (data.entryTag === "WAIT") {
            lines.push("The setup is forming, but confirmation is still pending.");
        } else {
            lines.push("Conditions are not aligned for a reliable setup.");
        }

        if (options.short) {
            // Tooltip short version: First sentence + sector logic
            const sectorLine = this._getSectorExplanationPart(data.sectorState);
            return `${lines[0]} ${sectorLine}`;
        }

        // Sector logic
        lines.push(this._getSectorExplanationPart(data.sectorState));

        // Stock logic
        if (data.stockState === "ACTIVE") {
            lines.push("The stock is outperforming its sector with elevated trading activity.");
        } else {
            lines.push("The stock is not showing strong relative participation.");
        }

        // Price & volume
        if (data.priceAboveVWAP) {
            lines.push("Price is trading above VWAP, indicating buyer control.");
        } else {
            lines.push("Price is below VWAP, indicating weaker demand.");
        }

        if (data.breakoutConfirmed) {
            lines.push("A breakout has been confirmed with participation.");
        } else {
            lines.push("No confirmed breakout has occurred yet.");
        }

        if (data.volumeRatio >= 2) {
            lines.push("Trading volume is significantly above normal levels.");
        } else if (data.volumeRatio >= 1.5) {
            lines.push("Trading volume is moderately above normal levels.");
        } else {
            lines.push("Trading volume is near or below normal levels.");
        }

        // Session timing
        if (data.sessionTag === "BEST") {
            lines.push("The signal appears during an optimal trading session window.");
        } else if (data.sessionTag === "CAUTION") {
            lines.push("The signal appears during a higher-noise session period.");
        } else {
            lines.push("Signals during this session are typically unreliable.");
        }

        // Risk
        lines.push(`Overall risk level is classified as ${data.riskLevel.toLowerCase()}.`);

        return lines.join(" ");
    }

    _getSectorExplanationPart(state) {
        const mapping = {
            'LEADING': "Sector is rising and outperforming the broader market.",
            'WEAKENING': "Sector is still up but momentum is slowing.",
            'IMPROVING': "Sector is down in absolute terms but showing relative improvement versus the market.",
            'LAGGING': "Sector is underperforming the market with declining momentum.",
            'NEUTRAL': "Sector performance is mixed and lacks a clear relative-strength edge."
        };
        return mapping[state] || mapping['NEUTRAL'];
    }

    _renderHitsTable() {
        if (!this.hitsBody) return;

        // Current threshold from UI (Handover v1.3)
        const filterEl = document.getElementById('confidence-filter');
        const threshold = filterEl ? parseInt(filterEl.value) : 60;
        const highProbabilityOnlyEl = document.getElementById('high-probability-only');
        const highProbabilityOnly = !!(highProbabilityOnlyEl && highProbabilityOnlyEl.checked);

        const working = this.allHits.filter(hit => {
            const conf = this._calculateConfidence(hit);
            const session = hit.session || {};

            // EDGE-CASE GUARDS (Handover v1.3)
            const avoidSession = session.quality === "AVOID";
            const laggingSector = hit.sectorState === "LAGGING";
            const belowThreshold = conf.score < threshold;

            if (avoidSession || laggingSector || belowThreshold) {
                if (window.location.search.includes('debug=true')) {
                    console.log(`[Filter] ${hit.symbol} hidden: session=${session.quality}, sector=${hit.sectorState}, score=${conf.score}% (threshold=${threshold})`);
                }
                return false;
            }

            const filterCategory = hit.filterMeta?.filterCategory || hit.filterCategory || this._deriveFilterMeta(hit).filterCategory;
            if (highProbabilityOnly && filterCategory !== 'HIGH PROBABILITY') return false;

            // Existing Sector Focus filter
            if (this.activeSectorKey && hit.sectorKey !== this.activeSectorKey) return false;

            // NEW: Quick Filters Logic (v1.6)
            if (window.activeQuickFilters) {
                if (window.activeQuickFilters.leaders && hit.sectorState !== 'LEADING' && hit.leader !== true) return false;
                if (window.activeQuickFilters.smart && hit.technical?.institutionalActivity !== 'STRONG' && hit.technical?.institutionalActivity !== 'MODERATE') return false;
                if (window.activeQuickFilters.momentum && hit.technical?.momentumStrength !== 'STRONG') return false;
                if (window.activeQuickFilters.early && hit.technical?.earlyTag !== 'EARLY_SETUP') return false;
            }

            return true;
        }).sort((a, b) => {
            const scoreA = a.technical?.qualityScore || this._calculateConfidence(a).score;
            const scoreB = b.technical?.qualityScore || this._calculateConfidence(b).score;
            return scoreB - scoreA;
        });

        // Top Momentum Setup Logic (v1.0)
        // Top Momentum Setup Logic (v1.0)
        const topSetupCard = document.getElementById('top-setup-card');
        const topSetupContent = document.getElementById('top-setup-content');
        if (topSetupCard && working.length > 0) {
            const top = working[0];
            topSetupCard.classList.remove('hidden');
            const score = top.technical?.qualityScore || this._calculateConfidence(top).score;
            const grade = top.confidence || top.grade || 'C';
            const sectorName = top.sector ? top.sector.replace('NIFTY_', '').replace('_', ' ') : 'Unknown';
            const mStrength = top.technical?.momentumStrength || 'MODERATE';
            const smTier = top.technical?.institutionalActivity || 'NONE';

            topSetupContent.innerHTML = `
                    <div class="flex flex-col">
                        <span class="text-[9px] text-gray-500 uppercase font-bold mb-1">Symbol</span>
                        <span class="text-sm font-bold text-white">${top.symbol}</span>
                    </div>
                    <div class="flex flex-col">
                        <span class="text-[9px] text-gray-500 uppercase font-bold mb-1">Sector</span>
                        <span class="text-sm font-bold text-indigo-400">${sectorName}</span>
                    </div>
                    <div class="flex flex-col">
                        <span class="text-[9px] text-gray-500 uppercase font-bold mb-1">Intelligence</span>
                        <div class="flex flex-col gap-1">
                            <span class="text-[10px] font-bold text-white">${grade} (${Math.round(score)}%)</span>
                            <div class="flex items-center gap-1">
                                <span class="text-[8px] font-bold text-indigo-400 uppercase">Mom: ${mStrength}</span>
                                <span class="text-[8px] text-gray-500">•</span>
                                <span class="text-[8px] font-bold ${smTier === 'STRONG' ? 'text-green-400' : (smTier === 'MODERATE' ? 'text-yellow-500' : (smTier === 'WEAK' ? 'text-gray-400' : 'text-gray-600'))} uppercase">SM: ${smTier}</span>
                            </div>
                        </div>
                    </div>
                    <div class="flex flex-col">
                        <span class="text-[9px] text-gray-500 uppercase font-bold mb-1">Actionable Trigger</span>
                        <span class="text-[10px] font-bold text-green-400">Break above recent high</span>
                    </div>
                `;
        } else if (topSetupCard) {
            topSetupCard.classList.add('hidden');
        }

        if (window.location.search.includes('debug=true')) {
            console.log(`[Dashboard] Showing ${working.length} of ${this.allHits.length} signals. Session: ${this.allHits[0]?.session?.phase || 'N/A'}`);
        }

        if (!working.length) {
            const hasHiddenHits = this.allHits.length > 0;
            const msg = hasHiddenHits
                ? `No setups match the ${threshold}% confidence threshold. ${this.allHits.length} potential signals are being filtered. Try lowering the threshold.`
                : 'No momentum hits found in the current market scan.';
            this.hitsBody.innerHTML = `<tr><td colspan="12" class="px-4 py-10 text-center text-gray-500 italic">${msg}</td></tr>`;
            return;
        }

        this.hitsBody.innerHTML = working.map(hit => {
            const vol = hit.volumeShocker ?? hit.volRatio ?? 0;
            const shockerBadge = vol >= 2.5 ? '🔥' : vol >= 2.0 ? '⚡' : '';
            const tradeReady = !!hit.tradeReady;
            const tradeLabel = tradeReady
                ? '<span class="ml-2 px-2 py-0.5 rounded-full text-[9px] font-bold tracking-widest bg-green-600/10 text-green-400 border border-green-500/40">TRADE&nbsp;READY</span>'
                : '';

            // Status Tag Logic
            let statusColor = 'bg-gray-800 text-gray-400';
            const currentTag = hit.entryStatus || hit.entryTag;

            // EARLY SETUP hierarchy: only surface when the base tag is not already actionable
            const earlyTag = hit.technical?.earlyTag;
            const isEarlySetup = (earlyTag === 'EARLY_SETUP') && (currentTag === 'WATCHLIST' || currentTag === 'WAIT' || currentTag === 'AVOID' || !currentTag);
            const earlyTooltip = hit.technical?.earlyTooltip || 'Stock showing early accumulation with tight range and volume build-up. Potential breakout candidate.';

            if (currentTag === 'STRONG_ENTRY') statusColor = 'bg-green-600/30 text-green-400 border border-green-500/50 drop-shadow-[0_0_8px_rgba(74,222,128,0.5)]';
            else if (currentTag === 'ENTRY_READY') statusColor = 'bg-green-600/20 text-green-400 border border-green-500/30';
            else if (currentTag === 'WATCHLIST' || currentTag === 'WAIT') statusColor = 'bg-yellow-600/20 text-yellow-500 border border-yellow-500/30';
            if (hit.exitTag === 'EXIT') statusColor = 'bg-red-600/20 text-red-400 border border-red-500/30';
            if (isEarlySetup) statusColor = 'bg-purple-600/20 text-purple-300 border border-purple-500/40 shadow-[0_0_10px_rgba(168,85,247,0.3)] animate-pulse';

            // Setup Type Styling
            const setupType = hit.technical?.setupType || 'MOMENTUM';
            const setupIcons = {
                'BREAKOUT': '🚀',
                'RSI_PULLBACK': '📉',
                'VOLUME_SURGE': '📈',
                'MOMENTUM_HIT': '🔥'
            };
            const setupIcon = setupIcons[setupType] || '🔥';

            // Grade Content Mapping
            const grade = hit.confidence || hit.grade || 'C';
            const score = hit.technical?.qualityScore || this._calculateConfidence(hit).score;

            // Grade Color Logic
            let gradeColor = 'text-gray-400';
            if (grade === 'A+' || grade === 'A') gradeColor = 'text-green-400';
            else if (grade === 'B') gradeColor = 'text-green-200';
            else if (grade === 'C') gradeColor = 'text-yellow-500';
            else if (grade === 'D') gradeColor = 'text-red-400';

            // Risk Tag Logic
            let riskColor = 'text-gray-400';
            if (hit.riskLevel === 'LOW') riskColor = 'text-green-400';
            if (hit.riskLevel === 'MEDIUM') riskColor = 'text-yellow-500';
            if (hit.riskLevel === 'HIGH') riskColor = 'text-red-400';

            // Position Sizing & Session Metrics
            const ru = hit.riskUnits ?? 0;
            const session = hit.session || { phase: '—', quality: 'AVOID' };

            let sessionColor = 'text-gray-500';
            if (session.phase === 'EARLY') sessionColor = 'text-green-400 bg-green-400/10 px-1.5 py-0.5 rounded-md font-bold';
            else if (session.phase === 'MID') sessionColor = 'text-yellow-500 bg-yellow-500/10 px-1.5 py-0.5 rounded-md font-bold';
            else if (session.phase === 'LATE') sessionColor = 'text-red-400 bg-red-400/10 px-1.5 py-0.5 rounded-md font-bold';
            else if (session.quality === 'BEST') sessionColor = 'text-green-400 font-bold';
            else if (session.quality === 'CAUTION') sessionColor = 'text-yellow-500';

            // Streamlined Tooltips v1.1 (AUTO-EXPLANATION)
            const tooltip = this._generateExplanation(hit, { short: true });

            // Institutional Clarity Colors (NEW)
            const instTier = hit.technical?.institutionalActivity || 'NONE';
            let instColor = 'text-gray-600';
            if (instTier === 'STRONG') instColor = 'text-green-400 drop-shadow-[0_0_5px_rgba(74,222,128,0.4)]';
            else if (instTier === 'MODERATE') instColor = 'text-yellow-500';
            else if (instTier === 'WEAK') instColor = 'text-gray-400';

            // Momentum Strength Tooltips (NEW)
            const momStrength = hit.technical?.momentumStrength || 'MODERATE';
            const momTooltip = momStrength === 'STRONG' ? 'High velocity momentum with volume confirmation' : (momStrength === 'MODERATE' ? 'Steady trend with average volume' : 'Low velocity or stalling momentum');

            const filterMeta = hit.filterMeta || this._deriveFilterMeta(hit);
            const probabilityCategory = filterMeta.filterCategory || 'LOW';
            const probabilityClass = probabilityCategory === 'HIGH PROBABILITY'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                : (probabilityCategory === 'MEDIUM'
                    ? 'bg-amber-500/15 text-amber-300 border border-amber-500/25'
                    : 'bg-gray-800/60 text-gray-400 border border-gray-700/60');

            // Sector Highlight & STRONG ENTRY Highlight (v1.6 Enhancements)
            const isLeadingSector = (hit.sectorState === 'LEADING') || (hit.leader === true);
            const isStrongEntry = (currentTag === 'STRONG_ENTRY') || (hit.tradeReady) || (score >= 80);

            let rowHighlightClasses = [];
            if (isLeadingSector) rowHighlightClasses.push('border-l-[3px] border-green-500/70 bg-green-500/[0.03]');
            if (isStrongEntry) rowHighlightClasses.push('ring-1 ring-green-500/60 shadow-[0_0_10px_rgba(0,192,118,0.15)] z-10 relative');

            const rowHighlight = rowHighlightClasses.join(' ');

            return `
                <tr class="hover:bg-gray-800/60 transition-colors group cursor-pointer border-b border-gray-800/50 ${rowHighlight}"
                    data-sector-key="${hit.sectorKey || ''}"
                    title="${tooltip}"
                    onclick="window.fetchDataForSymbol('${hit.symbol}', { fromIntelligence: true })">
                    <td class="px-3 py-1.5 text-xs">
                        <div class="flex flex-col gap-0.5">
                            <span class="font-bold text-white group-hover:text-blue-400 transition-colors flex items-center gap-1.5">
                                ${hit.symbol}
                                ${isLeadingSector ? '<span class="text-[7px] bg-green-500/20 text-green-400 px-1 rounded border border-green-500/20 uppercase tracking-tighter">LEADER</span>' : ''}
                                <span class="text-[7px] px-1 rounded uppercase tracking-tighter ${probabilityClass}">${probabilityCategory}</span>
                            </span>
                            <span class="text-[8px] font-black text-gray-500 uppercase tracking-widest flex items-center gap-1">
                                ${setupIcon} ${setupType.replace('_', ' ')}
                            </span>
                            ${hit.technical?.isFalseBreakout ? '<span class="text-[7px] font-bold text-red-400 uppercase tracking-tighter flex items-center gap-0.5">⚠️ FALSE</span>' : ''}
                        </div>
                        ${tradeLabel}
                    </td>
                    <td class="px-3 py-1.5 text-right"><span class="text-[9px] bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded font-bold uppercase">${hit.sector ? hit.sector.replace('NIFTY_', '') : ''}</span></td>
                    <td class="px-3 py-1.5 font-mono text-gray-300 text-right">₹${hit.price}</td>
                    <td class="px-3 py-1.5 font-bold ${hit.change >= 0 ? 'text-up' : 'text-down'} text-xs text-right">${(hit.change >= 0 ? '+' : '') + (hit.change ?? 0).toFixed(2)}%</td>
                    <td class="px-3 py-1.5 text-right">
                        <div class="flex items-center justify-end gap-1 font-mono text-xs">
                            <span class="text-gray-300">${vol.toFixed(2)}x</span>
                            ${shockerBadge ? `<span class="text-xs">${shockerBadge}</span>` : ''}
                        </div>
                    </td>
                    <td class="px-3 py-1.5 text-center">
                         ${instTier !== 'NONE'
                    ? `<span class="text-[9px] font-black ${instColor} flex items-center justify-center gap-0.5" title="Institutional Activity: ${instTier}">⚡ ${instTier}</span>`
                    : '<span class="text-[10px] font-bold text-gray-600">NONE</span>'}
                    </td>
                    <td class="px-3 py-1.5 text-center">
                        <div class="flex items-center justify-center gap-1">${this._renderHits(hit.hits3d, hit.hits2d, hit.hits1d)}</div>
                    </td>
                    <td class="px-3 py-1.5 text-center">
                         <span class="px-1.5 py-0.5 rounded text-[8px] font-black uppercase transition-all ${hit.technical?.momentumStrength === 'STRONG' ? 'bg-green-500/20 text-green-400 border border-green-500/30' : (hit.technical?.momentumStrength === 'MODERATE' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' : 'bg-gray-800/50 text-gray-500 border border-gray-700/50')}" 
                               title="${momTooltip}">
                             ${momStrength}
                         </span>
                    </td>
                    <td class="px-3 py-1.5">
                         <div class="flex flex-col gap-0.5 items-start">
                             <span class="px-1.5 py-0.5 rounded text-[8px] font-bold uppercase tracking-wider ${statusColor}" title="${isEarlySetup ? earlyTooltip : ''}">
                                 ${hit.exitTag === 'EXIT'
                    ? 'EXIT'
                    : (isEarlySetup
                        ? '🟣 EARLY'
                        : (hit.tradeDecisionTag || hit.entryStatus || hit.entryTag || 'AVOID').replace('_', ' '))}
                             </span>
                             <div class="text-[9px] text-gray-400 leading-tight italic max-w-[120px] line-clamp-2 mt-1" title="${hit.aiCommentary || ''}">
                                 ${hit.aiCommentary || 'Analyzing setup...'}
                             </div>
                             <button class="text-[7px] text-indigo-400 font-bold uppercase hover:underline cursor-pointer mt-1" 
                                     title="Click for full signal explanation"
                                     onclick="event.stopPropagation(); window.showExplanation('${hit.symbol}')">
                                 Details
                             </button>
                         </div>
                    </td>
                    <td class="px-3 py-1.5">
                        ${(() => {
                            const tp = hit.executionPlan || {};
                            const rr = Number(tp.riskRewardToT1 || 0);
                            const rrClass = rr >= 1.5 ? 'text-green-400' : 'text-red-400';
                            const q = tp.tradeQuality || 'LOW QUALITY TRADE';
                            const qClass = q === 'HIGH QUALITY TRADE' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-rose-500/15 text-rose-300 border border-rose-500/25';
                            const conf = tp.executionConfidence || 'LOW';
                            const confClass = conf === 'HIGH CONFIDENCE' ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30' : (conf === 'MEDIUM' ? 'bg-blue-500/15 text-blue-300 border border-blue-500/25' : 'bg-gray-800 text-gray-400 border border-gray-700');
                            return `
                                <div class="text-[8px] leading-3 font-mono">
                                    <div class="flex items-center gap-1 mb-1">
                                        <span class="px-1 rounded text-[7px] font-bold uppercase ${qClass}">${q.replace(' TRADE', '')}</span>
                                        <span class="px-1 rounded text-[7px] font-bold uppercase ${confClass}">${conf.replace(' CONFIDENCE', '')}</span>
                                    </div>
                                    <div class="flex gap-2">
                                        <div><span class="text-gray-500">E:</span> <span class="text-white">₹${tp.entry ?? '—'}</span></div>
                                        <div><span class="text-gray-500">SL:</span> <span class="text-red-300">₹${tp.stopLoss ?? '—'}</span></div>
                                        <div><span class="text-gray-500">T1:</span> <span class="text-green-300">₹${tp.target1 ?? '—'}</span></div>
                                    </div>
                                    <div class="flex gap-2">
                                        <div><span class="text-gray-500">R/R:</span> <span class="${rrClass}">${rr ? rr.toFixed(2) : '—'}</span></div>
                                    </div>
                                </div>
                            `;
                        })()}
                    </td>
                    <td class="px-3 py-1.5 text-center text-white">
                         <div class="flex flex-col items-center gap-0" title="Confidence Score: ${Math.round(score)}%">
                             <span class="text-sm font-black tracking-tight ${gradeColor}">${grade}</span>
                             <span class="text-[8px] font-bold text-gray-500">${Math.round(score)}%</span>
                         </div>
                    </td>
                </tr>
            `;
        }).join('');
    }

    _renderHits(hits3d, hits2d, hits1d) {
        return this.renderBadge(hits3d, '3D') + this.renderBadge(hits2d, '2D') + this.renderBadge(hits1d, '1D');
    }

    renderBadge(active, label) {
        let activeClass = 'bg-gray-900 border-gray-800 text-gray-700';
        if (active) {
            if (label === '3D') {
                activeClass = 'bg-indigo-500 border-indigo-400 text-white shadow-[0_0_10px_rgba(99,102,241,0.8)] scale-110 ring-1 ring-indigo-400 z-10';
            } else if (label === '2D') {
                activeClass = 'bg-indigo-500/40 border-indigo-500/50 text-indigo-200 z-0';
            } else {
                activeClass = 'bg-gray-800 border-gray-700 text-gray-400 z-0';
            }
        }
        const inactiveClass = 'bg-gray-900 border-gray-800 text-gray-700';
        return `
            <div class="w-6 h-6 rounded-md flex items-center justify-center font-bold text-[8px] border transition-all relative ${active ? activeClass : inactiveClass}">${label}</div>
        `;
    }

    _deriveFilterMeta(hit) {
        const vol = Number(hit?.volRatio ?? 0);
        const volumeStrength = vol >= 2 ? 'STRONG' : (vol >= 1.2 ? 'MODERATE' : 'WEAK');
        const momentumCount = [hit?.hits1d, hit?.hits2d, hit?.hits3d].filter(Boolean).length;
        let score = 50;

        if (volumeStrength === 'STRONG') score += 16;
        else if (volumeStrength === 'MODERATE') score += 8;
        else score -= 8;

        if (momentumCount >= 3) score += 16;
        else if (momentumCount === 2) score += 8;
        else if (momentumCount === 1) score -= 8;

        const entryTag = (hit?.entryTag || '').toUpperCase();
        if (entryTag === 'STRONG_ENTRY') score += 16;
        else if (entryTag === 'ENTRY_READY') score += 8;

        const category = score >= 70 ? 'HIGH PROBABILITY' : (score >= 55 ? 'MEDIUM' : 'LOW');
        return { filterCategory: category, filterScore: Math.max(0, Math.min(100, Math.round(score))) };
    }

    showSignalExplanation(hit) {
        this.currentExplHit = hit;
        const overlay = document.getElementById('signal-modal-overlay');
        if (!overlay || !hit) {
            console.warn('[Explain] Modal overlay not found or no hit data', { overlay, hit });
            return;
        }
        // Show modal FIRST so a render error doesn't block opening
        overlay.classList.remove('hidden');
        try {
            this._updateExplanationView();
        } catch (e) {
            console.error('[Explain] Error rendering explanation:', e);
        }
    }

    _updateExplanationView() {
        const hit = this.currentExplHit;
        if (!hit) return;

        const technical = hit.technical || {};
        const session = hit.session || {};
        const isPro = this.isProView;

        // Header
        document.getElementById('expl-title').textContent = `${hit.symbol} Signal Analysis`;

        // 1. Sector Context
        const sectorStateText = isPro ? hit.sectorState : (hit.sectorState === 'LEADING' ? 'Strong (Growing)' : (hit.sectorState === 'IMPROVING' ? 'Improving' : 'Wait'));
        document.getElementById('expl-sector-state').textContent = sectorStateText;

        // 2. Stock Strength
        const volRatio = (hit.volRatio || 0).toFixed(2);
        const stockStateText = isPro ? 'ACTIVE' : 'Strong vs Sector';
        document.getElementById('expl-stock-state').textContent = stockStateText;
        document.getElementById('expl-vol-ratio').textContent = isPro ? `${volRatio}x` : 'Elevated';

        // 3. Price Structure
        document.getElementById('expl-vwap').textContent = technical.aboveVWAP ? 'Above VWAP' : 'Below VWAP';
        document.getElementById('expl-breakout').textContent = isPro
            ? (technical.isBreakout ? 'Confirmed' : 'Pending')
            : (technical.isBreakout ? 'Pattern Confirmed' : 'Waiting for Pattern');

        // 4. Session Timing
        const sessionQualityRaw = (session.quality || 'UNKNOWN');
        document.getElementById('expl-session-quality').textContent = isPro ? sessionQualityRaw : (sessionQualityRaw === 'BEST' ? 'Best Reliability' : 'Caution');

        // 5. Quality Score Breakdown
        const breakdownList = document.getElementById('expl-breakdown');
        if (breakdownList) {
            try {
                const conf = this._calculateConfidence(hit) || {};
                const factors = Array.isArray(conf.factors) ? conf.factors : [];
                const sectorName = hit.sector ? hit.sector.replace('NIFTY_', '').replace('_', ' ') : 'Unknown';
                const totalScore = Math.round(conf.score || 0);

                let factorsHtml = factors.length > 0
                    ? factors.map(f => `
                        <div class="flex justify-between items-center text-[10px] py-0.5">
                            <span class="text-gray-400">${f.label || 'Metric'}</span>
                            <span class="font-bold font-mono ${f.positive ? 'text-green-400' : 'text-gray-500'}">${f.value || '-'}</span>
                        </div>
                    `).join('')
                    : '<p class="text-[10px] text-gray-500 italic">Scoring factors not available.</p>';

                // Intelligence Layer Highlights (NEW)
                const intelHighlights = `
                    <div class="flex flex-wrap gap-2 mt-2 pt-2 border-t border-gray-800">
                        <div class="px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/20">
                            <span class="text-[8px] font-bold text-blue-400 uppercase">Institutional: ⚡ ${hit.technical?.institutionalActivity || 'NONE'}</span>
                        </div>
                        <div class="px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20">
                            <span class="text-[8px] font-bold text-indigo-400 uppercase">Strength: ${hit.technical?.momentumStrength || 'MODERATE'}</span>
                        </div>
                        <div class="px-2 py-0.5 rounded bg-purple-500/10 border border-purple-500/20">
                            <span class="text-[8px] font-bold text-purple-400 uppercase">Sector: ${hit.sectorState || 'N/A'}</span>
                        </div>
                        ${hit.technical?.isFalseBreakout ? `
                        <div class="px-2 py-0.5 rounded bg-red-500/10 border border-red-500/20">
                            <span class="text-[8px] font-bold text-red-400 uppercase">⚠️ False Breakout Warning</span>
                        </div>` : ''}
                    </div>
                `;

                breakdownList.innerHTML = `
                    <div class="mb-3 flex justify-between items-center text-[10px] border-b border-gray-800 pb-2">
                        <span class="text-indigo-400 font-bold">${hit.symbol}</span>
                        <span class="text-gray-500 uppercase tracking-tighter">${sectorName} (${hit.sectorState || 'N/A'})</span>
                    </div>
                    ${factorsHtml}
                    ${intelHighlights}
                    
                    <div class="pt-2 mt-2 border-t border-gray-800 space-y-2">
                        <div class="flex justify-between items-center text-xs font-bold mb-2">
                            <span class="text-white">TOTAL CONFIDENCE</span>
                            <span class="text-indigo-400">${totalScore}%</span>
                        </div>
                        
                        <div class="space-y-1">
                            <span class="text-[9px] text-indigo-400 uppercase font-bold tracking-widest">Signal Interpretation:</span>
                            <p class="text-[10px] text-gray-400 leading-relaxed italic">${typeof this._generateExplanation === 'function' ? this._generateExplanation(hit) : 'No explanation details available.'}</p>
                        </div>

                        ${hit.technical?.isFalseBreakout ? `
                        <div class="p-2 bg-red-900/20 border border-red-500/30 rounded-lg">
                            <p class="text-[9px] text-red-400 font-bold uppercase mb-1">⚠️ False Breakout Warning</p>
                            <p class="text-[8px] text-gray-400 leading-tight">Price reached a new high but volume confirmation is weak. Retail trap probability is higher.</p>
                        </div>
                        ` : ''}

                        <div class="space-y-1">
                            <span class="text-[9px] text-green-400 uppercase font-bold tracking-widest">Suggested Action:</span>
                            <p class="text-[10px] text-gray-400">
                                ${hit.technical?.isFalseBreakout
                        ? 'Avoid aggressive entries. Wait for a solid close above high with >1.5x volume.'
                        : (totalScore >= 70 ? 'High probability setup. Standard position sizing recommended.' : 'Wait for better sector alignment or volume expansion.')}
                            </p>
                        </div>
                    </div>
                `;
            } catch (err) {
                console.error('[Dashboard] Failed to render breakdown:', err);
                breakdownList.innerHTML = '<p class="text-[10px] text-red-400 italic">Error loading signal details.</p>';
            }
        }

        // 6. Risk
        document.getElementById('expl-ru').textContent = `${hit.riskUnits || 0} RU`;

        // Icon
        const statusIcon = document.getElementById('expl-status-icon');
        if (hit.exitTag === 'EXIT') statusIcon.textContent = '🔴';
        else if (hit.entryTag === 'ENTRY_READY') statusIcon.textContent = '🟢';
        else if (hit.entryTag === 'WAIT') statusIcon.textContent = '🟡';
        else statusIcon.textContent = '⚪';

        // Confidence Metrics
        const confidence = this._calculateConfidence(hit);
        const scoreVal = confidence.score;
        const grade = hit.grade || this._getConfidenceLabel(scoreVal, true);

        let gradeColor = 'text-gray-400';
        if (grade === 'A+' || grade === 'A') gradeColor = 'text-green-400 drop-shadow-[0_0_5px_rgba(74,222,128,0.8)]';
        else if (grade === 'B') gradeColor = 'text-green-200';
        else if (grade === 'C') gradeColor = 'text-yellow-500';
        else if (grade === 'D') gradeColor = 'text-red-400';

        document.getElementById('expl-confidence-dots').textContent = grade;
        document.getElementById('expl-confidence-dots').className = `text-2xl font-black ${gradeColor}`;

        document.getElementById('expl-confidence-score').textContent = `${Math.round(scoreVal)}%`;
        const labelEl = document.getElementById('expl-confidence-label');
        labelEl.textContent = this._getConfidenceLabel(scoreVal);

        // Dynamic Label Styling
        labelEl.className = 'text-[9px] font-bold px-1.5 py-0.5 rounded uppercase ' +
            (scoreVal >= 80 ? 'bg-green-600/20 text-green-400' :
                scoreVal >= 60 ? 'bg-yellow-600/20 text-yellow-500' :
                    'bg-red-600/20 text-red-400');

        const confList = document.getElementById('expl-confidence-list');
        confList.innerHTML = confidence.factors.map(f => `
            <li class="flex items-center justify-between">
                <span class="text-gray-400">${f.label}</span>
                <span class="${f.positive ? 'text-green-400' : 'text-red-400'} font-bold">${f.value}</span>
            </li>
        `).join('');

        // Summary Line
        const fullExplanation = this._generateExplanation(hit, { short: false });

        // Use auto-explanation as summary if in Beginner Mode or just always for maximum transparency
        const summary = isPro
            ? `“${hit.symbol} is showing optimal alignment with ${hit.sector} strength (RS+), confirmed by VWAP and Volume Expansion during ${session.phase}.”`
            : `“${fullExplanation}”`;

        document.getElementById('expl-summary').textContent = summary;

        // Header Text
        document.getElementById('expl-header-text').textContent = isPro ? 'Technical Alignment Breakdown' : 'Why this signal appeared';

        // Debug Mode raw values (MUST-HAVE for trust)
        const isDebug = new URLSearchParams(window.location.search).get('debug') === 'true';
        let debugContainer = document.getElementById('expl-debug-values');
        if (isDebug) {
            if (!debugContainer) {
                debugContainer = document.createElement('div');
                debugContainer.id = 'expl-debug-values';
                debugContainer.className = 'mt-4 p-3 bg-black/40 rounded-xl border border-gray-800 font-mono text-[9px] text-gray-500 grid grid-cols-2 gap-y-1';
                document.getElementById('expl-summary').parentNode.appendChild(debugContainer);
            }
            debugContainer.classList.remove('hidden');
            debugContainer.innerHTML = `
                <span>SEC STATE:</span> <span class="text-gray-300">${hit.sectorState}</span>
                <span>VOL RATIO:</span> <span class="text-gray-300">${(hit.volRatio || 0).toFixed(2)}x</span>
                <span>VWAP BIAS:</span> <span class="text-gray-300">${technical.aboveVWAP ? 'POSITIVE' : 'NEGATIVE'}</span>
                <span>BREAKOUT:</span> <span class="text-gray-300">${technical.isBreakout ? 'CONFIRMED' : 'NONE'}</span>
                <span>SESSION:</span> <span class="text-gray-300">${session.phase} (${session.quality})</span>
                <span>RISK UNITS:</span> <span class="text-gray-300">${hit.riskUnits} RU</span>
            `;
        } else if (debugContainer) {
            debugContainer.classList.add('hidden');
        }
    }
}

window.showExplanation = (symbol) => {
    if (!window.intelligenceApp) return;
    const hit = window.intelligenceApp.allHits.find(h => h.symbol === symbol);
    if (hit) window.intelligenceApp.showSignalExplanation(hit);
};

window.focusSector = (sectorKey) => {
    if (!window.intelligenceApp) return;
    if (window.intelligenceApp.activeSectorKey === sectorKey) {
        window.intelligenceApp.activeSectorKey = null;
    } else {
        window.intelligenceApp.activeSectorKey = sectorKey;
    }
    window.intelligenceApp._renderHitsTable();

    const cards = document.querySelectorAll('#sector-intelligence-list [data-sector-key]');
    cards.forEach(card => {
        if (card.getAttribute('data-sector-key') === window.intelligenceApp.activeSectorKey) {
            card.classList.add('ring-2', 'ring-green-400/70', 'ring-offset-2', 'ring-offset-gray-900');
        } else {
            card.classList.remove('ring-2', 'ring-green-400/70', 'ring-offset-2', 'ring-offset-gray-900');
        }
    });
};

window.fetchDataForSymbol = (symbol, options = {}) => {
    const input = document.getElementById('symbol-input');
    const intelTog = document.getElementById('intelligence-toggle');
    const rotTog = document.getElementById('rotation-toggle');
    const fromIntelligence = !!options.fromIntelligence;

    if (input) {
        let mappedSymbol = symbol;
        if (symbol.startsWith('NIFTY_')) {
            const mapping = {
                "NIFTY_BANK": "^NSEBANK",
                "NIFTY_IT": "^CNXIT",
                "NIFTY_FMCG": "^CNXFMCG",
                "NIFTY_METAL": "^CNXMETAL",
                "NIFTY_PHARMA": "^CNXPHARMA",
                "NIFTY_ENERGY": "^CNXENERGY",
                "NIFTY_AUTO": "^CNXAUTO",
                "NIFTY_REALTY": "^CNXREALTY",
                "NIFTY_PSU_BANK": "^CNXPSUBANK",
                "NIFTY_MEDIA": "^CNXMEDIA"
            };
            mappedSymbol = mapping[symbol] || symbol.replace('NIFTY_', '^CNX');
        }
        input.value = mappedSymbol;

        if (fromIntelligence) {
            const syncEl = document.getElementById('hits-sync-status');
            if (syncEl) {
                syncEl.innerHTML = `<span class="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-pulse"></span>OPENING ${mappedSymbol} DETAILS...`;
                setTimeout(() => {
                    syncEl.innerHTML = '<span class="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-pulse"></span>LIVE SYNC';
                }, 2500);
            }
        }

        if (intelTog && intelTog.checked) {
            intelTog.checked = false;
            intelTog.dispatchEvent(new Event('change'));
        } else if (!intelTog && fromIntelligence) {
            document.getElementById('intelligence-section')?.classList.add('hidden');
            document.getElementById('rotation-section')?.classList.add('hidden');
            document.getElementById('standard-dashboard')?.classList.remove('hidden');
            document.getElementById('view-dashboard')?.classList.add('bg-blue-600', 'text-white');
            document.getElementById('view-dashboard')?.classList.remove('text-gray-400');
            document.getElementById('view-intelligence')?.classList.remove('bg-blue-600', 'text-white');
            document.getElementById('view-intelligence')?.classList.add('text-gray-400');
        }
        if (rotTog && rotTog.checked) {
            rotTog.checked = false;
            rotTog.dispatchEvent(new Event('change'));
        }

        setTimeout(() => {
            if (window.fetchData) {
                // Keep Details action responsive from Intelligence view by avoiding full-screen overlay
                // while still performing a real foreground fetch/error flow.
                window.fetchData(fromIntelligence ? { showLoader: false, isBackground: false } : false);
            } else {
                console.error("fetchData not found on window object!");
            }
        }, 50);
    }
};

window.showAICommentary = (sectorName) => {
    const data = window.lastSectorData?.[sectorName];
    const panel = document.getElementById('ai-detail-panel');
    const text = document.getElementById('ai-detail-text');
    const title = document.getElementById('ai-detail-title');
    const rank = document.getElementById('ai-detail-rank');

    if (!(panel && text && title && rank)) return;

    panel.classList.remove('hidden');
    title.textContent = sectorName.replace('NIFTY_', '').replace('_', ' ');
    rank.textContent = `#${data?.rank || '—'}`;
    text.textContent = data?.commentary || 'AI commentary is not available for this sector yet. Use DETAILS to open the sector chart and context.';
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
};
