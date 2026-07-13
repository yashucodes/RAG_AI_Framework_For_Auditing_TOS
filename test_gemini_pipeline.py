# test_gemini_pipeline.py
#
# Purpose: Quick smoke test for the new Gemini-based classify_risk() and
# find_contradictions(). Confirms the API key/connection works AND that
# the LLM gets the obvious cases right, before testing on a full ToS.
#
# Run this from your project root: python test_gemini_pipeline.py

from app import classify_risk, find_contradictions

print("=== classify_risk() sanity check ===\n")

test_clauses = {
    "SHOULD flag": [
        "We collect your contacts and share them with advertising partners.",
        "Snaplink shall not be liable for unauthorized access arising from circumstances beyond our reasonable control.",
        "We may retain your data indefinitely for analytics purposes.",
        "We may terminate your account at any time without prior notice.",
    ],
    "should NOT flag (protective, same topics)": [
        "You retain ownership of content you upload.",
        "Disputes shall be resolved through arbitration under Indian law.",
        "When you close your account, your personal files and profile information are removed from our active systems within 45 days.",
        "We accept full responsibility for any unauthorized access resulting from our own security failures.",
        "We will provide at least 30 days' notice before terminating your account.",
    ],
}

for label, clauses in test_clauses.items():
    print(f"--- {label} ---")
    for clause in clauses:
        category, confidence, reason, excerpt = classify_risk(clause)
        flagged = "FLAGGED" if category != "compliant" else "compliant"
        print(f"  [{confidence:.2f}] {flagged:10s} ({category:20s}) {clause[:70]}...")
    print()

print("\n=== find_contradictions() sanity check ===\n")

clauses = [
    "1. COMMUNICATION PREFERENCES\nYou are in control of what you hear from us — you can turn off promotional messages whenever you like, and we'll stop sending them right away.",
    "2. SERVICE COMMUNICATIONS\nCertain partner offers and network updates are a built-in part of how the Service works, and continue to reach your device as part of your normal use of the Service, independent of your notification settings.",
    "3. DATA RETENTION\nWhen you close your account, your personal files and profile information are removed from our active systems within 45 days.",
    "4. CONTINUOUS IMPROVEMENT\nTo train and refine our recommendation systems, certain usage and account records may be kept on our servers for as long as we determine is useful for internal research, beyond the point of account closure.",
    "5. GOVERNING LAW\nThese Terms are governed by the laws of India, with disputes resolved through arbitration.",
]

pairs = find_contradictions(clauses)
print(f"{len(pairs)} contradiction(s) found (expecting 2: clause 1 vs 2, and clause 3 vs 4)\n")
for num_a, num_b, excerpt_a, excerpt_b, explanation in pairs:
    print(f"  Clauses #{num_a} vs #{num_b}:")
    print(f"  A: {excerpt_a[:70]}...")
    print(f"  B: {excerpt_b[:70]}...")
    print(f"  Why: {explanation}\n") 