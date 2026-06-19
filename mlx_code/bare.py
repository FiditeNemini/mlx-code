from __future__ import annotations
import asyncio
import datetime
import json
import os
import re
import sys
import logging
from typing import Callable
from .repl import Agent, TabModel, CommandEngine, UIAdapter, HELP_TEXT
from .gits import GitError, get_branch_base_sha, get_diff_between_refs, get_commit_history_with_stats, find_rev_commit, create_worktree, git_new_branch, git_new_branch_at
logger = logging.getLogger(__name__)

class BareAdapter:

    def __init__(self, repl: 'BareRepl'):
        self.repl = repl

    def show_error(self, text: str) -> None:
        print(f'\n✗ {text}', flush=True)

    def show_command_result(self, cmd: str, content: str | object) -> None:
        if isinstance(content, str):
            print(content)
        else:
            print(str(content))

    def show_diff(self, diff_text: str, ref1_label: str, ref2_label: str) -> None:
        print(diff_text)

    def show_history_list(self, lines: list[str]) -> None:
        print('\n'.join(lines))

    def show_history_raw(self, json_text: str) -> None:
        print(json_text)

    async def add_tab(self, tab: TabModel) -> None:
        pass

    def remove_tab(self, removed_index: int) -> None:
        if self.repl.engine.active_index >= len(self.repl.engine.tabs):
            self.repl.engine.active_index = len(self.repl.engine.tabs) - 1

    def switch_to_tab(self, index: int) -> None:
        self.repl._render_tab_delimiter()
        self.repl._print_history_for_tab(self.repl.engine.tabs[index])

    def refresh_chrome(self) -> None:
        pass

    def clear_tab_display(self, tab: TabModel) -> None:
        pass

    def on_agent_event(self, event: dict, tab: TabModel) -> None:
        self.repl._handle_event(event, tab)

    async def run_captured_shell(self, command: str, cwd: str, env: dict | None) -> str:
        proc = await asyncio.create_subprocess_shell(command, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
        stdout, stderr = await proc.communicate()
        out = stdout.decode(errors='replace').rstrip('\n')
        err = stderr.decode(errors='replace').rstrip('\n')
        body = out
        if err:
            body = (body + '\n' if body else '') + f'[stderr]\n{err}'
        if proc.returncode:
            body += f'\n[exit {proc.returncode}]'
        return body

    async def run_interactive_shell(self, command: str, cwd: str, env: dict | None) -> int:
        proc = await asyncio.create_subprocess_shell(command, cwd=cwd, stdin=None, stdout=None, stderr=None, env=env)
        await proc.wait()
        return proc.returncode or 0

    def exit_app(self, summary: list[dict]) -> None:
        raise SystemExit

class BareRepl:

    def __init__(self, engine: CommandEngine, init_prompt: str | None=None):
        self.engine = engine
        self.adapter = BareAdapter(self)
        self.engine.bind(self.adapter)
        self.engine.attach_agent(self.engine.tabs[0])
        self.init_prompt = init_prompt
        self._pending_nls: int = 0
        self._awaiting_content: bool = False
        self._has_output: bool = False
        self._last_stream_type: str | None = None

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        if self.init_prompt:
            p, self.init_prompt = (self.init_prompt, None)
            await self.engine.active_tab.agent.run(p)
        while True:
            try:
                line = await loop.run_in_executor(None, self._read_input)
            except KeyboardInterrupt:
                print('\n(Use /exit or Ctrl-D to quit)')
                continue
            except EOFError:
                print()
                break
            if line is None:
                break
            line = line.strip()
            if not line:
                continue
            if line.lower() in {'exit', 'quit'}:
                break
            await self.engine.handle_input(line)
            tab = self.engine.active_tab
            if tab.running_task is not None:
                try:
                    await tab.running_task
                except asyncio.CancelledError:
                    pass

    def _read_input(self) -> str | None:
        tab = self.engine.active_tab
        prompt = f'[{tab.title}] ≫ '
        lines: list[str] = []
        while True:
            try:
                line = input(prompt)
            except EOFError:
                return None
            lines.append(line)
            if line.endswith('\\'):
                lines[-1] = line[:-1]
                prompt = '... '
            else:
                break
        return '\n'.join(lines)

    def _handle_event(self, event: dict, tab: TabModel) -> None:
        t, p = (event['type'], event.get('payload', {}))
        if t in ('text_delta', 'thinking_delta'):
            delta = p.get('delta', '')
            if delta:
                self._write_delta(delta, t)
        elif t == 'tool_start':
            self._pending_nls = 0
            self._awaiting_content = False
            self._has_output = True
            self._last_stream_type = t
        elif t == 'tool_end':
            result_msg = p.get('result', {})
            content = result_msg.get('content')
            is_err = p.get('is_error', False)
            out_text = ''
            if content:
                parts: list[str] = []
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get('type') == 'text':
                            parts.append(block.get('text', ''))
                out_text = '\n'.join(parts).strip('\n')
            if is_err:
                prefix = '✗ '
                if not out_text:
                    out_text = f'{p.get('name', '?')} failed'
            else:
                prefix = '→ ' if out_text else ''
            if out_text:
                self._write_delta(prefix + out_text, 'tool_result')
            self._last_stream_type = t
            print()
        elif t == 'commit':
            self._pending_nls = 0
            self._awaiting_content = False
            self._has_output = True
            print(f'\n◇ [{p.get('sha', '')}] committed', flush=True)
            self._last_stream_type = t
        elif t == 'error':
            self._pending_nls = 0
            self._awaiting_content = False
            self._has_output = True
            err = str(p.get('error', p))
            print(f'\n✗ {err}', flush=True)
            self._last_stream_type = t
        elif t in ('agent_start', 'turn_start'):
            self._pending_nls = 0
            self._awaiting_content = False
            self._has_output = False
            self._last_stream_type = None
        elif t == 'agent_end':
            self._pending_nls = 0
            if self._has_output:
                print()
            self._last_stream_type = None
            self._has_output = False
            self._awaiting_content = False

    def _write_delta(self, text: str, delta_type: str) -> None:
        if delta_type != self._last_stream_type:
            self._pending_nls = 0
            self._awaiting_content = True
            self._last_stream_type = delta_type
        if self._awaiting_content:
            text = text.lstrip('\n')
            if not text:
                return
        if self._awaiting_content:
            if self._has_output:
                print()
            self._awaiting_content = False
        if not self._awaiting_content and self._pending_nls > 0:
            print('\n' * self._pending_nls, end='', flush=True)
            self._pending_nls = 0
        rstripped = text.rstrip('\n')
        if rstripped:
            if delta_type == 'thinking_delta':
                print(f'\x1b[2m{rstripped}\x1b[0m', end='', flush=True)
            else:
                print(rstripped, end='', flush=True)
            self._has_output = True
        self._pending_nls = len(text) - len(rstripped)

    def _render_tab_delimiter(self) -> None:
        tab_strs: list[str] = []
        for i, t in enumerate(self.engine.tabs):
            if i == self.engine.active_index:
                tab_strs.append(f'\x1b[1m▶ {i + 1}. {t.title}\x1b[0m')
            else:
                tab_strs.append(f'\x1b[2m▷ {i + 1}. {t.title}\x1b[0m')
        print('\n' + '┗━━┫ ' + ' ┃ '.join(tab_strs) + ' ┃')

    def _print_history_for_tab(self, tab: TabModel) -> None:
        for msg in tab.agent.messages:
            role = msg.get('role', '')
            content = msg.get('content', '')
            is_error = msg.get('is_error', False)
            if isinstance(content, list):
                blocks = content
            elif isinstance(content, str):
                blocks = [{'type': 'text', 'text': content}]
            else:
                continue
            if role == 'toolResult':
                parts: list[str] = []
                for block in blocks:
                    if isinstance(block, dict) and block.get('type') == 'text':
                        t = block.get('text', '').strip('\n')
                        if t:
                            parts.append(t)
                if parts:
                    prefix = '✗ ' if is_error else '→ '
                    print(prefix + '\n'.join(parts))
                continue
            for block in blocks:
                btype = block.get('type', 'text')
                if btype == 'toolCall':
                    args = block.get('arguments', {})
                    if isinstance(args, dict):
                        args = json.dumps(args, ensure_ascii=False)
                    print(f'⚙ {block.get('name', '')} {args}')
                    continue
                text = block.get('text', '') or block.get('thinking', '') or ''
                text = text.strip('\n')
                if not text:
                    continue
                if btype == 'thinking':
                    print(f'\x1b[2m{text}\x1b[0m')
                elif is_error:
                    print(f'✗ {text}')
                elif role == 'user':
                    print(f'≫ {text}')
                elif role == 'commit':
                    print(f'◇ {text}')
                elif role == 'toolResult':
                    print(f'→ {text}')
                else:
                    print(text)