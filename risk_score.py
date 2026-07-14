"""
risk_score.py

Calculates:
1. AI Risk Score (0–10)
2. Overall Risk
3. User Suggestion
"""


def calculate_risk(summary_text):

    summary = summary_text.lower()

    score = 0

    # High Risk Indicators
    high = [
        "illegal",
        "violation",
        "breach",
        "non compliant",
        "non-compliant",
        "share your data",
        "third party",
        "without consent",
        "not responsible",
        "unfair",
        "predatory"
    ]

    # Medium Risk Indicators
    medium = [
        "terminate",
        "modify",
        "update",
        "suspend",
        "collect",
        "tracking",
        "cookies",
        "discretion",
        "retain"
    ]

    # Positive Indicators
    safe = [
        "privacy",
        "encrypted",
        "transparent",
        "security",
        "consent",
        "user rights",
        "refund"
    ]

    # Risk Score
    for word in high:
        if word in summary:
            score += 2

    for word in medium:
        if word in summary:
            score += 1

    for word in safe:
        if word in summary:
            score -= 0.5

    # Keep score between 0 and 10
    score = max(0, min(round(score, 1), 10))

    # Overall Risk
    if score >= 7:
        overall_risk = "high"

    elif score >= 4:
        overall_risk = "medium"

    else:
        overall_risk = "low"

    # Suggestion
    if overall_risk == "high":
        suggestion = "This agreement contains significant risks. Read it carefully before accepting."

    elif overall_risk == "medium":
        suggestion = "Some clauses require attention. Review the highlighted sections before accepting."

    else:
        suggestion = "This agreement appears generally safe, but reviewing the important clauses is recommended."

    return score, overall_risk, suggestion