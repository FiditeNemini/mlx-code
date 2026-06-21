from __future__ import annotations
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static, Header, Footer
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text

class GitError(Exception):
    pass

class Git:

    def __init__(self, cwd: str):
        self.cwd = cwd
        try:
            self._run('rev-parse', '--git-dir')
        except subprocess.CalledProcessError as e:
            raise GitError(f'Not a git repository: {cwd}') from e

    def _run(self, *args: str, check: bool=True) -> str:
        result = subprocess.run(['git', *args], cwd=self.cwd, capture_output=True, text=True, check=False)
        if check and result.returncode != 0:
            raise GitError(f'git {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}')
        return result.stdout

    def current_branch(self) -> Optional[str]:
        out = self._run('branch', '--show-current').strip()
        return out or None

    def list_branches(self) -> list[tuple[str, str]]:
        out = self._run('for-each-ref', '--format=%(refname:short)%09%(objectname)', 'refs/heads/')
        result = []
        for line in out.splitlines():
            if not line.strip():
                continue
            name, sha = line.split('\t')
            result.append((name, sha))
        return result

    def merge_base(self, a: str, b: str) -> str:
        return self._run('merge-base', a, b, check=False).strip()

    def is_ancestor(self, a: str, b: str) -> bool:
        result = subprocess.run(['git', 'merge-base', '--is-ancestor', a, b], cwd=self.cwd, capture_output=True, text=True)
        return result.returncode == 0

    def first_parent_shas(self, tip: str, stop_at: Optional[str]=None) -> list[str]:
        if stop_at:
            out = self._run('rev-list', '--first-parent', f'{stop_at}..{tip}', check=False).strip()
        else:
            out = self._run('rev-list', '--first-parent', tip, check=False).strip()
        if not out:
            return []
        return out.splitlines()

    def first_parent_shas_soft_stop(self, tip: str, nesting_point: Optional[str]) -> list[str]:
        line = self.first_parent_shas(tip, None)
        if not nesting_point:
            return line
        result: list[str] = []
        for sha in line:
            if self.is_ancestor(sha, nesting_point):
                break
            result.append(sha)
        return result

    def commit_info(self, sha: str) -> 'CommitInfo':
        out = self._run('show', '-s', '--format=%H%x09%P%x09%an%x09%aI%x09%cI%x09%s%x09%b%x1e', sha)
        record = out.rstrip('\n')
        if record.endswith('\x1e'):
            record = record[:-1]
        full_sha, parents_str, author, author_date, commit_date, subject, body = record.split('\t')
        parents = parents_str.split() if parents_str else []
        return CommitInfo(sha=full_sha, parents=parents, author=author, author_date=author_date, commit_date=commit_date, subject=subject, body=body, is_merge=len(parents) > 1)

    def short_sha(self, sha: str) -> str:
        return self._run('rev-parse', '--short=7', sha).strip()

    def diff_stat(self, sha: str) -> list['DiffStat']:
        if not self.commit_info(sha).parents:
            parent = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
        else:
            parent = sha + '^'
        out = self._run('diff', '--no-color', '--numstat', '--format=', '-z', parent, sha)
        result = []
        if not out:
            return result
        parts = out.split('\x00')
        for part in parts:
            if not part:
                continue
            try:
                added_s, deleted_s, path = part.split('\t', 2)
            except ValueError:
                continue
            status = 'M'
            if added_s == '-' and deleted_s == '-':
                status = 'R'
                added = 0
                deleted = 0
            else:
                added = int(added_s) if added_s.isdigit() else 0
                deleted = int(deleted_s) if deleted_s.isdigit() else 0
            result.append(DiffStat(file=path, added=added, deleted=deleted, status=status))
        out2 = self._run('diff', '--no-color', '--name-status', '--format=', parent, sha)
        statuses = {}
        for line in out2.splitlines():
            if not line.strip():
                continue
            bits = line.split('\t')
            status_code = bits[0]
            path = bits[-1]
            statuses[path] = status_code[0] if status_code else 'M'
        for ds in result:
            if ds.file in statuses:
                ds.status = statuses[ds.file]
        return result

    def full_diff(self, sha: str) -> str:
        if not self.commit_info(sha).parents:
            parent = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
        else:
            parent = sha + '^'
        return self._run('diff', '--no-color', '--patch', '--format=', parent, sha)

    def file_diff(self, sha: str, path: str) -> str:
        if not self.commit_info(sha).parents:
            parent = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
        else:
            parent = sha + '^'
        return self._run('diff', '--no-color', '--patch', '--format=', parent, sha, '--', path)

    def ahead_behind(self, branch: str, parent: str) -> tuple[int, int]:
        out = self._run('rev-list', '--left-right', '--count', f'{parent}...{branch}').strip()
        left, right = out.split()
        return (int(right), int(left))

    def head_sha(self) -> Optional[str]:
        return self._run('rev-parse', 'HEAD', check=False).strip() or None

@dataclass
class CommitInfo:
    sha: str
    parents: list[str]
    author: str
    author_date: str
    commit_date: str
    subject: str
    body: str
    is_merge: bool

@dataclass
class DiffStat:
    file: str
    added: int
    deleted: int
    status: str

@dataclass
class BranchInfo:
    name: str
    tip: str
    parent_branch: Optional[str] = None
    nesting_point: Optional[str] = None
    fork_commit: Optional[str] = None
    own_commits: list[str] = field(default_factory=list)
    child_branches: list[str] = field(default_factory=list)

@dataclass
class Row:
    kind: str
    depth: int
    ancestor_last: list[bool]
    is_last: bool
    branch_name: Optional[str] = None
    sha: Optional[str] = None
    file: Optional[str] = None
    owning_branch: Optional[str] = None
    branch_info: Optional[BranchInfo] = None
    commit_info: Optional[CommitInfo] = None
    diff_stat: Optional[DiffStat] = None
    is_head: bool = False

    def identity(self) -> tuple:
        return (self.kind, self.branch_name, self.sha, self.file)

class TreeState:

    def __init__(self, git: Git):
        self.git = git
        self.branches: dict[str, BranchInfo] = {}
        self.root_branches: list[str] = []
        self.current_branch_name: Optional[str] = None
        self.head_tip: Optional[str] = None
        self.show_children: set[str] = set()
        self.show_commits: set[str] = set()
        self.show_commit_details: set[str] = set()
        self._commit_cache: dict[str, CommitInfo] = {}
        self._diff_stat_cache: dict[str, list[DiffStat]] = {}

    def rebuild(self) -> None:
        all_branches = self.git.list_branches()
        if not all_branches:
            self.branches = {}
            self.root_branches = []
            return
        included = all_branches
        self.branches = {name: BranchInfo(name=name, tip=tip) for name, tip in included}
        first_parent_lines = {name: self.git.first_parent_shas(b.tip, None) for name, b in self.branches.items()}
        fp_line_sets = {n: set(line) for n, line in first_parent_lines.items()}
        mb_cache: dict[tuple[str, str], str] = {}

        def get_mb(a: str, b: str) -> str:
            key = (a, b) if a < b else (b, a)
            if key not in mb_cache:
                mb_cache[key] = self.git.merge_base(a, b)
            return mb_cache[key]
        reach_from: dict[str, set[str]] = {n: set() for n in self.branches}
        for aname, ainfo in self.branches.items():
            for bname, binfo in self.branches.items():
                if aname == bname:
                    continue
                if self.git.is_ancestor(binfo.tip, ainfo.tip):
                    reach_from[aname].add(bname)
        merge_count_cache: dict[str, bool] = {}

        def is_merge(sha: str) -> bool:
            if sha not in merge_count_cache:
                merge_count_cache[sha] = len(self.git.commit_info(sha).parents) > 1
            return merge_count_cache[sha]

        def more_ancestral(a_name: str, b_name: str, mb: str) -> Optional[bool]:
            trunks = {'master', 'main'}
            if a_name in trunks and b_name not in trunks:
                return True
            if b_name in trunks and a_name not in trunks:
                return False
            a_line = first_parent_lines[a_name]
            a_line = first_parent_lines[a_name]
            b_line = first_parent_lines[b_name]
            mb_on_a = mb in fp_line_sets[a_name]
            mb_on_b = mb in fp_line_sets[b_name]
            if mb_on_a and (not mb_on_b):
                return True
            if mb_on_b and (not mb_on_a):
                return False
            if a_name in reach_from[b_name]:
                return True
            if b_name in reach_from[a_name]:
                return False
            a_beyond = a_line.index(mb)
            b_beyond = b_line.index(mb)
            if a_beyond > b_beyond:
                return True
            if a_beyond < b_beyond:
                return False
            a_merges = sum((1 for s in a_line[:a_beyond] if is_merge(s)))
            b_merges = sum((1 for s in b_line[:b_beyond] if is_merge(s)))
            if a_merges > b_merges:
                return True
            if a_merges < b_merges:
                return False
            a_reaches = sum((1 for other in self.branches if other != a_name and a_name in reach_from[other]))
            b_reaches = sum((1 for other in self.branches if other != b_name and b_name in reach_from[other]))
            if a_reaches > b_reaches:
                return True
            if a_reaches < b_reaches:
                return False
            return None
        for bname, binfo in self.branches.items():
            b_line = first_parent_lines[bname]
            candidates: list[tuple[str, str, int]] = []
            for aname, ainfo in self.branches.items():
                if aname == bname:
                    continue
                mb = get_mb(aname, bname)
                if not mb:
                    continue
                if mb not in fp_line_sets[aname]:
                    continue
                ancestral = more_ancestral(aname, bname, mb)
                if ancestral is not True:
                    continue
                if mb in fp_line_sets[bname]:
                    b_dist = b_line.index(mb)
                else:
                    b_dist = -1
                    for i, sha in enumerate(b_line):
                        if self.git.is_ancestor(mb, sha):
                            b_dist = i
                            break
                    if b_dist < 0:
                        continue
                candidates.append((aname, mb, b_dist))
            best_parent: Optional[str] = None
            best_mb: Optional[str] = None
            if candidates:
                candidates.sort(key=lambda c: c[2])
                best = candidates[0]
                for c in candidates[1:]:
                    if c[2] != best[2]:
                        break
                    mb_bc = get_mb(best[0], c[0])
                    ancestral_bc = more_ancestral(best[0], c[0], mb_bc)
                    if ancestral_bc is False:
                        best = c
                best_parent, best_mb, _ = best
            binfo.parent_branch = best_parent
            binfo.nesting_point = best_mb
            if best_parent is not None:
                binfo.own_commits = self.git.first_parent_shas_soft_stop(binfo.tip, best_mb)
                parent_line = first_parent_lines[best_parent]
                if best_mb in fp_line_sets[best_parent]:
                    binfo.fork_commit = best_mb
                else:
                    binfo.fork_commit = None
                    for sha in parent_line:
                        if self.git.is_ancestor(best_mb, sha):
                            binfo.fork_commit = sha
                            break
            else:
                binfo.own_commits = list(first_parent_lines[bname])
                binfo.fork_commit = None
        for binfo in self.branches.values():
            binfo.child_branches = []
        self.root_branches = []
        for bname, binfo in self.branches.items():
            if binfo.parent_branch is None:
                self.root_branches.append(bname)
            else:
                parent = self.branches.get(binfo.parent_branch)
                if parent:
                    parent.child_branches.append(bname)
        for binfo in self.branches.values():

            def get_fork_index(child_name: str) -> float:
                cinfo = self.branches[child_name]
                if cinfo.fork_commit and cinfo.fork_commit in binfo.own_commits:
                    return binfo.own_commits.index(cinfo.fork_commit)
                return float('inf')
            binfo.child_branches.sort(key=lambda c: (get_fork_index(c), c))
        self.root_branches.sort()
        self.current_branch_name = self.git.current_branch()
        self.head_tip = self.git.head_sha()

    def commit(self, sha: str) -> CommitInfo:
        if sha not in self._commit_cache:
            self._commit_cache[sha] = self.git.commit_info(sha)
        return self._commit_cache[sha]

    def diff_stats(self, sha: str) -> list[DiffStat]:
        if sha not in self._diff_stat_cache:
            self._diff_stat_cache[sha] = self.git.diff_stat(sha)
        return self._diff_stat_cache[sha]

    def refresh_branch(self, name: str) -> None:
        saved_show_children = set(self.show_children)
        saved_show_commits = set(self.show_commits)
        saved_show_details = set(self.show_commit_details)
        self.rebuild()
        self.show_children = saved_show_children & set(self.branches)
        self.show_commits = saved_show_commits & set(self.branches)
        self.show_commit_details = saved_show_details

    def visible_rows(self) -> list[Row]:
        rows: list[Row] = []

        def emit_branch(name: str, depth: int, ancestor_last: list[bool], is_last: bool) -> None:
            binfo = self.branches[name]
            is_head = self.current_branch_name == name or (self.current_branch_name is None and self.head_tip == binfo.tip)
            rows.append(Row(kind='branch', depth=depth, ancestor_last=list(ancestor_last), is_last=is_last, branch_name=name, owning_branch=name, branch_info=binfo, is_head=is_head))
            show_commits = name in self.show_commits
            show_children = name in self.show_children
            child_ancestor = ancestor_last + [is_last]
            if show_commits:
                children_by_np: dict[Optional[str], list[str]] = {}
                for cname in binfo.child_branches:
                    cinfo = self.branches[cname]
                    children_by_np.setdefault(cinfo.fork_commit, []).append(cname)
                commits_to_render = list(binfo.own_commits)
                emitted_nps = set(commits_to_render)
                leftovers = [c for c in binfo.child_branches if self.branches[c].fork_commit not in emitted_nps]
                for ci, sha in enumerate(commits_to_render):
                    has_later_children = False
                    if ci < len(commits_to_render) - 1 or leftovers:
                        has_later_children = True
                    commit_children_kinds: list[str] = []
                    if sha in self.show_commit_details:
                        commit_children_kinds.append('details')
                    if sha in children_by_np:
                        commit_children_kinds.append('branches')
                    commit_row_idx = len(rows)
                    rows.append(Row(kind='commit', depth=depth + 1, ancestor_last=list(child_ancestor), is_last=False, sha=sha, commit_info=self.commit(sha), owning_branch=name, is_head=False))
                    commit_is_last = not has_later_children and (not commit_children_kinds)
                    rows[commit_row_idx].is_last = commit_is_last
                    child_of_commit_ancestor = child_ancestor + [commit_is_last]
                    sub_children: list[tuple[str, str, object]] = []
                    if 'details' in commit_children_kinds:
                        sub_children.append(('message', sha, None))
                        for ds in self.diff_stats(sha):
                            sub_children.append(('file', sha, ds))
                    if 'branches' in commit_children_kinds:
                        for cname in children_by_np[sha]:
                            sub_children.append(('branch_child', cname, None))
                    for i, (ckind, ckey, payload) in enumerate(sub_children):
                        clast = i == len(sub_children) - 1
                        if ckind == 'message':
                            rows.append(Row(kind='message', depth=depth + 2, ancestor_last=list(child_of_commit_ancestor), is_last=clast, sha=ckey, commit_info=self.commit(ckey), owning_branch=name))
                        elif ckind == 'file':
                            ds = payload
                            rows.append(Row(kind='file', depth=depth + 2, ancestor_last=list(child_of_commit_ancestor), is_last=clast, sha=ckey, file=ds.file, diff_stat=ds, owning_branch=name, commit_info=self.commit(ckey)))
                        elif ckind == 'branch_child':
                            emit_branch(ckey, depth + 2, child_of_commit_ancestor, clast)
                for i, cname in enumerate(leftovers):
                    clast = i == len(leftovers) - 1
                    emit_branch(cname, depth + 1, child_ancestor, clast)
            elif show_children:
                for i, cname in enumerate(binfo.child_branches):
                    clast = i == len(binfo.child_branches) - 1
                    emit_branch(cname, depth + 1, child_ancestor, clast)
        for i, root in enumerate(self.root_branches):
            emit_branch(root, 0, [], i == len(self.root_branches) - 1)
        return rows
BRANCH_GLYPH = '⑂'
COMMIT_GLYPH = '●'

def style_branch_glyph(is_head: bool) -> str:
    return 'bold cyan' if is_head else 'cyan'

def style_commit_glyph(is_merge: bool) -> str:
    return 'magenta' if is_merge else 'yellow'

def render_row(row: Row, is_cursor: bool) -> Text:
    line = Text()
    for anc_last in row.ancestor_last:
        if anc_last:
            line.append('   ')
        else:
            line.append('│  ')
    if row.depth > 0:
        if row.is_last:
            line.append('└─ ')
        else:
            line.append('├─ ')
    if row.kind == 'branch':
        binfo = row.branch_info
        head_tag = ' [HEAD]' if row.is_head else ''
        line.append(BRANCH_GLYPH + ' ', style=style_branch_glyph(row.is_head))
        line.append(binfo.name, style='bold' if row.is_head else '')
        if head_tag:
            line.append(head_tag, style='bold green')
        try:
            cmt = binfo and row.owning_branch and None
        except Exception:
            pass
    elif row.kind == 'commit':
        cinfo = row.commit_info
        line.append(COMMIT_GLYPH + ' ', style=style_commit_glyph(cinfo.is_merge))
        short = cinfo.sha[:7]
        line.append(short + '  ', style='magenta' if cinfo.is_merge else 'yellow')
        line.append(cinfo.subject)
        if cinfo.is_merge:
            line.append('   (merge)', style='italic magenta')
    elif row.kind == 'message':
        cinfo = row.commit_info
        line.append(f'message: "{cinfo.subject}"', style='italic dim')
    elif row.kind == 'file':
        ds = row.diff_stat
        status_color = {'A': 'green', 'M': 'yellow', 'D': 'red', 'R': 'blue'}.get(ds.status, 'white')
        stat_str = f' (+{ds.added}/-{ds.deleted})' if ds.status in ('A', 'M', 'D') else ''
        line.append(ds.file, style=status_color)
        line.append(stat_str, style='dim')
    if is_cursor:
        line.stylize('reverse')
    return line

def render_branch_content(binfo: BranchInfo, state: TreeState) -> Text:
    git = state.git
    text = Text()
    text.append('Branch: ', style='bold cyan')
    text.append(binfo.name + '\n\n', style='bold')
    if binfo.parent_branch:
        parent = state.branches[binfo.parent_branch]
        text.append('Parent branch: ', style='dim')
        text.append(parent.name + '\n', style='cyan')
        text.append('Forked from:    ', style='dim')
        text.append(f'{binfo.nesting_point[:7]}  {state.commit(binfo.nesting_point).subject}\n', style='white')
        ahead, behind = git.ahead_behind(binfo.name, parent.name)
        text.append('Ahead/behind:   ', style='dim')
        text.append(f'+{ahead} / -{behind}\n', style='green' if ahead else 'white')
    else:
        text.append('(root branch — no parent)\n', style='dim')
    text.append('\n')
    tip_cmt = state.commit(binfo.tip)
    text.append('Tip commit:     ', style='dim')
    text.append(f'{tip_cmt.sha[:7]}  {tip_cmt.subject}\n', style='white')
    text.append('Author:         ', style='dim')
    text.append(f'{tip_cmt.author}  ({tip_cmt.author_date})\n', style='white')
    text.append('Commit count:   ', style='dim')
    text.append(f'{len(binfo.own_commits)} (first-parent walk)\n', style='white')
    text.append('HEAD:           ', style='dim')
    text.append('yes\n' if state.current_branch_name == binfo.name else 'no\n', style='green' if state.current_branch_name == binfo.name else 'white')
    text.append('\n')
    text.append('\nCommits in this branch:\n', style='bold')
    if not binfo.own_commits:
        text.append('(no unique commits)\n', style='dim')
    else:
        for sha in binfo.own_commits:
            cmt = state.commit(sha)
            text.append(f'\n{sha[:7]}  ', style='bold yellow')
            text.append(f'{cmt.subject}\n', style='bold white')
            stats = state.diff_stats(sha)
            if not stats:
                text.append('  (no changes)\n', style='dim')
            else:
                for ds in stats:
                    color = {'A': 'green', 'M': 'yellow', 'D': 'red', 'R': 'blue'}.get(ds.status, 'white')
                    text.append(f'  {ds.status} ', style=color)
                    text.append(ds.file)
                    if ds.status in ('A', 'M', 'D'):
                        text.append(f'  (+{ds.added}/-{ds.deleted})\n', style='dim')
                    else:
                        text.append('\n')
    return text

def render_commit_content(cinfo: CommitInfo, state: TreeState) -> Text:
    text = Text()
    text.append('Commit: ', style='bold yellow')
    text.append(cinfo.sha[:7] + '\n\n', style='bold')
    text.append('Full hash:  ', style='dim')
    text.append(cinfo.sha + '\n', style='white')
    text.append('Author:     ', style='dim')
    text.append(f'{cinfo.author}  ({cinfo.author_date})\n', style='white')
    text.append('Commit date:', style='dim')
    text.append(f'  {cinfo.commit_date}\n', style='white')
    text.append('Parents:    ', style='dim')
    if not cinfo.parents:
        text.append('(root commit)\n', style='dim')
    else:
        for i, psha in enumerate(cinfo.parents):
            label = 'merge parent' if cinfo.is_merge and i == 1 else 'parent'
            try:
                pcmt = state.commit(psha)
                text.append(f'\n  {label} {psha[:7]}  {pcmt.subject}', style='magenta' if cinfo.is_merge and i == 1 else 'white')
            except Exception:
                text.append(f'\n  {label} {psha[:7]}', style='white')
        text.append('\n')
        if cinfo.is_merge:
            text.append('  (merge commit — has multiple parents)\n', style='italic magenta')
    text.append('\n')
    text.append('Message:\n', style='bold')
    text.append(cinfo.subject + '\n', style='white')
    if cinfo.body:
        text.append(cinfo.body.rstrip() + '\n', style='dim')
    text.append('\n')
    text.append('Changed files:\n', style='bold')
    for ds in state.diff_stats(cinfo.sha):
        color = {'A': 'green', 'M': 'yellow', 'D': 'red', 'R': 'blue'}.get(ds.status, 'white')
        text.append(f'  {ds.status} ', style=color)
        text.append(ds.file)
        if ds.status in ('A', 'M', 'D'):
            text.append(f'  (+{ds.added}/-{ds.deleted})\n', style='dim')
        else:
            text.append('\n')
    text.append('\n')
    text.append('Full diff:\n', style='bold')
    try:
        diff = state.git.full_diff(cinfo.sha)
        if diff:
            for line in diff.splitlines():
                if line.startswith('+') and (not line.startswith('+++')):
                    text.append(line + '\n', style='green')
                elif line.startswith('-') and (not line.startswith('---')):
                    text.append(line + '\n', style='red')
                elif line.startswith('@@'):
                    text.append(line + '\n', style='cyan')
                elif line.startswith('diff ') or line.startswith('index '):
                    text.append(line + '\n', style='bold yellow')
                else:
                    text.append(line + '\n', style='white')
        else:
            text.append('(no diff)\n', style='dim')
    except Exception as e:
        text.append(f'(error reading diff: {e})\n', style='red')
    return text

def render_message_content(cinfo: CommitInfo) -> Text:
    text = Text()
    text.append('Commit message:\n\n', style='bold')
    text.append(cinfo.subject + '\n', style='white')
    if cinfo.body:
        text.append('\n' + cinfo.body.rstrip() + '\n', style='dim')
    text.append('\n')
    text.append(f'From commit {cinfo.sha[:7]}\n', style='dim')
    return text

def render_file_content(cinfo: CommitInfo, ds: DiffStat, state: TreeState) -> Text:
    text = Text()
    text.append('File diff: ', style='bold')
    color = {'A': 'green', 'M': 'yellow', 'D': 'red', 'R': 'blue'}.get(ds.status, 'white')
    text.append(ds.file + '\n', style=color)
    text.append(f'Commit: {cinfo.sha[:7]}  {cinfo.subject}\n\n', style='dim')
    try:
        diff = state.git.file_diff(cinfo.sha, ds.file)
        if diff:
            for line in diff.splitlines():
                if line.startswith('+') and (not line.startswith('+++')):
                    text.append(line + '\n', style='green')
                elif line.startswith('-') and (not line.startswith('---')):
                    text.append(line + '\n', style='red')
                elif line.startswith('@@'):
                    text.append(line + '\n', style='cyan')
                elif line.startswith('diff ') or line.startswith('index '):
                    text.append(line + '\n', style='bold yellow')
                else:
                    text.append(line + '\n', style='white')
        else:
            text.append('(no diff content)\n', style='dim')
    except Exception as e:
        text.append(f'(error reading file diff: {e})\n', style='red')
    return text

class TreeWidget(Static):
    can_focus = True
    cursor_index: reactive[int] = reactive(0)
    viewport_y: reactive[int] = reactive(0)

    class CursorMoved(Message):

        def __init__(self, row: Optional[Row]) -> None:
            self.row = row
            super().__init__()

    def __init__(self, state: TreeState, **kwargs):
        super().__init__(**kwargs)
        self.state = state
        self._rows: list[Row] = []
        self.cursor_index = 0
        self.auto_scroll = True

    def on_mount(self) -> None:
        self.recompute_rows()
        self.refresh()
        self.focus()

    def recompute_rows(self) -> None:
        prev_identity = None
        if 0 <= self.cursor_index < len(self._rows):
            prev_identity = self._rows[self.cursor_index].identity()
        self._rows = self.state.visible_rows()
        if prev_identity is not None:
            for i, r in enumerate(self._rows):
                if r.identity() == prev_identity:
                    self.cursor_index = i
                    self._ensure_cursor_visible()
                    self.refresh()
                    self._emit_cursor_moved()
                    return
        if self._rows:
            self.cursor_index = min(self.cursor_index, len(self._rows) - 1)
        else:
            self.cursor_index = 0
        self._ensure_cursor_visible()
        self.refresh()
        self._emit_cursor_moved()

    def _emit_cursor_moved(self) -> None:
        row = self._rows[self.cursor_index] if 0 <= self.cursor_index < len(self._rows) else None
        self.post_message(self.CursorMoved(row))

    def _ensure_cursor_visible(self) -> None:
        if not self._rows:
            return
        height = self.size.height
        if height <= 0:
            return
        if self.cursor_index < self.viewport_y:
            self.viewport_y = self.cursor_index
        elif self.cursor_index >= self.viewport_y + height:
            self.viewport_y = self.cursor_index - height + 1

    def render(self) -> Text:
        if not self._rows:
            return Text('(no branches found)\n', style='dim')
        height = max(self.size.height, 1)
        start = self.viewport_y
        end = min(start + height, len(self._rows))
        lines = []
        for i in range(start, end):
            row = self._rows[i]
            is_cursor = i == self.cursor_index
            line = render_row(row, is_cursor)
            lines.append(line)
        while len(lines) < height:
            lines.append(Text())
        return Text('\n').join(lines)

    def on_mouse_scroll_down(self, event) -> None:
        if self.viewport_y + self.size.height < len(self._rows):
            self.viewport_y += 1
            event.stop()

    def on_mouse_scroll_up(self, event) -> None:
        if self.viewport_y > 0:
            self.viewport_y -= 1
            event.stop()

    def _move_cursor(self, delta: int) -> None:
        if not self._rows:
            return
        new_idx = max(0, min(len(self._rows) - 1, self.cursor_index + delta))
        if new_idx != self.cursor_index:
            self.cursor_index = new_idx
            self._ensure_cursor_visible()
            self.refresh()
            self._emit_cursor_moved()

    def _parent_index(self, idx: int) -> Optional[int]:
        if idx < 0 or idx >= len(self._rows):
            return None
        row = self._rows[idx]
        target_depth = row.depth - 1
        if target_depth < 0:
            return None
        for i in range(idx - 1, -1, -1):
            r = self._rows[i]
            if r.depth == target_depth:
                return i
            if r.depth < target_depth:
                continue
        return None

    def _owning_branch_of(self, idx: int) -> Optional[str]:
        if idx < 0 or idx >= len(self._rows):
            return None
        row = self._rows[idx]
        for i in range(idx, -1, -1):
            r = self._rows[i]
            if r.kind == 'branch':
                return r.branch_name
        return None

    def _collapse_current(self) -> bool:
        if not self._rows:
            return False
        row = self._rows[self.cursor_index]
        if row.kind == 'branch':
            name = row.branch_name
            if name in self.state.show_commits:
                self.state.show_commits.discard(name)
                if row.branch_info.child_branches:
                    self.state.show_children.add(name)
                self.recompute_rows()
                return True
            if name in self.state.show_children:
                self.state.show_children.discard(name)
                self.recompute_rows()
                return True
            return False
        elif row.kind == 'commit':
            sha = row.sha
            if sha in self.state.show_commit_details:
                self.state.show_commit_details.discard(sha)
                self.recompute_rows()
                return True
            return False
        return False

    def _expand_current(self) -> None:
        if not self._rows:
            return
        row = self._rows[self.cursor_index]
        if row.kind == 'branch':
            name = row.branch_name
            binfo = row.branch_info
            if name not in self.state.show_children and name not in self.state.show_commits:
                if binfo.child_branches:
                    self.state.show_children.add(name)
                else:
                    self.state.show_commits.add(name)
                self.recompute_rows()
                return
            if name in self.state.show_children and name not in self.state.show_commits:
                self.state.show_children.discard(name)
                self.state.show_commits.add(name)
                self.recompute_rows()
                return
            return
        elif row.kind == 'commit':
            sha = row.sha
            if sha not in self.state.show_commit_details:
                self.state.show_commit_details.add(sha)
                self.recompute_rows()
                return
            return

    def _refresh_current(self) -> None:
        name = self._owning_branch_of(self.cursor_index)
        if name is None:
            return
        self.state.refresh_branch(name)
        self.recompute_rows()
        self.app.bell()

class ContentWidget(VerticalScroll):

    def __init__(self, state: TreeState, **kwargs):
        super().__init__(**kwargs)
        self.state = state

    def compose(self) -> ComposeResult:
        yield Static(id='content-text')

    def show_row(self, row: Optional[Row]) -> None:
        if row is None:
            text = Text('(no selection)\n', style='dim')
        else:
            try:
                if row.kind == 'branch':
                    text = render_branch_content(row.branch_info, self.state)
                elif row.kind == 'commit':
                    text = render_commit_content(row.commit_info, self.state)
                elif row.kind == 'message':
                    text = render_message_content(row.commit_info)
                elif row.kind == 'file':
                    text = render_file_content(row.commit_info, row.diff_stat, self.state)
                else:
                    text = Text('(unknown row)\n', style='dim')
            except Exception as e:
                text = Text(f'(error rendering content: {e})\n', style='red')
        self.query_one('#content-text', Static).update(text)
        self.scroll_home(animate=False)
CSS = '\nScreen {\n    layout: horizontal;\n}\n\n#tree-pane {\n    width: 2fr;\n    height: 100%;\n    border: solid $primary;\n    padding: 0 1;\n    background: $surface;\n}\n\n#tree-pane.hidden {\n    display: none;\n}\n\n#content-pane {\n    width: 3fr;\n    height: 100%;\n    border: solid $accent;\n    padding: 0 1;\n    background: $surface;\n    overflow-y: auto;\n}\n\n#content-text {\n    width: 100%;\n    height: auto;\n}\n\nHeader {\n    dock: top;\n    height: 1;\n}\n\nFooter {\n    dock: bottom;\n    height: 1;\n}\n'

class GitNavigatorApp(App):
    CSS = CSS
    BINDINGS = [('j', 'move_down', 'Down'), ('k', 'move_up', 'Up'), ('h', 'collapse_or_parent', 'Collapse/Parent'), ('l', 'expand', 'Expand'), ('o', 'toggle_fullscreen', 'Fullscreen'), ('r', 'refresh', 'Refresh'), ('g', 'goto_top', 'Top'), ('G', 'goto_bottom', 'Bottom'), ('q', 'quit', 'Quit')]

    def __init__(self, repo_path: str):
        super().__init__()
        self.repo_path = repo_path
        self.git = Git(repo_path)
        self.state = TreeState(self.git)

    def _tree(self) -> 'TreeWidget':
        return self.query_one('#tree-pane', TreeWidget)

    def action_toggle_fullscreen(self) -> None:
        tree = self._tree()
        if tree.has_class('hidden'):
            tree.remove_class('hidden')
        else:
            tree.add_class('hidden')

    def action_quit(self) -> None:
        tree = self._tree()
        selected_hash = None
        if tree._rows and 0 <= tree.cursor_index < len(tree._rows):
            row = tree._rows[tree.cursor_index]
            if row.kind == 'branch' and row.branch_info:
                selected_hash = row.branch_info.tip
            elif row.sha:
                selected_hash = row.commit_info.sha if row.commit_info else row.sha
        self.exit(selected_hash)

    def action_move_down(self) -> None:
        tree = self._tree()
        if tree.has_class('hidden'):
            self.query_one('#content-pane').scroll_down(animate=False)
        else:
            tree._move_cursor(1)

    def action_move_up(self) -> None:
        tree = self._tree()
        if tree.has_class('hidden'):
            self.query_one('#content-pane').scroll_up(animate=False)
        else:
            tree._move_cursor(-1)

    def action_goto_top(self) -> None:
        tree = self._tree()
        if tree.has_class('hidden'):
            self.query_one('#content-pane').scroll_home(animate=False)
        else:
            tree.cursor_index = 0
            tree._ensure_cursor_visible()
            tree.refresh()
            tree._emit_cursor_moved()

    def action_goto_bottom(self) -> None:
        tree = self._tree()
        if tree.has_class('hidden'):
            self.query_one('#content-pane').scroll_end(animate=False)
        else:
            tree.cursor_index = max(0, len(tree._rows) - 1)
            tree._ensure_cursor_visible()
            tree.refresh()
            tree._emit_cursor_moved()

    def action_collapse_or_parent(self) -> None:
        tree = self._tree()
        if not tree._collapse_current():
            parent = tree._parent_index(tree.cursor_index)
            if parent is not None:
                tree.cursor_index = parent
                tree._ensure_cursor_visible()
                tree.refresh()
                tree._emit_cursor_moved()

    def action_expand(self) -> None:
        self._tree()._expand_current()

    def action_refresh(self) -> None:
        self._tree()._refresh_current()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            yield TreeWidget(self.state, id='tree-pane')
            yield ContentWidget(self.state, id='content-pane')
        yield Footer()

    def on_mount(self) -> None:
        self.title = 'Git Navigator'
        self.sub_title = self.repo_path
        try:
            self.state.rebuild()
        except Exception as e:
            self.exit(f'Error building git snapshot: {e}')
            return
        current = self.state.current_branch_name
        if current and current in self.state.branches:
            target = current
        elif self.state.root_branches:
            target = self.state.root_branches[0]
        else:
            target = None
        if target:
            chain: list[str] = []
            cursor: Optional[str] = target
            seen = set()
            while cursor and cursor not in seen:
                seen.add(cursor)
                chain.append(cursor)
                binfo = self.state.branches.get(cursor)
                if not binfo:
                    break
                cursor = binfo.parent_branch
            for name in reversed(chain):
                self.state.show_children.add(name)
        tree = self.query_one('#tree-pane', TreeWidget)
        tree.recompute_rows()
        if target:
            for i, r in enumerate(tree._rows):
                if r.kind == 'branch' and r.branch_name == target:
                    tree.cursor_index = i
                    tree._ensure_cursor_visible()
                    break
        tree.refresh()
        tree._emit_cursor_moved()

    def on_tree_widget_cursor_moved(self, event: TreeWidget.CursorMoved) -> None:
        content = self.query_one('#content-pane', ContentWidget)
        content.show_row(event.row)

    def action_refresh(self) -> None:
        tree = self.query_one('#tree-pane', TreeWidget)
        tree._refresh_current()

def main() -> int:
    if len(sys.argv) > 1:
        repo_path = sys.argv[1]
    else:
        repo_path = os.getcwd()
    repo_path = os.path.abspath(repo_path)
    try:
        app = GitNavigatorApp(repo_path)
    except GitError as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1
    try:
        result = app.run()
        if isinstance(result, str):
            print(result)
    except KeyboardInterrupt:
        return 130
    return 0
if __name__ == '__main__':
    sys.exit(main())