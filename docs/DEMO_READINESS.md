# Demo Readiness v1

This page summarizes what SprintOS can show after the canonical, generic, and broad arbitrary app-generation acceptance passes. It is a lightweight demo guide, not a generated report.

## Acceptance Coverage

- Canonical acceptance covers `Idea Scorecard`, `Budget Snapshot`, `Study Card Builder`, `Decision Matrix`, and `Pricing ROI Calculator`.
- Generic acceptance covers `Habit Tracker`, `Mini CRM`, `Inventory Tracker`, and `Content Calendar`.
- Broad arbitrary acceptance covers `Tattoo Studio CRM`, `Barber Booking Tracker`, `Landscaping Quote Estimator`, `Client Onboarding Checklist`, `Meal Planner`, `Workout Planner`, `Event Planner`, `Support Ticket Board`, `Lesson Planner`, and `Agency Project Tracker`.

Live acceptance reports are local, redacted, and not committed. This summary intentionally names only the case coverage and does not embed provider payloads, secrets, or generated report contents.

## Demo Flow

1. Start SprintOS locally with `python3 sprintos.py`.
2. Paste one recommended prompt into Create App.
3. Show Intent Review and App Blueprint if SprintOS displays them.
4. Click Create App.
5. Open Preview.
6. Click Test App.
7. Download App.
8. Show Source Pack as the editable handoff files.
9. Prepare App for Codex.
10. Try a vague prompt such as `Build an app for my business` and show the follow-up questions plus Generate With Assumptions.

## Recommended Demo Prompts

Canonical:

```text
Create an Idea Scorecard where founders paste a rough business idea and see a local score, risks, smallest test, and next action.
```

Generic:

```text
Create a local mini CRM for freelancers to track leads, status, next follow-up date, and notes.
```

Broad arbitrary:

```text
Create a local booking tracker for a barber to manage client names, service type, appointment time, status, and daily schedule.
```
