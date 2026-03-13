import argparse
import json
import os
import re
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

DEFAULT_MODEL      = "mlx-community/Qwen3.5-4B-OptiQ-4bit"
DEFAULT_SKILL_DIRS = ["./skills", os.path.expanduser("~/.claude/skills")]
LOG_PROMPT_TAIL    = 1000   

model     = None
tokenizer = None
model_id  = None
skills    = {}


def log(tag, text):
    bar = "─" * 60
    print(f"\n{bar}\n{tag}\n{bar}\n{text}\n", flush=True)


def parse_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}, text
    fm_raw = m.group(1)
    body   = text[m.end():]
    if yaml:
        try:
            return yaml.safe_load(fm_raw) or {}, body
        except Exception:
            pass
    fm = {}
    for line in fm_raw.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, body

def scan_skills(dirs):
    found = {}
    for d in dirs:
        p = Path(d)
        if not p.exists():
            continue
        for f in p.rglob("SKILL.md"):
            try:
                text = f.read_text()
                fm, _ = parse_frontmatter(text)
                name, desc = fm.get("name"), fm.get("description")
                if name and desc:
                    found[name] = {"description": desc, "path": str(f)}
                    print(f"  skill: {name}", flush=True)
            except Exception as e:
                print(f"  warn: {f}: {e}", flush=True)
    return found

def skill_body(name):
    if name not in skills:
        return f"Unknown skill '{name}'. Available: {', '.join(skills) or 'none'}"
    try:
        return Path(skills[name]["path"]).read_text()
    except Exception as e:
        return f"Error reading skill: {e}"


def load_model(path):
    global model, tokenizer, model_id
    from mlx_lm import load
    print(f"Loading {path} …", flush=True)
    model, tokenizer = load(path)
    model_id = path
    print("Ready.\n", flush=True)

def generate(prompt, max_tokens, temp, top_p):
    from mlx_lm import generate as mlx_gen
    return mlx_gen(
        model, tokenizer,
        prompt=prompt,
        max_tokens=max_tokens,
        verbose=False,
    )


READ_SKILL_TOOL = {
    "type": "function",
    "function": {
        "name": "read_skill",
        "description": (
            "Read the full SKILL.md for a skill before using it. "
            "Call this whenever a task matches a skill description."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name from available_skills"}
            },
            "required": ["name"],
        },
    },
}

def skills_system_addon():
    if not skills:
        return ""
    entries = "\n".join(
        f"<skill><name>{n}</name><description>{s['description']}</description></skill>"
        for n, s in skills.items()
    )
    return (
        "\n\n<available_skills>\n" + entries +
        "\nUse the read_skill tool to get full instructions before attempting "
        "any task that matches a skill.\n</available_skills>"
    )

def tools_to_text(tools):
    header = (
        "You have access to these tools. "
        "To call a tool output ONLY a <tool_call> block:\n"
        "<tool_call>\n<function=ToolName>\n<parameter=key>value</parameter>\n</function>\n</tool_call>"
    )
    lines = [header]
    for t in tools:
        name   = t.get("name", "")
        desc   = t.get("description", "")
        schema = t.get("input_schema", {})
        params = ", ".join(schema.get("properties", {}).keys())
        lines.append(f"- {name}({params}): {desc}")
    return "\n".join(lines)

def build_messages(body, extra=None):
    msgs = []

    sys_parts = []
    raw = body.get("system")
    if isinstance(raw, str) and raw:
        sys_parts.append(raw)
    elif isinstance(raw, list):
        t = "\n".join(b.get("text","") for b in raw if b.get("type")=="text")
        if t: sys_parts.append(t)
    sys_parts.append(skills_system_addon())

    if skills:
        sys_parts.append(tools_to_text([{
            "name": "read_skill",
            "description": "Read the full SKILL.md instructions for a skill before using it.",
            "input_schema": {"type":"object","properties":{"name":{"type":"string"}},"required":["name"]},
        }]))

    system = "\n".join(p for p in sys_parts if p).strip()
    if system:
        msgs.append({"role": "system", "content": system})

    for msg in body.get("messages", []):
        role    = msg["role"]
        content = msg["content"]
        if isinstance(content, str):
            msgs.append({"role": role, "content": content})
            continue
        parts = []
        for block in content:
            t = block.get("type")
            if t == "text":
                parts.append(block["text"])
            elif t == "thinking":
                parts.append(f"<think>\n{block.get('thinking','')}\n</think>")
            elif t == "tool_use":
                args = "".join(
                    f"<parameter={k}>\n{v}\n</parameter>"
                    for k, v in block.get("input", {}).items()
                )
                parts.append(f"<tool_call>\n<function={block['name']}>\n{args}</function>\n</tool_call>")
            elif t == "tool_result":
                rc = block.get("content", "")
                if isinstance(rc, list):
                    rc = "\n".join(c.get("text","") for c in rc if c.get("type")=="text")
                parts.append(f"<tool_response>\n{rc}\n</tool_response>")
        msgs.append({"role": role, "content": "\n".join(parts)})

    if extra:
        msgs.extend(extra)
    return msgs


def build_prompt(body, extra=None):
    msgs = build_messages(body, extra=extra)
    return tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def parse_output(raw):
    blocks    = []
    remaining = raw

    while "<think>" in remaining and "</think>" in remaining:
        s = remaining.index("<think>")
        e = remaining.index("</think>")
        before = remaining[:s].strip()
        if before:
            blocks.append({"type": "text", "text": before})
        blocks.append({"type": "thinking", "thinking": remaining[s+7:e].strip()})
        remaining = remaining[e+8:].strip()
    remaining = remaining.replace("</think>", "").strip()

    tool_blocks = []
    leftover    = remaining
    for m in re.finditer(r"<tool_call>(.*?)</tool_call>", remaining, re.DOTALL):
        inner = m.group(1).strip()
        parsed = None

        try:
            obj  = json.loads(inner)
            name = obj.get("name") or obj.get("tool")
            args = obj.get("arguments") or obj.get("input") or {}
            if isinstance(args, str):
                try:    args = json.loads(args)
                except: args = {"raw": args}
            if name:
                parsed = {"name": name, "input": args}
        except Exception:
            pass

        if not parsed:
            fn_m = re.search(r"<function=([\w-]+)>", inner)
            if fn_m:
                name = fn_m.group(1)
                args = {}
                for pm in re.finditer(r"<parameter=([\w-]+)>\s*(.*?)\s*</parameter>", inner, re.DOTALL):
                    args[pm.group(1)] = pm.group(2).strip()
                parsed = {"name": name, "input": args}

        if parsed:
            tool_blocks.append({
                "type": "tool_use",
                "id":   f"toolu_{uuid.uuid4().hex[:8]}",
                "name": parsed["name"],
                "input": parsed["input"],
            })
        leftover = leftover.replace(m.group(0), "").strip()

    if tool_blocks:
        if leftover:
            blocks.append({"type": "text", "text": leftover})
        blocks.extend(tool_blocks)
        return blocks, "tool_use"

    stripped = remaining.strip()
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            name = obj.get("name") or obj.get("tool")
            args = obj.get("arguments") or obj.get("input") or {}
            if name:
                if isinstance(args, str):
                    try:    args = json.loads(args)
                    except: args = {"raw": args}
                blocks.append({
                    "type": "tool_use",
                    "id":   f"toolu_{uuid.uuid4().hex[:8]}",
                    "name": name,
                    "input": args,
                })
                return blocks, "tool_use"
    except Exception:
        pass

    if remaining:
        blocks.append({"type": "text", "text": remaining})
    return blocks or [{"type": "text", "text": raw}], "end_turn"


def resolve_read_skill(blocks, body, max_tokens, temp, top_p):
    extra = []
    for _ in range(5):
        skill_calls = [b for b in blocks if b.get("type")=="tool_use" and b["name"]=="read_skill"]
        if not skill_calls:
            break
        log("↻ SKILL TOOL", "\n".join(f"  read_skill({c['input']})" for c in skill_calls))
        for c in skill_calls:
            name    = c["input"].get("name","")
            content = skill_body(name)
            args    = f"<parameter=name>\n{name}\n</parameter>"
            extra.append({"role": "assistant", "content": f"<tool_call>\n<function=read_skill>\n{args}</function>\n</tool_call>"})
            log(f"↻ SKILL BODY [{name}]", content[:500] + ("…" if len(content)>500 else ""))
            extra.append({"role": "user", "content": f"<tool_response>\n{content}\n</tool_response>"})
        prompt = build_prompt(body, extra=extra)
        log("→ MLX (re-prompt tail)", prompt[-LOG_PROMPT_TAIL:])
        raw = generate(prompt, max_tokens, temp, top_p)
        log("← MLX RAW", raw)
        blocks, stop_reason = parse_output(raw)
        log("← PARSED", json.dumps(blocks, indent=2))
    stop_reason = "tool_use" if any(b.get("type")=="tool_use" for b in blocks) else "end_turn"
    return blocks, stop_reason

def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()

def blocks_to_sse(blocks, msg_id, stop_reason, in_tokens, out_tokens):
    out = bytearray()

    out += sse("message_start", {
        "type": "message_start",
        "message": {
            "id": msg_id, "type": "message", "role": "assistant",
            "model": model_id, "content": [], "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": in_tokens, "output_tokens": 0},
        },
    })

    for i, block in enumerate(blocks):
        bt = block["type"]

        if bt == "text":
            out += sse("content_block_start", {
                "type": "content_block_start", "index": i,
                "content_block": {"type": "text", "text": ""},
            })
            out += sse("content_block_delta", {
                "type": "content_block_delta", "index": i,
                "delta": {"type": "text_delta", "text": block["text"]},
            })

        elif bt == "thinking":
            out += sse("content_block_start", {
                "type": "content_block_start", "index": i,
                "content_block": {"type": "thinking", "thinking": ""},
            })
            out += sse("content_block_delta", {
                "type": "content_block_delta", "index": i,
                "delta": {"type": "thinking_delta", "thinking": block["thinking"]},
            })

        elif bt == "tool_use":
            out += sse("content_block_start", {
                "type": "content_block_start", "index": i,
                "content_block": {
                    "type": "tool_use", "id": block["id"],
                    "name": block["name"], "input": {},
                },
            })
            out += sse("content_block_delta", {
                "type": "content_block_delta", "index": i,
                "delta": {"type": "input_json_delta", "partial_json": json.dumps(block["input"])},
            })

        out += sse("content_block_stop", {"type": "content_block_stop", "index": i})

    out += sse("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": out_tokens},
    })
    out += sse("message_stop", {"type": "message_stop"})

    return bytes(out)


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"  HTTP {fmt % args}", flush=True)

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n))

    def path_base(self):
        return self.path.split("?")[0].rstrip("/")

    def do_GET(self):
        if self.path_base() == "/v1/models":
            self.send_json(200, {"data": [
                {"id": model_id, "object": "model",
                 "created": int(time.time()), "owned_by": "local"},
            ]})
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        pb = self.path_base()

        if pb == "/v1/messages/count_tokens":
            self.send_json(200, {"input_tokens": 0})
            return

        if pb != "/v1/messages":
            self.send_json(404, {"error": f"unknown endpoint {pb}"})
            return

        body = self.read_json()
        body["model"] = model_id   

        max_tokens = body.get("max_tokens", 8192)
        temp       = body.get("temperature", 0.7)
        top_p      = body.get("top_p", 0.9)
        msg_id     = f"msg_{uuid.uuid4().hex}"

        tools_requested = [t["name"] for t in body.get("tools", [])]
        last_msg = body.get("messages", [{}])[-1]
        last_content = last_msg.get("content", "")
        if isinstance(last_content, list):
            last_content = " | ".join(
                b.get("text", b.get("type","?"))[:80]
                for b in last_content
            )
        tool_schemas = body.get("tools", [])
        if len(body.get("messages", [])) <= 1:
            tools_summary = json.dumps(tool_schemas, indent=2)
        else:
            tools_summary = str(tools_requested)

        log("→ CC REQUEST", (
            f"tools: {tools_summary}\n"
            f"msgs:  {len(body.get('messages',[]))}\n"
            f"last:  {str(last_content)[:200]}"
        ))

        prompt = build_prompt(body)
        log("→ MLX PROMPT (tail)", prompt[-LOG_PROMPT_TAIL:])

        t0  = time.time()
        raw = generate(prompt, max_tokens, temp, top_p)
        dt  = time.time() - t0

        log(f"← MLX RAW ({dt:.1f}s)", raw)

        blocks, stop_reason = parse_output(raw)
        log("← PARSED", json.dumps(blocks, indent=2))

        if any(b.get("type")=="tool_use" and b["name"]=="read_skill" for b in blocks):
            blocks, stop_reason = resolve_read_skill(blocks, body, max_tokens, temp, top_p)

        in_tokens  = len(tokenizer.encode(prompt))
        out_tokens = len(tokenizer.encode(raw))

        sse_bytes = blocks_to_sse(blocks, msg_id, stop_reason, in_tokens, out_tokens)

        log("→ CC RESPONSE", (
            f"stop_reason: {stop_reason}\n"
            f"blocks: {[b['type'] for b in blocks]}\n"
            f"tokens: {in_tokens} in / {out_tokens} out\n"
            f"sse_bytes: {len(sse_bytes)}"
        ))

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(sse_bytes)))
        self.end_headers()
        try:
            self.wfile.write(sse_bytes)
            self.wfile.flush()
        except BrokenPipeError:
            pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model",  default=DEFAULT_MODEL)
    parser.add_argument("--port",   type=int, default=8000)
    parser.add_argument("--host",   default="127.0.0.1")
    parser.add_argument("--skills", action="append", metavar="DIR")
    args = parser.parse_args()

    skill_dirs = args.skills or DEFAULT_SKILL_DIRS
    print("Scanning skills …", flush=True)
    skills = scan_skills(skill_dirs)
    print(f"Found {len(skills)} skill(s).\n", flush=True)

    load_model(args.model)

    print(f"🍎  mlx-claude-server  http://{args.host}:{args.port}")
    print(f"    model  : {args.model}")
    print(f"    skills : {len(skills)}")
    print()
    print("    Other terminal:")
    print(f"      export ANTHROPIC_BASE_URL=http://{args.host}:{args.port}")
    print( "      export ANTHROPIC_AUTH_TOKEN=local")
    print(f"      export ANTHROPIC_MODEL={args.model}")
    print(f"      export ANTHROPIC_SMALL_FAST_MODEL={args.model}")
    print( "      claude")
    print()

    server = HTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")

if __name__ == "__main__":
    main()
