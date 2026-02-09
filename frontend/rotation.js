/**
 * Antigravity Sector Rotation Physics Engine
 * Handles rendering, physics forces, and interactivity for RS/RM quadrants.
 */

class RotationDashboard {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.particles = [];
        this.width = 0;
        this.height = 0;
        this.centerX = 0;
        this.centerY = 0;
        this.zoom = 1.0;
        this.panX = 0;
        this.panY = 0;
        this.isDragging = false;
        this.lastMouseX = 0;
        this.lastMouseY = 0;

        // Physics Params
        this.friction = 0.98; // (1 - 0.02)
        this.rotationStrength = 0.0005; // Gentle rotational force
        this.attractionStrength = 0.08;
        this.repulsionStrength = 0.8;
        this.repulsionDistance = 60;

        // Data State
        this.allData = null;
        this.playbackIndex = 29; // Latest day
        this.hoveredParticle = null;
        this.tooltip = document.getElementById('rotation-tooltip');
        this.alertEl = document.getElementById('hud-alert');
        this.alertList = document.getElementById('alert-list');
        this.aiPanel = document.getElementById('ai-detail-panel');
        this.processedAlerts = new Set();

        this.init();
    }

    init() {
        this.resize();
        window.addEventListener('resize', () => this.resize());
        this.setupInteractions();
        this.animate();
    }

    resize() {
        const container = this.canvas.parentElement;
        this.width = container.clientWidth;
        this.height = container.clientHeight;
        this.canvas.width = this.width;
        this.canvas.height = this.height;
        this.centerX = this.width / 2;
        this.centerY = this.height / 2;
    }

    setupInteractions() {
        this.canvas.addEventListener('mousedown', (e) => {
            this.isDragging = true;
            this.lastMouseX = e.clientX;
            this.lastMouseY = e.clientY;
            this.canvas.style.cursor = 'grabbing';
        });

        window.addEventListener('mousemove', (e) => {
            if (this.isDragging) {
                this.panX += (e.clientX - this.lastMouseX);
                this.panY += (e.clientY - this.lastMouseY);
                this.lastMouseX = e.clientX;
                this.lastMouseY = e.clientY;
            }
        });

        window.addEventListener('mouseup', () => {
            if (this.isDragging) {
                this.isDragging = false;
                this.canvas.style.cursor = 'grab';
            }
        });

        this.canvas.addEventListener('mousemove', (e) => {
            if (this.isDragging) return;
            this.handleHover(e);
        });

        this.canvas.addEventListener('click', (e) => {
            this.handleClick(e);
        });

        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const delta = e.deltaY > 0 ? 0.9 : 1.1;
            this.zoom *= delta;
            this.zoom = Math.max(0.2, Math.min(5, this.zoom));
            this.updateTooltip();
        }, { passive: false });
    }

    handleHover(e) {
        const rect = this.canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        // Convert mouse to world coords
        const worldX = (mx - this.centerX - this.panX) / this.zoom;
        const worldY = (my - this.centerY - this.panY) / this.zoom;

        let found = null;
        for (const p of this.particles) {
            const dx = p.x - worldX;
            const dy = p.y - worldY;
            if (Math.sqrt(dx * dx + dy * dy) < p.radius) {
                found = p;
                break;
            }
        }

        if (found !== this.hoveredParticle) {
            this.hoveredParticle = found;
            if (found) {
                this.showTooltip(e, found);
                this.canvas.style.cursor = 'pointer';
            } else {
                this.hideTooltip();
                this.canvas.style.cursor = 'grab';
            }
        } else if (found) {
            this.moveTooltip(e);
        }
    }

    showTooltip(e, p) {
        if (!this.tooltip) return;
        const trend = this.getTrendDescription(p.rs, p.rm);
        const commentary = p.commentary ? `<div class="mt-2 pt-2 border-t border-gray-800 text-[10px] text-gray-400 italic">${p.commentary.slice(0, 100)}...</div>` : '';
        this.tooltip.style.display = 'block';
        this.tooltip.innerHTML = `
            <div class="font-bold text-white mb-1">${p.name.replace("NIFTY_", "Nifty ")}</div>
            <div class="flex justify-between gap-4">
                <span class="text-gray-400">Strength (RS)</span>
                <span class="mono font-bold">${p.rs.toFixed(4)}</span>
            </div>
            <div class="flex justify-between gap-4">
                <span class="text-gray-400">Momentum (RM)</span>
                <span class="mono font-bold" style="color: ${p.rm >= 0 ? '#00C853' : '#D50000'}">${p.rm.toFixed(6)}</span>
            </div>
            <div class="mt-2 text-[9px] font-bold uppercase tracking-widest px-2 py-0.5 rounded bg-gray-800 text-center" style="color: ${p.color}">
                ${trend}
            </div>
            ${commentary}
            <div class="mt-1 text-[8px] text-gray-600 text-center">Click for Deep Dive</div>
        `;
        this.moveTooltip(e);
    }

    moveTooltip(e) {
        if (!this.tooltip) return;
        this.tooltip.style.left = (e.clientX + 15) + 'px';
        this.tooltip.style.top = (e.clientY + 15) + 'px';
    }

    hideTooltip() {
        if (this.tooltip) this.tooltip.style.display = 'none';
    }

    updateTooltip() {
        if (this.tooltip && this.tooltip.style.display === 'block' && this.hoveredParticle) {
            // Content stays same, but maybe something changes? 
            // Actually tooltip is fixed position based on screen mouse, so zoom doesn't move it.
            // But if we wanted to show specific zoomed stats, we could.
        }
    }

    getTrendDescription(rs, rm) {
        if (rs >= 1.0 && rm >= 0) return "Leading / Accelerating";
        if (rs >= 1.0 && rm < 0) return "Weakening / Distributing";
        if (rs < 1.0 && rm < 0) return "Lagging / Selling Off";
        return "Improving / Rebounding";
    }

    handleClick(e) {
        if (this.hoveredParticle) {
            const p = this.hoveredParticle;

            // Show AI Panel
            if (this.aiPanel) {
                this.aiPanel.classList.remove('hidden');
                document.getElementById('ai-detail-title').textContent = p.name.replace("NIFTY_", "Nifty ") + " Analysis";
                document.getElementById('ai-detail-rank').textContent = `#${p.rank || '?'} Overall Strength`;
                document.getElementById('ai-detail-text').textContent = p.commentary || "No analysis available for this state.";
            }

            // Dril down button added inside panel dynamically if needed, 
            // but for now let's also keep the direct drill down after a small delay or just allow it.
            // Actually, let's add a "View Detailed Chart" button to the panel instead of auto-drilling.
            const panel = document.getElementById('ai-detail-panel');
            let btn = panel.querySelector('#drill-btn');
            if (!btn) {
                btn = document.createElement('button');
                btn.id = 'drill-btn';
                btn.className = "mt-4 w-full py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-[10px] font-bold uppercase transition-colors";
                btn.textContent = "View Detailed Chart";
                panel.querySelector('.p-4').appendChild(btn);
            }
            btn.onclick = () => {
                const symbol = this.getSectorSymbol(p.name);
                const stdToggle = document.getElementById('rotation-toggle');
                if (stdToggle) {
                    stdToggle.checked = false;
                    stdToggle.dispatchEvent(new Event('change'));
                }
                const input = document.getElementById('symbol-input');
                if (input) {
                    input.value = symbol;
                    if (typeof fetchData === 'function') fetchData();
                }
            };
        }
    }

    getSectorSymbol(name) {
        const symbols = {
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
        return symbols[name] || name;
    }

    setData(data, alerts = []) {
        this.allData = data;
        if (this.particles.length === 0) {
            this.createParticles();
        } else {
            this.updateTargets();
        }

        if (alerts && alerts.length > 0) {
            this.handleAlerts(alerts);
        }
    }

    handleAlerts(alerts) {
        alerts.forEach(alert => {
            const alertKey = `${alert.symbol}-${alert.timestamp}`;
            if (this.processedAlerts.has(alertKey)) return;

            this.processedAlerts.add(alertKey);

            const isRecent = (Date.now() / 1000) - alert.timestamp < 60; // 60 seconds

            // 1. Visual Reaction (Only Recent)
            if (isRecent) {
                const particle = this.particles.find(p => p.name === alert.symbol);
                if (particle) {
                    this.triggerVisualAlert(particle, alert);
                }

                // 2. HUD Alert
                this.showHUD(`${alert.symbol.replace("NIFTY_", "")}: ${alert.type.replace("_", " ")}`);
            }

            // 3. Log Update (Filter: Last 7 days only)
            const daysOld = (Date.now() / 1000 - alert.timestamp) / (24 * 60 * 60);
            if (daysOld <= 7) {
                this.addToAlertLog(alert);
            }
        });

        // Cleanup old alerts from set
        if (this.processedAlerts.size > 100) {
            const arr = Array.from(this.processedAlerts);
            this.processedAlerts = new Set(arr.slice(-50));
        }
    }

    triggerVisualAlert(p, alert) {
        // Pulse effect
        p.visualPulse = 1.0;
        p.visualFlash = 1.0;

        // Physics Kick for High Priority
        if (alert.priority === "HIGH") {
            const force = 15;
            p.vx += (Math.random() - 0.5) * force;
            p.vy += (Math.random() - 0.5) * force;
        }
    }

    addToAlertLog(alert) {
        if (!this.alertList) return;

        // Remove placeholder
        if (this.alertList.innerHTML.includes('Waiting for transitions...')) {
            this.alertList.innerHTML = '';
        }

        const alertDate = new Date(alert.timestamp * 1000);
        const today = new Date();
        const isToday = alertDate.getDate() === today.getDate() &&
            alertDate.getMonth() === today.getMonth() &&
            alertDate.getFullYear() === today.getFullYear();

        const timeDisplay = isToday
            ? alertDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : alertDate.toLocaleDateString([], { month: 'short', day: 'numeric' });

        const div = document.createElement('div');
        const color = this.getQuadrantColor(alert.rs, alert.rm);
        const priorityColor = alert.priority === "HIGH" ? "border-indigo-500 bg-indigo-500/10" : "border-gray-800 bg-gray-900/40";

        div.className = `p-2 rounded-xl border ${priorityColor} animate-in slide-in-from-right duration-300`;
        div.innerHTML = `
            <div class="flex justify-between items-start mb-1">
                <span class="font-bold text-[10px] text-white">${alert.symbol.replace("NIFTY_", "")}</span>
                <span class="text-[8px] text-gray-500 font-mono">${timeDisplay}</span>
            </div>
            <div class="flex items-center gap-2">
                <div class="w-1.5 h-1.5 rounded-full" style="background: ${color}"></div>
                <span class="text-[9px] font-bold uppercase tracking-tighter" style="color: ${color}">${alert.type.replace("_", " ")}</span>
            </div>
        `;

        this.alertList.prepend(div);

        // Limit log entries
        if (this.alertList.children.length > 20) {
            this.alertList.lastElementChild.remove();
        }
    }

    createParticles() {
        const sectors = Object.keys(this.allData);
        sectors.forEach(name => {
            const data = this.allData[name];
            const weight = data.weight || 0.05;

            const metrics = data.metrics || {};
            const state = metrics.state || "NEUTRAL";

            // Random initial pos near center
            const p = {
                name: name,
                x: (Math.random() - 0.5) * 100,
                y: (Math.random() - 0.5) * 100,
                vx: 0,
                vy: 0,
                radius: 12 + weight * 50,
                mass: 1 + weight * 2,
                targetX: 0,
                targetY: 0,
                color: this.getQuadrantColor(data.current.rs, data.current.rm, state),
                rs: data.current.rs,
                rm: data.current.rm,
                shiningState: state,
                relVolume: metrics.relVolume || 1.0,
                breadth: metrics.breadth || 50,
                trail: [],
                quadrant: "",
                visualPulse: 0,
                visualFlash: 0
            };
            this.particles.push(p);
        });
        this.updateTargets();
    }

    updateTargets() {
        this.particles.forEach(p => {
            const sectorData = this.allData[p.name];
            const hist = sectorData.history[this.playbackIndex];

            p.rs = hist.rs;
            p.rm = hist.rm;
            p.commentary = sectorData.commentary;
            p.rank = sectorData.rank;

            // Map RS (0.8 - 1.2) -> (-500, 500)
            p.targetX = (hist.rs - 1.0) * 2500;
            p.targetY = -(hist.rm * 10000);

            const newQuad = this.getQuadrantName(p.rs, p.rm);
            if (p.quadrant && p.quadrant !== newQuad) {
                this.showHUD(`${p.name.replace("NIFTY_", "")}: ${p.quadrant} → ${newQuad}`);
            }
            p.quadrant = newQuad;
            p.color = this.getQuadrantColor(p.rs, p.rm);

            // Calculate Trail (last 5 days from playback)
            p.trail = [];
            const trailDays = 5;
            for (let i = Math.max(0, this.playbackIndex - trailDays); i < this.playbackIndex; i++) {
                const step = sectorData.history[i];
                p.trail.push({
                    x: (step.rs - 1.0) * 2500,
                    y: -(step.rm * 10000)
                });
            }

            document.getElementById('playback-date').textContent = hist.date === this.getTodayStr() ? "Today" : hist.date;
        });
    }

    getQuadrantName(rs, rm) {
        if (rs >= 1.0 && rm >= 0) return "Leading";
        if (rs >= 1.0 && rm < 0) return "Weakening";
        if (rs < 1.0 && rm < 0) return "Lagging";
        return "Improving";
    }

    showHUD(text) {
        if (!this.alertEl) return;
        this.alertEl.textContent = text;
        this.alertEl.style.display = 'block';
        // Auto-hide via CSS animation logic or manual
        setTimeout(() => {
            if (this.alertEl.textContent === text) this.alertEl.style.display = 'none';
        }, 3000);
    }

    getTodayStr() {
        return new Date().toISOString().split('T')[0];
    }

    getQuadrantColor(rs, rm, state = null) {
        if (state === "SHINING") return "#00E676"; // Neon Green for Shining
        if (state === "WEAK") return "#424242";    // Dim Grey for Weak
        if (state === "NEUTRAL") return "#757575"; // Grey for Neutral

        // Fallback to standard quadrant colors if no state provided
        if (rs >= 1.0 && rm >= 0) return "#00C853"; // Leading
        if (rs >= 1.0 && rm < 0) return "#FFD600";  // Weakening
        if (rs < 1.0 && rm < 0) return "#D50000";   // Lagging
        return "#2979FF";                           // Improving
    }

    animate() {
        this.updatePhysics();
        this.draw();
        requestAnimationFrame(() => this.animate());
    }

    updatePhysics() {
        // Apply Forces
        for (let i = 0; i < this.particles.length; i++) {
            const p = this.particles[i];

            // 1. Attraction to target
            const dx = p.targetX - p.x;
            const dy = p.targetY - p.y;
            p.vx += dx * this.attractionStrength * 0.1;
            p.vy += dy * this.attractionStrength * 0.1;

            // 2. Rotational Force (Clockwise)
            // Vector perpendicular to radius from center (0,0)
            const rx = p.x;
            const ry = p.y;
            const dist = Math.sqrt(rx * rx + ry * ry) || 1;
            // Perpendicular vector is (ry, -rx)
            p.vx += (ry / dist) * this.rotationStrength * 50;
            p.vy += (-rx / dist) * this.rotationStrength * 50;

            // 3. Repulsion between particles
            for (let j = i + 1; j < this.particles.length; j++) {
                const p2 = this.particles[j];
                const rdx = p2.x - p.x;
                const rdy = p2.y - p.y;
                const rDist = Math.sqrt(rdx * rdx + rdy * rdy) || 1;

                if (rDist < this.repulsionDistance) {
                    const force = (this.repulsionDistance - rDist) * this.repulsionStrength * 0.05;
                    const fx = (rdx / rDist) * force;
                    const fy = (rdy / rDist) * force;
                    p.vx -= fx / p.mass;
                    p.vy -= fy / p.mass;
                    p2.vx += fx / p2.mass;
                    p2.vy += fy / p2.mass;
                }
            }

            // Apply Velocity & Friction
            p.x += p.vx;
            p.y += p.vy;
            p.vx *= this.friction;
            p.vy *= this.friction;

            // Decaying visual effects
            if (p.visualPulse > 0) p.visualPulse *= 0.92;
            if (p.visualFlash > 0) p.visualFlash *= 0.9;
        }
    }

    draw() {
        this.ctx.clearRect(0, 0, this.width, this.height);

        this.ctx.save();
        this.ctx.translate(this.centerX + this.panX, this.centerY + this.panY);
        this.ctx.scale(this.zoom, this.zoom);

        // Draw Grid Cross
        this.ctx.beginPath();
        this.ctx.strokeStyle = '#1E2630';
        this.ctx.lineWidth = 1;
        this.ctx.moveTo(-2000, 0);
        this.ctx.lineTo(2000, 0);
        this.ctx.moveTo(0, -2000);
        this.ctx.lineTo(0, 2000);
        this.ctx.stroke();

        // 0.5 & 1.0 Reference Circles
        this.ctx.beginPath();
        this.ctx.strokeStyle = '#1E2630';
        this.ctx.setLineDash([5, 5]);
        this.ctx.arc(0, 0, 100, 0, Math.PI * 2);
        this.ctx.stroke();
        this.ctx.setLineDash([]);

        // Determine top 3 RS for glowing
        const top3 = [...this.particles].sort((a, b) => b.rs - a.rs).slice(0, 3);

        // Draw Particles
        this.particles.forEach(p => {
            // Draw Trail
            if (p.trail.length > 1) {
                this.ctx.beginPath();
                this.ctx.strokeStyle = p.color + "33";
                this.ctx.lineWidth = 2;
                this.ctx.moveTo(p.trail[0].x, p.trail[0].y);
                for (let i = 1; i < p.trail.length; i++) {
                    this.ctx.lineTo(p.trail[i].x, p.trail[i].y);
                }
                this.ctx.lineTo(p.x, p.y);
                this.ctx.stroke();
            }

            const isTop = top3.includes(p);
            const isShining = p.shiningState === "SHINING";

            // Pulse Scale (Stronger for Shining)
            const pulseBase = isShining ? 0.8 : 0.5;
            const scale = 1.0 + (p.visualPulse || 0) * pulseBase;

            // Continuous Pulse for Shining
            let shineScale = 1.0;
            if (isShining) {
                shineScale = 1.0 + Math.sin(Date.now() / 200) * 0.1;
            }

            // Glow
            this.ctx.beginPath();
            const glowRadius = (isTop || isShining ? p.radius * 4 : p.radius * 2) * scale * shineScale;
            const gradient = this.ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, glowRadius);

            // Neon glow for shining, regular for others
            const glowColor = isShining ? "#00E676" : p.color;
            const glowOpacity = isShining ? "44" : (isTop ? "66" : "44");

            gradient.addColorStop(0, glowColor + glowOpacity);
            gradient.addColorStop(1, glowColor + "00");
            this.ctx.fillStyle = gradient;
            this.ctx.arc(p.x, p.y, glowRadius, 0, Math.PI * 2);
            this.ctx.fill();

            // Core
            this.ctx.beginPath();
            this.ctx.fillStyle = p.color;
            if (isTop || isShining) {
                this.ctx.shadowBlur = (isShining ? 30 : 20) * scale;
                this.ctx.shadowColor = isShining ? "#00E676" : p.color;
            } else {
                this.ctx.shadowBlur = 10 * scale;
                this.ctx.shadowColor = p.color;
            }
            this.ctx.arc(p.x, p.y, p.radius * scale, 0, Math.PI * 2);
            this.ctx.fill();
            this.ctx.shadowBlur = 0;

            // Flash overlay
            if (p.visualFlash > 0.05) {
                this.ctx.beginPath();
                this.ctx.fillStyle = `rgba(255, 255, 255, ${p.visualFlash * 0.5})`;
                this.ctx.arc(p.x, p.y, p.radius * scale, 0, Math.PI * 2);
                this.ctx.fill();
            }

            // Hover indicator
            if (this.hoveredParticle === p) {
                this.ctx.beginPath();
                this.ctx.strokeStyle = "white";
                this.ctx.lineWidth = 2;
                this.ctx.arc(p.x, p.y, p.radius + 4, 0, Math.PI * 2);
                this.ctx.stroke();

                // Show floating stats near particle
                this.ctx.fillStyle = "white";
                this.ctx.font = "10px monospace";
                this.ctx.textAlign = "left";
                this.ctx.fillText(`Vol: ${p.relVolume}x`, p.x + p.radius + 8, p.y);
                this.ctx.fillText(`Br: ${p.breadth}%`, p.x + p.radius + 8, p.y + 12);
            }

            // Label
            this.ctx.fillStyle = isShining ? "#00E676" : "white";
            this.ctx.font = `bold ${Math.max(8, 10 / this.zoom)}px Inter, sans-serif`;
            this.ctx.textAlign = "center";
            this.ctx.fillText(p.name.replace("NIFTY_", ""), p.x, p.y + p.radius + 15);

            // Stats
            this.ctx.fillStyle = "#888";
            this.ctx.font = `${8 / this.zoom}px monospace`;
            this.ctx.fillText(`${p.rs.toFixed(2)}`, p.x, p.y + p.radius + 28);
        });

        this.ctx.restore();
    }
}

// Global instance (Declared in script.js)
// let rotationApp; 

function initRotation() {
    if (typeof RotationDashboard !== 'undefined') {
        rotationApp = new RotationDashboard('rotation-canvas');
    }
}

function zoomReset() {
    if (rotationApp) {
        rotationApp.zoom = 1.0;
        rotationApp.panX = 0;
        rotationApp.panY = 0;
    }
}

// Playback handling
document.getElementById('playback-slider')?.addEventListener('input', (e) => {
    if (rotationApp) {
        rotationApp.playbackIndex = parseInt(e.target.value);
        rotationApp.updateTargets();
    }
});
