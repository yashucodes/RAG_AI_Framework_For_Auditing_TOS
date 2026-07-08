# calibrate_thresholds.py
#
# Purpose: Run a batch of KNOWN-good and KNOWN-bad test clauses through the
# retrieval pipeline and PRINT the raw scores, so you can pick sensible
# threshold numbers instead of guessing.
#
# Run this from your project root: python calibrate_thresholds.py

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from sentence_transformers import CrossEncoder

# --- Load models once ---
print("Loading embedding model...")
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

print("Loading FAISS database...")
vector_db = FAISS.load_local("./faiss_db", embeddings, allow_dangerous_deserialization=True)

print("Loading cross-encoder reranker...")
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

# --- Test inputs ---
# RELEVANT: real Terms-of-Service-style clauses that SHOULD match a law
relevant_examples = [
    "The company shall not be liable for any indirect or consequential damages arising from use of this product.",
    "Users must be at least 18 years old to create an account and use this service.",
    "We reserve the right to collect and share your personal data with third-party partners.",
    "Any disputes arising from this agreement shall be settled through arbitration in Mumbai.",
    "The seller is not responsible for defects caused by improper use of the product by the buyer.",
]

# IRRELEVANT: everyday statements that should NOT match any law
irrelevant_examples = [
    "I am bad at cooking.",
    "My favorite color is blue.",
    "The weather today is quite sunny.",
    "I went for a walk in the park yesterday.",
    "Cats are cuter than dogs.",
]

def run_batch(label, examples):
    print(f"\n{'='*70}\n{label}\n{'='*70}")
    for text in examples:
        print(f"\nINPUT: \"{text}\"")

        # Stage 1: FAISS distance
        candidates = vector_db.similarity_search_with_score(text, k=3)
        for doc, distance in candidates:
            snippet = doc.page_content[:80].replace("\n", " ")
            print(f"  [FAISS distance = {distance:.3f}]  {snippet}...")

        # Stage 2: Cross-encoder score (on the same top-3, just for comparison)
        if candidates:
            pairs = [(text, doc.page_content) for doc, _ in candidates]
            ce_scores = reranker.predict(pairs)
            for (doc, _), ce_score in zip(candidates, ce_scores):
                snippet = doc.page_content[:80].replace("\n", " ")
                print(f"  [Cross-encoder score = {ce_score:.3f}]  {snippet}...")

if __name__ == "__main__":
    run_batch("RELEVANT EXAMPLES (should match well)", relevant_examples)
    run_batch("IRRELEVANT EXAMPLES (should NOT match well)", irrelevant_examples)

    print("\n\n" + "="*70)
    print("HOW TO READ THIS:")
    print("="*70)
    print("""
FAISS distance: LOWER = more similar. Look at where relevant examples
cluster (probably low numbers) vs irrelevant examples (probably higher,
but maybe not as high as you'd hope). Pick FAISS_DISTANCE_THRESHOLD
somewhere between the two clusters, leaning toward the relevant side
to avoid rejecting real matches.

Cross-encoder score: HIGHER = more relevant. This should separate
the two groups much more clearly than FAISS distance does. Relevant
examples should score noticeably higher (often positive) and
irrelevant examples should score low/negative.

Once you see the actual numbers, update these two lines in app.py:
    FAISS_DISTANCE_THRESHOLD = <your chosen value>
    CROSSENCODER_SCORE_THRESHOLD = <your chosen value>
""")