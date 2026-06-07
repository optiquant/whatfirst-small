"""whatfirst-small — a Gradio app that turns a messy brain-dump (or a photo of a
to-do list) into a transparently-ranked "do this first" list, using a small
local model for the messy-language part and a deterministic, legible engine for
the ranking.

Capture -> AI structures each task (impact / readiness / effort / due) -> the
scoring engine ranks -> you can correct any score and it re-ranks live.
"""

from __future__ import annotations

import os
from datetime import datetime

import gradio as gr

import llm
import score

SAMPLE_DUMP = """email the landlord about the lease renewal, kind of important and due Friday
finish the Q3 board deck — big deal, maybe 4 hours of work, needs to be done by next Wednesday
5 min: cancel the unused gym membership
look into switching the team to the new CI, no rush, not sure where to start
book the dentist, due tomorrow
reply to Sam's thread, quick one
draft the hiring plan — important but I'm blocked until we agree on budget"""

FORMULA_BLURB = """
Two scores compete and the higher one shows:

- **do = (Impact · Urgency · Readiness_eff · QuickWin) / 10** — the case for doing it now.
- **prep = (Impact · Urgency · (10 − Readiness)) / 10 · 0.7 · QuickWin** — the case for de-risking it first (wins only when a task is valuable but not ready).

**Urgency** climbs as a deadline nears and *explodes* once it's within a day, so a looming deadline can't be buried by a shiny far-off task. **QuickWin** rewards short, ready tasks. Deadlines act as a *constraint*, not just a term: anything overdue, or that genuinely won't finish in time given everything ahead of it, is lifted above the value pack. Every number is shown — nothing is a black box.
"""

DF_HEADERS = ["#", "Task", "Score", "Due", "Flag", "Why", "I", "R", "Eff·h"]
DF_DATATYPES = ["number", "str", "str", "str", "str", "str", "number", "number", "number"]


def _label(t: dict) -> str:
    return f"{t['id']} · {t['title']}"


def render(tasks: list[dict]):
    """tasks -> (header_md, dataframe_rows, dropdown_choices)."""
    if not tasks:
        return "### Add a brain-dump or a photo, then hit **Prioritize**.", [], []
    now = datetime.now()
    ranked = score.rank_active(tasks, now)
    risk = score.deadline_risk_map(ranked, now)
    rows = []
    for i, t in enumerate(ranked):
        c = score.score_components(t)
        flag = score.deadline_status(t, now) or risk.get(t["id"], "")
        rows.append([
            i + 1,
            t["title"],
            score.format_score(c["display"]),
            score.due_label(t.get("due_date"), now) if t.get("due_date") else "—",
            flag,
            t.get("reason", "") or "",
            round(c["I"]),
            round(c["R"]),
            round(t["effort_hours"], 2),
        ])
    top = ranked[0]
    header = f"### ▶ Do this first: **{top['title']}**  ·  score {score.format_score(score.priority(top))}"
    return header, rows, [_label(t) for t in ranked]


def prioritize(text, image, tasks):
    if not llm.is_ready():
        return tasks, "### ⏳ The local model is still loading — give it a moment and try again.", [], gr.update()
    collected = []
    if text and text.strip():
        collected += llm.parse_braindump(text)
    if image is not None:
        collected += llm.extract_from_image(image)
    for i, t in enumerate(collected):
        t["id"] = f"t{i}"
    if not collected:
        return collected, "### Nothing actionable found — try a different dump or photo.", [], gr.update(choices=[], value=None)
    header, rows, choices = render(collected)
    return collected, header, rows, gr.update(choices=choices, value=(choices[0] if choices else None))


def load_task(sel, tasks):
    t = _find(sel, tasks)
    if not t:
        return 5, 8, 1.0
    return t["impact"], t["readiness"], t["effort_hours"]


def apply_edit(sel, impact, readiness, effort, tasks):
    t = _find(sel, tasks)
    if t:
        t["impact"] = int(impact)
        t["readiness"] = int(readiness)
        t["effort_hours"] = float(effort)
        t["reason"] = (t.get("reason") or "").split(" · edited")[0] + " · edited"
    header, rows, choices = render(tasks)
    keep = sel if sel in choices else (choices[0] if choices else None)
    return tasks, header, rows, gr.update(choices=choices, value=keep)


def resuggest(sel, tasks):
    t = _find(sel, tasks)
    if not t or not llm.is_ready():
        return gr.update(), gr.update(), gr.update()
    s = llm.score_task(t["title"], t.get("notes") or "", t.get("category") or "")
    if not s:
        return t["impact"], t["readiness"], t["effort_hours"]
    return s["impact"], s["readiness"], s["effort_hours"]


def _find(sel, tasks):
    if not sel:
        return None
    tid = sel.split(" · ", 1)[0]
    return next((x for x in tasks if x["id"] == tid), None)


with gr.Blocks(title="whatfirst-small", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        "# whatfirst · small\n"
        "Dump everything on your mind — or snap a photo of your to-do list — and a "
        "**small local model** turns it into structured tasks. A **transparent scoring "
        "engine** then tells you what to do *first*, and shows its work. No cloud, no API keys."
    )
    tasks_state = gr.State([])

    with gr.Row():
        with gr.Column(scale=2):
            dump = gr.Textbox(
                label="Brain-dump", lines=8,
                placeholder="email the landlord by Friday, finish the deck (4h, big deal), 5-min: cancel the gym…",
            )
            image = gr.Image(label="…or a photo of a list", type="pil", height=180)
            with gr.Row():
                go = gr.Button("Prioritize", variant="primary")
                sample = gr.Button("Try a sample")
        with gr.Column(scale=3):
            header = gr.Markdown("### Add a brain-dump or a photo, then hit **Prioritize**.")
            table = gr.Dataframe(
                headers=DF_HEADERS, datatype=DF_DATATYPES, interactive=False,
                wrap=True, label="Ranked",
            )

    with gr.Accordion("Correct a score (the model proposes — you decide)", open=False):
        picker = gr.Dropdown(label="Task", choices=[], interactive=True)
        with gr.Row():
            impact = gr.Slider(1, 10, value=5, step=1, label="Impact")
            readiness = gr.Slider(1, 10, value=8, step=1, label="Readiness")
            effort = gr.Slider(0.05, 8, value=1.0, step=0.05, label="Effort (hours)")
        with gr.Row():
            apply_btn = gr.Button("Apply & re-rank", variant="primary")
            resuggest_btn = gr.Button("Re-suggest with AI")

    with gr.Accordion("How the score works", open=False):
        gr.Markdown(FORMULA_BLURB)

    go.click(prioritize, [dump, image, tasks_state], [tasks_state, header, table, picker])
    sample.click(lambda: SAMPLE_DUMP, None, dump)
    picker.change(load_task, [picker, tasks_state], [impact, readiness, effort])
    apply_btn.click(apply_edit, [picker, impact, readiness, effort, tasks_state],
                    [tasks_state, header, table, picker])
    resuggest_btn.click(resuggest, [picker, tasks_state], [impact, readiness, effort])


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", "7860")))
