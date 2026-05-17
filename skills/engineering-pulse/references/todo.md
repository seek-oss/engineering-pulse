# Tasks & reading queue (Todoist)

Execution task — parse intent and run the command. No confirmation needed.

**Prerequisites:** `TODOIST_API_TOKEN`, `TODOIST_PROJECT_ID` (run `python3 scripts/todo.py setup` if missing).

## Add task (work)

```bash
python3 scripts/todo.py add "<title>" --priority <high|medium|low>
```

Personal: `--domain personal`. Urgency words → priority.

## Add reading item

```bash
python3 scripts/todo.py add "<title>" --type read --url "<url>"
```

## List

```bash
python3 scripts/todo.py list
python3 scripts/todo.py list --type read
```

## Done / cancel

Look up ID via `list` if needed, then `done <id>` or `cancel <id>`.

Confirm result in one sentence.
