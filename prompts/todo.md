# Todo Manager

## Overview

This is an execution task. Parse the user's request and run the appropriate command.
Do not ask for confirmation — just do it.

## Prerequisites

| Variable | Required | Purpose |
|----------|----------|---------|
| `TODOIST_API_TOKEN` | yes | Todoist API token |
| `TODOIST_PROJECT_ID` | yes | Auto-set by `setup`; Todoist project ID |

If `TODOIST_PROJECT_ID` is missing, run `python3 scripts/todo.py setup` first.

---

## Intent mapping

Read the user's message and match it to one of these intents:

### Add a task

Triggers: "remind me to …", "add task …", "todo: …", "I need to …"

**Work** (default — goes to Todoist section **Tasks**):

```bash
python3 scripts/todo.py add "<title>" --priority <high|medium|low>
```

**Personal life** (Todoist section **Personal**):

```bash
python3 scripts/todo.py add "<title>" --domain personal
```

Infer priority from urgency words: "urgent", "ASAP", "critical" → `high`;
"when you get a chance", "eventually" → `low`; otherwise omit (defaults to none).

### Add a reading item

Triggers: "save this article …", "I want to read …", "bookmark …", any message with a URL + reading intent

```bash
python3 scripts/todo.py add "<title>" --type read --url "<url>"
```

If the user only gives a URL, use the domain or path as the title.

### List items

Triggers: "what's on my list?", "show my todos", "reading queue", "what do I need to do?"

```bash
python3 scripts/todo.py list                        # work + personal + reading
python3 scripts/todo.py list --type task            # all tasks (work + personal)
python3 scripts/todo.py list --type task --domain work
python3 scripts/todo.py list --type task --domain personal
python3 scripts/todo.py list --domain personal      # same as --type task --domain personal
python3 scripts/todo.py list --type read            # reading queue only
```

### Mark done

Triggers: "done with …", "finished …", "completed …", "tick off …"

If the user names a task by title (not ID), run `python3 scripts/todo.py list` first
to find the matching ID, then:

```bash
python3 scripts/todo.py done <task-id> --comment "<optional reason>"
```

### Cancel

Triggers: "cancel …", "drop …", "never mind about …", "remove …"

Same ID-lookup logic as done, then:

```bash
python3 scripts/todo.py cancel <task-id> --comment "<optional reason>"
```

---

## Output

After running the command, confirm what happened in one sentence.
If listing, show the table output as-is.
