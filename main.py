#!/usr/bin/env python3
"""mlx-code: local Claude Code-style agent via mlx-lm."""
from __future__ import annotations
import argparse, json, re, subprocess, sys, textwrap
from pathlib import Path

try:
    from mlx_lm import load, stream_generate
except ImportError:
    sys.exit("mlx-lm not found.  Run: pip install mlx-lm")

FILES = {

"~/.claude/CLAUDE.md": """## Project
mlx-code — local Claude Code-style agent via mlx-lm on Apple Silicon.

## Stack
Python 3.11+, mlx-lm, no other runtime deps.

## Commands
- mlx-code                       run agent in current directory
- mlx-code --dir ~/project       specify project directory
- mlx-code --model <hf-id>       use a different model
- python main.py                 run without installing

## Conventions
- Type hints on all function signatures
- grep before cat — never read whole files speculatively
- Functions under 40 lines
- f-strings, not .format()

## Adding skills
Drop a SKILL.md into ~/.claude/skills/<n>/SKILL.md
Or ask mlx-code to create one for you.
description field drives auto-activation — make it keyword-rich.
disable-model-invocation: true for sensitive skills (deploy etc).
""",

"~/.claude/skills/code-search/SKILL.md": """---
name: code-search
description: Search and explore a codebase to understand how it works, find functions, trace data flow, or read code. Use when asked to explain, understand, find, read, or explore code.
---

## Rules
- ALWAYS grep before reading. Never cat a whole file without knowing its size.
- Check line count with `wc -l` before reading anything.
- Read specific ranges with `cat -n file.py | sed -n 'A,Bp'`.

## Workflow

### Find relevant code first
```
grep -n "def agent_loop" main.py
grep -rn "class Trainer" src/
grep -n "import" main.py | head -20
```

### Then read only that section
```
grep -n "def agent_loop" main.py        # shows line 230
cat -n main.py | sed -n '230,280p'      # read just those lines
```

### Map a large file before diving in
```
wc -l bigfile.py
grep -n "^class\\|^def " bigfile.py | head -40
```

### Trace data flow
```
grep -rn "history" main.py
grep -n "def.*history\\|history.*=" main.py
```

## Output format
1. What the code does in 1-2 sentences
2. Key data structures
3. Execution flow step by step
4. Any gotchas
""",

"~/.claude/skills/python-debug/SKILL.md": """---
name: python-debug
description: Debug Python errors, tracebacks, exceptions, crashes, and unexpected behaviour. Use when the user mentions an error, traceback, crash, bug, or asks why something is broken.
---

## Workflow
1. Read the traceback — bottom line is the error, last frame in YOUR code is relevant
2. Jump to the line: `grep -n "fn_name" file.py` then `cat -n file.py | sed -n 'A,Bp'`
3. Reproduce mentally — what value arrives there, why does it fail
4. Fix minimally — no refactoring while debugging
5. Verify: `python -m pytest tests/ -x -q` or `python script.py`

## Common errors
| Error | Cause |
|-------|-------|
| `AttributeError: 'NoneType'` | missing None check before .attr |
| `KeyError` | key absent — use .get() or check with `in` |
| `IndexError` | off-by-one or empty list |
| `TypeError: unsupported operand` | wrong type passed |
| `RecursionError` | missing base case |
| `ImportError` | missing package or wrong path |

## Debug commands
```
python -W all script.py
git diff HEAD~1 -- file.py
grep -n "TODO\\|FIXME\\|HACK" .
```
""",

"~/.claude/skills/write-skill/SKILL.md": """---
name: write-skill
description: Create a new skill to teach the agent a reusable capability. Use when asked to add a skill, create a skill, or teach the agent to do something new.
---

## Steps
1. Choose name: lowercase hyphens, e.g. `deploy-heroku`
2. Use write_file with path `~/.claude/skills/<n>/SKILL.md` for global,
   or `.claude/skills/<n>/SKILL.md` for project-only

## SKILL.md structure
```
---
name: skill-name
description: What it does AND when to activate it. Keywords drive auto-activation.
disable-model-invocation: true   # optional: manual /skill only
allowed-tools: bash              # optional: restrict tools
---

# Instructions
Step by step. Under 400 lines.
```

## Verify
```
ls ~/.claude/skills/
cat ~/.claude/skills/<n>/SKILL.md
```
The agent rescans after every turn — new skills appear immediately.
""",

}  # end FILES


def _deploy_files() -> None:
    """Write any missing FILES to disk. Skips files that already exist."""
    deployed = []
    for dest_s, content in FILES.items():
        dest = Path(dest_s).expanduser()
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        deployed.append(str(dest))
    if deployed:
        print("mlx-code: installed missing files:")
        for f in deployed: print(f"  {f}")

_deploy_files()

DEFAULT_MODEL  = "mlx-community/Qwen3.5-4B-OptiQ-4bit"
MAX_TOOL_TURNS = 30

R="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"
CYAN="\033[36m"; GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"
def cp(c,t): print(f"{c}{t}{R}",flush=True)

# ── CLAUDE.md ─────────────────────────────────────────────────────────────────

def load_claude_md(project_dir: Path) -> str:
    parts = []
    for path, label in [
        (Path.home()/".claude"/"CLAUDE.md", "~/.claude/CLAUDE.md"),
        (project_dir/"CLAUDE.md",           "CLAUDE.md"),
    ]:
        if path.exists():
            parts.append(f"<!-- {label} -->\n{path.read_text().strip()}")
    root = project_dir/"CLAUDE.md"
    for sub in sorted(project_dir.rglob("CLAUDE.md")):
        if sub == root: continue
        parts.append(f"<!-- {sub.relative_to(project_dir)} -->\n{sub.read_text().strip()}")
    return "\n\n".join(parts)

# ── Skills ────────────────────────────────────────────────────────────────────

SKILL_DIRS = [Path.home()/".claude"/"skills"]

def _fm(text: str) -> dict:
    m = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*\n", text, re.DOTALL)
    if not m: return {}
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k,_,v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm

def discover_skills(project_dir: Path) -> list[dict]:
    dirs = SKILL_DIRS + [project_dir/".claude"/"skills"]
    out: list[dict] = []; seen: set[str] = set()
    for base in dirs:
        if not base.exists(): continue
        for md in sorted(base.rglob("SKILL.md")):
            text = md.read_text(errors="replace")
            fm   = _fm(text)
            name = (fm.get("name") or md.parent.name).strip()
            if not name or name in seen: continue
            seen.add(name)
            desc = fm.get("description","").strip()
            if not desc: continue
            raw  = fm.get("allowed-tools","")
            out.append({
                "name":    name,
                "desc":    desc,
                "path":    md,
                "allowed": {t.strip() for t in raw.split(",")} if raw else None,
                "no_auto": fm.get("disable-model-invocation","false").lower() in ("true","1","yes"),
                "no_user": fm.get("user-invocable","true").lower() in ("false","0","no"),
            })
    return out

# ── Prompt ────────────────────────────────────────────────────────────────────

CORE = """\
━━━ TOOLS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Call tools with a JSON object on its own line:

{"tool": "bash", "args": {"cmd": "..."}}
{"tool": "write_file", "args": {"path": "...", "content": "..."}}

bash  cwd=project root, 30s timeout
  ALWAYS grep/find before cat:
    grep -n "def foo" main.py
    grep -rn "pattern" src/
    cat -n file.py | sed -n '40,80p'
    wc -l file.py
  Run:    python -m pytest tests/ -x
  Update: printf '\\n## Rule\\n- text\\n' >> CLAUDE.md

write_file  path relative to project root, content = full file text\
"""

def skill_tools(skills: list[dict]) -> str:
    auto = [s for s in skills if not s["no_auto"]]
    if not auto: return "\n(no skills installed)"
    lines = ["\n━━━ SKILLS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
             "Call a skill tool to load its full instructions into context:\n"]
    for s in auto:
        lines.append(f'{{"tool":"activate_skill_{s["name"]}","args":{{"reason":"..."}}}}\n  → {s["desc"]}')
    return "\n".join(lines)

def sys_prompt(cwd: Path, claude_md: str, skills: list[dict]) -> str:
    return (
        f"You are mlx-code, a local AI coding assistant (mlx-lm, Apple Silicon).\n"
        f"Explore before writing. Persist knowledge to files.\n\n"
        f"PROJECT: {cwd}\n\n"
        f"━━━ CLAUDE.md ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{claude_md.strip() or '(none)'}\n\n"
        + CORE + skill_tools(skills)
    )

# ── Tools ─────────────────────────────────────────────────────────────────────

def run_bash(cmd: str, cwd: Path) -> str:
    if not cmd.strip(): return "ERROR: empty cmd"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, cwd=str(cwd), timeout=30)
        out = (r.stdout+r.stderr).strip()
        if not out: return f"(exit {r.returncode}, no output)"
        return out[:8000]+("\n…[truncated]" if len(out)>8000 else "")
    except subprocess.TimeoutExpired: return "ERROR: timed out"
    except Exception as e:            return f"ERROR: {e}"

def execute(name: str, args: dict, cwd: Path,
            skills: list[dict], active: dict|None
            ) -> tuple[str, bool, dict|None, str|None]:
    if name == "done":
        return args.get("answer",""), True, active, None
    if name.startswith("activate_skill_"):
        sname = name[len("activate_skill_"):]
        s = next((x for x in skills if x["name"]==sname), None)
        if not s: return f"ERROR: no skill '{sname}'", False, active, None
        return f"Skill '{sname}' loaded.", False, s, s["path"].read_text(errors="replace")
    if active and active.get("allowed"):
        if name.lower() not in {t.lower() for t in active["allowed"]}:
            return f"ERROR: skill '{active['name']}' restricts to {active['allowed']}", False, active, None
    if name == "bash":
        return run_bash(args.get("cmd",""), cwd), False, active, None
    if name == "write_file":
        p = args.get("path","")
        if not p: return "ERROR: missing path", False, active, None
        fp = cwd/p; fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(args.get("content",""))
        return f"OK: wrote {fp}", False, active, None
    return f"ERROR: unknown tool '{name}'", False, active, None

# ── Parser ────────────────────────────────────────────────────────────────────

_JSON_RE  = re.compile(r'\{\s*"tool"\s*:\s*"(?P<n>[^"]+)"\s*,\s*"args"\s*:\s*\{')
_FENCE_RE = re.compile(r'```(?:bash|sh)\n(.*?)```', re.DOTALL)

def _bend(text: str, start: int) -> int|None:
    d=0; ins=False; esc=False
    for i in range(start, len(text)):
        c=text[i]
        if esc:             esc=False; continue
        if c=="\\" and ins: esc=True;  continue
        if c=='"':          ins=not ins; continue
        if ins:             continue
        if c=="{": d+=1
        elif c=="}":
            d-=1
            if d==0: return i
    return None

# def parse_call(text: str) -> tuple[str,dict]|None:
#     text = _FENCE_RE.sub(
#         lambda m: json.dumps({"tool":"bash","args":{"cmd":m.group(1).strip()}}), text)
#     for m in _JSON_RE.finditer(text):
#         ab=m.end()-1; ae=_bend(text,ab)
#         if ae is None: continue
#         try: return m.group("n"), json.loads(text[ab:ae+1])
#         except json.JSONDecodeError: continue
#     return None

def parse_call(text: str):
    last = text.strip().splitlines()[-1]

    try:
        obj = json.loads(last)
    except Exception:
        return None

    if "tool" in obj and "args" in obj:
        return obj["tool"], obj["args"]

    return None

# ── Generate ──────────────────────────────────────────────────────────────────

def generate(model, tok, messages: list[dict], max_tok: int) -> str:
    prompt = tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
    buf: list[str] = []
    for chunk in stream_generate(model, tok, prompt=prompt, max_tokens=max_tok):
        print(chunk.text, end="", flush=True); buf.append(chunk.text)
    print()
    return "".join(buf)

# ── Agent loop ────────────────────────────────────────────────────────────────

def agent_loop(model, tok, user_input: str, cwd: Path,
               claude_md: str, skills: list[dict], history: list[dict],
               max_tok: int, forced_skill: dict|None=None
               ) -> tuple[str, str, list[dict]]:
    active: dict|None = None
    preamble = ""
    if forced_skill:
        preamble = f"[Skill '{forced_skill['name']}' activated]\n{forced_skill['path'].read_text().strip()}\n\n"
        active   = forced_skill
        cp(DIM, f"  [skill '{forced_skill['name']}' force-loaded]")

    history.append({"role":"user","content":preamble+user_input})
    injected: list[str] = []
    recent:   list[str] = []

    for _ in range(MAX_TOOL_TURNS):
        msgs = ([{"role":"system","content":sys_prompt(cwd,claude_md,skills)}]
                + [{"role":"system","content":b} for b in injected]
                + history)
        cp(CYAN, f"\n{'─'*60}"); cp(BOLD+CYAN, "Assistant:")
        resp = generate(model, tok, msgs, max_tok)
        history.append({"role":"assistant","content":resp})

        call = parse_call(resp)
        if call is None: return resp, claude_md, skills

        name, args = call
        if name == "done":
            cp(GREEN,"\n✅ Done.")
            return args.get("answer",resp), claude_md, skills

        sig = json.dumps({"t":name,"a":args},sort_keys=True)
        if sig in recent:
            history.append({"role":"user","content":
                "[SYSTEM] You already ran this exact call. Do not repeat it. "
                "Write your final answer as plain text now."})
            recent.clear(); continue
        recent.append(sig)
        if len(recent)>6: recent.pop(0)

        cp(YELLOW, f"\n🔧 {name}: {json.dumps(args,ensure_ascii=False)[:160]}")
        result, done, active, skill_body = execute(name, args, cwd, skills, active)

        if done: cp(GREEN,"\n✅ Done."); return result, claude_md, skills
        if skill_body:
            injected.append(f"[Skill '{name[len('activate_skill_'):]}']\n{skill_body}")
            cp(DIM, "  [skill body injected]")

        cp(DIM, textwrap.indent(result[:600],"    "))

        touched = args.get("cmd","") + args.get("path","")
        if "CLAUDE.md" in touched:
            claude_md = load_claude_md(cwd); cp(DIM,"  [CLAUDE.md reloaded]")
        if ".claude/skills" in touched:
            skills = discover_skills(cwd); cp(DIM,f"  [skills reloaded: {len(skills)}]")

        history.append({"role":"user","content":f"[tool result: {name}]\n{result}"})

    cp(RED,f"\n⚠️  Hit {MAX_TOOL_TURNS}-turn limit.")
    return "(turn limit reached)", claude_md, skills

# ── REPL ──────────────────────────────────────────────────────────────────────

HELP = """\
  /help              this message
  /claude            print CLAUDE.md
  /skills            list skills
  /skill <n>      force-invoke a skill
  /reload            rescan CLAUDE.md + skills
  /clear             clear conversation history
  /quit              exit"""

def main():
    ap = argparse.ArgumentParser(description="mlx-code: local Claude Code via mlx-lm")
    ap.add_argument("--model",      default=DEFAULT_MODEL)
    ap.add_argument("--dir",        default=".")
    ap.add_argument("--max-tokens", default=2048, type=int)
    a = ap.parse_args(); cwd = Path(a.dir).resolve()

    cp(BOLD+GREEN,"\n╔════════════════════════════════╗")
    cp(BOLD+GREEN,  "║           mlx-code             ║")
    cp(BOLD+GREEN,  "║  Local Claude Code via mlx-lm  ║")
    cp(BOLD+GREEN,  "╚════════════════════════════════╝\n")
    cp(DIM,f"Project : {cwd}"); cp(DIM,f"Model   : {a.model}\n")

    cp(YELLOW,f"Loading {a.model} …")
    tc = {"trust_remote_code":True} if "qwen" in a.model.lower() else {}
    model, tok = load(a.model, tokenizer_config=tc)
    cp(GREEN,"Model loaded ✓\n")

    claude_md = load_claude_md(cwd)
    skills    = discover_skills(cwd)
    cp(DIM,f"📄 CLAUDE.md : {'loaded' if claude_md else 'not found'}")
    n = sum(1 for s in skills if not s["no_auto"])
    cp(DIM,f"🧩 Skills    : {len(skills)} total, {n} model-invocable" +
       (f"  ({', '.join(s['name'] for s in skills)})" if skills else
        "  (none — add ~/.claude/skills/<n>/SKILL.md)"))
    cp(DIM,"\nType /help for commands.\n")

    history: list[dict] = []; forced: dict|None = None
    while True:
        try:
            cp(BOLD+GREEN,"\n> You: "); ui = input("").strip()
        except (EOFError,KeyboardInterrupt):
            cp(YELLOW,"\nGoodbye!"); break
        if not ui: continue
        if ui.startswith("/"):
            ps=ui.split(maxsplit=1); cmd=ps[0].lower(); arg=ps[1].strip() if len(ps)>1 else ""
            if   cmd=="/quit":   cp(YELLOW,"Goodbye!"); break
            elif cmd=="/help":   print(HELP)
            elif cmd=="/claude": print(claude_md or "(empty)")
            elif cmd=="/skills":
                if skills:
                    for s in skills:
                        flags = " [manual-only]" if s["no_auto"] else ""
                        cp(GREEN,f"  • {s['name']}{flags}"); print(f"    {s['desc']}")
                else: cp(DIM,"No skills found.")
            elif cmd=="/skill":
                m=next((s for s in skills if s["name"]==arg and not s["no_user"]),None)
                if m: forced=m; cp(GREEN,f"Skill '{arg}' injected next turn.")
                else: cp(RED,f"No skill '{arg}'.  /skills to list.")
            elif cmd=="/reload":
                claude_md=load_claude_md(cwd); skills=discover_skills(cwd)
                cp(GREEN,f"Reloaded. {len(skills)} skill(s).")
            elif cmd=="/clear":
                history.clear(); cp(GREEN,"History cleared.")
            else: cp(RED,f"Unknown '{cmd}'.  /help")
            continue
        _, claude_md, skills = agent_loop(
            model,tok,ui,cwd,claude_md,skills,history,a.max_tokens,forced)
        forced=None
        claude_md=load_claude_md(cwd); skills=discover_skills(cwd)

if __name__=="__main__":
    main()
