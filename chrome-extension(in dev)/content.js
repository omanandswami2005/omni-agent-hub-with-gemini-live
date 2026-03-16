/**
 * Content Script — Injected into web pages.
 *
 * Provides page interaction capabilities for cross-client actions:
 * - Read page content / selected text
 * - Click elements by selector
 * - Fill form fields
 * - Extract structured data
 * - Scroll to elements
 */

// TODO: Implement:
//   - Message listener for background script commands
//   - DOM interaction helpers (click, type, scroll, extract)
//   - Page content extraction (readability-style)
//   - Selected text capture
//   - Screenshot via html2canvas (optional)

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.action) {
    case 'GET_PAGE_CONTENT':
      sendResponse({
        title: document.title,
        url: window.location.href,
        text: document.body.innerText.slice(0, 10000),
      });
      break;

    case 'GET_SELECTION':
      sendResponse({ selection: window.getSelection()?.toString() || '' });
      break;

    case 'CLICK_ELEMENT':
      {
        const el = document.querySelector(message.selector);
        el?.click();
        sendResponse({ success: !!el });
      }
      break;

    case 'SCROLL_TO':
      window.scrollTo({ top: message.y || 0, behavior: 'smooth' });
      sendResponse({ success: true });
      break;

    default:
      sendResponse({ error: 'Unknown action' });
  }
  return true;
});
