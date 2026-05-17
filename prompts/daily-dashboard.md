# Daily Dashboard

Apply the **engineering-pulse** Agent Skill and run the full workflow in this repo.

1. Read [`skills/engineering-pulse/SKILL.md`](../skills/engineering-pulse/SKILL.md)
2. Follow [`skills/engineering-pulse/references/daily-workflow.md`](../skills/engineering-pulse/references/daily-workflow.md) and linked references (env, stakeholder pulse when `STAKEHOLDERS` is set)
3. **Execute** all steps from the workspace root — do not stop until SMTP reports `Sent to <SMTP_TO>`

**Time window:** past 7 days (`--days 7` on Datadog extracts).
