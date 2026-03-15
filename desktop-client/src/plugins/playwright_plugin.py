"""Playwright plugin — browser automation for Chrome via Playwright."""

from __future__ import annotations

import logging
from typing import Any

from src.plugin_registry import DesktopPlugin

logger = logging.getLogger(__name__)

# Global state for browser persistence
_playwright = None
_browser = None
_page = None

async def _ensure_browser():
    """Ensure a browser instance and page are running."""
    global _playwright, _browser, _page
    if _page is not None and not _page.is_closed():
        return

    try:
        from playwright.async_api import async_playwright
        if _playwright is None:
            _playwright = await async_playwright().start()
        if _browser is None:
            # Run headful to show the user what is happening
            _browser = await _playwright.chromium.launch(headless=False)
        _page = await _browser.new_page()
    except Exception as e:
        logger.error(f"Failed to start Playwright browser: {e}")
        raise

async def _handle_browser_navigate(**kwargs) -> dict:
    url = kwargs.get("url", "")
    if not url:
        return {"error": "No url provided"}

    # Prefix http if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        await _ensure_browser()
        await _page.goto(url, wait_until="networkidle")
        return {"ok": True, "url": _page.url, "title": await _page.title()}
    except Exception as e:
        logger.error(f"Navigation failed: {e}")
        return {"error": str(e)}

async def _handle_browser_click(**kwargs) -> dict:
    selector = kwargs.get("selector", "")
    if not selector:
        return {"error": "No selector provided"}

    try:
        await _ensure_browser()
        await _page.click(selector)
        return {"ok": True, "selector": selector}
    except Exception as e:
        logger.error(f"Click failed: {e}")
        return {"error": str(e)}

async def _handle_browser_fill(**kwargs) -> dict:
    selector = kwargs.get("selector", "")
    text = kwargs.get("text", "")
    if not selector or not text:
        return {"error": "Selector and text are required"}

    try:
        await _ensure_browser()
        await _page.fill(selector, text)
        return {"ok": True, "selector": selector}
    except Exception as e:
        logger.error(f"Fill failed: {e}")
        return {"error": str(e)}

async def _handle_browser_evaluate(**kwargs) -> dict:
    script = kwargs.get("script", "")
    if not script:
        return {"error": "No script provided"}

    try:
        await _ensure_browser()
        result = await _page.evaluate(script)
        return {"ok": True, "result": result}
    except Exception as e:
        logger.error(f"Evaluate failed: {e}")
        return {"error": str(e)}

async def _handle_browser_get_text(**kwargs) -> dict:
    selector = kwargs.get("selector", "body")
    try:
        await _ensure_browser()
        text = await _page.locator(selector).inner_text()
        return {"ok": True, "text": text}
    except Exception as e:
        logger.error(f"Get text failed: {e}")
        return {"error": str(e)}

async def cleanup():
    """Cleanup Playwright resources."""
    global _playwright, _browser, _page
    if _page:
        await _page.close()
    if _browser:
        await _browser.close()
    if _playwright:
        await _playwright.stop()
    _playwright = _browser = _page = None

def register() -> DesktopPlugin:
    return DesktopPlugin(
        name="browser",
        capabilities=["web_automation"],
        handlers={
            "browser_navigate": _handle_browser_navigate,
            "browser_click": _handle_browser_click,
            "browser_fill": _handle_browser_fill,
            "browser_evaluate": _handle_browser_evaluate,
            "browser_get_text": _handle_browser_get_text,
        },
        tool_defs=[
            {
                "name": "browser_navigate",
                "description": "Navigate to a URL in the Chrome browser",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to navigate to"},
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "browser_click",
                "description": "Click an element on the current webpage",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS or Text selector to click"},
                    },
                    "required": ["selector"],
                },
            },
            {
                "name": "browser_fill",
                "description": "Fill in a form field on the current webpage",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector of the input field"},
                        "text": {"type": "string", "description": "Text to type into the field"},
                    },
                    "required": ["selector", "text"],
                },
            },
            {
                "name": "browser_evaluate",
                "description": "Execute JavaScript in the current browser page",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "script": {"type": "string", "description": "JavaScript code to execute"},
                    },
                    "required": ["script"],
                },
            },
            {
                "name": "browser_get_text",
                "description": "Get the text content of a specific element or the whole page",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector (defaults to 'body' if omitted)", "default": "body"},
                    },
                },
            },
        ],
    )
