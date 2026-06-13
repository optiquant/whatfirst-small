"""Drive the real whatfirst-small Gradio app and screenshot each demo scene.

The app is launched with a stubbed ``llm`` (stub_llm.py) so it needs no
llama.cpp server: the UI is genuine, only the model is faked. We then walk the
core flow with Playwright — paste a brain-dump, prioritize, correct a score and
watch it re-rank, and open the formula — capturing one PNG per scene.

Output: demo/shots/*.png
"""

import os
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SHOTS = os.path.join(HERE, "shots")
os.makedirs(SHOTS, exist_ok=True)

# Quiet Gradio down before it is imported.
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

# Register the stub as `llm` BEFORE app imports it, then import the real app.
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import stub_llm                       # noqa: E402
sys.modules["llm"] = stub_llm
import app as wfapp                    # noqa: E402  (builds the genuine Blocks)

from playwright.sync_api import sync_playwright   # noqa: E402

PORT = int(os.environ.get("DEMO_PORT", "7861"))
VIEWPORT = {"width": 1280, "height": 1024}
SAMPLE = wfapp.SAMPLE_DUMP


def launch_app():
    wfapp.demo.queue()
    wfapp.demo.launch(
        server_name="127.0.0.1", server_port=PORT,
        prevent_thread_lock=True, quiet=True, inbrowser=False,
    )


def main():
    launch_app()
    base = f"http://127.0.0.1:{PORT}/"

    # Wait for the Gradio server to accept connections before driving it.
    import urllib.request
    import time
    for _ in range(60):
        try:
            urllib.request.urlopen(base, timeout=2)
            break
        except Exception:
            time.sleep(0.5)

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb"])
        ctx = browser.new_context(
            viewport=VIEWPORT, device_scale_factor=2,
            color_scheme="light", reduced_motion="reduce",
        )
        page = ctx.new_page()

        def settle(ms=700):
            page.wait_for_timeout(ms)

        def shot(name):
            page.wait_for_timeout(200)
            page.screenshot(path=os.path.join(SHOTS, f"{name}.png"))
            print("captured", name)

        page.goto(base, wait_until="domcontentloaded")
        page.wait_for_selector("textarea", timeout=30000)
        settle(900)
        shot("01_empty")

        # Fill the brain-dump with the app's own sample, via its button.
        page.get_by_role("button", name="Try a sample").click()
        settle(700)
        shot("02_filled")

        # Prioritize → the stubbed parse returns instantly; the table fills.
        page.get_by_role("button", name="Prioritize").click()
        page.wait_for_selector("table", timeout=30000)
        # wait for a known row to render
        page.wait_for_selector("text=Q3 board deck", timeout=30000)
        settle(900)
        page.evaluate("window.scrollTo(0, 0)")
        settle(300)
        shot("03_ranked")

        # Open "Correct a score", select a low task, raise it, re-rank.
        try:
            page.get_by_text("Correct a score", exact=False).first.click()
            settle(600)
            # Open the dropdown (Gradio renders it as a role=listbox input) and
            # pick the CI task — a low, not-ready item near the bottom — so that
            # raising its scores visibly climbs it up the ranking.
            page.locator("[role=listbox]").first.click()
            settle(400)
            page.get_by_role("option", name="Switch the team to the new CI").first.click()
            settle(600)
        except Exception as e:
            print("  (selection step note:", e, ")")

        # Drag impact + readiness sliders up so the task visibly climbs.
        def set_slider(label, value):
            js = (
                "([lbl, val]) => {"
                "  const blocks = [...document.querySelectorAll('.block, .form, div')];"
                "  let el = null;"
                "  for (const r of document.querySelectorAll('input[type=range]')) {"
                "    const wrap = r.closest('.block') || r.parentElement;"
                "    if (wrap && wrap.textContent && wrap.textContent.includes(lbl)) { el = r; break; }"
                "  }"
                "  if (!el) return false;"
                "  const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
                "  set.call(el, String(val));"
                "  el.dispatchEvent(new Event('input',{bubbles:true}));"
                "  el.dispatchEvent(new Event('change',{bubbles:true}));"
                "  return true;"
                "}"
            )
            return page.evaluate(js, [label, value])

        try:
            set_slider("Impact", 10)
            set_slider("Readiness", 10)
            settle(500)
            shot("04_correct")
            page.get_by_role("button", name="Apply & re-rank").click()
            page.wait_for_selector("text=Q3 board deck", timeout=15000)
            settle(900)
            shot("05_reranked")
        except Exception as e:
            print("  (slider/apply step note:", e, ")")
            shot("04_correct")

        # Open "How the score works".
        try:
            page.get_by_text("How the score works", exact=False).first.click()
            settle(600)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            settle(500)
            shot("06_formula")
        except Exception as e:
            print("  (formula step note:", e, ")")

        browser.close()

    print("done — shots in", SHOTS)
    os._exit(0)   # the Gradio server thread is a daemon; exit cleanly


if __name__ == "__main__":
    main()
