class MarketIntelligence {
    constructor(hitsTableId, sectorListId) {
        this.hitsBody = document.getElementById(hitsTableId);
        this.sectorList = document.getElementById(sectorListId);
        this.allHits = [];
        this.allSectors = {};
        this.activeSectorKey = null;
    }

    updateHits(hits) {
        if (!this.hitsBody) return;
        this.allHits = Array.isArray(hits) ? hits : [];
        this._renderHitsTable();
    }

    updateSectors(sectorData) {
        if (!this.sectorList) return;
        this.allSectors = sectorData || {};

        if (!sectorData || Object.keys(sectorData).length === 0) {
            this.sectorList.innerHTML = '<div class="p-8 text-center text-gray-500 italic border border-gray-800 rounded-2xl">Awaiting sector rotation data...</div>';
            return;
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

        this.sectorList.innerHTML = sectors.map(sector => {
            const metrics = sector.metrics || {};
            const state = metrics.state || 'NEUTRAL';
            const stateMeta = this._stateMeta(state);
            const rsPercent = ((sector.current?.rs || 1) - 1) * 100;
            const explanation = this._buildSectorExplanation(state, sector.current?.rs || 1, sector.current?.rm || 0);

            return `
                <div class="glass p-4 rounded-2xl border-l-4 ${stateMeta.borderClass} relative overflow-hidden group cursor-pointer"
                     data-sector-key="${sector.name}">
                    <div class="flex justify-between items-start relative z-10">
                        <div>
                            <h3 class="font-bold text-sm text-white">${sector.name ? sector.name.replace('NIFTY_', '').replace('_', ' ') : 'Unknown'}</h3>
                            <div class="flex items-center gap-3 mt-1">
                                <span class="text-[10px] font-bold ${stateMeta.textClass} uppercase tracking-tighter">${state}</span>
                                <span class="text-[10px] text-gray-400 font-mono">RS ${(rsPercent >= 0 ? '+' : '') + rsPercent.toFixed(2)}%</span>
                            </div>
                            <p class="text-[11px] text-gray-300 mt-2 leading-relaxed">${explanation}</p>
                        </div>
                        <div class="text-right">
                            <p class="text-[10px] text-gray-500 font-bold uppercase tracking-widest leading-none mb-1">Rank</p>
                            <p class="text-lg font-bold text-white mono">#${sector.rank || '—'}</p>
                        </div>
                    </div>
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
                if (window.fetchDataForSymbol && sectorName) window.fetchDataForSymbol(sectorName);
            });
        });

        this._renderHitsTable();

        if (window.renderActionableSectors) {
            window.renderActionableSectors(sectorData);
        }
    }

    _buildSectorExplanation(state, rs, rm) {
        if (state === 'LEADING') return 'Sector is strong: RS is above benchmark and RS momentum is rising.';
        if (state === 'WEAKENING') return 'Sector was strong but momentum is cooling, so follow-through is weaker.';
        if (state === 'LAGGING') return 'Sector is weak: RS is below benchmark and momentum is still falling.';
        if (state === 'IMPROVING') return 'Sector is recovering: RS is below benchmark but momentum has turned positive.';
        return 'Sector is balanced near benchmark with no clear relative-strength edge.';
    }

    _statePriority(state) {
        return ({ LEADING: 5, IMPROVING: 4, WEAKENING: 3, NEUTRAL: 2, LAGGING: 1 })[state] || 0;
    }

    _stateMeta(state) {
        if (state === 'LEADING' || state === 'IMPROVING') return { textClass: 'text-green-400', borderClass: 'border-l-green-500' };
        if (state === 'LAGGING' || state === 'WEAKENING') return { textClass: 'text-red-400', borderClass: 'border-l-red-500' };
        return { textClass: 'text-gray-400', borderClass: 'border-l-gray-600' };
    }

    _renderHitsTable() {
        if (!this.hitsBody) return;

        const actionableSectorStates = new Set(['LEADING', 'IMPROVING']);

        let working = this.allHits.filter((hit) => {
            const sector = this.allSectors?.[hit.sectorKey];
            const sectorState = sector?.metrics?.state || 'NEUTRAL';
            if (!actionableSectorStates.has(sectorState)) return false;
            if ((hit.rsSector ?? 0) <= 1) return false;
            if (!hit.volumeExpansion) return false;
            return true;
        });

        if (this.activeSectorKey) {
            working = working.filter(h => h.sectorKey === this.activeSectorKey);
        }

        if (!working.length) {
            this.hitsBody.innerHTML = '<tr><td colspan="7" class="px-4 py-10 text-center text-gray-500 italic">No actionable stock intelligence. Requires sector LEADING/IMPROVING, stock RS vs sector > 1, and volume expansion.</td></tr>';
            return;
        }

        working.sort((a, b) => {
            const av = a.volumeShocker ?? a.volRatio ?? 0;
            const bv = b.volumeShocker ?? b.volRatio ?? 0;
            if (bv !== av) return bv - av;
            const ars = a.rsSector ?? 0;
            const brs = b.rsSector ?? 0;
            return brs - ars;
        });

        this.hitsBody.innerHTML = working.map(hit => {
            const vol = hit.volumeShocker ?? hit.volRatio ?? 0;
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
                        <div class="flex items-center justify-center gap-1">${this._renderHits(hit.hits3d, hit.hits2d, hit.hits1d)}</div>
                    </td>
                    <td class="px-4 py-3 text-right">
                        <div class="flex items-center justify-end gap-1">
                            <span class="font-mono text-gray-300">${vol.toFixed(2)}x</span>
                            ${shockerBadge ? `<span class="text-sm">${shockerBadge}</span>` : ''}
                        </div>
                    </td>
                    <td class="px-4 py-3 text-right"><span class="text-[9px] bg-gray-800 text-gray-400 px-2 py-0.5 rounded-full font-bold uppercase">${hit.sector}</span></td>
                </tr>
            `;
        }).join('');
    }

    _renderHits(hits3d, hits2d, hits1d) {
        const renderBadge = (active, label) => `
            <div class="w-6 h-6 rounded-md flex items-center justify-center font-bold text-[8px] border transition-all ${active ? 'bg-indigo-600 border-indigo-500 text-white shadow-[0_0_8px_rgba(99,102,241,0.4)]' : 'bg-gray-900 border-gray-800 text-gray-700'}">${label}</div>
        `;
        return renderBadge(hits3d, '3D') + renderBadge(hits2d, '2D') + renderBadge(hits1d, '1D');
    }
}

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

window.fetchDataForSymbol = (symbol) => {
    const input = document.getElementById('symbol-input');
    const intelTog = document.getElementById('intelligence-toggle');
    const rotTog = document.getElementById('rotation-toggle');

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

        if (intelTog && intelTog.checked) {
            intelTog.checked = false;
            intelTog.dispatchEvent(new Event('change'));
        }
        if (rotTog && rotTog.checked) {
            rotTog.checked = false;
            rotTog.dispatchEvent(new Event('change'));
        }

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
    const data = window.lastSectorData?.[sectorName];
    if (data && data.commentary) {
        const panel = document.getElementById('ai-detail-panel');
        const text = document.getElementById('ai-detail-text');
        const title = document.getElementById('ai-detail-title');
        const rank = document.getElementById('ai-detail-rank');

        if (panel && text && title && rank) {
            panel.classList.remove('hidden');
            title.textContent = sectorName.replace('NIFTY_', '').replace('_', ' ');
            text.textContent = data.commentary;
            rank.textContent = `#${data.rank || '—'}`;
        }
    }
};
