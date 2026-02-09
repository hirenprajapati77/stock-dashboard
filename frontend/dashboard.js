class MarketIntelligence {
    constructor(hitsTableId, sectorListId) {
        this.hitsBody = document.getElementById(hitsTableId);
        this.sectorList = document.getElementById(sectorListId);
    }

    updateHits(hits) {
        if (!this.hitsBody) return;

        if (!hits || hits.length === 0) {
            this.hitsBody.innerHTML = '<tr><td colspan="6" class="px-4 py-10 text-center text-gray-500 italic">No momentum hits detected in the current session.</td></tr>';
            return;
        }

        this.hitsBody.innerHTML = hits.map(hit => `
            <tr class="hover:bg-gray-800/30 transition-colors group cursor-pointer" onclick="window.fetchDataForSymbol('${hit.symbol}')">
                <td class="px-4 py-3 font-bold text-white group-hover:text-blue-400 transition-colors">${hit.symbol}</td>
                <td class="px-4 py-3 font-mono text-gray-300">₹${hit.price}</td>
                <td class="px-4 py-3 font-bold ${hit.change >= 0 ? 'text-up' : 'text-down'}">${hit.change >= 0 ? '+' : ''}${hit.change}%</td>
                <td class="px-4 py-3 text-center">
                    <div class="flex items-center justify-center gap-1">
                        ${this._renderHits(hit.hits3d, hit.hits2d, hit.hits1d)}
                    </div>
                </td>
                <td class="px-4 py-3 font-mono text-gray-400">${hit.volRatio}x</td>
                <td class="px-4 py-3 text-right">
                    <span class="text-[9px] bg-gray-800 text-gray-400 px-2 py-0.5 rounded-full font-bold uppercase">${hit.sector}</span>
                </td>
            </tr>
        `).join('');
    }

    updateSectors(sectorData) {
        if (!this.sectorList) return;

        if (!sectorData || Object.keys(sectorData).length === 0) {
            this.sectorList.innerHTML = '<div class="p-8 text-center text-gray-500 italic border border-gray-800 rounded-2xl">Awaiting sector rotation data...</div>';
            return;
        }

        // Convert to array and sort by momentum score
        const sectors = Object.entries(sectorData)
            .map(([name, data]) => ({ name, ...data }))
            .filter(s => s && s.metrics) // Guard against malformed entries
            .sort((a, b) => (b.metrics.momentumScore || 0) - (a.metrics.momentumScore || 0));

        this.sectorList.innerHTML = sectors.map(sector => {
            const metrics = sector.metrics || {};
            const shift = metrics.shift || 'NEUTRAL';
            const shiftColor = shift === 'GAINING' ? 'text-up' : shift === 'LOSING' ? 'text-down' : 'text-gray-400';
            const bgGradient = shift === 'GAINING' ? 'from-green-500/10 to-transparent' : shift === 'LOSING' ? 'from-red-500/10 to-transparent' : 'from-gray-500/5 to-transparent';
            const score = metrics.momentumScore || 0;
            const rank = sector.rank || '—';

            return `
                <div class="glass p-4 rounded-2xl border-l-4 ${shift === 'GAINING' ? 'border-l-up' : shift === 'LOSING' ? 'border-l-down' : 'border-l-gray-700'} relative overflow-hidden group">
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
                            ${sector.commentary ? `<button class="px-2 py-0.5 bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-md hover:bg-indigo-500/20 transition-colors" onclick="window.showAICommentary('${sector.name}')">AI VIEW</button>` : ''}
                            <button class="px-2 py-0.5 bg-gray-800 text-gray-400 border border-gray-700 rounded-md hover:bg-gray-700 transition-colors" onclick="window.fetchDataForSymbol('${sector.name}')">DETAILS</button>
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
