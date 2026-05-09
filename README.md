# 🤖 Autonomous AI Agent

An agentic AI that builds a real software product autonomously — 
running every 30 minutes via GitHub Actions, writing code and committing it.

## How It Works

```
GitHub Actions cron (every 30 min)
         ↓
   agent.py runs
         ↓
   Reads memory.json  ←── persistent state between runs
         ↓
   Queries Context7 API ←── live, up-to-date library docs
         ↓
   Calls Gemini API  ←── reasons + writes code
         ↓
   Writes files to src/
         ↓
   git commit & push ←── shows on your GitHub profile
```

## Stack

| Component | Tool | Cost |
|-----------|------|------|
| CI/CD runner | GitHub Actions (public repo) | Free ∞ |
| LLM | Gemini 2.5 Flash-Lite | Free tier |
| Live docs | Context7 API | Free tier |
| Memory | `memory.json` in repo | Free |
| Scheduling | GitHub Actions cron | Free |

## Setup

1. Fork or clone this repo (make it **public**)
2. Add secrets in **Settings → Secrets → Actions**:
   - `GEMINI_API_KEY` — from [aistudio.google.com](https://aistudio.google.com)
   - `CONTEXT7_API_KEY` — from [context7.com/dashboard](https://context7.com/dashboard) _(optional, raises rate limits)_
3. Edit `memory.json` → set your `business_idea`
4. Push — first run triggers within 30 minutes

## Files

| File | Purpose |
|------|---------|
| `.github/workflows/agent.yml` | Cron schedule + git commit logic |
| `agent.py` | Agent brain: Context7 + Gemini + file writing |
| `memory.json` | Persistent agent state (phase, tasks, notes) |
| `PROGRESS.md` | Human-readable log of every iteration |
| `src/` | All code the agent writes lives here |

## Customise

Edit `memory.json` anytime to redirect the agent:
- Change `business_idea` to pivot the product
- Change `next_task` to override what it does next run
- Change `libraries_in_use` to influence Context7 doc fetching

---
*Built autonomously. Last updated by the agent.*
