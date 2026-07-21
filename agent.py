"""
Autonomous AI Agent — powered by Gemini + Context7
Runs every 30 minutes via GitHub Actions.
"""

import sys
import json
import os
import re
import time
import requests
import subprocess
from google import genai
from google.genai import types
from pathlib import Path
from pydantic import BaseModel, Field

# Ensure stdout/stderr use UTF-8 encoding on Windows to prevent UnicodeEncodeError with emojis
if sys.platform.startswith("win"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "")
CONTEXT7_API_KEY = os.environ.get("CONTEXT7_API_KEY", "")
GEMINI_MODEL     = "gemini-2.5-flash" 

MEMORY_FILE      = Path("memory.json")
PROGRESS_FILE    = Path("PROGRESS.md")
COMMIT_MSG_FILE  = Path("commit_msg.txt")
SRC_DIR          = Path("src")

SRC_DIR.mkdir(exist_ok=True)

class FileEdit(BaseModel):
    path: str = Field(description="The path of the file to modify or create.")
    content: str = Field(description="The complete new content of the file.")

# ── Response Schema ───────────────────────────────────────────────────────────
class AgentResponse(BaseModel):
    files: list[FileEdit] = Field(description="A list of files to be modified/created.")
    next_task: str = Field(description="The next task the agent should work on.")
    current_phase: str = Field(description="The current phase of the project.")
    libraries_for_next_task: list[str] = Field(description="Any libraries needed for the next task.")
    commit_message: str = Field(description="Commit message for the changes.")
    progress_note: str = Field(description="A note describing the progress made.")
    notes: str = Field(description="Any additional notes or observations.")
    roadmap: list[str] = Field(description="The updated roadmap.")
    completed_steps: list[str] = Field(description="The updated list of completed steps.")

# ── Gemini setup ──────────────────────────────────────────────────────────────
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

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
        if r.status_code != 200:
            return ""
            
        data = r.json()
        parts = []
        
        # Process code snippets with triple quotes for safety
        for snippet in data.get("codeSnippets", []):
            title = snippet.get("codeTitle", "Untitled")
            for code_item in snippet.get("codeList", []):
                lang = code_item.get("lang", "python")
                code = code_item.get("code", "")
                parts.append(f"""### {title}\n```{lang}\n{code}\n
```""")

        # Process info snippets
        for info in data.get("infoSnippets", []):
            content = info.get("content", "")
            if content:
                parts.append(content)
                
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
            try:
                content = path.read_text(errors="ignore")
                if total + len(content) > max_chars: break
                files[str(path)] = content
                total += len(content)
            except: continue
    return files

# ── Gemini call ────────────────────────────────────────────────────────────────
def call_gemini(prompt: str, retries: int = 3) -> str:
    if not client:
        raise ValueError("GEMINI_API_KEY environment variable is not set. Please set it to run the agent.")
    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=65536,
                    temperature=0.7,
                    response_mime_type="application/json",
                    response_schema=AgentResponse
                ),
            )
            candidate = response.candidates[0] if response.candidates else None
            finish_reason = getattr(candidate, "finish_reason", None)
            if finish_reason is not None and str(finish_reason) not in ("STOP", "FinishReason.STOP", "1"):
                print(f"[Gemini] Response truncated or blocked: finish_reason={finish_reason}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt * 5)
                    continue
                raise RuntimeError(
                    f"Gemini response did not finish normally (finish_reason={finish_reason}). "
                    "Likely hit max_output_tokens — the task is too large for one response."
                )
            return response.text
        except Exception as e:
            wait = 2 ** attempt * 5
            print(f"[Gemini] Error: {e} — retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError("Gemini failed after retries.")

# ── Response parser ────────────────────────────────────────────────────────────
def parse_response(text: str) -> dict:
    try:
        # With response_mime_type="application/json", the response should be
        # pure JSON — try direct parse first.
        stripped = text.strip()
        if stripped:
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass

        # Fallback: extract JSON object from surrounding text
        start = stripped.find('{')
        end = stripped.rfind('}') + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON object found.")

        raw = stripped[start:end]
        # Clean up trailing commas before closing braces/brackets
        raw = re.sub(r",\s*([\}\]])", r"\1", raw)
        return json.loads(raw)
    except Exception as e:
        print(f"DEBUG: Raw response from Gemini: {text}")
        raise ValueError(f"JSON Parse Error: {e}")


def run_tests() -> tuple[bool, str]:
    """Runs pytest on the repository and returns (success, output)."""
    print("🧪 Running tests...")
    try:
        res = subprocess.run(
            ["python", "-m", "pytest"],
            capture_output=True,
            text=True,
            timeout=45
        )
        success = (res.returncode == 0)
        output = f"Exit code: {res.returncode}\n\nSTDOUT:\n{res.stdout}\n\nSTDERR:\n{res.stderr}"
        return success, output
    except subprocess.TimeoutExpired as e:
        output = f"Test run timed out:\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}"
        return False, output
    except Exception as e:
        return False, f"Failed to execute tests: {e}"

# ── Main agent loop ────────────────────────────────────────────────────────────
def run_iteration():
    print("🤖 Agent starting...")
    memory = load_memory()
    memory["iteration"] = memory.get("iteration", 0) + 1
    iteration = memory["iteration"]

    task = memory.get("next_task", "Continue building BookSlot")
    libs = memory.get("libraries_in_use", [])
    
    live_docs = fetch_docs_for_task(task, libs)
    src_files = read_src_files()

    initial_prompt = f"""You are an autonomous software agent. 
BUSINESS IDEA: {memory.get('business_idea', 'N/A')}
CURRENT TASK: {task}
COMPLETED STEPS: {json.dumps(memory.get('completed_steps', []))}
ROADMAP: {json.dumps(memory.get('roadmap', []))}

=== LIVE DOCUMENTATION ===
{live_docs}

=== CURRENT FILES ===
{json.dumps(src_files)}

Output a JSON object with these exact keys:
"files" (list of objects containing "path" and "content"), 
"next_task" (string), 
"current_phase" (string), 
"libraries_for_next_task" (list), 
"commit_message" (string), 
"progress_note" (string), 
"notes" (string),
"roadmap" (list of strings representing the updated roadmap),
"completed_steps" (list of strings representing the updated completed steps).

You are encouraged to dynamically update the roadmap (add, remove, or modify items) and mark completed steps based on your progress.
"""

    current_prompt = initial_prompt
    max_healing_attempts = 3
    parsed = {}
    success = False
    test_output = ""

    for attempt in range(max_healing_attempts + 1):
        if attempt > 0:
            print(f"🩹 Self-healing attempt {attempt}/{max_healing_attempts}...")
            # Re-read files to capture the state edited by previous generation
            src_files = read_src_files()
            current_prompt = f"""You are an autonomous software agent.
BUSINESS IDEA: {memory.get('business_idea', 'N/A')}
CURRENT TASK: {task}
COMPLETED STEPS: {json.dumps(memory.get('completed_steps', []))}
ROADMAP: {json.dumps(memory.get('roadmap', []))}

=== TEST FAILURE OUTPUT ===
{test_output}

=== CURRENT FILES ===
{json.dumps(src_files)}

The previous code changes caused test failures. Analyze the error output above, inspect the current files, and fix the bugs.
Rewrite or modify only the necessary files. Do not break unrelated functionality.
Ensure you output the complete corrected files in the JSON object.

Output a JSON object with these exact keys:
"files" (list of objects containing "path" and "content"), 
"next_task" (string), 
"current_phase" (string), 
"libraries_for_next_task" (list), 
"commit_message" (string), 
"progress_note" (string), 
"notes" (string),
"roadmap" (list of strings representing the updated roadmap),
"completed_steps" (list of strings representing the updated completed steps).
"""

        try:
            raw_response = call_gemini(current_prompt)
            parsed = parse_response(raw_response)
        except Exception as e:
            print(f"❌ Gemini call or JSON parse failed: {e}")
            if attempt == 0:
                raise e
            break

        # Save generated/fixed files
        files_data = parsed.get("files", [])
        if isinstance(files_data, list):
            # Convert list of FileEdit to a dict
            files_dict = {}
            for f in files_data:
                if isinstance(f, dict):
                    files_dict[f.get("path")] = f.get("content")
                elif hasattr(f, "path") and hasattr(f, "content"):
                    files_dict[f.path] = f.content
            files_data = files_dict

        for filepath, content in files_data.items():
            p = Path(filepath)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(content), encoding="utf-8")

        # Run tests
        success, test_output = run_tests()
        if success:
            print("✨ All tests passed!")
            break
        else:
            print(f"❌ Tests failed on attempt {attempt}:")
            print(test_output[:1000] + ("\n... [truncated]" if len(test_output) > 1000 else ""))

    if not success:
        print(f"⚠️ Proceeding with iteration {iteration} despite test failures after {max_healing_attempts} self-healing attempts.")

    # Update state
    if parsed:
        memory["next_task"] = parsed.get("next_task", "Continue")
        memory["current_phase"] = parsed.get("current_phase", "development")
        memory["libraries_in_use"] = parsed.get("libraries_for_next_task", [])
        memory["notes"] = parsed.get("notes", "")
        if "roadmap" in parsed:
            memory["roadmap"] = parsed["roadmap"]
        if "completed_steps" in parsed:
            memory["completed_steps"] = parsed["completed_steps"]
        save_memory(memory)

        update_progress(parsed.get("progress_note", "No note provided."), iteration)
        COMMIT_MSG_FILE.write_text(parsed.get("commit_message", f"chore: iteration {iteration}"), encoding="utf-8")
    
    print(f"✅ Run {iteration} complete.")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous AI Agent")
    parser.add_argument("--loop", action="store_true", help="Run the agent in a continuous loop")
    parser.add_argument("--interval", type=int, default=60, help="Sleep interval between iterations in seconds")
    args = parser.parse_args()

    if args.loop:
        print(f"🔄 Starting continuous loop (interval: {args.interval}s)...")
        while True:
            try:
                run_iteration()
            except Exception as e:
                print(f"❌ Error during iteration: {e}")
            print(f"Sleeping for {args.interval}s...")
            time.sleep(args.interval)
    else:
        run_iteration()

if __name__ == "__main__":
    main()
