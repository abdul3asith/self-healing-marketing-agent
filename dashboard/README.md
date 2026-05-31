# Dashboard (Person D)

Minimal UI: live score chart + fix-attempt log + audit trail.
Decision (open #1): FastAPI + one HTML/JS page, OR CLI + static chart — whichever
Person D can polish fastest. A trigger button calls fixer.orchestrate.attempt_self_heal.
Serve with: uvicorn dashboard.app:app --reload (once app.py exists).
