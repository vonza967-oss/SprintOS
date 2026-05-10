from __future__ import annotations

import html
import json
from typing import Any


EXAMPLE_PROMPT_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "id": "canonical",
        "title": "Canonical examples",
        "note": "Known app patterns with stricter verification.",
        "kind": "canonical",
        "examples": (
            {
                "label": "Idea Scorecard",
                "prompt": "Create an Idea Scorecard where founders paste a rough business idea and see a local score, risks, smallest test, and next action.",
            },
            {
                "label": "Budget Snapshot",
                "prompt": "Create a Budget Snapshot where users enter monthly income and expenses and see savings, spending breakdown, and a practical recommendation.",
            },
            {
                "label": "Study Card Builder",
                "prompt": "Create a Study Card Builder where students paste study notes and get local flashcards they can review immediately.",
            },
            {
                "label": "Decision Matrix",
                "prompt": "Create a Decision Matrix where I enter options and criteria, compare them locally, see a ranked list, recommendation, and tradeoff notes.",
            },
            {
                "label": "Pricing ROI Calculator",
                "prompt": "Create a Pricing ROI Calculator where I enter price, unit cost, customers, and investment, then see revenue, margin, break-even, payback, and a recommendation.",
            },
        ),
    },
    {
        "id": "generic",
        "title": "Generic examples",
        "note": "Universal local prototype prompts.",
        "kind": "generic/custom",
        "examples": (
            {
                "label": "Habit Tracker",
                "prompt": "Create a local habit tracker that lets a user enter habits, mark completion, see today's progress, and reset the day.",
            },
            {
                "label": "Mini CRM",
                "prompt": "Create a local mini CRM for freelancers to track leads, status, next follow-up date, and notes.",
            },
            {
                "label": "Inventory Tracker",
                "prompt": "Create a local inventory tracker for a small shop with item name, quantity, reorder threshold, and low-stock alerts.",
            },
            {
                "label": "Content Calendar",
                "prompt": "Create a local content calendar planner with post idea, channel, deadline, status, and a weekly overview.",
            },
        ),
    },
    {
        "id": "broad",
        "title": "Broad arbitrary examples",
        "note": "Custom prompts that stay on the generic verifier path.",
        "kind": "generic/custom",
        "examples": (
            {
                "label": "Tattoo Studio CRM",
                "prompt": "Create a local CRM for a tattoo studio to track clients, tattoo ideas, appointment dates, deposits, status, and follow-up notes.",
            },
            {
                "label": "Barber Booking Tracker",
                "prompt": "Create a local booking tracker for a barber to manage client names, service type, appointment time, status, and daily schedule.",
            },
            {
                "label": "Landscaping Quote Estimator",
                "prompt": "Create a local quote estimator for a landscaping business with job type, yard size, material cost, labor hours, and a final estimate.",
            },
            {
                "label": "Client Onboarding Checklist",
                "prompt": "Create a local client onboarding checklist for an agency with client name, onboarding tasks, owner, due date, status, and progress summary.",
            },
            {
                "label": "Meal Planner",
                "prompt": "Create a local weekly meal planner with meals, ingredients, dietary notes, shopping list, and weekly overview.",
            },
            {
                "label": "Workout Planner",
                "prompt": "Create a local workout planner with exercises, sets, reps, target muscle group, weekly schedule, and progress notes.",
            },
            {
                "label": "Event Planner",
                "prompt": "Create a local event planner with event name, date, tasks, vendors, budget notes, and readiness summary.",
            },
            {
                "label": "Support Ticket Board",
                "prompt": "Create a local support ticket board with ticket title, customer, priority, status, notes, and open issue summary.",
            },
            {
                "label": "Lesson Planner",
                "prompt": "Create a local lesson planner for teachers with lesson topic, objectives, activities, materials, homework, and class notes.",
            },
            {
                "label": "Agency Project Tracker",
                "prompt": "Create a local project tracker for a small agency with project name, client, deadline, status, owner, next action, and workload summary.",
            },
        ),
    },
)


def example_prompt_groups_json() -> str:
    return json.dumps(EXAMPLE_PROMPT_GROUPS, ensure_ascii=True)


def render_example_prompt_gallery(prefix: str) -> str:
    prefix_attr = html.escape(prefix, quote=True)
    groups_html: list[str] = []
    for group in EXAMPLE_PROMPT_GROUPS:
        examples = []
        for example in group["examples"]:
            examples.append(
                '<button type="button" class="secondary mini example-prompt-button" '
                f'data-demo-prompt="{html.escape(example["prompt"], quote=True)}" '
                f'data-demo-kind="{html.escape(group["kind"], quote=True)}" '
                f'onclick="fillExamplePrompt(this, \'{prefix_attr}\')">'
                f'{html.escape(example["label"], quote=True)}</button>'
            )
        groups_html.append(
            '<div class="example-prompt-group">'
            '<div class="example-prompt-group-head">'
            f'<strong>{html.escape(group["title"], quote=True)}</strong>'
            f'<span class="tiny-badge">{html.escape(group["kind"], quote=True)}</span>'
            '</div>'
            f'<p class="muted">{html.escape(group["note"], quote=True)}</p>'
            f'<div class="example-prompt-buttons">{"".join(examples)}</div>'
            '</div>'
        )
    return (
        '<details class="resume-plan example-prompt-gallery">'
        '<summary><strong>Example Prompt Gallery</strong></summary>'
        '<p class="muted">Pick one to fill the Create App prompt. Examples do not call AI or create anything until you click Create App.</p>'
        f'<div data-example-gallery-prefix="{prefix_attr}">'
        f'{"".join(groups_html)}'
        '</div>'
        '</details>'
    )
