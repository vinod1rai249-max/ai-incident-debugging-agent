Run this task using the autonomous agent workflow.

Use:
- Planner Agent
- Executor Agent
- Debugger Agent
- Security Agent
- Reviewer Agent

Rules:
- Plan first
- Wait for approval
- Execute one step at a time
- Run tests
- Fix safe failures automatically
- Stop on risky/destructive actions
- Summarize every step

## Cost Control Rules

- Never run full test suite repeatedly
- Prefer running only failing tests (--lf)
- Fix multiple errors in one iteration
- Avoid analyzing entire repository unless necessary
- Limit unnecessary reasoning steps