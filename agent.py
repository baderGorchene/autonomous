"""
Autonomous AI Agent — powered by Gemini + Context7
Runs every 30 minutes via GitHub Actions.
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
CONTEXT7_API_KEY = os.environ.get("CONTEXT7_API_KEY", "")
GEMINI_MODEL     = "gemini-3.1-flash-lite" 

MEMORY_FILE      = Path("memory.json")
PROGRESS_FILE    = Path("PROGRESS.md")
COMMIT_MSG_FILE  = Path("commit_msg.txt")
SRC_DIR          = Path("src")

SRC_DIR.mkdir(exist_ok=True)

# ── Gemini setup ──────────────────────────────────────────────────────────────
client = genai.Client(api_key=GEMINI_API_KEY)

# ── Context7 helpers ──────────────────────────────────────────────────────────
C7_HEADERS = {"Authorization": f"Bearer {CONTEXT7_API_KEY}"} if CONTEXT7_API_KEY else {}
C7_BASE     = "https://context7.com/api/v2"

def c7_search_library(library_name: str) -> str | None:
    try:
        r = requests.get(
            f"{C7_BASE}/libs/search",
            headers=C7_HEADERS,
            params={"libraryName": library_name},
            timeout=10,
        )
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results: return results[0]["id"]
    except Exception as e:
        print(f"[Context7] Search error: {e}")
    return None

def c7_get_docs(library_id: str, query: str, tokens: int = 4000) -> str:
    try:
        r = requests.get(
            f"{C7_BASE}/context",
            headers=C7_HEADERS,
            params={"libraryId": library_id, "query": query, "tokens": tokens, "type": "json"},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            parts = [f"### {s['codeTitle']}\n```{c['lang']}\n{c['code']}\n
```" 
                     for s in data.get("codeSnippets", []) for c in s.get("codeList", [])]
            parts += [i.get("content", "") for i in data.get("infoSnippets", []) if i.get("content")]
            return "\n\n".join(parts)
    except Exception as e:
        print(f"[Context7] Docs error: {e}")
    return ""

def fetch_docs_for_task(task: str, libraries: list[str]) -> str:
    if not libraries: return ""
    all_docs = []
    for lib_name in libraries:
        lib_id = c7_search_library(lib_name)
        if lib_id:
            docs = c7_get_docs(lib_id, query=task, tokens=3000)
            if docs: all_docs.append(f"## 📚 {lib_name}\n\n{docs}")
        time.sleep(0.5)
    return "\n\n---\n\n".join(all_docs)

# ── Memory helpers ─────────────────────────────────────────────────────────────
def load_memory() -> dict:
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE) as f: return json.load(f)
    return {"iteration": 0, "next_task": "Initial setup", "libraries_in_use": []}

def save_memory(memory: dict):
    with open(MEMORY_FILE, "w") as f: json.dump(memory, f, indent=2)

def update_progress(note: str, iteration: int):
    header = f"## Iteration {iteration}\n_{time.strftime('%Y-%m-%d %H:%M UTC')}_\n\n{note}\n\n"
    existing = PROGRESS_FILE.read_text() if PROGRESS_FILE.exists() else ""
    PROGRESS_FILE.write_text(header + existing)

def read_src_files(max_chars: int = 8000) -> dict[str, str]:
    files = {}
    total = 0
    for path in sorted(SRC_DIR.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".html", ".js", ".css", ".json"}:
            content = path.read_text(errors="ignore")
            if total + len(content) > max_chars: break
            files[str(path)] = content
            total += len(content)
    return files

# ── Gemini call ────────────────────────────────────────────────────────────────
def call_gemini(prompt: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=8192,
                    temperature=0.7,
                    # FORCES Gemini to output valid JSON
                    response_mime_type="application/json"
                ),
            )
            return response.text
        except Exception as e:
            wait = 2 ** attempt * 5
            print(f"[Gemini] Error: {e} — retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError("Gemini failed after retries.")

# ── Response parser ────────────────────────────────────────────────────────────
def parse_response(text: str) -> dict:
    """Robust parser that finds the outermost JSON object."""
    try:
        # Find the first '{' and the last '}' to handle greedy matching correctly
        start = text.find('{')
        end = text.rfind('}') + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON object found in response.")
        
        raw = text[start:end]
        # Remove common trailing comma issues before loading
        raw = re.sub(r",\s*([\}\]])", r"\1", raw)
        return json.loads(raw)
    except Exception as e:
        print(f"FAILED TO PARSE: {text}")
        raise ValueError(f"JSON Parse Error: {e}")

# ── Main agent loop ────────────────────────────────────────────────────────────
def run():
    print("🤖 Agent starting...")
    memory = load_memory()
    memory["iteration"] = memory.get("iteration", 0) + 1
    iteration = memory["iteration"]

    live_docs = fetch_docs_for_task(memory.get("next_task", ""), memory.get("libraries_in_use", []))
    src_files = read_src_files()

    prompt = f"""You are an autonomous software agent. 
BUSINESS IDEA: {memory.get('business_idea', 'N/A')}
CURRENT TASK: {memory.get('next_task', 'N/A')}

=== LIVE DOCUMENTATION ===
{live_docs}

=== CURRENT FILES ===
{json.dumps(src_files)}

Output a JSON object with these exact keys:
"files" (dict of path: content), "next_task" (string), "current_phase" (string), 
"libraries_for_next_task" (list), "commit_message" (string), "progress_note" (string), "notes" (string).
"""

    raw_response = call_gemini(prompt)
    parsed = parse_response(raw_response)

    files_written = []
    for filepath, content in parsed.get("files", {}).items():
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content))
        files_written.append(str(p))

    # Update state
    memory["next_task"] = parsed.get("next_task", "Continue")
    memory["current_phase"] = parsed.get("current_phase", "development")
    memory["libraries_in_use"] = parsed.get("libraries_for_next_task", [])
    memory["notes"] = parsed.get("notes", "")
    save_memory(memory)

    update_progress(parsed.get("progress_note", "Update."), iteration)
    COMMIT_MSG_FILE.write_text(parsed.get("commit_message", f"chore: iteration {iteration}"))
    print(f"✅ Run {iteration} complete.")

if __name__ == "__main__":
    run()
