<!-- SKIP: This is a reference example only. Do NOT include this file in the report. -->

# Example — Extra Task Plugin

> **This file is a format reference only.** The renderer skips any file in
> this directory whose name starts with `_`.
>
> To add a real extra task, drop a new `*.md` file into `prompts/extras/`.
> The next dashboard run will pick it up automatically — no code changes
> needed.

---

## How it works

Each `*.md` file in `prompts/extras/` becomes one card under **Part E —
Extras** in the daily report.

- The first `# Heading` is used as the card **title**.
- Everything below is rendered as the card **body**.
- If there is no `# Heading`, the filename (without `.md`) is the title and
  the entire file is the body.

## What you can put in a file

The renderer supports a small but useful markdown subset:

- `#`, `##`, `###` headings
- **bold**, *italic*, and `inline code`
- Bullet lists and `1.` numbered lists
- [Links](https://example.com) and bare URLs like https://example.com
- Fenced code blocks:

```
echo "drop me anywhere — I'll show up in the next run"
```

That's it — drop the file, run the dashboard, your card appears.
