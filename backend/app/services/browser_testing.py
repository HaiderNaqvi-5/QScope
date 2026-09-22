"""QSScope-owned, non-destructive browser smoke and responsive testing."""
from __future__ import annotations

import shutil
import time
from typing import Any

from app.services.schema_testing import validate_loopback_base_url

DEFAULT_VIEWPORTS = ((320, 568), (360, 800), (375, 812), (390, 844), (412, 915),
                     (768, 1024), (1024, 768), (1280, 720), (1366, 768), (1440, 900), (1920, 1080))


def analyze_layout(snapshot: dict[str, Any], viewport: tuple[int, int]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if snapshot.get("scroll_width", 0) > viewport[0] + 1:
        issues.append({"kind": "HORIZONTAL_OVERFLOW", "viewport": f"{viewport[0]}x{viewport[1]}",
                       "actual_width": snapshot["scroll_width"]})
    for control in snapshot.get("small_controls", [])[:100]:
        issues.append({"kind": "SMALL_TAP_TARGET", "viewport": f"{viewport[0]}x{viewport[1]}",
                       "selector": control.get("selector"), "width": control.get("width"),
                       "height": control.get("height")})
    return issues


async def run_browser_audit(target: str, viewports: tuple[tuple[int, int], ...] = DEFAULT_VIEWPORTS
                            ) -> tuple[dict[str, Any], list[tuple[str, bytes]]]:
    target = validate_loopback_base_url(target)
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return ({"status": "TOOL_MISSING", "message": "Python Playwright is not installed.",
                 "browser_coverage": {}}, [])
    executable = shutil.which("chromium") or shutil.which("google-chrome")
    console_errors: list[dict[str, str]] = []
    page_errors: list[str] = []
    failed_requests: list[dict[str, str]] = []
    broken_links: list[dict[str, Any]] = []
    unlabeled_controls: list[dict[str, str]] = []
    layout_issues: list[dict[str, Any]] = []
    screenshots: list[tuple[str, bytes]] = []
    browser_coverage = {"chromium": "NOT_INSTALLED", "firefox": "NOT_INSTALLED", "webkit": "NOT_INSTALLED"}
    started = time.monotonic()
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, executable_path=executable)
            browser_coverage["chromium"] = "COMPLETED"
            page = await browser.new_page()
            page.on("console", lambda message: console_errors.append(
                {"type": message.type, "text": message.text[:1000]}) if message.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append(str(error)[:1000]))
            page.on("requestfailed", lambda request: failed_requests.append(
                {"url": request.url[:2000], "failure": str(request.failure)[:500]}))
            response = await page.goto(target, wait_until="domcontentloaded", timeout=15_000)
            initial_status = response.status if response else None
            title = (await page.title())[:500]
            audit = await page.evaluate("""function () {
                var links = Array.from(document.querySelectorAll('a[href]')).map(function (a) { return a.href; })
                  .filter(function (href) { try { return new URL(href).origin === location.origin; } catch (error) { return false; } }).slice(0, 20);
                var unlabeled = Array.from(document.querySelectorAll('input,select,textarea')).filter(function (element) {
                  return !element.getAttribute('aria-label') && !element.getAttribute('aria-labelledby') &&
                    !(element.labels && element.labels.length) && !element.closest('label');
                }).slice(0, 100).map(function (element, index) {
                  return {selector: element.id ? '#' + element.id : element.tagName.toLowerCase() + ':nth(' + index + ')'};
                });
                return {links: links, unlabeled: unlabeled};
            }""")
            unlabeled_controls.extend(audit["unlabeled"])
            for link in sorted(set(audit["links"])):
                try:
                    link_response = await page.request.get(link, timeout=5_000, fail_on_status_code=False)
                    if link_response.status >= 400:
                        broken_links.append({"url": link[:2000], "status": link_response.status})
                except Exception as exc:
                    broken_links.append({"url": link[:2000], "error": exc.__class__.__name__})
            for width, height in viewports:
                await page.set_viewport_size({"width": width, "height": height})
                await page.wait_for_timeout(50)
                snapshot = await page.evaluate("""function () {
                    var controls = Array.from(document.querySelectorAll('a,button,input,select,textarea,[role="button"]'))
                      .filter(function (element) { var rect=element.getBoundingClientRect(); return rect.width>0 && rect.height>0 && (rect.width<24 || rect.height<24); })
                      .slice(0,100).map(function (element,index) { var rect=element.getBoundingClientRect(); return {
                        selector: element.id ? '#'+element.id : element.tagName.toLowerCase()+':nth('+index+')',
                        width: Math.round(rect.width), height: Math.round(rect.height)}; });
                    return {scroll_width: Math.max(document.documentElement.scrollWidth,
                      document.body ? document.body.scrollWidth : 0), small_controls: controls};
                }""")
                layout_issues.extend(analyze_layout(snapshot, (width, height)))
                screenshots.append((f"browser-{width}x{height}.png", await page.screenshot(full_page=True)))
            await browser.close()
            for name in ("firefox", "webkit"):
                try:
                    secondary = await getattr(playwright, name).launch(headless=True)
                    secondary_page = await secondary.new_page(viewport={"width": 1280, "height": 720})
                    await secondary_page.goto(target, wait_until="domcontentloaded", timeout=15_000)
                    await secondary.close()
                    browser_coverage[name] = "COMPLETED"
                except Exception:
                    browser_coverage[name] = "NOT_INSTALLED"
    except Exception as exc:
        return ({"status": "TOOL_ERROR", "message": f"Browser audit failed: {exc.__class__.__name__}: {str(exc)[:500]}",
                 "browser_coverage": {**browser_coverage, "chromium": "FAILED"}}, screenshots)
    return ({"status": "PASSED" if not (console_errors or page_errors or failed_requests or layout_issues or broken_links or unlabeled_controls) else "FAILED",
             "message": "Generated non-destructive navigation and responsive audit completed.",
             "target": target, "http_status": initial_status, "title": title,
             "duration_ms": int((time.monotonic() - started) * 1000),
             "console_errors": console_errors[:100], "page_errors": page_errors[:100],
             "failed_requests": failed_requests[:100], "layout_issues": layout_issues[:500],
             "broken_links": broken_links[:100], "unlabeled_controls": unlabeled_controls[:100],
             "viewports": [f"{width}x{height}" for width, height in viewports],
             "browser_coverage": browser_coverage}, screenshots)
