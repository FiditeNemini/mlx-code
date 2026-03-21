# mlx-code: Local Claude Code for Mac

<img width="1024" height="1536" alt="mlxcodelogo" src="https://github.com/user-attachments/assets/df605c1d-f8e7-433c-9aaf-176c73e3d628" />
![mlxcode](https://github.com/user-attachments/assets/86004bd2-549f-44b8-9a05-a9b6d9f1c4a2)

### Quick Start

```bash
brew install --cask claude-code
pip install mlx-code
```

### Commands
| Command | What it does | Example |
|--------|--------------|--------|
| `mlx-code` | Start interactive mode | `mlx-code` |
| `mlx-code "task"` | Run a one-time task | `mlx-code "fix the build error"` |
| `mlx-code -p "query"` | Run one-off query, then exit | `mlx-code -p "explain this function"` |
| `mlx-code -c` | Continue most recent conversation in current directory | `mlx-code -c` |
| `mlx-code -r` | Resume a previous conversation | `mlx-code -r` |
| `mlx-code commit` | Create a Git commit | `mlx-code commit` |
| `/clear` | Clear conversation history | `/clear` |
| `/help` | Show available commands | `/help` |
| `exit` or `Ctrl+C` | Exit Claude Code | `exit` |

<details><summary>Click to expand</summary><pre>
╭─── Claude Code v2.1.74 ────────────────────────────────────────────────────────────────────────────────╮
│                                                    │ Tips for getting started                          │
│                    Welcome back!                   │ Run /init to create a CLAUDE.md file with instru… │
│                                                    │ ───────────────────────────────────────────────── │
│                       ▐▛███▜▌                      │ Recent activity                                   │
│                      ▝▜█████▛▘                     │ No recent activity                                │
│                        ▘▘ ▝▝                       │                                                   │
│                                                    │                                                   │
│ mlx-community/Qwen3.5-4B-Opti… · API Usage Billing │                                                   │
│             /…/T/tmpg4sztu_h/workspace             │                                                   │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────╯

❯ explain the folder structure

⏺

⏺ Searched for 1 pattern (ctrl+o to expand)

⏺ Here's the folder structure of your workspace:

  workspace/
  ├── .DS_Store
  ├── cache/
  │   └── cache.safetensors
  ├── cc/
  │   ├── .DS_Store
  │   ├── mlx-code-v1.py
  │   └── mlx-code-v2.py
  ├── cyberpunk/
  │   ├── build.zig
  │   ├── help.py
  │   ├── map.c
  │   └── main.zig
  ├── rag/
  │   └── jina.py
  ├── rts/
  │   ├── build.zig
  │   ├── main.zig
  │   └── battle_sim.c
  ├── splat_zig_raylib/
  │   ├── README.md
  │   ├── .DS_Store
  │   ├── build.zig
  │   ├── build_web.sh
  │   ├── index.html
  │   ├── main.zig
  │   ├── gsplat_transform.py
  │   ├── src/
  │   │   └── main.zig
  │   └── splat_zig/
  │       ├── .DS_Store
  │       ├── build.zig
  │       ├── build_web.sh
  │       ├── gsplat_transform.py
  │       ├── index.html
  │       ├── main.zig
  │       └── splat/
  │           └── build.zig
  ├── tarot/
  │   ├── index.html
  │   └── tarot.py
  └── tmp.md

  Summary of projects:

  ┌───────────────────┬────────────────────────────────────────────┐
  │      Folder       │                  Purpose                   │
  ├───────────────────┼────────────────────────────────────────────┤
  │ cc/               │ MLX code versions (v1, v2)                 │
  ├───────────────────┼────────────────────────────────────────────┤
  │ cyberpunk/        │ Zig game project with C map integration    │
  ├───────────────────┼────────────────────────────────────────────┤
  │ rag/              │ RAG (Retrieval-Augmented Generation) setup │
  ├───────────────────┼────────────────────────────────────────────┤
  │ rts/              │ Real-time strategy battle simulation       │
  ├───────────────────┼────────────────────────────────────────────┤
  │ splat_zig_raylib/ │ Raylib game with splat transform features  │
  ├───────────────────┼────────────────────────────────────────────┤
  │ tarot/            │ Tarot card application                     │
  ├───────────────────┼────────────────────────────────────────────┤
  │ cache/            │ Model cache files                          │
  ├───────────────────┼────────────────────────────────────────────┤
  │ tmp.md            │ Temporary notes                            │
  └───────────────────┴────────────────────────────────────────────┘

❯ how is output parsed in mlx-code.py?

⏺

⏺ Read 1 file (ctrl+o to expand)

⏺ Based on the code, here's how output is parsed in mlx-code.py:

  Output Parsing Flow

  1. decode() function (lines 109-143)

  This is the core parsing function that converts raw model output into structured blocks:

  - Input: Raw text from the model
  - Output: List of blocks with types: thinking, text, or tool_use

  Key parsing logic:
  - Splits text by `

⏺ ` markers for thinking content
  - Extracts tool calls wrapped in <tool_call>...</tool_call> tags
  - Parses function name and parameters from XML-like tags

  2. Tool Call Extraction (lines 125-141)

  When parsing tool calls:
  tool_pattern = re.compile(r'<tool_call>(.*?)</tool_call>', re.DOTALL)
  - Matches content between <tool_call> and </tool_call>
  - Extracts function name: <function=name>
  - Extracts parameters: <parameter=name>value</parameter>
  - Creates tool_use block with:
    - type: "tool_use"
    - id: UUID
    - name: function name
    - input: params dict

  3. blocks_to_sse() function (lines 145-177)

  Converts parsed blocks to Server-Sent Events (SSE) format:

  def event(name: str, data: dict) -> bytes:
      return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()

  Event types sent:
  - message_start - Initial message header
  - content_block_start - Start of a content block
  - content_block_delta - Streaming content (text/thinking/tool)
  - content_block_stop - End of block
  - message_delta - Stop reason
  - message_stop - End of message

  4. HTTP Response (lines 288-297)

  Sends SSE stream with headers:
  self.send_header("Content-Type", "text/event-stream")
  self.send_header("Cache-Control", "no-cache")

  5. Endpoint (/v1/messages)

  - POST request with JSON body
  - Returns streaming SSE response
  - Supports max_tokens parameter

  6. Stop Reason Detection

  - tool_use - If tool calls were generated
  - end_turn - If just text/thinking was generated

✻ Brewed for 35s

❯ cool mate, bye

⏺ Got it! Feel free to come back anytime if you need help. Have a great day! 👋
</pre></details><br>

