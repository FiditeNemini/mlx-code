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
╭─── Claude Code v2.1.74 ──────────────────────────────────────────────────────────────────────────────────╮
│                                                    │ Tips for getting started                            │
│                    Welcome back!                   │ Run /init to create a CLAUDE.md file with instruct… │
│                                                    │ ─────────────────────────────────────────────────── │
│                       ▐▛███▜▌                      │ Recent activity                                     │
│                      ▝▜█████▛▘                     │ No recent activity                                  │
│                        ▘▘ ▝▝                       │                                                     │
│                                                    │                                                     │
│ mlx-community/Qwen3.5-4B-Opti… · API Usage Billing │                                                     │
│                  ~/Downloads/tmp                   │                                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────╯

❯ list the files in this directory and explain what each one does

⏺ The user wants to understand the files in the current directory, so I'll use the Glob tool to list all files first.

⏺ Searched for 1 pattern (ctrl+o to expand)

⏺ I need to fix the Glob tool call - the parameter should be pattern, not key.

⏺ Searched for 1 pattern (ctrl+o to expand)

⏺ The user wants me to explain what each file does. I should organize these by project directory and explain the purpose of each file. Let me read a few key files to provide accurate explanations.

  This directory contains several project folders. Let me explain each one:

  Main Projects

  cyberpunk/

  - main.zig - Main entry point for a Zig-based cyberpunk project
  - build.zig - Build configuration file for Zig
  - map.c - C source file, likely for map rendering or game logic
  - help.py - Python helper script, possibly for documentation or utilities

  rts/

  - main.zig - Main entry point for a real-time strategy (RTS) game in Zig
  - build.zig - Build configuration for Zig
  - battle_sim.c - C file for battle simulation logic

  splat_zig_raylib/

  - main.zig (two versions - one in splat_zig/, one in root) - Main entry point for a Raylib-based game
  - build.zig - Build configuration
  - gsplat_transform.py - Python script for splat transform calculations
  - index.html - Web entry point for the game
  - build_web.sh - Shell script for building web version
  - README.md - Project documentation

  tarot/

  - tarot.py - Python script for tarot-related functionality
  - index.html - Web entry point

  yorha/

  - index.html - Web entry point (likely a simple web page)

  jina.py

  - jina.py - Python script, possibly related to Jina AI or a utility

  mlx-code-v1.py & mlx-code.py

  - These appear to be different versions of the mlx-code agent wrapper (the local Claude Code-style agent for Apple Silicon)

  tmp.md

  - tmp.md - Temporary markdown file (contents unknown)

  mlx_trace.log

  - mlx_trace.log - Trace log file from the mlx model runtime

  .DS_Store files

  - macOS metadata files (can be ignored)

  ---
  Summary: This is a temporary download folder (/Users/jjms/Downloads/tmp) containing multiple small projects:
  - Game projects in Zig (cyberpunk, RTS, Raylib-based game)
  - Python scripts for various utilities
  - Web entry points (HTML files)
  - Build configurations (Zig build files)

  The Zig projects appear to be the main focus, with game-related code and build systems.

✻ Brewed for 42s

❯ explain how output is parsed in mlx-code.py

⏺ The user wants to understand how output is parsed in mlx-code.py, so I need to read that file first to understand its structure and find the output parsing logic.

⏺ Read 1 file (ctrl+o to expand)

⏺ I need to fix the Read tool call - it should use file_path not key.

⏺ Read 1 file (ctrl+o to expand)

⏺ Now I have the full file. Let me explain the output parsing logic, which is the key part the user asked about.


  The output parsing logic is in the parse_output(raw: str) function (lines 233-315). Here's how it works:

  Output Parsing Flow

  1. Extract Thinking Blocks (lines 237-244)

  First, it extracts any `

⏺ The output parsing logic is in the parse_output(raw: str) function (lines 233-315). Here's how it works:

  Output Parsing Flow

  1. Extract Thinking Blocks (lines 237-244)

  First, it extracts any `

⏺ ` blocks by finding the earliest occurrences of both markers and splitting them out:
  while "

⏺ " in remaining:
      s = remaining.index("

⏺ ")
      # Extract thinking block
      remaining = remaining[e + 8:].strip()

  ### 2. **Extract Tool Use Blocks** (lines 247-289)
  It searches for `<tool_call>...</tool_call>` markers and tries to parse the content:
  - **First attempt**: Try parsing as JSON with `name` or `tool` field
  - **Fallback**: Parse as XML-like format with `<function=...>` and `<parameter=...>` tags
  - Creates tool blocks with `type: "tool_use"`, unique ID, name, and input

  ### 3. **Handle JSON Tool Response** (lines 291-311)
  If no `<tool_call>...</tool_call>` blocks were found, it checks if the remaining output is a JSON object with `name` field (indicating a tool response).

  ### 4. **Return Result** (line 315)
  Returns a tuple of `(blocks, stop_reason)`:
  - `blocks`: List of parsed blocks (`{"type": "text"}`, `{"type": "thinking"}`, `{"type": "tool_use"}`)
  - `stop_reason`: `"tool_use"` if tools were detected, `"end_turn"` otherwise

  ## Key Patterns Used

  | Pattern | Purpose |
  |---------|---------|
  | `

⏺ | Thinking block markers | |...| Tool invocation markers | | JSON withname/tool| Tool response format | |<function=...>/<parameter=...>` | Alternative tool format |

  The parser is designed to handle both the tool invocation format (<tool_call>...</tool_call>) and tool response format (JSON with name field) used by the system.

✻ Worked for 1m 9s
</pre></details><br>

