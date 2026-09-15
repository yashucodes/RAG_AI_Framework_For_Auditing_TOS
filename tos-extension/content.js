// Check if content script is already injected
if (!window.tosAuditorInjected) {
  window.tosAuditorInjected = true;

  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "extract_text") {
      // Grab selected text if highlighted; otherwise grab all page body text
      const selectedText = window.getSelection().toString().trim();
      const pageText = selectedText.length > 0 ? selectedText : document.body.innerText;
      sendResponse({ text: pageText });
    }
  });
}