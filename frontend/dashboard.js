class MarketIntelligence {
    constructor(hitsTableId, sectorListId) {
        this.hitsBody = document.getElementById(hitsTableId);
        this.sectorList = document.getElementById(sectorListId);
        this.allHits = [];
        this.activeSectorKey = null;
    }

    updateHits(hits) {
        if (!this.hitsBody) return;
        this.allHits = Array.isArray(hits) ? hits : [];
        this._renderHitsTable();
    }

    updateSectors(sectorData) {
        if (!this.sectorList) return;

        if (!sectorData || Object.keys(sectorData).length === 0) {
            this.sectorList.innerHTML = '<div class="p-8 text-center text-gray-500 italic border border-gray-800 rounded-2xl">Awaiting sector rotation data...</div>';
            return;
        }

        // Convert to array and sort by momentum score (SHINING sectors get a small boost)
        const sectors = Object.entries(sectorData)
            .map(([name, data]) => ({ name, ...data }))
            .filter(s => s && s.metrics) // Guard against malformed entries
            .sort((a, b) => {
                const aShine = (a.metrics.state === 'SHINING') ? 50 : 0;
                const bShine = (b.metrics.state === 'SHINING') ? 50 : 0;
                return (b.metrics.momentumScore || 0) + bShine - ((a.metrics.momentumScore || 0) + aShine);
            });

        this.sectorList.innerHTML = sectors.map(sector => {
            const metrics = sector.metrics || {};
            const shift = metrics.shift || 'NEUTRAL';
            const shiftColor = shift === 'GAINING' ? 'text-up' : shift === 'LOSING' ? 'text-down' : 'text-gray-400';
            const bgGradient = shift === 'GAINING' ? 'from-green-500/10 to-transparent' : shift === 'LOSING' ? 'from-red-500/10 to-transparent' : 'from-gray-500/5 to-transparent';
            const score = metrics.momentumScore || 0;
            const rank = sector.rank || '—';
            const isShining = metrics.state === 'SHINING';

            return `
                <div class="glass p-4 rounded-2xl border-l-4 ${isShining ? 'border-l-up shadow-[0_0_18px_rgba(34,197,94,0.55)]' : shift === 'GAINING' ? 'border-l-up' : shift === 'LOSING' ? 'border-l-down' : 'border-l-gray-700'} relative overflow-hidden group cursor-pointer"
                     data-sector-key="${sector.name}">

                    <div class="absolute inset-0 bg-gradient-to-r ${bgGradient} opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
                    
                    <div class="flex justify-between items-start relative z-10">
                        <div>
                            <div class="flex items-center gap-2 mb-1">
                                <span class="text-[10px] font-bold text-gray-500 font-mono">#${rank}</span>
                                <h3 class="font-bold text-sm text-white">${sector.name ? sector.name.replace('NIFTY_', '').replace('_', ' ') : 'Unknown'}</h3>
                            </div>
                            <div class="flex items-center gap-3">
                                <span class="text-[10px] font-bold ${shiftColor} flex items-center gap-1 uppercase tracking-tighter">
                                    <span class="w-1.5 h-1.5 rounded-full ${shift === 'GAINING' ? 'bg-up animate-pulse' : shift === 'LOSING' ? 'bg-down animate-pulse' : 'bg-gray-500'}"></span>
                                    ${shift}
                                </span>
                                <span class="text-[10px] text-gray-500 font-medium">Breadth: <span class="text-gray-300">${metrics.breadth || 0}%</span></span>
                            </div>
                        </div>
                        <div class="text-right">
                            <p class="text-[10px] text-gray-500 font-bold uppercase tracking-widest leading-none mb-1">Momentum</p>
                            <p class="text-xl font-bold text-white mono">${Math.round(score)}</p>
                        </div>
                    </div>
                    
                    <div class="mt-4 flex items-center justify-between text-[9px] relative z-10">
                        <div class="flex gap-1.5">
                            ${sector.commentary ? `<button class="px-2 py-0.5 bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-md hover:bg-indigo-500/20 transition-colors" data-action="ai-view" data-sector="${sector.name}">AI VIEW</button>` : ''}
                            <button class="px-2 py-0.5 bg-gray-800 text-gray-400 border border-gray-700 rounded-md hover:bg-gray-700 transition-colors" data-action="details" data-sector="${sector.name}">DETAILS</button>
                        </div>
                            <div class="flex items-center gap-2">
                             <div class="flex flex-col text-right">
                                <span class="text-[8px] text-gray-600 uppercase">Vol Ratio</span>
                                <span class="font-bold text-gray-300">${metrics.relVolume || 0}x</span>
                             </div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        // Bind interaction handlers explicitly (avoid brittle inline-event reliance).
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
                if (window.fetchDataForSymbol && sectorName) window.fetchDataForSymbol(sectorName);
            });
        });

        // Render SHINING sectors primary card (new UX feature)
        if (window.renderShiningSectors) {
            window.renderShiningSectors(sectorData);
        }
    }

    _renderHitsTable() {
        if (!this.hitsBody) return;

        const rows = this.allHits.slice(); // shallow copy

        if (!rows.length) {
            this.hitsBody.innerHTML = '<tr><td colspan="7" class="px-4 py-10 text-center text-gray-500 italic">No momentum hits detected in the current session.</td></tr>';
            return;
        }

        // Filter by active sector if one is selected
        let working = rows;
        if (this.activeSectorKey) {
            working = rows.filter(h => h.sectorKey === this.activeSectorKey);
        }

        // Rank: Volume Shocker then RS vs Sector then price change
        working.sort((a, b) => {
            const av = a.volumeShocker ?? a.volRatio ?? 0;
            const bv = b.volumeShocker ?? b.volRatio ?? 0;
            if (bv !== av) return bv - av;
            const ars = a.rsSector ?? 1;
            const brs = b.rsSector ?? 1;
            if (brs !== ars) return brs - ars;
            return (b.change ?? 0) - (a.change ?? 0);
        });

        // Limit to top 10 when a sector is focused
        if (this.activeSectorKey) {
            working = working.slice(0, 10);
        }

        this.hitsBody.innerHTML = working.map(hit => {
            const vol = hit.volumeShocker ?? hit.volRatio ?? 0;
            const rs = hit.rsSector ?? 1;
            const shockerBadge = vol >= 2.5 ? '🔥' : vol >= 2.0 ? '⚡' : '';
            const tradeReady = !!hit.tradeReady;
            const tradeLabel = tradeReady
                ? '<span class="ml-2 px-2 py-0.5 rounded-full text-[9px] font-bold tracking-widest bg-green-600/10 text-green-400 border border-green-500/40">TRADE&nbsp;READY</span>'
                : '';

            return `
                <tr class="hover:bg-gray-800/30 transition-colors group cursor-pointer" 
                    data-sector-key="${hit.sectorKey || ''}"
                    onclick="window.fetchDataForSymbol('${hit.symbol}')">
                    <td class="px-4 py-3 font-bold text-white group-hover:text-blue-400 transition-colors">
                        ${hit.symbol}
                        ${tradeLabel}
                    </td>
                    <td class="px-4 py-3 font-mono text-gray-300">₹${hit.price}</td>
                    <td class="px-4 py-3 font-bold ${hit.change >= 0 ? 'text-up' : 'text-down'}">${(hit.change >= 0 ? '+' : '') + (hit.change ?? 0).toFixed(2)}%</td>
                    <td class="px-4 py-3 text-center">
                        <div class="flex items-center justify-center gap-1">
                            ${this._renderHits(hit.hits3d, hit.hits2d, hit.hits1d)}
                        </div>
                    </td>
                    <td class="px-4 py-3 text-right">
                        <div class="flex items-center justify-end gap-1">
                            <span class="font-mono text-gray-300">${vol.toFixed(2)}x</span>
                            ${shockerBadge ? `<span class="text-sm">${shockerBadge}</span>` : ''}
                        </div>
                    </td>
                    <td class="px-4 py-3 text-right">
                        <span class="text-[9px] bg-gray-800 text-gray-400 px-2 py-0.5 rounded-full font-bold uppercase">${hit.sector}</span>
                    </td>
                </tr>
            `;
        }).join('');

        // Auto scroll first row into view when focusing a sector
        if (this.activeSectorKey) {
            const first = this.hitsBody.querySelector('tr');
            if (first) {
                first.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }
    }

    _renderHits(hits3d, hits2d, hits1d) {
        const renderBadge = (active, label) => `
            <div class="w-6 h-6 rounded-md flex items-center justify-center font-bold text-[8px] border transition-all ${active ? 'bg-indigo-600 border-indigo-500 text-white shadow-[0_0_8px_rgba(99,102,241,0.4)]' : 'bg-gray-900 border-gray-800 text-gray-700'
            }">
                ${label}
            </div>
        `;
        return renderBadge(hits3d, '3D') + renderBadge(hits2d, '2D') + renderBadge(hits1d, '1D');
    }
}

// Global Helpers for dashboard interaction
window.focusSector = (sectorKey) => {
    if (!window.intelligenceApp) return;
    // Toggle behaviour: clicking same sector again clears the filter
    if (window.intelligenceApp.activeSectorKey === sectorKey) {
        window.intelligenceApp.activeSectorKey = null;
    } else {
        window.intelligenceApp.activeSectorKey = sectorKey;
    }
    window.intelligenceApp._renderHitsTable();

    // Visually mark active sector card
    const cards = document.querySelectorAll('#sector-intelligence-list [data-sector-key]');
    cards.forEach(card => {
        if (card.getAttribute('data-sector-key') === window.intelligenceApp.activeSectorKey) {
            card.classList.add('ring-2', 'ring-green-400/70', 'ring-offset-2', 'ring-offset-gray-900');
        } else {
            card.classList.remove('ring-2', 'ring-green-400/70', 'ring-offset-2', 'ring-offset-gray-900');
        }
    });
};

window.fetchDataForSymbol = (symbol) => {
    const input = document.getElementById('symbol-input');
    const intelTog = document.getElementById('intelligence-toggle');
    const rotTog = document.getElementById('rotation-toggle');

    if (input) {
        // 1. Map symbols
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

        // 2. Switch UI back to standard view BEFORE fetching
        if (intelTog && intelTog.checked) {
            intelTog.checked = false;
            intelTog.dispatchEvent(new Event('change'));
        }
        if (rotTog && rotTog.checked) {
            rotTog.checked = false;
            rotTog.dispatchEvent(new Event('change'));
        }

        // 3. Trigger Fetch with a slight delay
        setTimeout(() => {
            if (window.fetchData) {
                window.fetchData();
            } else {
                console.error("fetchData not found on window object!");
            }
        }, 50);
    }
};

window.showAICommentary = (sectorName) => {
    // Logic to show commentary in the AI detail panel
    const data = window.lastSectorData?.[sectorName];
    if (data && data.commentary) {
        const panel = document.getElementById('ai-detail-panel');
        const text = document.getElementById('ai-detail-text');
        const title = document.getElementById('ai-detail-title');
        const rank = document.getElementById('ai-detail-rank');

        if (panel && text && title && rank) {
            title.textContent = sectorName.replace('NIFTY_', '').replace('_', ' ') + ' Analysis';
            text.textContent = data.commentary;
            rank.textContent = `#${data.rank || '--'} Overall Strength`;
            panel.classList.remove('hidden');
        }
    }
};
