"""CricAnalyze technique score engine (ca-score-v2). Deterministic: same inputs + version -> same score."""
import hashlib, json

SCORE_VERSION = "ca-score-v2"
SCORABLE = ("measured", "measured_estimated_phase")
EST_PHASE_FACTOR = 0.5
IN_RANGE_FLOOR = 80
GATE = {"min_metrics": 3, "min_coverage": 0.6, "min_detected_phases": 2, "min_components": 2}

# Per metric: target range [lo, hi] and tolerance beyond it. Weights are relative inside each analysis type.
RUBRICS = {
    "batting": {
        "components": [
            {"key": "balance", "name": "Balance", "metrics": {"setup_balance": 0.8}},
            {"key": "alignment", "name": "Head & body alignment", "metrics": {"head_over_front_foot": 1.0, "shoulder_alignment": 0.6}},
            {"key": "joint_angles", "name": "Front-leg joint angle", "metrics": {"front_knee_angle": 1.0}},
            {"key": "backlift", "name": "Backlift position", "metrics": {"hands_height_backlift": 0.8}},
        ],
        "ranges": {"front_knee_angle": ([140, 165], 30), "hands_height_backlift": ([0.0, 0.5], 0.6), "head_over_front_foot": ([0.0, 0.2], 0.5),
                   "setup_balance": ([0.0, 0.15], 0.4), "shoulder_alignment": ([0, 10], 20)},
    },
    "bowling": {
        "components": [
            {"key": "balance", "name": "Follow-through balance", "metrics": {"follow_through_balance": 0.8}},
            {"key": "alignment", "name": "Trunk alignment", "metrics": {"trunk_tilt": 0.8}},
            {"key": "joint_angles", "name": "Front knee & front arm angles", "metrics": {"front_knee_angle": 1.0, "front_arm_elbow": 0.6}},
            {"key": "release", "name": "Release position", "metrics": {"release_height": 0.8}},
        ],
        "ranges": {"front_knee_angle": ([160, 185], 35), "trunk_tilt": ([0, 20], 25), "front_arm_elbow": ([70, 130], 40),
                   "release_height": ([0.5, 1.4], 0.6), "follow_through_balance": ([0.0, 0.25], 0.5)},
    },
}
NOT_ASSESSED = [{"key": "consistency", "name": "Movement consistency", "reason": "Needs several repetitions of the same shot or delivery; one clip shows one repetition."}]

METHOD = {
    "version": SCORE_VERSION,
    "normalisation": f"Metric score: inside the target range [lo, hi], 100 at the range centre falling linearly to {IN_RANGE_FLOOR} at the range edges; "
                     f"outside it, {IN_RANGE_FLOOR} x max(0, 1 - distance/tolerance). Always clamped to 0-100.",
    "weighting": f"Each metric has a weight. Metrics on an estimated phase count at x{EST_PHASE_FACTOR} weight. Low-confidence and unmeasurable metrics are excluded "
                 "(never counted as 0 or 100) and reduce coverage instead.",
    "components": "Component score = weighted mean of its included metrics. Overall = weighted mean of all included metrics, i.e. the sum of component contributions.",
    "coverage": "Coverage = included effective weight / total rubric weight.",
    "gate": f"An overall score is shown only with >= {GATE['min_metrics']} included metrics, >= {int(GATE['min_coverage'] * 100)}% coverage, "
            f">= {GATE['min_detected_phases']} detected (not estimated) phases and >= {GATE['min_components']} scored components. Otherwise only component scores are shown.",
    "provisional": "When the gate is not met but at least one metric is included, a Provisional Technique Score is shown: the same weighted mean over only the "
                   "included metrics (weights re-normalised; missing or low-confidence metrics are left out, never counted as 0). Coverage and evidence level are shown "
                   "with it because it may change once a clearer clip measures the rest. With zero included metrics no score is shown. Fully assessed scores are unchanged.",
    "evidence_level": "High: coverage >= 80%, mean joint-detection confidence of scored metrics >= 0.7 and >= 3 clearly identified phases. Medium: coverage >= 50% and "
                      "confidence >= 0.55. Otherwise Limited. Describes how much the score can be trusted, not technique quality.",
    "status": "Configurable coaching heuristic from 2D pose measurements. Not a validated, official or universally comparable cricket rating, and it does not predict match performance.",
}


def rubric_hash(kind):
    return hashlib.sha256(json.dumps(RUBRICS[kind], sort_keys=True).encode()).hexdigest()[:12]


def metric_score(v, lo, hi, tol):
    if lo <= v <= hi:
        half = (hi - lo) / 2
        s = 100 - (100 - IN_RANGE_FLOOR) * (abs(v - (lo + hi) / 2) / half if half else 0)
    else:
        d = lo - v if v < lo else v - hi
        s = IN_RANGE_FLOOR * max(0.0, 1 - d / tol)
    return round(max(0.0, min(100.0, s)), 1)


def compute(kind, inputs, detected_phases):
    """inputs: list of {key, value, status, confidence}. Pure function of (inputs, detected_phases, SCORE_VERSION, RUBRICS)."""
    rb = RUBRICS[kind]
    by = {i["key"]: i for i in inputs}
    total_w = sum(w for c in rb["components"] for w in c["metrics"].values())
    comps, per_metric, all_w, all_acc, confs = [], [], 0.0, 0.0, []
    for c in rb["components"]:
        cw_total = sum(c["metrics"].values())
        cw, cacc, used, missing = 0.0, 0.0, [], []
        for k, w in c["metrics"].items():
            m = by.get(k)
            if not m or m.get("status") not in SCORABLE or m.get("value") is None:
                missing.append({"key": k, "status": (m or {}).get("status", "not_measurable")})
                continue
            (lo, hi), tol = rb["ranges"][k]
            s = metric_score(m["value"], lo, hi, tol)
            ew = w * (EST_PHASE_FACTOR if m["status"] == "measured_estimated_phase" else 1)
            cw, cacc = cw + ew, cacc + ew * s
            used.append(k)
            confs.append(m.get("confidence") or 0)
            per_metric.append({"key": k, "value": m["value"], "score": s, "weight": w, "effective_weight": ew, "target": [lo, hi], "tolerance": tol})
        comps.append({"key": c["key"], "name": c["name"], "score": round(cacc / cw, 1) if cw else None, "effective_weight": round(cw, 3),
                      "max_weight": cw_total, "coverage": round(cw / cw_total, 2), "metrics": used, "missing": missing, "_acc": cacc})
        all_w, all_acc = all_w + cw, all_acc + cacc
    coverage = all_w / total_w if total_w else 0
    scored = [c for c in comps if c["score"] is not None]
    ok = (len(per_metric) >= GATE["min_metrics"] and coverage >= GATE["min_coverage"] and detected_phases >= GATE["min_detected_phases"]
          and len(scored) >= GATE["min_components"])
    overall = round(all_acc / all_w) if ok and all_w else None
    for c in comps:
        c["contribution"] = round(c.pop("_acc") / all_w, 1) if all_w and c["score"] is not None else None
    mean_conf = sum(confs) / len(confs) if confs else 0
    level = "high" if coverage >= 0.8 and mean_conf >= 0.7 and detected_phases >= 3 else "medium" if coverage >= 0.5 and mean_conf >= 0.55 else "low"
    ranked = sorted(per_metric, key=lambda m: -m["score"])
    return {
        "value": overall, "version": SCORE_VERSION, "rubric_hash": rubric_hash(kind), "status": "complete" if ok else "provisional",
        "label": "Technique Score" if ok else "Provisional - not enough measurements for an overall score",
        "reason": None if ok else "Insufficient evidence to calculate a reliable overall score. Component results below use only the available measurements.",
        "components": comps, "not_assessed": NOT_ASSESSED, "metric_scores": per_metric,
        "coverage": round(coverage, 2), "detected_phases": detected_phases, "included": [m["key"] for m in per_metric],
        "evidence": {"level": level, "mean_keypoint_confidence": round(mean_conf, 2), "coverage": round(coverage, 2)},
        "strongest": [m["key"] for m in ranked[:2] if m["score"] >= IN_RANGE_FLOOR],
        "opportunities": [m["key"] for m in ranked[::-1][:2] if m["score"] < IN_RANGE_FLOOR + 10],
        "inputs": [{k: i.get(k) for k in ("key", "value", "status", "confidence")} for i in inputs],
        "requirements": f">={GATE['min_metrics']} included metrics, >={int(GATE['min_coverage'] * 100)}% weight coverage, >={GATE['min_detected_phases']} detected phases, >={GATE['min_components']} components",
        "method": METHOD,
        "provisional_value": None if ok else (round(all_acc / all_w) if all_w else None),
    }


EVIDENCE_LABEL = {"high": "High", "medium": "Medium", "low": "Limited"}


def display(sc):
    """Customer-facing score from a saved score record (works for stored v2 records). Never invents a value."""
    sc = sc or {}
    if not sc.get("components"):
        v = sc.get("value")
        return {"value": v, "status": "complete" if v is not None else "unavailable", "included": None, "total": None, "coverage": None, "evidence": None}
    total = sum(len(c.get("metrics") or []) + len(c.get("missing") or []) for c in sc["components"])
    ms = [m for m in sc.get("metric_scores") or [] if m.get("score") is not None and m.get("effective_weight")]
    if sc.get("value") is not None:
        v, st = sc["value"], "complete"
    elif sc.get("provisional_value") is not None:
        v, st = sc["provisional_value"], "provisional"
    elif ms:
        v, st = round(sum(m["score"] * m["effective_weight"] for m in ms) / sum(m["effective_weight"] for m in ms)), "provisional"
    else:
        v, st = None, "unavailable"
    n = len(sc.get("included") or ms)
    ev = EVIDENCE_LABEL.get((sc.get("evidence") or {}).get("level")) if st != "unavailable" else None
    return {"value": v, "status": st, "included": n, "total": total, "coverage": sc.get("coverage"), "detected_phases": sc.get("detected_phases"), "evidence": ev}


def recompute(kind, saved):
    """Re-run from a saved score record (reproducibility check)."""
    return compute(kind, saved["inputs"], saved["detected_phases"])
