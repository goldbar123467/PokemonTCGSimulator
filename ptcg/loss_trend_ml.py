from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score
from sklearn.model_selection import train_test_split


def _safe(value: Any) -> str:
    text = str(value or "unknown").strip().lower()
    return text.replace(" ", "_")[:120] or "unknown"


def build_feature_row(row: dict[str, Any], *, include_flaw_features: bool = True) -> dict[str, float | int]:
    features: dict[str, float | int] = {
        f"agent_family={_safe(row.get('agent_family'))}": 1,
        f"matchup={_safe(row.get('matchup_tag'))}": 1,
        f"actor_archetype={_safe(row.get('actor_archetype'))}": 1,
        f"opponent_archetype={_safe(row.get('opponent_archetype'))}": 1,
        f"decision_window={_safe(row.get('decision_window'))}": 1,
        f"teacher_window={_safe(row.get('teacher_decision_window'))}": 1,
    }
    if row.get("teacher_agrees") is False:
        features["teacher_disagrees"] = 1
    if row.get("teacher_agrees") is True:
        features["teacher_agrees"] = 1
    try:
        delta = float(row.get("teacher_score", 0.0) or 0.0) - float(row.get("selected_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        delta = 0.0
    if delta > 0:
        features["teacher_score_delta_positive"] = 1
        features["teacher_score_delta"] = min(delta, 10.0)
    try:
        option_count = int(row.get("option_count", len(row.get("legal_actions") or [])) or 0)
    except (TypeError, ValueError):
        option_count = 0
    features[f"option_bucket={min(option_count // 5, 8) * 5}"] = 1
    for label in row.get("selected_penalties") or []:
        features[f"selected_penalty={_safe(label)}"] = 1
    if include_flaw_features:
        for label in row.get("flaw_tags") or []:
            features[f"flaw={_safe(label)}"] = 1
    for label in row.get("pipeline_labels") or []:
        features[f"pipeline={_safe(label)}"] = 1
    return features


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _signal_rows(feature_names: list[str], coefficients: list[float], *, reverse: bool) -> list[dict[str, Any]]:
    pairs = sorted(zip(feature_names, coefficients), key=lambda item: item[1], reverse=reverse)
    return [
        {"feature": feature, "coefficient": coefficient}
        for feature, coefficient in pairs[:25]
        if (coefficient > 0 if reverse else coefficient < 0)
    ]


def write_loss_trend_report(*, input_path: Path, output_dir: Path, seed: int = 17) -> dict[str, Any]:
    rows = _read_jsonl(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    y = [1 if row.get("outcome") == "loss" else 0 for row in rows]
    class_counts = {"loss": sum(y), "not_loss": len(y) - sum(y)}
    report: dict[str, Any] = {
        "input_path": str(input_path),
        "rows": len(rows),
        "loss_rows": class_counts["loss"],
        "not_loss_rows": class_counts["not_loss"],
        "seed": seed,
        "model": "sklearn.LogisticRegression categorical DictVectorizer",
        "feature_note": "Predictive model excludes outcome-derived flaw_tags; flaw counts are reported separately in loss_trends.json.",
        "top_loss_signals": [],
        "top_win_signals": [],
        "kaggle_submission_made": False,
    }
    if len(set(y)) < 2:
        report["skipped_reason"] = "need both loss and non-loss rows"
    else:
        features = [build_feature_row(row, include_flaw_features=False) for row in rows]
        vectorizer = DictVectorizer(sparse=True)
        x = vectorizer.fit_transform(features)
        stratify = y if min(class_counts.values()) >= 2 else None
        x_train, x_test, y_train, y_test = train_test_split(
            x,
            y,
            test_size=0.25,
            random_state=seed,
            stratify=stratify,
        )
        model = LogisticRegression(max_iter=1000, class_weight="balanced", solver="liblinear", random_state=seed)
        model.fit(x_train, y_train)
        predicted = model.predict(x_test)
        names = list(vectorizer.get_feature_names_out())
        coefs = [float(value) for value in model.coef_[0]]
        report.update(
            {
                "accuracy": float(accuracy_score(y_test, predicted)),
                "balanced_accuracy": float(balanced_accuracy_score(y_test, predicted)),
                "feature_count": len(names),
                "top_loss_signals": _signal_rows(names, coefs, reverse=True),
                "top_win_signals": _signal_rows(names, coefs, reverse=False),
            }
        )

    json_path = output_dir / "loss_trend_model_report.json"
    markdown_path = output_dir / "loss_trend_model_report.md"
    report["paths"] = {"json_report": str(json_path), "markdown_report": str(markdown_path)}
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Loss Trend ML Report",
        "",
        f"- Rows: {report['rows']}",
        f"- Loss rows: {report['loss_rows']}",
        f"- Balanced accuracy: {report.get('balanced_accuracy', 'skipped')}",
        "- Kaggle submission made: no",
        "",
        "## Top Loss Signals",
        "",
    ]
    for item in report.get("top_loss_signals", [])[:15]:
        lines.append(f"- {item['feature']}: {item['coefficient']:.4f}")
    lines.extend(["", "## Top Win Signals", ""])
    for item in report.get("top_win_signals", [])[:15]:
        lines.append(f"- {item['feature']}: {item['coefficient']:.4f}")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
