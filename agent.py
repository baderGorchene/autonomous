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
                    content = f"""### {title}\n```{lang}\n{code.get('code', '')}\n```"""
                    parts.append(content)

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
    if not libraries:
        return ""
    all_docs = []
    for lib_name in libraries:
        lib_id = c7_search_library(lib_name)
        if lib_id:
            docs = c7_get_docs(lib_id, query=task, tokens=3000)
            if docs:
                all_docs.append(f"## 📚 {lib_name} (live docs via Context7)\n\n{docs}")
        time.sleep(0.5)
    return "\n\n---\n\n".join(all_docs)

# ── Memory helpers ─────────────────────────────────────────────────────────────
DEFAULT_MEMORY = {
    "business_idea": "A SaaS tool that helps solo founders track their MRR, churn, and growth metrics.",
    "current_phase": "project_setup",
    "completed_steps": [],
    "next_task": "Create the project structure: a FastAPI backend with a health endpoint.",
    "libraries_in_use": ["fastapi", "uvicorn"],
    "iteration": 0,
    "last_run": "",
    "notes": ""
}

def load_memory() -> dict:
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE) as f:
            return json.load(f)
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
            print(f"[Gemini] Error: {e} — retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError("Gemini failed after retries.")

# ── Response parser ────────────────────────────────────────────────────────────
def parse_response(text: str) -> dict:
    # Fixed the unterminated string literal here by keeping it on one line
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        raw = match.group(1)
    else:
        # Made this regex non-greedy to avoid swallowing trailing text
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            raw = match.group(0)
        else:
            raise ValueError("No JSON found in response.")
            
    raw = re.sub(r",\s*([\}\]])", r"\1", raw)
    return json.loads(raw)

# ── Main agent loop ────────────────────────────────────────────────────────────
def run():
    print("🤖 Agent starting...")
    memory = load_memory()
    memory["iteration"] += 1
    iteration = memory["iteration"]

    live_docs = fetch_docs_for_task(memory["next_task"], memory.get("libraries_in_use", []))
    src_files = read_src_files()

    docs_section = f"=== LIVE DOCS ===\n{live_docs}\n" if live_docs else ""
    
    prompt = f"""You are an autonomous agent. 
BUSINESS: {memory['business_idea']}
TASK: {memory['next_task']}
{docs_section}
FILES: {json.dumps(src_files)}

Return ONLY a valid JSON object with the following keys:
- "files": a dictionary mapping file paths to their string content.
- "next_task": a string.
- "current_phase": a string.
- "libraries_for_next_task": a list of strings.
- "commit_message": a string.
- "progress_note": a string.
- "notes": a string.
"""

    raw_response = call_gemini(prompt)
    parsed = parse_response(raw_response)

    files_written = []
    for filepath, content in parsed.get("files", {}).items():
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content))
        files_written.append(str(p))

    memory["next_task"] = parsed.get("next_task", "Continue building")
    memory["current_phase"] = parsed.get("current_phase", memory.get("current_phase", "project_setup"))
    memory["libraries_in_use"] = parsed.get("libraries_for_next_task", [])
    memory["notes"] = parsed.get("notes", memory.get("notes", ""))
    
    completed = memory.get("completed_steps", [])
    completed.append(f"[#{iteration}] {memory['next_task']}")
    memory["completed_steps"] = completed[-20:] # keep last 20

    save_memory(memory)

    update_progress(parsed.get("progress_note", "Ran successfully."), iteration)
    COMMIT_MSG_FILE.write_text(parsed.get("commit_message", "chore: iteration"))
    print(f"✅ Run {iteration} complete.")

if __name__ == "__main__":
    run()
