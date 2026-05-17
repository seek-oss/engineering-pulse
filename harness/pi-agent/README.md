# Pi Agent

Install the skill directory the same way as other Agent Skills consumers:

```bash
ln -sf /path/to/engineering-pulse/skills/engineering-pulse <pi-skills-dir>/engineering-pulse
```

Ensure the agent's workspace is the engineering-pulse repo root (or `~/.engineering-pulse`) so `scripts/` and `.env` resolve.

Document Pi-specific manifest paths here when your Pi Agent version publishes a stable skill layout.
