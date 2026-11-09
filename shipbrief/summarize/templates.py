"""MODE 1 prompt-of-the-day and try-this-today. Original text written for ShipBrief.

Each template is tied to a real item by its tag; the item title is inserted only into the
`useCase` line (never into the prompt body, so untrusted text never becomes part of a prompt
the reader pastes). Selection rotates by date so readers see variety.
"""
from __future__ import annotations

from datetime import date

PROMPTS: dict[str, list[dict]] = {
    "agents": [
        {"title": "Turn a chore into an agent spec",
         "prompt": "I want to automate this recurring task: <DESCRIBE THE TASK>. Break it into steps an AI agent could follow. For each step, list the tool or data it needs, what could go wrong, and when a human should approve before it continues. End with the smallest version I could test this week.",
         "roles": ["developer", "product"]},
        {"title": "Stress-test an agent plan",
         "prompt": "Here is the plan my AI agent will follow: <PASTE PLAN>. Act as a careful reviewer. List the five most likely ways it fails in real use, how I would notice each failure, and one guardrail for each. Keep it concrete and short.",
         "roles": ["developer"]},
    ],
    "coding": [
        {"title": "Get a focused code review",
         "prompt": "Review this code as a senior engineer: <PASTE CODE>. First explain in two sentences what it does. Then list up to five issues ranked by risk (bugs before style), each with a one-line fix. Say 'no issues found' rather than inventing problems.",
         "roles": ["developer"]},
        {"title": "Write tests before you refactor",
         "prompt": "Before I refactor this function, write unit tests that pin down its current behaviour: <PASTE FUNCTION>. Cover normal inputs, edge cases, and error paths. Add a comment above each test saying which behaviour it protects.",
         "roles": ["developer"]},
    ],
    "models": [
        {"title": "Compare two models on your own task",
         "prompt": "I am choosing between AI models for this job: <DESCRIBE YOUR TASK>. Write ten realistic test inputs that would reveal differences between models, including two tricky edge cases. For each input, describe what an excellent answer must contain so I can score the results myself.",
         "roles": ["developer", "product", "everyone"]},
        {"title": "Explain a model launch to your team",
         "prompt": "Summarize this announcement for my team in plain English: <PASTE ANNOUNCEMENT TEXT>. Cover what changed, who it matters to, and what we would need to test before switching. Clearly separate facts stated in the text from your own assumptions.",
         "roles": ["everyone", "product"]},
    ],
    "research": [
        {"title": "Read a paper in ten minutes",
         "prompt": "Help me understand this paper abstract: <PASTE ABSTRACT>. Explain the problem, the core idea, and the main claimed result in plain English. Then list three questions I should ask before trusting the result, and say what kind of team would find it useful.",
         "roles": ["researcher", "everyone"]},
    ],
    "evals": [
        {"title": "Build a mini eval set",
         "prompt": "I use an AI prompt for this purpose: <DESCRIBE PURPOSE>. Create eight test cases as a table with columns: input, what a good answer must include, what a bad answer looks like. Include one adversarial input and one input with missing information.",
         "roles": ["developer", "product"]},
    ],
    "rag": [
        {"title": "Check answers against your documents",
         "prompt": "Answer the question using only the document excerpts below. If the excerpts do not contain the answer, say so plainly. After the answer, list which excerpt supports each claim.\n\nQuestion: <YOUR QUESTION>\n\nExcerpts: <PASTE EXCERPTS>",
         "roles": ["developer", "everyone"]},
    ],
    "multimodal": [
        {"title": "Write a precise image brief",
         "prompt": "Turn my rough idea into a clear brief for an image or video generation tool: <DESCRIBE IDEA>. Specify subject, setting, composition, lighting, style, and what to avoid. Then give two alternative directions that change only the style.",
         "roles": ["designer"]},
    ],
    "safety": [
        {"title": "Red-team your own prompt",
         "prompt": "Here is a prompt my product sends to an AI model: <PASTE PROMPT>. List ways a user could misuse it or make it produce harmful or off-brand output, without writing the actual harmful content. For each, suggest one wording change or check that reduces the risk.",
         "roles": ["developer", "product"]},
    ],
    "default": [
        {"title": "Turn news into an action",
         "prompt": "Here is an AI announcement I read today: <PASTE SUMMARY>. Given my role as <YOUR ROLE>, tell me in five bullet points whether it matters to me, what I could try in under 30 minutes, and what I should ignore. Be honest if the answer is 'nothing yet'.",
         "roles": ["everyone"]},
        {"title": "Draft a decision memo",
         "prompt": "Help me decide whether my team should adopt <TOOL OR MODEL>. Ask me up to five clarifying questions first. Then write a one-page memo with options, costs, risks, and a recommendation, and flag anything you are unsure about.",
         "roles": ["founder", "product"]},
    ],
}

WORKFLOWS: dict[str, list[dict]] = {
    "agents": [{"title": "Prototype a small agent in an hour",
                "steps": ["Pick one repetitive task you did this week.",
                          "Write the steps down as if training a new teammate.",
                          "Give an agent framework only the tools those steps need.",
                          "Run it on three real examples and log every tool call.",
                          "Add a human approval step before any irreversible action."],
                "roles": ["developer"]}],
    "coding": [{"title": "Try an AI coding tool on a real ticket",
                "steps": ["Choose a small, well-defined ticket from your backlog.",
                          "Ask the tool for a plan before it writes code.",
                          "Let it implement, then run your tests.",
                          "Review the diff line by line and note what you had to fix."],
                "roles": ["developer"]}],
    "models": [{"title": "Run a 20-minute model bake-off",
                "steps": ["Collect five real prompts from your own work.",
                          "Run them through your current model and the new one.",
                          "Score each answer blind on accuracy and usefulness.",
                          "Switch only if the new model wins clearly on your tasks."],
                "roles": ["developer", "product"]}],
    "research": [{"title": "Turn one paper into one experiment",
                  "steps": ["Read the abstract and the main figure only.",
                            "Write down the single claim you care about.",
                            "Design the smallest test of that claim on your data.",
                            "Share the result with your team, including if it failed."],
                  "roles": ["researcher"]}],
    "open-source": [{"title": "Upgrade a dependency safely",
                     "steps": ["Read the release notes and list changes that touch your code.",
                               "Upgrade in a separate branch.",
                               "Run your tests and one end-to-end check.",
                               "Roll out behind a flag if behaviour changed."],
                     "roles": ["developer"]}],
    "default": [{"title": "Save one hour this week with AI",
                 "steps": ["List three tasks you repeat every week.",
                           "Pick the one with the clearest input and output.",
                           "Write a reusable prompt for it and save it somewhere handy.",
                           "Use it three times and refine it after each run."],
                 "roles": ["everyone"]}],
}

TAG_PRIORITY = ["agents", "coding", "evals", "rag", "models", "multimodal", "safety", "research", "open-source"]


def _pick(table: dict[str, list[dict]], tags: list[str], day: date) -> tuple[str, dict]:
    for t in TAG_PRIORITY:
        if t in tags and t in table:
            options = table[t]
            return t, options[day.toordinal() % len(options)]
    options = table["default"]
    return "default", options[day.toordinal() % len(options)]


def prompt_for(item_title: str, tags: list[str], day: date) -> dict:
    _, tpl = _pick(PROMPTS, tags, day)
    return {"title": tpl["title"], "prompt": tpl["prompt"],
            "useCase": f"Inspired by today's item: {item_title}"[:300], "roles": list(tpl["roles"])}


def workflow_for(tags: list[str], day: date) -> dict:
    _, tpl = _pick(WORKFLOWS, tags, day)
    return {"title": tpl["title"], "steps": list(tpl["steps"]), "roles": list(tpl["roles"])}
