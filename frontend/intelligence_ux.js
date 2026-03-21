// UX IMPROVEMENTS - Add to dashboard.js

// ========================================
// 1. LEADING SECTORS PRIMARY CARD
// ========================================

function renderActionableSectors(sectorData) {
    const container = document.getElementById('shining-sectors-list');
    if (!container) return;

    // Filter for LEADING sectors only
    const shiningSectors = Object.entries(sectorData)
        .filter(([name, data]) => ['LEADING', 'IMPROVING'].includes(data.metrics?.state))
        .sort((a, b) => (b[1].metrics?.momentumScore || 0) - (a[1].metrics?.momentumScore || 0))
        .slice(0, 4); // Top 4 only

    if (shiningSectors.length === 0) {
        container.innerHTML = `
            <div class="text-xs text-gray-500 italic">
                No actionable sectors right now. Watch sectors in LEADING or IMPROVING state for opportunities.
            </div>
        `;
        return;
    }

    container.innerHTML = shiningSectors.map(([name, data]) => {
        const displayName = name.replace('NIFTY_', '');
        const score = Math.round(data.metrics?.momentumScore || 0);
        const breadth = Math.round(data.metrics?.breadth || 0);

        return `
            <button 
                onclick="selectActionableSector('${name}')" 
                class="flex-shrink-0 glass px-4 py-3 rounded-xl border-2 border-green-500/50 hover:border-green-500 transition-all cursor-pointer group min-w-[140px]">
                <div class="flex items-center gap-2 mb-1">
                    <div class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                    <span class="text-sm font-bold text-green-400 group-hover:text-green-300">${displayName}</span>
                </div>
                <div class="flex items-center justify-between text-[9px] text-gray-500">
                    <span>Score: ${score}</span>
                    <span>•</span>
                    <span>Breadth: ${breadth}%</span>
                </div>
            </button>
        `;
    }).join('');

    // Show "What to Watch Now" panel
    updateWhatToWatchNow(shiningSectors, sectorData);
}

// ========================================
// 2. WHAT TO WATCH NOW PANEL
// ========================================

function updateWhatToWatchNow(shiningSectors, allSectorData) {
    const panel = document.getElementById('watch-now-panel');
    const content = document.getElementById('watch-now-content');

    if (!panel || !content) return;

    if (shiningSectors.length === 0) {
        panel.classList.add('hidden');
        return;
    }

    panel.classList.remove('hidden');

    const topSector = shiningSectors[0];
    const [sectorName, sectorData] = topSector;
    const displayName = sectorName.replace('NIFTY_', '');
    const shift = sectorData.metrics?.shift || 'NEUTRAL';
    const breadth = Math.round(sectorData.metrics?.breadth || 0);
    const volume = sectorData.metrics?.relVolume || 0;

    const insights = [];

    // Insight 1: Top sector
    insights.push(`<strong>${displayName}</strong> sector showing strongest performance`);

    // Insight 2: Momentum direction
    if (shift === 'GAINING') {
        insights.push(`Strength is <span class="text-green-400">accelerating</span> (both RS and momentum rising)`);
    } else if (shift === 'LOSING') {
        insights.push(`Strength is <span class="text-red-400">weakening</span> (both RS and momentum falling)`);
    }

    // Insight 3: Breadth
    if (breadth >= 70) {
        insights.push(`<span class="text-green-400">${breadth}%</span> of stocks are advancing - broad participation`);
    } else if (breadth >= 60) {
        insights.push(`${breadth}% of stocks are advancing - healthy breadth`);
    }

    // Insight 4: Volume
    if (volume >= 1.5) {
        insights.push(`<span class="text-green-400">High volume</span> seen - ${volume.toFixed(1)}x above average`);
    } else if (volume >= 1.3) {
        insights.push(`Volume is elevated - ${volume.toFixed(1)}x above average`);
    }

    // Insight 5: Action suggestion
    if (shiningSectors.length >= 2) {
        const secondSector = shiningSectors[1][0].replace('NIFTY_', '');
        insights.push(`Focus on top names with green indicators`);
    }

    content.innerHTML = insights.map(insight => `
        <p class="text-xs text-gray-300 leading-relaxed">• ${insight}</p>
    `).join('');
}

// ========================================
// 3. SECTOR SELECTION & FILTERING
// ========================================

let selectedSector = null;

function selectActionableSector(sectorName) {
    // Toggle off if the same sector chip is clicked again
    if (selectedSector === sectorName) {
        clearFilter();
        if (window.focusSector) window.focusSector(sectorName);
        return;
    }

    selectedSector = sectorName;

    // Update filter banner
    const filterBanner = document.getElementById('filter-banner');
    const filterSector = document.getElementById('filter-sector');
    const filterTimeframe = document.getElementById('filter-timeframe');

    if (filterBanner && filterSector) {
        filterBanner.classList.remove('hidden');
        filterSector.textContent = sectorName.replace('NIFTY_', '');
        filterTimeframe.textContent = getCurrentIntelTimeframe();
    }

    // Highlight selected sector card
    document.querySelectorAll('#shining-sectors-list button').forEach(btn => {
        if (btn.onclick.toString().includes(sectorName)) {
            btn.classList.add('ring-2', 'ring-green-500');
        } else {
            btn.classList.remove('ring-2', 'ring-green-500');
        }
    });

    // Filter stock activity table
    filterStockActivityTable(sectorName);

    // Scroll to sector in strength list
    focusSector(sectorName);
}

function clearFilter() {
    selectedSector = null;
    document.getElementById('filter-banner')?.classList.add('hidden');
    document.querySelectorAll('#shining-sectors-list button').forEach(btn => {
        btn.classList.remove('ring-2', 'ring-green-500');
    });
    filterStockActivityTable(null); // Show all
}

function filterStockActivityTable(sectorName) {
    const rows = document.querySelectorAll('#momentum-hits-body tr');

    rows.forEach(row => {
        if (!sectorName) {
            row.style.display = '';
            return;
        }

        const sectorCell = row.querySelector('td:last-child');
        if (sectorCell && sectorCell.textContent.includes(sectorName.replace('NIFTY_', ''))) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

// ========================================
// 4. CONTEXTUAL TIMEFRAME TOGGLE
// ========================================

let currentIntelTimeframe = '15m';

function getCurrentIntelTimeframe() {
    return currentIntelTimeframe;
}

function setupIntelTimeframeToggles() {
    document.querySelectorAll('[data-intel-tf]').forEach(btn => {
        btn.addEventListener('click', function () {
            const tf = this.getAttribute('data-intel-tf');
            currentIntelTimeframe = tf;

            // Update button states
            document.querySelectorAll('[data-intel-tf]').forEach(b => {
                b.classList.remove('bg-green-600', 'text-white');
                b.classList.add('text-gray-400');
            });
            this.classList.add('bg-green-600', 'text-white');
            this.classList.remove('text-gray-400');

            // Refresh intelligence data
            if (window.fetchIntelligence) {
                window.fetchIntelligence(tf);
            }
        });
    });
}

// ========================================
// 5. VIEW MODE TOGGLE
// ========================================

function setupViewModeToggle() {
    const dashboardBtn = document.getElementById('view-dashboard');
    const intelligenceBtn = document.getElementById('view-intelligence');
    const dashboardSection = document.getElementById('standard-dashboard');
    const intelligenceSection = document.getElementById('intelligence-section');
    const rotationSection = document.getElementById('rotation-section');
    const screenerPanel = document.getElementById('screener-panel');

    if (!dashboardBtn || !intelligenceBtn) return;

    dashboardBtn.addEventListener('click', function () {
        // Show dashboard, hide others
        dashboardSection?.classList.remove('hidden');
        intelligenceSection?.classList.add('hidden');
        rotationSection?.classList.add('hidden');
        screenerPanel?.classList.add('hidden');

        // Update button states
        this.classList.add('bg-blue-600', 'text-white');
        this.classList.remove('text-gray-400');
        intelligenceBtn.classList.remove('bg-blue-600', 'text-white');
        intelligenceBtn.classList.add('text-gray-400');
    });

    intelligenceBtn.addEventListener('click', function () {
        // Show intelligence, hide others
        dashboardSection?.classList.add('hidden');
        intelligenceSection?.classList.remove('hidden');
        rotationSection?.classList.add('hidden');
        screenerPanel?.classList.add('hidden');

        // Update button states
        this.classList.add('bg-blue-600', 'text-white');
        this.classList.remove('text-gray-400');
        dashboardBtn.classList.remove('bg-blue-600', 'text-white');
        dashboardBtn.classList.add('text-gray-400');

        // Fetch intelligence data
        if (window.fetchIntelligence) {
            window.fetchIntelligence();
        }
    });
}

// ========================================
// 6. ADVANCED SECTION TOGGLE
// ========================================

let advancedExpanded = false;

function setupAdvancedToggle() {
    const toggleBtn = document.getElementById('toggle-advanced');
    if (!toggleBtn) return;

    toggleBtn.addEventListener('click', function () {
        advancedExpanded = !advancedExpanded;
        this.textContent = advancedExpanded ? 'Advanced ▲' : 'Advanced ▼';

        // Show/hide additional metrics in sector cards
        document.querySelectorAll('.sector-advanced-metrics').forEach(el => {
            el.classList.toggle('hidden', !advancedExpanded);
        });
    });
}

// ========================================
// 7. INITIALIZE ON LOAD
// ========================================

document.addEventListener('DOMContentLoaded', function () {
    setupViewModeToggle();
    setupIntelTimeframeToggles();
    setupAdvancedToggle();

    // Clear filter button
    document.getElementById('clear-filter')?.addEventListener('click', clearFilter);

    // Quick Filters (NEW v1.4)
    const filterLeaders = document.getElementById('filter-leaders');
    const filterSmart = document.getElementById('filter-smart');
    const filterMomentum = document.getElementById('filter-momentum');

    const clearQuickFilters = () => {
        [filterLeaders, filterSmart, filterMomentum].forEach(btn => {
            if (btn) {
                btn.classList.remove('border-indigo-500', 'text-indigo-400', 'bg-indigo-500/10');
                btn.classList.add('border-gray-800', 'text-gray-500', 'bg-gray-900/50');
            }
        });
    };

    if (filterLeaders) {
        filterLeaders.addEventListener('click', () => {
            const isActive = filterLeaders.classList.contains('border-indigo-500');
            clearQuickFilters();
            if (!isActive) {
                filterLeaders.classList.replace('border-gray-800', 'border-indigo-500');
                filterLeaders.classList.replace('text-gray-500', 'text-indigo-400');
                filterLeaders.classList.replace('bg-gray-900/50', 'bg-indigo-500/10');
                window.marketIntelligence.filterMode = 'leaders';
            } else {
                window.marketIntelligence.filterMode = null;
            }
            window.marketIntelligence.updateHits(window.marketIntelligence.lastHitsData);
        });
    }

    if (filterSmart) {
        filterSmart.addEventListener('click', () => {
            const isActive = filterSmart.classList.contains('border-indigo-500');
            clearQuickFilters();
            if (!isActive) {
                filterSmart.classList.replace('border-gray-800', 'border-indigo-500');
                filterSmart.classList.replace('text-gray-500', 'text-indigo-400');
                filterSmart.classList.replace('bg-gray-900/50', 'bg-indigo-500/10');
                window.marketIntelligence.filterMode = 'smart';
            } else {
                window.marketIntelligence.filterMode = null;
            }
            window.marketIntelligence.updateHits(window.marketIntelligence.lastHitsData);
        });
    }

    if (filterMomentum) {
        filterMomentum.addEventListener('click', () => {
            const isActive = filterMomentum.classList.contains('border-indigo-500');
            clearQuickFilters();
            if (!isActive) {
                filterMomentum.classList.replace('border-gray-800', 'border-indigo-500');
                filterMomentum.classList.replace('text-gray-500', 'text-indigo-400');
                filterMomentum.classList.replace('bg-gray-900/50', 'bg-indigo-500/10');
                window.marketIntelligence.filterMode = 'momentum';
            } else {
                window.marketIntelligence.filterMode = null;
            }
            window.marketIntelligence.updateHits(window.marketIntelligence.lastHitsData);
        });
    }
});

// ========================================
// 9. AI TOP PICKS (v2.0)
// ========================================

function renderTopTradesContextBanner(marketContext) {
    const banner = document.getElementById('top-trades-context');
    if (!banner) return;

    if (!marketContext || !marketContext.message) {
        banner.textContent = '';
        banner.className = 'mb-3 text-[10px] text-yellow-300 bg-yellow-500/10 border border-yellow-500/20 rounded-xl px-3 py-2 hidden';
        return;
    }

    banner.textContent = marketContext.message;
    if (marketContext.lowConviction) {
        banner.className = 'mb-3 text-[10px] text-yellow-300 bg-yellow-500/10 border border-yellow-500/20 rounded-xl px-3 py-2';
    } else {
        banner.className = 'mb-3 text-[10px] text-green-300 bg-green-500/10 border border-green-500/20 rounded-xl px-3 py-2';
    }
}

function renderTopPicks(hits, options = {}) {
    const section = document.getElementById('top-picks-section');
    const container = document.getElementById('top-picks-container');
    if (!section || !container) return;

    const topPicks = (hits || []).filter(h => (h.action || '').toUpperCase() === 'BUY');

    renderTopTradesContextBanner(options.marketContext);

    if (topPicks.length === 0) {
        section.classList.add('hidden');
        return;
    }

    section.classList.remove('hidden');
    container.innerHTML = topPicks.map(h => {
        const plan = h.executionPlan || {};
        const trust = h.trustSignals || {};
        const tags = (h.reasonTags || []).slice(0, 3).map(tag => `<span class="reason-tag">${tag}</span>`).join('');
        const confirmations = (plan.entryConfirmation || []).map(item => `<li>${item}</li>`).join('');
        const invalidates = (h.whatInvalidates || []).slice(0, 2).join(' • ');
        return `
            <div onclick="window.fetchDataForSymbol('${h.symbol}')" 
                 class="bg-gray-900 border border-green-500/20 p-4 rounded-2xl cursor-pointer hover:border-green-500/50 transition-all group">
                <div class="flex justify-between items-start mb-2">
                    <div>
                        <span class="text-lg font-bold text-white">${h.symbol}</span>
                        <div class="text-[9px] text-green-400 font-black uppercase tracking-widest mt-1">🔥 TOP TRADE #${h.topTradeRank || ''}</div>
                    </div>
                    <div class="text-right">
                        <span class="text-xs font-black mono text-green-400">${Math.round(h.score || 0)}</span>
                        <div class="text-[8px] text-gray-500 uppercase">Score</div>
                    </div>
                </div>
                <div class="flex items-center justify-between mb-3">
                    <div class="text-[10px] font-black uppercase tracking-widest text-green-400">${h.action}</div>
                    <div class="text-[10px] font-bold text-blue-300">${plan.executeNotice || 'Execute only if conditions are met'}</div>
                </div>
                <div class="grid grid-cols-2 gap-2 text-[10px]">
                    <div class="rounded-xl bg-gray-800/60 p-2"><div class="text-gray-500 uppercase">Entry</div><div class="mono font-bold text-white">₹${window.formatVal ? window.formatVal(plan.entry) : plan.entry}</div></div>
                    <div class="rounded-xl bg-gray-800/60 p-2"><div class="text-gray-500 uppercase">SL</div><div class="mono font-bold text-red-400">₹${window.formatVal ? window.formatVal(plan.stopLoss) : plan.stopLoss}</div></div>
                    <div class="rounded-xl bg-gray-800/60 p-2"><div class="text-gray-500 uppercase">Target</div><div class="mono font-bold text-green-400">₹${window.formatVal ? window.formatVal(plan.target1) : plan.target1}</div></div>
                    <div class="rounded-xl bg-gray-800/60 p-2"><div class="text-gray-500 uppercase">RR</div><div class="mono font-bold text-white">${Number(plan.riskRewardToT1 || h.rr || 0).toFixed(2)}x</div></div>
                </div>
                <div class="mt-3 text-[10px] text-gray-300"><span class="text-gray-500 uppercase">Entry Type:</span> ${plan.entryType || '—'}</div>
                <div class="mt-1 text-[10px] text-gray-300"><span class="text-gray-500 uppercase">Position:</span> ${plan.positionSizingSuggestion || '—'}</div>
                <div class="mt-1 text-[10px] text-gray-300"><span class="text-gray-500 uppercase">Exit:</span> ${plan.partialProfitPlan || ''} ${plan.trailingStopPlan || ''}</div>
                <div class="mt-3 grid grid-cols-2 gap-2 text-[10px]">
                    <div class="rounded-xl bg-cyan-500/5 border border-cyan-500/20 p-2">
                        <div class="text-cyan-300 uppercase tracking-widest text-[8px]">Setup Win Rate</div>
                        <div class="mt-1 font-black text-white">${Number(trust.setupWinRate || 0).toFixed(0)}%</div>
                    </div>
                    <div class="rounded-xl bg-indigo-500/5 border border-indigo-500/20 p-2">
                        <div class="text-indigo-300 uppercase tracking-widest text-[8px]">Sector Performance</div>
                        <div class="mt-1 font-black text-white">${Number(trust.sectorPerformancePct || 0).toFixed(1)}%</div>
                    </div>
                </div>
                <div class="mt-2 text-[10px] text-cyan-100">${trust.trustMessage || ''}</div>
                <div class="mt-2 text-[10px] text-gray-400">${h.whyRankedTop || h.explanation || ''}</div>
                <ul class="mt-2 text-[10px] text-blue-300 list-disc list-inside space-y-1">${confirmations}</ul>
                <div class="mt-2 flex flex-wrap gap-2">${tags}</div>
                <div class="mt-2 text-[10px] text-red-300"><span class="font-bold uppercase">What can go wrong:</span> ${(h.whatCanGoWrong || []).join(' • ')}</div>
                <div class="mt-1 text-[10px] text-yellow-300"><span class="font-bold uppercase">Invalidates:</span> ${invalidates || '—'}</div>
            </div>
        `;
    }).join('');
}

window.fetchDataForSymbol = function(symbol) {
    document.getElementById('symbol-input').value = symbol;
    
    // Switch view to dashboard so the user sees the chart update
    const dashboardBtn = document.getElementById('view-dashboard');
    if (dashboardBtn) {
        dashboardBtn.click();
    }
    
    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
    
    // Fetch dashboard charts and strategy details
    window.fetchData();
};

window.renderTopPicks = renderTopPicks;

// ========================================
// 10. EXPORT FUNCTIONS
// ========================================

window.renderActionableSectors = renderActionableSectors;
window.selectActionableSector = selectActionableSector;
window.clearFilter = clearFilter;
window.getCurrentIntelTimeframe = getCurrentIntelTimeframe;

// SCANNERS FILTERS (v2.1) - WIRE UP UI CONTROLS
const initScannerFilters = () => {
    const confSlider = document.getElementById('confidence-filter');
    const confVal = document.getElementById('confidence-val');
    const probToggle = document.getElementById('high-probability-only');

    if (confSlider && confVal) {
        confSlider.addEventListener('input', (e) => {
            const val = e.target.value;
            confVal.textContent = `${val}%`;
            if (window.marketIntelligence) {
                window.marketIntelligence._renderHitsTable();
            }
        });
    }

    if (probToggle) {
        probToggle.addEventListener('change', () => {
            if (window.marketIntelligence) {
                window.marketIntelligence._renderHitsTable();
            }
        });
    }
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initScannerFilters);
} else {
    initScannerFilters();
}
