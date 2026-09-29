const BACKEND_URL = "http://127.0.0.1:8000/audit-text/";

// --- Caching config -----------------------------------------------------
// Chrome destroys the popup's JS/DOM every time it loses focus (e.g. the
// user switches tabs), so on reopen the extension looked "reset" even
// though nothing actually broke. We cache the last audit result per page
// URL in chrome.storage.local and replay it immediately on open instead
// of forcing a full re-audit every time.
const CACHE_KEY = "tosAuditCache";
const CACHE_TTL_MS = 15 * 60 * 1000; // keep a cached result for 15 minutes

async function saveCache(tab, data) {
  try {
    await chrome.storage.local.set({
      [CACHE_KEY]: {
        url: tab.url,
        tabId: tab.id,
        data,
        timestamp: Date.now(),
      },
    });
  } catch (e) {
    console.error("Failed to cache audit result:", e);
  }
}

async function loadCache() {
  try {
    const stored = await chrome.storage.local.get(CACHE_KEY);
    return stored[CACHE_KEY] || null;
  } catch (e) {
    console.error("Failed to read cached audit result:", e);
    return null;
  }
}

async function clearCache() {
  try {
    await chrome.storage.local.remove(CACHE_KEY);
  } catch (e) {
    console.error("Failed to clear cached audit result:", e);
  }
}

// --- Restore cached results on popup open --------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  const statusDiv = document.getElementById("status");

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) return;

    const cached = await loadCache();
    if (!cached) return;

    const isFresh = Date.now() - cached.timestamp < CACHE_TTL_MS;
    const isSamePage = cached.url === tab.url;

    if (isFresh && isSamePage) {
      renderResults(cached.data);
      const ageSeconds = Math.round((Date.now() - cached.timestamp) / 1000);
      statusDiv.innerText = `Showing cached results from ${ageSeconds}s ago. Click "Audit" to refresh.`;
    } else if (!isSamePage) {
      // Popup reopened on a different page -- stale cache, drop it silently.
      await clearCache();
    }
  } catch (e) {
    console.error("Cache restore failed:", e);
  }
});

// --- Run a fresh audit -----------------------------------------------------
document.getElementById("auditBtn").addEventListener("click", async () => {
  const statusDiv = document.getElementById("status");
  const resultsDiv = document.getElementById("results");
  statusDiv.innerText = "Extracting webpage text...";
  resultsDiv.classList.add("hidden");

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) {
      statusDiv.innerText = "Unable to query the current active tab.";
      return;
    }

    // Inject content script safely
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["content.js"],
      });
    } catch (e) {
      statusDiv.innerText = "Cannot run on browser system pages.";
      return;
    }

    // Request DOM content
    chrome.tabs.sendMessage(tab.id, { action: "extract_text" }, async (response) => {
      if (chrome.runtime.lastError || !response || !response.text) {
        statusDiv.innerText = "Could not extract text from this page.";
        return;
      }

      statusDiv.innerText = "Analyzing risk scores and contradictions...";

      try {
        const formData = new FormData();
        formData.append("raw_text", response.text.substring(0, 15000));

        const res = await fetch(BACKEND_URL, {
          method: "POST",
          body: formData,
        });

        if (!res.ok) throw new Error(`HTTP Error status: ${res.status}`);

        const data = await res.json();
        statusDiv.innerText = "";
        renderResults(data);

        // Cache this result so it survives the popup closing on tab switch.
        await saveCache(tab, data);
      } catch (err) {
        console.error(err);
        statusDiv.innerText = "Error reaching backend. Verify Uvicorn is running.";
      }
    });
  } catch (err) {
    console.error(err);
    statusDiv.innerText = "Unexpected error occurred.";
  }
});

// Escape anything that came from the audited webpage or the model before it
// goes into innerHTML. The extension reads arbitrary pages, so clause text
// must never be trusted as markup.
function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderResults(data) {
  const resultsDiv = document.getElementById("results");
  const scoreGauge = document.getElementById("scoreGauge");
  const scoreText = document.getElementById("scoreText");
  const riskBadge = document.getElementById("riskBadge");
  const summaryText = document.getElementById("summaryText");
  const suggestionText = document.getElementById("suggestionText");
  const contradictionsSection = document.getElementById("contradictionsSection");
  const contradictionsList = document.getElementById("contradictionsList");
  const contradictionCount = document.getElementById("contradictionCount");
  const riskySection = document.getElementById("riskySection");
  const riskyList = document.getElementById("riskyList");
  const riskyCount = document.getElementById("riskyCount");
  const cleanState = document.getElementById("cleanState");

  // 1. Risk gauge + overview
  const score = Number(data.risk_score) || 0;
  const riskLevel = String(data.risk_level || "LOW").toUpperCase();

  scoreText.innerText = score;
  riskBadge.innerText = `${riskLevel} RISK`;
  riskBadge.className = "badge";

  let color = "#22c55e";
  let badgeClass = "badge-low";
  if (riskLevel === "HIGH") {
    color = "#ef4444";
    badgeClass = "badge-high";
  } else if (riskLevel === "MEDIUM") {
    color = "#f59e0b";
    badgeClass = "badge-medium";
  }
  riskBadge.classList.add(badgeClass);

  const pct = Math.max(0, Math.min(score * 10, 100));
  scoreGauge.style.background = `conic-gradient(${color} ${pct}%, #2a2a2e 0)`;

  summaryText.innerText = data.summary || "No overview provided.";
  suggestionText.innerText = data.suggestion || "Review the agreement carefully before accepting.";

  // 2. Contradictions
  const contradictions = data.contradictions || [];
  contradictionsList.innerHTML = "";

  if (contradictions.length > 0) {
    contradictionCount.innerText = contradictions.length;
    contradictionsSection.classList.remove("hidden");

    contradictions.forEach((c) => {
      const card = document.createElement("div");
      card.className = "clause-card contradiction-card";
      card.innerHTML = `
        <strong>Conflict Found</strong>
        <span class="clause-quote">Clause A: "${esc(c.clause_1)}"</span>
        <span class="clause-quote">Clause B: "${esc(c.clause_2)}"</span>
        <div class="contradiction-explanation">${esc(c.explanation)}</div>
      `;
      contradictionsList.appendChild(card);
    });
  } else {
    contradictionsSection.classList.add("hidden");
  }

  // 3. Risky clauses
  const riskyClauses = data.risky_clauses || [];
  riskyList.innerHTML = "";

  if (riskyClauses.length > 0) {
    riskyCount.innerText = riskyClauses.length;
    riskySection.classList.remove("hidden");

    riskyClauses.forEach((r) => {
      const label = String(r.category || "Risky Clause").replace(/_/g, " ");
      const card = document.createElement("div");
      card.className = "clause-card";
      card.innerHTML = `
        <strong>${esc(label)}</strong>
        <span class="clause-quote">"${esc(r.clause_text)}"</span>
        <div class="explanation">${esc(r.explanation)}</div>
        ${r.legal_citation ? `<small class="law-tag">Law: ${esc(r.legal_citation)}</small>` : ""}
      `;
      riskyList.appendChild(card);
    });
  } else {
    riskySection.classList.add("hidden");
  }

  // 4. Clean state
  if (contradictions.length === 0 && riskyClauses.length === 0) {
    cleanState.classList.remove("hidden");
  } else {
    cleanState.classList.add("hidden");
  }

  resultsDiv.classList.remove("hidden");
}