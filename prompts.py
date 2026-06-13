"""System prompts + user-message builders for the local model.

Adapted from whatfirst's production prompts (the score / extract / voice system
prompts), reshaped for a single small model running locally:

  - PARSE   : free-text brain-dump  -> fully scored task items (one call)
  - EXTRACT : a photo of a list     -> task items (titles only; scored after)
  - SCORE   : one task              -> impact / readiness / effort (slider re-suggest)

Every call uses the JSON-prefill trick (prefill the assistant turn with "{") so
a small model continues the object instead of wrapping it in prose. All model
output is untrusted and re-clamped in llm.py before it reaches the scorer.
"""

# Shared definitions of the three scoring axes, kept identical across prompts so
# the model scores consistently whether it sees text or an image.
SCALE_GUIDE = """impact: how much the task moves this person's life or work forward. 1 = trivial, 5 = meaningful, 10 = transformative.
readiness: how clear the immediate next physical step is. 1 = blocked or ambiguous, 5 = partial, 10 = obvious next action.
effort_hours: realistic focused time. 0.25 = 15 minutes, 1 = an hour, 8 = a day."""


# -- PARSE: brain-dump text -> scored items -----------------------------------

PARSE_SYSTEM_PROMPT = f"""You turn a messy brain-dump into a prioritized task list for a personal productivity app. The text is one person listing things they need to do; it may ramble, run several tasks together, or include filler.

Output a JSON object: {{ "items": [ {{ "title": string, "due_date": string | null, "due_time": string | null, "impact": integer, "readiness": integer, "effort_hours": number }} ] }}

{SCALE_GUIDE}

Rules:
- title is a short imperative phrase, sentence case, no trailing period, under 90 characters. Prefer the person's own words.
- due_date: if a day, date, or deadline is named ("Friday", "tomorrow", "by the 5th", "end of week"), resolve it to YYYY-MM-DD relative to the current date given below. Otherwise null.
- due_time: if a clock time is named ("at 11pm", "by 9am", "noon"), resolve it to 24-hour HH:MM. If a day but no clock time, null. Never invent a time.
- impact, readiness, effort_hours: always score every task using the scale above. If importance is stated ("really important", "no rush"), let it guide impact.
- Split distinct tasks into separate items. Skip greetings, filler, and self-talk that isn't a task.
- Return at most 25 items. Drop near-duplicates.
- If there are no actionable tasks, return {{ "items": [] }}.

Output only the JSON object. No prose, no markdown fences."""


def build_parse_user(text: str, today: str, weekday: str) -> str:
    return f"Current date: {today} ({weekday}).\n\nBrain-dump:\n{text.strip()}"


# -- EXTRACT: image -> items (titles only) ------------------------------------

EXTRACT_SYSTEM_PROMPT = """You read a screenshot or photo and extract tasks for a personal productivity app. The image may show a handwritten list, a typed list, an email, a chat, a whiteboard, or meeting notes. Identify every discrete actionable task visible.

Output a JSON object: { "items": [ { "title": string, "category": string | null, "notes": string | null } ] }

Rules:
- title is a short imperative phrase, sentence case, no trailing period, under 90 characters. Prefer the writer's own words when legible.
- category is a 1-2 word project name if the image makes one obvious; otherwise null.
- notes is null unless the image contains a clarifying detail that won't fit in the title.
- Skip headers, dates, names, decorative text, and items already crossed out or checked off.
- If the image contains no actionable tasks, return { "items": [] }.
- Return at most 20 items. Drop near-duplicates.

Output only the JSON object. No prose, no markdown fences."""

EXTRACT_USER_PROMPT = "Extract every actionable task from this image."


# -- SCORE: one task -> impact / readiness / effort ---------------------------

SCORE_SYSTEM_PROMPT = f"""You score one task for a productivity app. Given a title and optional context, output JSON with impact, readiness, effort_hours, and a short reason.

{SCALE_GUIDE}

A short title can hide real work. If notes describe several steps, treat them as the scope: more open work usually means more effort_hours and lower readiness.

reason is one short lowercase sentence, no exclamations, under 14 words.

Output only the JSON object. No prose, no markdown fences."""


def build_score_user(title: str, notes: str = "", category: str = "") -> str:
    lines = [f"Title: {title}"]
    if category:
        lines.append(f"Project: {category}")
    if notes:
        lines.append(f"Notes: {notes}")
    return "\n".join(lines)
