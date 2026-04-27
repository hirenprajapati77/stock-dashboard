from typing import Tuple

class MetaScoreEngine:
    """
    Final decision layer: Combines all intelligence signals into a single meta score.
    Outputs a Trade Grade (A+, A, B, C) and final decision (EXECUTE, WATCH, REJECT).
    """

    @staticmethod
    def compute(
        confluence_score: float,          # 0–100
        regime_confidence: float,         # 0–100
        micro_conf_adj: float,            # +/- delta
        liquidity_strength: str,          # HIGH, MEDIUM, LOW
        perf_win_rate: float,             # 0–100
        risk_level: str,                  # NORMAL, HIGH, CRITICAL
        drawdown_status: str,             # SAFE, WARNING, STOP
        time_adj: float                   # +/- delta
    ) -> Tuple[float, str, str]:
        """
        Returns: (meta_score, trade_grade, final_decision)
        """
        score = 0.0

        # 1. Confluence (30% weight)
        score += (confluence_score / 100) * 30

        # 2. Regime confidence (20% weight)
        score += (regime_confidence / 100) * 20

        # 3. Microstructure adjustment (15% weight normalised)
        micro_norm = max(0, min(15, (micro_conf_adj + 15) / 2))
        score += micro_norm

        # 4. Liquidity alignment (10% weight)
        liq_map = {"HIGH": 10, "MEDIUM": 6, "LOW": 2}
        score += liq_map.get(liquidity_strength, 0)

        # 5. Historical performance (15% weight)
        score += (perf_win_rate / 100) * 15

        # 6. Penalties
        if risk_level == "HIGH":    score -= 10
        if risk_level == "CRITICAL": score -= 25
        if drawdown_status == "WARNING": score -= 10
        if drawdown_status == "STOP":    score -= 40

        # 7. Session timing (10% weight)
        score += max(-5, min(5, time_adj))

        final_score = max(0, min(100, score))

        # Grade mapping
        if final_score >= 88:   grade, decision = "A+", "EXECUTE"
        elif final_score >= 75: grade, decision = "A",  "EXECUTE"
        elif final_score >= 60: grade, decision = "B",  "WATCH"
        elif final_score >= 45: grade, decision = "C",  "WATCH"
        else:                   grade, decision = "D",  "REJECT"

        return round(final_score, 1), grade, decision
