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
        this._initExplanationEvents();
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

    updateHits(hits) {
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

        // SANITY CHECK: Too many leading sectors
        const leadingCount = sectors.filter(s => s.metrics.state === 'LEADING').length;
        if (leadingCount > 3) console.warn(`Too many LEADING sectors (${leadingCount}) — check RS logic scaling`);

        this.sectorList.innerHTML = sectors.map(sector => {
            const metrics = sector.metrics || {};
            const state = metrics.state || 'NEUTRAL';
            const stateMeta = this._stateMeta(state);
            const rsPercent = (sector.current?.rs || 0) * 100;
            const explanation = this._buildSectorExplanation(state, sector.current?.rs || 0, sector.current?.rm || 0);

            // --- DEBUG OVERLAY CALCULATIONS (MUST-HAVE) ---
            const isDebug = new URLSearchParams(window.location.search).get('debug') === 'true';
            const sr = (metrics.sr || 0) * 100;
            const br = (metrics.br || 0) * 100;
            const rs = (sector.current?.rs || 0) * 100;
            const drs = (sector.current?.rm || 0) * 100;

            // AUTOMATIC SANITY WARNINGS (LOCKED)
            const srVal = metrics.sr || 0;
            if (srVal < 0 && state === 'LEADING') {
                console.error(`VALIDATION FAILURE: ${sector.name} is down (SR: ${(srVal * 100).toFixed(2)}%) but marked LEADING`);
            }
            if (state === 'IMPROVING' && srVal > 0) {
                console.error(`VALIDATION FAILURE: ${sector.name} is up (SR: ${(srVal * 100).toFixed(2)}%) but marked IMPROVING`);
            }

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

    updateMarketSummary(summaryData) {
        if (!this.summaryText || !this.summaryBlock || !summaryData) return;
        this.summaryData = summaryData;

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
            lines.push(`**${leadershipWord}** was observed in **${data.leadingSectors.join(", ")}**, showing higher participation versus the broader market.`);
        }

        if (data.weakeningSectors && data.weakeningSectors.length) {
            lines.push(`Momentum slowed in **${data.weakeningSectors.join(", ")}**, suggesting reduced follow-through.`);
        }

        if (data.improvingSectors && data.improvingSectors.length) {
            lines.push(`**${data.improvingSectors.join(", ")}** are down in absolute terms but showing relative improvement versus the market despite broader weakness.`);
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
            lines.push(`Strength was observed in **${data.leadingSectors.join(", ")}**, which remain key sectors to track.`);
        }

        if (data.weakeningSectors && data.weakeningSectors.length) {
            lines.push(`**${data.weakeningSectors.join(", ")}** showed signs of momentum fatigue and may remain selective.`);
        }

        lines.push("Traders may focus on stocks aligned with strong sectors while maintaining discipline in weaker areas.");
        return lines.join("\n\n");
    }

    _generateTomorrowOutlook(data) {
        const lines = [];

        if (data.leadingSectors && data.leadingSectors.length) {
            lines.push(`**${data.leadingSectors.join(", ")}** continue to display relative strength and may remain in focus if momentum sustains.`);
        }

        if (data.improvingSectors && data.improvingSectors.length) {
            lines.push(`**${data.improvingSectors.join(", ")}** are showing early improvement and may offer selective opportunities on confirmation.`);
        }

        if (data.weakeningSectors && data.weakeningSectors.length) {
            lines.push(`Momentum in **${data.weakeningSectors.join(", ")}** is slowing, and follow-through may remain limited.`);
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
            text += `Strong sectors from previous session: ${data.leadingSectors.join(", ")}\n`;
            if (data.weakeningSectors.length) text += `Weak areas: ${data.weakeningSectors.join(", ")}\n`;
            text += `Track stocks aligned with strong sectors.`;
        } else {
            text = `🧠 Daily Market Snapshot\n\n`;
            text += `Market: ${marketStatus}\n`;
            text += `Leading Sectors: ${data.leadingSectors.join(", ")}\n`;
            if (data.weakeningSectors.length) text += `Weakening: ${data.weakeningSectors.join(", ")}\n`;

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
        if (state === 'LEADING' || state === 'IMPROVING') return { textClass: 'text-green-400', borderClass: 'border-l-green-500' };
        if (state === 'LAGGING' || state === 'WEAKENING') return { textClass: 'text-red-400', borderClass: 'border-l-red-500' };
        return { textClass: 'text-gray-400', borderClass: 'border-l-gray-600' };
    }

    // CONFIDENCE METER ENGINE v1.2 (LOCKED)
    _calculateConfidence(hit) {
        if (!hit) return { score: 0, factors: [] };

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

    _renderConfidenceDots(score) {
        if (score >= 80) return "🟢🟢🟢🟢";
        if (score >= 60) return "🟢🟢🟢⚪";
        if (score >= 40) return "🟢🟢⚪⚪";
        return "🟢⚪⚪⚪";
    }

    _getConfidenceLabel(score) {
        if (score >= 80) return "HIGH";
        if (score >= 60) return "MEDIUM";
        if (score >= 40) return "LOW";
        return "VERY LOW";
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

            // Existing Sector Focus filter
            if (this.activeSectorKey && hit.sectorKey !== this.activeSectorKey) return false;

            return true;
        });

        if (window.location.search.includes('debug=true')) {
            console.log(`[Dashboard] Showing ${working.length} of ${this.allHits.length} signals. Session: ${this.allHits[0]?.session?.phase || 'N/A'}`);
        }

        if (!working.length) {
            this.hitsBody.innerHTML = '<tr><td colspan="12" class="px-4 py-10 text-center text-gray-500 italic">No setups match the confidence threshold. Recommended: 60% (Reliable).</td></tr>';
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

            if (currentTag === 'STRONG_ENTRY') statusColor = 'bg-green-600/30 text-green-400 border border-green-500/50 drop-shadow-[0_0_8px_rgba(74,222,128,0.5)]';
            else if (currentTag === 'ENTRY_READY') statusColor = 'bg-green-600/20 text-green-400 border border-green-500/30';
            else if (currentTag === 'WATCHLIST' || currentTag === 'WAIT') statusColor = 'bg-yellow-600/20 text-yellow-500 border border-yellow-500/30';
            if (hit.exitTag === 'EXIT') statusColor = 'bg-red-600/20 text-red-400 border border-red-500/30';

            // Grade Color Logic
            let gradeColor = 'text-gray-400';
            const grade = hit.grade || 'C';
            if (grade === 'A+') gradeColor = 'text-green-400 drop-shadow-[0_0_5px_rgba(74,222,128,0.8)]';
            else if (grade === 'A') gradeColor = 'text-green-400';
            else if (grade === 'B') gradeColor = 'text-green-200';
            else if (grade === 'C') gradeColor = 'text-yellow-500';

            // Risk Tag Logic
            let riskColor = 'text-gray-400';
            if (hit.riskLevel === 'LOW') riskColor = 'text-green-400';
            if (hit.riskLevel === 'MEDIUM') riskColor = 'text-yellow-500';
            if (hit.riskLevel === 'HIGH') riskColor = 'text-red-400';

            // Position Sizing & Session Metrics
            const ru = hit.riskUnits ?? 0;
            const session = hit.session || { phase: '—', quality: 'AVOID' };

            let sessionColor = 'text-gray-500';
            if (session.quality === 'BEST') sessionColor = 'text-green-400 font-bold';
            if (session.quality === 'CAUTION') sessionColor = 'text-yellow-500';

            // Streamlined Tooltips v1.1 (AUTO-EXPLANATION)
            const tooltip = this._generateExplanation(hit, { short: true });

            return `
                <tr class="hover:bg-gray-800/30 transition-colors group cursor-pointer"
                    data-sector-key="${hit.sectorKey || ''}"
                    title="${tooltip}"
                    onclick="window.fetchDataForSymbol('${hit.symbol}', { fromIntelligence: true })">
                    <td class="px-4 py-3 font-bold text-white group-hover:text-blue-400 transition-colors text-xs">
                        ${hit.symbol}
                        ${tradeLabel}
                    </td>
                    <td class="px-4 py-3 font-mono text-gray-300">₹${hit.price}</td>
                    <td class="px-4 py-3 font-bold ${hit.change >= 0 ? 'text-up' : 'text-down'} text-xs">${(hit.change >= 0 ? '+' : '') + (hit.change ?? 0).toFixed(2)}%</td>
                    <td class="px-4 py-3 text-center">
                        <div class="flex items-center justify-center gap-1">${this._renderHits(hit.hits3d, hit.hits2d, hit.hits1d)}</div>
                    </td>
                    <td class="px-4 py-3">
                         <div class="flex flex-col gap-1 items-start">
                             <span class="px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider ${statusColor}">
                                ${hit.exitTag === 'EXIT' ? 'EXIT' : (hit.entryStatus || hit.entryTag || 'AVOID').replace('_', ' ')}
                             </span>
                             <button class="text-[8px] text-indigo-400 font-bold uppercase hover:underline" 
                                     onclick="event.stopPropagation(); window.showExplanation('${hit.symbol}')">
                                Explain
                             </button>
                         </div>
                    </td>
                    <td class="px-4 py-3 text-center">
                         <div class="flex flex-col items-center gap-0.5" title="Confidence: ${hit.confidence || this._calculateConfidence(hit).score}%">
                             <span class="text-sm font-black tracking-tight ${gradeColor}">${grade}</span>
                             <span class="text-[9px] font-bold text-gray-500">${hit.confidence || this._calculateConfidence(hit).score}%</span>
                         </div>
                    </td>
                    <td class="px-4 py-3">
                         <span class="text-[10px] font-bold uppercase ${riskColor}">${hit.riskLevel || '—'}</span>
                    </td>
                    <td class="px-4 py-3">
                         <span class="text-[10px] font-bold uppercase ${ru > 1 ? 'text-blue-400' : 'text-gray-400'}">${ru} RU</span>
                    </td>
                    <td class="px-4 py-3">
                         <span class="text-[9px] font-bold uppercase ${sessionColor}">${session.phase}</span>
                    </td>
                    <td class="px-4 py-3 text-right">
                        <div class="flex items-center justify-end gap-1 font-mono text-xs">
                            <span class="text-gray-300">${vol.toFixed(2)}x</span>
                            ${shockerBadge ? `<span class="text-xs">${shockerBadge}</span>` : ''}
                        </div>
                    </td>
                    <td class="px-4 py-3 text-right"><span class="text-[9px] bg-gray-800 text-gray-400 px-2 py-0.5 rounded-full font-bold uppercase">${hit.sector}</span></td>
                </tr>
            `;
        }).join('');
    }

    _renderHits(hits3d, hits2d, hits1d) {
        return this.renderBadge(hits3d, '3D') + this.renderBadge(hits2d, '2D') + this.renderBadge(hits1d, '1D');
    }

    renderBadge(active, label) {
        const activeClass = 'bg-indigo-600 border-indigo-500 text-white shadow-[0_0_8px_rgba(99,102,241,0.4)]';
        const inactiveClass = 'bg-gray-900 border-gray-800 text-gray-700';
        return `
            <div class="w-6 h-6 rounded-md flex items-center justify-center font-bold text-[8px] border transition-all ${active ? activeClass : inactiveClass}">${label}</div>
        `;
    }

    showSignalExplanation(hit) {
        this.currentExplHit = hit;
        const overlay = document.getElementById('signal-modal-overlay');
        if (!overlay || !hit) return;
        this._updateExplanationView();
        overlay.classList.remove('hidden');
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

        // 5. Risk
        document.getElementById('expl-ru').textContent = `${hit.riskUnits || 0} RU`;

        // Icon
        const statusIcon = document.getElementById('expl-status-icon');
        if (hit.exitTag === 'EXIT') statusIcon.textContent = '🔴';
        else if (hit.entryTag === 'ENTRY_READY') statusIcon.textContent = '🟢';
        else if (hit.entryTag === 'WAIT') statusIcon.textContent = '🟡';
        else statusIcon.textContent = '⚪';

        // Confidence Metrics
        const confidence = this._calculateConfidence(hit);
        const grade = hit.grade || 'C';

        let gradeColor = 'text-gray-400';
        if (grade === 'A+') gradeColor = 'text-green-400 drop-shadow-[0_0_5px_rgba(74,222,128,0.8)]';
        else if (grade === 'A') gradeColor = 'text-green-400';
        else if (grade === 'B') gradeColor = 'text-green-200';
        else if (grade === 'C') gradeColor = 'text-yellow-500';

        document.getElementById('expl-confidence-dots').textContent = grade;
        document.getElementById('expl-confidence-dots').className = `text-2xl font-black ${gradeColor}`;

        document.getElementById('expl-confidence-score').textContent = `${hit.confidence || confidence.score}%`;
        const labelEl = document.getElementById('expl-confidence-label');
        labelEl.textContent = this._getConfidenceLabel(hit.confidence || confidence.score);

        // Dynamic Label Styling
        const scoreVal = hit.confidence || confidence.score;
        labelEl.className = 'text-[9px] font-bold px-1.5 py-0.5 rounded uppercase ' +
            (scoreVal >= 80 ? 'bg-green-600/20 text-green-400' :
                scoreVal >= 40 ? 'bg-yellow-600/20 text-yellow-500' :
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
