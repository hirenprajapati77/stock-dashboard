from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FilterMeta:
    filterScore: int
    filterCategory: str
    priorityBoost: int
    volumeStrength: str
    momentumType: str
    topSector: bool
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "filterScore": self.filterScore,
            "filterCategory": self.filterCategory,
            "priorityBoost": self.priorityBoost,
            "volumeStrength": self.volumeStrength,
            "momentumType": self.momentumType,
            "topSector": self.topSector,
            "reasons": self.reasons,
        }


class SignalFilterService:
    """
    Analysis-driven post-scoring prioritization layer.
    Does NOT alter scoring formulas or signal generation logic.
    """

    _report_path = Path(__file__).resolve().parents[3] / "docs" / "sr_pro_conversion_analysis.md"

    @classmethod
    def annotate(cls, hit: dict[str, Any]) -> dict[str, Any]:
        return cls.annotate_many([hit])[0]

    @classmethod
    def annotate_many(cls, hits: list[dict[str, Any]], high_cap_ratio: float = 0.25) -> list[dict[str, Any]]:
        """
        Batch annotation with separation guardrails:
        - Conditional HIGH gating
        - Hard LOW forcing for bad-context triples
        - HIGH-cap inflation control (top ~20-25%)
        """
        enriched: list[dict[str, Any]] = []
        for hit in hits or []:
            data = dict(hit)
            meta = cls.compute_filter_meta(data)
            data["filterMeta"] = meta.to_dict()
            data["filterCategory"] = meta.filterCategory
            data["filterScore"] = meta.filterScore
            data["priorityBoost"] = meta.priorityBoost
            enriched.append(data)

        if not enriched:
            return enriched

        high_idxs = [i for i, r in enumerate(enriched) if r.get("filterCategory") == "HIGH PROBABILITY"]
        max_high = max(1, int(len(enriched) * high_cap_ratio))

        if len(high_idxs) > max_high:
            sorted_high = sorted(high_idxs, key=lambda i: int(enriched[i].get("filterScore") or 0), reverse=True)
            keep = set(sorted_high[:max_high])
            for i in high_idxs:
                if i in keep:
                    continue
                enriched[i]["filterCategory"] = "MEDIUM"
                meta = enriched[i].get("filterMeta") or {}
                reasons = list(meta.get("reasons") or [])
                reasons.append("High-cap control: downgraded to MEDIUM for selectivity")
                meta["filterCategory"] = "MEDIUM"
                meta["reasons"] = reasons[:7]
                enriched[i]["filterMeta"] = meta

        return enriched

    @classmethod
    def compute_filter_meta(cls, hit: dict[str, Any]) -> FilterMeta:
        reasons: list[str] = []
        boost = 0

        top_sectors = cls._top_sectors_from_report()
        sector = str(hit.get("sector") or "").upper()
        top_sector = sector in top_sectors

        # Priority 1) Sector state (highest weight)
        sector_state = (hit.get("sectorState") or "NEUTRAL").upper()
        if sector_state == "LEADING":
            boost += 5
            reasons.append("Sector impact: LEADING (+5)")
        elif sector_state == "IMPROVING":
            boost += 3
            reasons.append("Sector impact: IMPROVING (+3)")
        elif sector_state == "WEAKENING":
            boost -= 2
            reasons.append("Sector impact: WEAKENING (-2)")
        elif sector_state == "LAGGING":
            boost -= 5
            reasons.append("Sector impact: LAGGING (-5)")
        else:
            reasons.append(f"Sector impact: {sector_state} (+0)")

        if top_sector:
            boost += 1
            reasons.append(f"Sector preference: {sector} (+1)")

        # Priority 2) Momentum alignment
        momentum_type = cls._momentum_type(hit)
        if momentum_type == "3D":
            boost += 4
            reasons.append("Momentum impact: 3D alignment (+4)")
        elif momentum_type == "2D":
            boost += 3
            reasons.append("Momentum impact: 2D alignment (+3)")
        elif momentum_type == "1D":
            boost -= 3
            reasons.append("Momentum impact: 1D-only (-3)")
        else:
            boost -= 3
            reasons.append("Momentum impact: no alignment (-3)")

        # Priority 3) Volume strength
        volume_strength = cls._volume_strength(hit.get("volRatio"))
        if volume_strength == "STRONG":
            boost += 2
            reasons.append("Volume impact: STRONG (+2)")
        elif volume_strength == "MODERATE":
            boost += 0
            reasons.append("Volume impact: MODERATE (+0)")
        else:
            boost -= 2
            reasons.append("Volume impact: WEAK (-2)")

        # Priority 4) Entry stage (minor)
        entry_tag = (hit.get("entryTag") or "").upper()
        if entry_tag == "STRONG_ENTRY":
            boost += 1
            reasons.append("Entry stage: STRONG_ENTRY (+1)")
        elif entry_tag == "ENTRY_READY":
            boost += 1
            reasons.append("Entry stage: ENTRY_READY (+1)")

        # Weighted base score
        score = max(0, min(100, 50 + (boost * 5)))

        # Strong negative gate: force LOW on clearly weak setup
        force_low = sector_state == "LAGGING" and volume_strength == "WEAK" and momentum_type == "1D"
        force_low_lagging_1d = sector_state == "LAGGING" and momentum_type == "1D"
        if force_low:
            score = min(score, 35)
            reasons.append("Forced LOW: LAGGING + WEAK volume + 1D-only momentum")
        elif force_low_lagging_1d:
            score = min(score, 45)
            reasons.append("Forced LOW: LAGGING + 1D-only momentum")

        # Positive gate: HIGH requires strong context confirmation
        sector_good = sector_state in {"LEADING", "IMPROVING"}
        momentum_good = momentum_type in {"2D", "3D"}
        volume_good = volume_strength == "STRONG"
        volume_not_weak = volume_strength in {"MODERATE", "STRONG"}
        strong_conditions = sum([1 if sector_good else 0, 1 if momentum_good else 0, 1 if volume_good else 0])

        # Micro-tune: HIGH now requires sector strength + momentum strength + at least moderate volume
        high_gate = sector_good and momentum_good and volume_not_weak

        if force_low or force_low_lagging_1d:
            category = "LOW"
        elif score >= 84 and high_gate:
            category = "HIGH PROBABILITY"
        elif score >= 60:
            category = "MEDIUM"
        else:
            category = "LOW"

        if score >= 84 and not high_gate and category != "HIGH PROBABILITY":
            reasons.append("HIGH gate not met: needs sector strength + momentum/volume confirmation")

        return FilterMeta(
            filterScore=score,
            filterCategory=category,
            priorityBoost=boost,
            volumeStrength=volume_strength,
            momentumType=momentum_type,
            topSector=top_sector,
            reasons=reasons[:7],
        )

    @staticmethod
    def _volume_strength(vol_ratio: Any) -> str:
        try:
            v = float(vol_ratio)
        except Exception:
            return "WEAK"
        if v >= 2.0:
            return "STRONG"
        if v >= 1.2:
            return "MODERATE"
        return "WEAK"

    @staticmethod
    def _momentum_type(hit: dict[str, Any]) -> str:
        active = sum(1 for k in ("hits1d", "hits2d", "hits3d") if bool(hit.get(k)))
        return f"{active}D" if active > 0 else "0D"

    @classmethod
    def _top_sectors_from_report(cls) -> set[str]:
        """
        Pull top sectors by win rate from analysis report.
        Falls back safely if report is unavailable.
        """
        fallback = {"PHARMA", "ENERGY", "IT"}
        try:
            if not cls._report_path.exists():
                return fallback
            lines = cls._report_path.read_text(encoding="utf-8").splitlines()
            in_sector_table = False
            rows: list[tuple[str, float]] = []
            for line in lines:
                if line.strip().startswith("## Segment Analysis — Sector"):
                    in_sector_table = True
                    continue
                if in_sector_table and line.strip().startswith("## "):
                    break
                if not in_sector_table or not line.strip().startswith("|"):
                    continue
                parts = [p.strip() for p in line.strip().strip("|").split("|")]
                if len(parts) < 6 or parts[0] in {"Segment", "---"}:
                    continue
                sector_name = parts[0].upper()
                try:
                    win_rate = float(parts[5])
                except Exception:
                    continue
                rows.append((sector_name, win_rate))

            if not rows:
                return fallback

            rows.sort(key=lambda x: x[1], reverse=True)
            top = [name for name, _ in rows[:3]]
            return set(top) if top else fallback
        except Exception:
            return fallback
