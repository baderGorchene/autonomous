"""
Autonomous AI Agent — powered by Gemini + Context7
Runs every 30 minutes via GitHub Actions.
Memory is persisted in memory.json inside the repo.
Context7 fetches live, up-to-date library docs before each code generation step.
"""

import json
import os
import re
import time
import requests
from google import genai
from google.genai import types
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY   = os.environ["GEMINI_API_KEY"]
CONTEXT7_API_KEY = os.environ.get("CONTEXT7_API_KEY", "")   # optional, raises rate limits
# Updated to GA version to avoid May 25 shutdown
GEMINI_MODEL     = "gemini-3.1-flash-lite" 

MEMORY_FILE      = Path("memory.json")
PROGRESS_FILE    = Path("PROGRESS.md")
COMMIT_MSG_FILE  = Path("commit_msg.txt")
SRC_DIR          = Path("src")

SRC_DIR.mkdir(exist_ok=True)

# ── Gemini setup ──────────────────────────────────────────────────────────────
# In google-genai, the client handles model interaction directly.
client = genai.Client(api_key=GEMINI_API_KEY)


# ── Context7 helpers ──────────────────────────────────────────────────────────
C7_HEADERS = {"Authorization": f"Bearer {CONTEXT7_API_KEY}"} if CONTEXT7_API_KEY else {}
C7_BASE     = "https://context7.com/api/v2"


def c7_search_library(library_name: str) -> str | None:
    """Search Context7 for a library and return its ID."""
    try:
        r = requests.get(
            f"{C7_BASE}/libs/search",
            headers=C7_HEADERS,
            params={"libraryName": library_name},
            timeout=10,
        )
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                lib_id = results[0]["id"]
                print(f"[Context7] Found library: {results[0]['title']} → {lib_id}")
                return lib_id
        print(f"[Context7] No library found for '{library_name}' (status {r.status_code})")
    except Exception as e:
        print(f"[Context7] Search error: {e}")
    return None


def c7_get_docs(library_id: str, query: str, tokens: int = 4000) -> str:
    """Fetch up-to-date documentation snippets from Context7."""
    try:
        r = requests.get(
            f"{C7_BASE}/context",
            headers=C7_HEADERS,
            params={
                "libraryId": library_id,
                "query": query,
                "tokens": tokens,
                "type": "json",
            },
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            parts = []

            for snippet in data.get("codeSnippets", []):
                title = snippet.get("codeTitle", "")
                for code in snippet.get("codeList", []):
                    lang = code.get("lang", "")
                    parts.append(f"### {title}\n```{lang}\n{code['code']}\n
```")

            for info in data.get("infoSnippets", []):
                content = info.get("content", "")
                if content:
                    parts.append(content)

            result = "\n\n".join(parts)
            print(f"[Context7] Fetched {len(parts)} snippets for '{query}'")
            return result
        else:
            print(f"[Context7] Context fetch failed: {r.status_code}")
    except Exception as e:
        print(f"[Context7] Docs error: {e}")
    return ""


def fetch_docs_for_task(task: str, libraries: list[str]) -> str:
    """
    Given a task description and list of libraries the agent needs,
    query Context7 for each and return a combined docs block.
    """
    if not libraries:
        return ""

    all_docs = []
    for lib_name in libraries:
        lib_id = c7_search_library(lib_name)
        if lib_id:
            docs = c7_get_docs(lib_id, query=task, tokens=3000)
            if docs:
                all_docs.append(f"## 📚 {lib_name} (live docs via Context7)\n\n{docs}")
        time.sleep(0.5)   # small delay to respect rate limits

    return "\n\n---\n\n".join(all_docs)


# ── Memory helpers ─────────────────────────────────────────────────────────────
DEFAULT_MEMORY = {
    "business_idea": "A SaaS tool that helps solo founders track their MRR, churn, and growth metrics with a simple dashboard — no Stripe required, works with manual data entry.",
    "current_phase": "project_setup",
    "completed_steps": [],
    "next_task": "Create the project structure: a FastAPI backend with a health endpoint, and a basic HTML/JS frontend skeleton.",
    "libraries_in_use": ["fastapi", "uvicorn"],
    "iteration": 0,
    "last_run": "",
    "notes": ""
}

def load_memory() -> dict:
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE) as f:
            return json.load(f)
    print("[Memory] No memory.json found — initialising with defaults.")
    return DEFAULT_MEMORY.copy()

def save_memory(memory: dict):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

def update_progress(note: str, iteration: int):
    header = f"## Iteration {iteration}\n_{time.strftime('%Y-%m-%d %H:%M UTC')}_\n\n{note}\n\n"
    existing = PROGRESS_FILE.read_text() if PROGRESS_FILE.exists() else ""
    PROGRESS_FILE.write_text(header + existing)


# ── Source code reader ────────────────────────────────────────────────────────
def read_src_files(max_chars: int = 8000) -> dict[str, str]:
    """Read current source files (truncated to keep prompt manageable)."""
    files = {}
    total = 0
    for path in sorted(SRC_DIR.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".html", ".js", ".ts", ".css", ".json", ".md", ".yaml", ".yml", ".txt", ".toml"}:
            content = path.read_text(errors="ignore")
            if total + len(content) > max_chars:
                files[str(path)] = content[: max_chars - total] + "\n... [truncated]"
                break
            files[str(path)] = content
            total += len(content)
    return files


# ── Gemini call ────────────────────────────────────────────────────────────────
def call_gemini(prompt: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            # Correct call structure for google-genai SDK
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=8192,
                    temperature=0.7,
                ),
            )
            return response.text
        except Exception as e:
            wait = 2 ** attempt * 5
            print(f"[Gemini] Error (attempt {attempt + 1}): {e} — retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError("Gemini failed after all retries.")


# ── Response parser ────────────────────────────────────────────────────────────
def parse_response(text: str) -> dict:
    """Extract JSON block from Gemini's response."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        raw = match.group(1)
    else:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            raw = match.group(0)
        else:
            raise ValueError("No JSON found in Gemini response.")

    raw = re.sub(r",\s*([\}\]])", r"\1", raw)
    return json.loads(raw)


# ── Main agent loop ────────────────────────────────────────────────────────────
def run():
    print("=" * 60)
    print(f"🤖 Agent starting — {time.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    memory = load_memory()
    memory["iteration"] += 1
    memory["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    iteration = memory["iteration"]

    print(f"[Agent] Iteration #{iteration}")
    print(f"[Agent] Phase: {memory['current_phase']}")
    print(f"[Agent] Next task: {memory['next_task']}")

    # ── Step 1: Fetch live docs from Context7 ─────────────────────────────────
    libraries = memory.get("libraries_in_use", [])
    print(f"[Context7] Fetching docs for libraries: {libraries}")
    live_docs = fetch_docs_for_task(memory["next_task"], libraries)

    # ── Step 2: Read current source files ─────────────────────────────────────
    src_files = read_src_files()

    # ── Step 3: Build the agent prompt ────────────────────────────────────────
    docs_section = f"""
=== LIVE DOCUMENTATION (fetched right now from Context7) ===
{live_docs}
=== END LIVE DOCS ===
""" if live_docs else "=== No live docs available this run ==="

    prompt = f"""You are an autonomous software agent building a real startup product.
You run every 30 minutes. Each run you complete ONE focused task and commit your work.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUSINESS IDEA:
{memory['business_idea']}

CURRENT PHASE: {memory['current_phase']}
ITERATION: #{iteration}
COMPLETED STEPS: {json.dumps(memory['completed_steps'], indent=2)}
NEXT TASK: {memory['next_task']}
NOTES FROM LAST RUN: {memory.get('notes', 'none')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{docs_section}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CURRENT SOURCE FILES:
{json.dumps(src_files, indent=2) if src_files else "No files yet — start from scratch."}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

YOUR JOB THIS RUN:
1. Complete the "next_task" above using the live docs provided.
2. Write production-quality code. Use correct, current API patterns from the docs.
3. Decide what libraries you'll need in the NEXT task and list them.

Respond ONLY with a valid JSON object (no extra text, no markdown except the code block):
```json
{{
  "files": {{
    "src/example.py": "# full file content here"
  }},
  "next_task": "Description of what to do next run",
  "current_phase": "e.g. backend_core / frontend / testing / polish",
  "libraries_for_next_task": ["fastapi", "sqlalchemy"],
  "commit_message": "feat: add user auth endpoint with JWT",
  "progress_note": "Built the login endpoint using FastAPI and python-jose.",
  "notes": "Any important context or decisions to remember for next run."
}}
