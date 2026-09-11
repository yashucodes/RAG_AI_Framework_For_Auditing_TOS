const BACKEND_URL = "http://127.0.0.1:8000/audit-text/";

document.getElementById("auditBtn").addEventListener("click", async () => {
  const statusDiv = document.getElementById("status");
  const resultsDiv = document.getElementById("results");
  statusDiv.innerText = "Extracting text from page...";
  resultsDiv.innerHTML = "";

  // 1. Get active tab
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  // 2. Inject content script dynamically
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ["content.js"]
  });

  // 3. Request page text from content script
  chrome.tabs.sendMessage(tab.id, { action: "extract_text" }, async (response) => {
    if (!response || !response.text) {
      statusDiv.innerText = "⚠️ Could not extract text from this page.";
      return;
    }

    statusDiv.innerText = "🔍 Auditing ToS via FastAPI backend...";

    try {
      // 4. Send text as Form Data to FastAPI
      const formData = new FormData();
      formData.append("raw_text", response.text.substring(0, 10000)); // Cap length for speed

      const res = await fetch(BACKEND_URL, {
        method: "POST",
        body: formData
      });

      if (!res.ok) throw new Error(`Server returned status ${res.status}`);

      const data = await res.json();
      statusDiv.innerText = "";

      // 5. Render overall risk badge and summary
      const riskClass = `badge-${data.overall_risk}`;
      let html = `<div class="badge ${riskClass}">Overall Risk: ${data.overall_risk.toUpperCase()}</div>`;
      html += `<p style="font-size:12px; color:#334155;">${data.summary}</p>`;

      // 6. Render findings
      if (data.findings && data.findings.length > 0) {
        html += `<h4 style="margin: 10px 0 6px 0;">Flagged Findings (${data.findings.length})</h4>`;
        data.findings.forEach(f => {
          html += `
            <div class="finding-card">
              <strong>Clause #${f.clause_number}</strong>: <em>"${f.clause_text}"</em><br>
              <span style="color:#dc2626;">${f.explanation}</span><br>
              <small><strong>Law:</strong> ${f.legal_citation}</small>
            </div>`;
        });
      } else {
        html += `<p style="color:#16a34a; font-size:12px;">✅ No risky clauses detected on this page!</p>`;
      }

      resultsDiv.innerHTML = html;

    } catch (err) {
      console.error(err);
      statusDiv.innerText = "❌ Error connecting to backend server. Make sure Uvicorn is running!";
    }
  });
});