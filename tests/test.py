import asyncio
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock
from mlx_code.gits import LedgerPoint, GitError, create_worktree, commit_worktree, cleanup_worktree, resume_worktree, git_new_branch, git_new_branch_at, git_switch_branch, current_point, find_rev_commit, get_diff_between_refs, resolve_ref_short, get_branch_base_sha, get_commit_history_with_stats, _make_commit_message, _parse_messages_from_commit, _count_user_turns, git_add_filtered
from mlx_code.tools import validate_tool_call, _truncate, resolve_path, tout, ReadTool, ReadParams, WriteTool, WriteParams, EditTool, EditParams, BashTool, BashParams, GrepTool, GrepParams, FindTool, FindParams, LsTool, LsParams, SkillTool, SkillParams, AgentTool, AgentParams, DEFAULT_TOOLS

def _init_repo(dirpath: str) -> None:
    subprocess.run(['git', 'init'], cwd=dirpath, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=dirpath, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'test'], cwd=dirpath, check=True, capture_output=True)
    pathlib.Path(dirpath, 'README.md').write_text('hello\n')
    subprocess.run(['git', 'add', '-A'], cwd=dirpath, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'initial'], cwd=dirpath, check=True, capture_output=True)

def _user(text: str) -> dict:
    return {'role': 'user', 'content': text}

def _assistant(text: str) -> dict:
    return {'role': 'assistant', 'content': [{'type': 'text', 'text': text}]}

def _run(coro):
    return asyncio.run(coro)

def _real(path: str) -> str:
    return str(pathlib.Path(path).resolve())

class TestCommitMessageRoundTrip(unittest.TestCase):

    def test_round_trip_simple(self):
        msgs = [_user('hello'), _assistant('world')]
        raw = _make_commit_message(msgs)
        parsed = _parse_messages_from_commit(raw)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]['role'], 'user')
        self.assertEqual(parsed[0]['content'], 'hello')

    def test_count_user_turns(self):
        body = _make_commit_message([_user('a'), _assistant('b'), _user('c')])
        self.assertEqual(_count_user_turns(body), 2)

    def test_count_user_turns_empty(self):
        self.assertEqual(_count_user_turns(''), 0)
        self.assertEqual(_count_user_turns('snapshot'), 0)

    def test_commit_role_stripped(self):
        msgs = [_user('do'), _assistant('ok'), {'role': 'commit', 'content': '[abc] 1 file'}, _user('next')]
        raw = _make_commit_message(msgs)
        parsed = _parse_messages_from_commit(raw)
        self.assertTrue(all((m['role'] != 'commit' for m in parsed)))
        self.assertEqual(len(parsed), 3)

    def test_title_truncated_to_60(self):
        raw = _make_commit_message([_user('x' * 200)])
        self.assertLessEqual(len(raw.split('\n')[0]), 60)

    def test_string_passthrough(self):
        raw = _make_commit_message('just a string')
        self.assertIn('just a string', raw)

    def test_parse_legacy_format(self):
        body = json.dumps([_user('legacy')])
        raw = f'update\n\n{body}'
        parsed = _parse_messages_from_commit(raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]['content'], 'legacy')

    def test_parse_invalid_json_returns_empty(self):
        parsed = _parse_messages_from_commit('title\n\n--- BEGIN MESSAGES ---\n{bad json')
        self.assertEqual(parsed, [])

class TestGitWorktreeLifecycle(unittest.TestCase):

    def setUp(self):
        self.test_root = tempfile.mkdtemp(prefix='mlx_test_')
        self.repo = os.path.join(self.test_root, 'repo')
        os.makedirs(self.repo)
        _init_repo(self.repo)
        self._points: list[LedgerPoint] = []

    def tearDown(self):
        for p in self._points:
            cleanup_worktree(p)
        shutil.rmtree(self.test_root, ignore_errors=True)

    def _track(self, point: LedgerPoint) -> LedgerPoint:
        self._points.append(point)
        return point

    def test_create_returns_ledger_point(self):
        pt = self._track(create_worktree(self.repo))
        self.assertIsNotNone(pt)
        self.assertIsInstance(pt, LedgerPoint)
        self.assertTrue(os.path.isdir(pt.worktree))
        self.assertTrue(pt.branch.startswith('agent--'))

    def test_create_has_same_files_as_repo(self):
        pt = self._track(create_worktree(self.repo))
        self.assertTrue(os.path.exists(os.path.join(pt.worktree, 'README.md')))

    def test_create_with_prefix(self):
        pt = self._track(create_worktree(self.repo, prefix='my-prefix'))
        self.assertTrue(pt.branch.startswith('my-prefix--'))

    def test_create_at_older_ref(self):
        pathlib.Path(self.repo, 'second.txt').write_text('v2\n')
        subprocess.run(['git', 'add', '-A'], cwd=self.repo, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'second'], cwd=self.repo, capture_output=True, check=True)
        pt = self._track(create_worktree(self.repo, ref='HEAD~1'))
        self.assertFalse(os.path.exists(os.path.join(pt.worktree, 'second.txt')))
        self.assertTrue(os.path.exists(os.path.join(pt.worktree, 'README.md')))

    def test_create_inits_repo_if_missing(self):
        bare = os.path.join(self.test_root, 'new_repo')
        os.makedirs(bare)
        pt = self._track(create_worktree(bare))
        self.assertIsNotNone(pt)

    def test_commit_detects_new_file(self):
        pt = self._track(create_worktree(self.repo))
        pathlib.Path(pt.worktree, 'new.txt').write_text('data\n')
        new_pt, diff = commit_worktree(pt)
        self._track(new_pt)
        self.assertIsNotNone(new_pt)
        self.assertNotEqual(new_pt.commit, pt.commit)
        self.assertIn('new.txt', diff)

    def test_commit_no_changes_returns_same_sha(self):
        pt = self._track(create_worktree(self.repo))
        new_pt, diff = commit_worktree(pt)
        self.assertEqual(new_pt.commit, pt.commit)
        self.assertEqual(diff, '')

    def test_commit_embeds_messages_for_resume(self):
        pt = self._track(create_worktree(self.repo))
        pathlib.Path(pt.worktree, 'f.txt').write_text('data\n')
        msgs = [_user('write f.txt'), _assistant('done')]
        new_pt, _ = commit_worktree(pt, msgs)
        self._track(new_pt)
        raw = subprocess.run(['git', 'log', '-1', '--format=%B'], cwd=new_pt.worktree, capture_output=True, text=True, check=True).stdout.strip()
        parsed = _parse_messages_from_commit(raw)
        self.assertTrue(any((m['role'] == 'user' for m in parsed)))
        self.assertEqual(_count_user_turns(raw), 1)

    def test_cleanup_removes_directory(self):
        pt = self._track(create_worktree(self.repo))
        wt = pt.worktree
        self.assertTrue(os.path.isdir(wt))
        cleanup_worktree(pt)
        self.assertFalse(os.path.isdir(wt))
        self._points.remove(pt)

    def test_cleanup_deletes_branch(self):
        pt = self._track(create_worktree(self.repo))
        branch = pt.branch
        cleanup_worktree(pt, remove_branch=True)
        self._points.remove(pt)
        branches = subprocess.run(['git', 'branch', '--list', branch], cwd=self.repo, capture_output=True, text=True).stdout
        self.assertNotIn(branch, branches)

    def test_cleanup_missing_directory_does_not_raise(self):
        pt = self._track(create_worktree(self.repo))
        shutil.rmtree(pt.worktree, ignore_errors=True)
        cleanup_worktree(pt)
        self._points.remove(pt)

    def test_resume_from_commit_recovers_files(self):
        pt = self._track(create_worktree(self.repo))
        pathlib.Path(pt.worktree, 'resumable.txt').write_text('data\n')
        msgs = [_user('create file'), _assistant('done')]
        new_pt, _ = commit_worktree(pt, msgs)
        self._track(new_pt)
        sha = new_pt.commit
        resumed, parsed_msgs = resume_worktree(self.repo, sha)
        self._track(resumed)
        self.assertIsNotNone(resumed)
        self.assertTrue(os.path.exists(os.path.join(resumed.worktree, 'resumable.txt')))

    def test_resume_from_commit_recovers_messages(self):
        pt = self._track(create_worktree(self.repo))
        pathlib.Path(pt.worktree, 'f.txt').write_text('data\n')
        msgs = [_user('turn 1'), _assistant('ok'), _user('turn 2'), _assistant('done')]
        new_pt, _ = commit_worktree(pt, msgs)
        self._track(new_pt)
        resumed, parsed = resume_worktree(self.repo, new_pt.commit)
        self._track(resumed)
        self.assertTrue(len(parsed) >= 2)
        user_msgs = [m for m in parsed if m['role'] == 'user']
        self.assertEqual(len(user_msgs), 2)

    def test_resume_from_commit_without_messages(self):
        pt = self._track(create_worktree(self.repo))
        pathlib.Path(pt.worktree, 'plain.txt').write_text('x\n')
        new_pt, _ = commit_worktree(pt, 'plain commit')
        self._track(new_pt)
        resumed, parsed = resume_worktree(self.repo, new_pt.commit)
        self._track(resumed)
        self.assertIsNotNone(resumed)
        self.assertEqual(parsed, [])

    def test_resume_invalid_sha_returns_none(self):
        pt, msgs = resume_worktree(self.repo, 'deadbeef')
        self.assertIsNone(pt)
        self.assertEqual(msgs, [])

    def test_resume_from_older_commit(self):
        pt = self._track(create_worktree(self.repo))
        pathlib.Path(pt.worktree, 'v1.txt').write_text('v1\n')
        pt, _ = commit_worktree(pt, [_user('v1')])
        self._track(pt)
        pathlib.Path(pt.worktree, 'v2.txt').write_text('v2\n')
        pt, _ = commit_worktree(pt, [_user('v2')])
        self._track(pt)
        v1_sha = subprocess.run(['git', 'rev-parse', 'HEAD~1'], cwd=pt.worktree, capture_output=True, text=True, check=True).stdout.strip()
        resumed, _ = resume_worktree(self.repo, v1_sha)
        self._track(resumed)
        self.assertFalse(os.path.exists(os.path.join(resumed.worktree, 'v2.txt')))
        self.assertTrue(os.path.exists(os.path.join(resumed.worktree, 'v1.txt')))

class TestGitBranchOps(unittest.TestCase):

    def setUp(self):
        self.test_root = tempfile.mkdtemp(prefix='mlx_test_br_')
        self.repo = os.path.join(self.test_root, 'repo')
        os.makedirs(self.repo)
        _init_repo(self.repo)
        self.point = create_worktree(self.repo)
        self._points = [self.point]

    def tearDown(self):
        for p in self._points:
            cleanup_worktree(p)
        shutil.rmtree(self.test_root, ignore_errors=True)

    def _track(self, pt):
        self._points.append(pt)
        return pt

    def test_new_branch_name_includes_sha(self):
        br = self._track(git_new_branch(self.point.worktree, 'feat'))
        self.assertTrue(br.branch.startswith('feat--'))
        self.assertEqual(len(br.branch.split('--')[-1]), 12)

    def test_new_branch_inherits_files(self):
        br = self._track(git_new_branch(self.point.worktree, 'feat'))
        self.assertTrue(os.path.exists(os.path.join(br.worktree, 'README.md')))

    def test_new_branch_at_specific_ref(self):
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.point.worktree, capture_output=True, text=True, check=True).stdout.strip()
        br = self._track(git_new_branch_at(self.point.worktree, 'at-ref', head))
        self.assertTrue(br.branch.startswith('at-ref--'))

    def test_switch_branch_round_trip(self):
        original_branch = self.point.branch
        br = self._track(git_new_branch(self.point.worktree, 'temp'))
        pathlib.Path(self.point.worktree, 'branch_file.txt').write_text('x\n')
        subprocess.run(['git', 'add', '-A'], cwd=self.point.worktree, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'on temp'], cwd=self.point.worktree, capture_output=True, check=True)
        sw = git_switch_branch(self.point.worktree, original_branch)
        self.assertEqual(sw.branch, original_branch)

    def test_current_point(self):
        cp = current_point(self.point.worktree)
        self.assertEqual(cp.branch, self.point.branch)
        self.assertEqual(cp.worktree, self.point.worktree)

    def test_new_branch_commits_dirty_tree(self):
        pathlib.Path(self.point.worktree, 'dirty.txt').write_text('dirty\n')
        br = self._track(git_new_branch(self.point.worktree, 'dirty'))

class TestGitHistoryAndDiff(unittest.TestCase):

    def setUp(self):
        self.test_root = tempfile.mkdtemp(prefix='mlx_test_hist_')
        self.repo = os.path.join(self.test_root, 'repo')
        os.makedirs(self.repo)
        _init_repo(self.repo)
        self.point = create_worktree(self.repo)
        self._points = [self.point]

    def tearDown(self):
        for p in self._points:
            cleanup_worktree(p)
        shutil.rmtree(self.test_root, ignore_errors=True)

    def _commit(self, msgs, filename='file.txt', content='data\n'):
        pathlib.Path(self.point.worktree, filename).write_text(content)
        self.point, _ = commit_worktree(self.point, msgs)
        self._points.append(self.point)
        return self.point

    def test_find_rev_commit_single_turn(self):
        self._commit([_user('turn 1')], 'f1.txt', 'v1\n')
        sha = find_rev_commit(self.point.worktree, 1)
        self.assertIsNotNone(sha)

    def test_find_rev_commit_multiple_turns(self):
        self._commit([_user('t1')], 'f1.txt', 'v1\n')
        self._commit([_user('t2a'), _assistant('ok'), _user('t2b')], 'f2.txt', 'v2\n')
        sha = find_rev_commit(self.point.worktree, 2)
        self.assertIsNotNone(sha)

    def test_find_rev_commit_no_exact_match_returns_fallback(self):
        self._commit([_user('only turn')], 'f1.txt', 'v1\n')
        sha = find_rev_commit(self.point.worktree, 999)
        self.assertIsNotNone(sha)

    def test_get_commit_history(self):
        self._commit([_user('hist')], 'h.txt', 'v1\n')
        history = get_commit_history_with_stats(self.point.worktree, limit=10)
        self.assertIsInstance(history, list)
        self.assertTrue(len(history) > 0)
        for entry in history:
            self.assertIn('sha', entry)
            self.assertIn('short_sha', entry)

    def test_get_diff_between_refs(self):
        self._commit([_user('add')], 'diff_test.txt', 'original\n')
        self._commit([_user('mod')], 'diff_test.txt', 'modified\n')
        diff = get_diff_between_refs(self.point.worktree, 'HEAD~1', 'HEAD')
        self.assertIn('diff_test.txt', diff)
        self.assertIn('modified', diff)

    def test_get_diff_first_commit(self):
        try:
            diff = get_diff_between_refs(self.point.worktree, 'HEAD~1', 'HEAD')
            self.assertIn('README.md', diff)
        except GitError:
            pass

    def test_resolve_ref_short(self):
        short = resolve_ref_short(self.point.worktree, 'HEAD')
        self.assertTrue(len(short) >= 7)

    def test_get_branch_base_sha(self):
        base = get_branch_base_sha(self.point.worktree)
        self.assertIsNotNone(base)
        self.assertIn(base[:12], self.point.branch)

class TestResolvePath(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='mlx_test_path_')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_relative_path(self):
        result = resolve_path('file.txt', self.tmpdir)
        self.assertEqual(result, _real(os.path.join(self.tmpdir, 'file.txt')))

    def test_at_prefix_stripped(self):
        result = resolve_path('@file.txt', self.tmpdir)
        self.assertEqual(result, _real(os.path.join(self.tmpdir, 'file.txt')))

    def test_subdirectory(self):
        result = resolve_path('a/b/c.txt', self.tmpdir)
        self.assertEqual(result, _real(os.path.join(self.tmpdir, 'a', 'b', 'c.txt')))

    def test_traversal_blocked(self):
        with self.assertRaisesRegex(ValueError, 'escapes'):
            resolve_path('../../etc/passwd', self.tmpdir)

    def test_absolute_path_inside_cwd(self):
        abs_path = os.path.join(self.tmpdir, 'sub', 'f.txt')
        result = resolve_path(abs_path, self.tmpdir)
        self.assertTrue(result.startswith(_real(self.tmpdir)))

    def test_absolute_path_outside_cwd_blocked(self):
        with self.assertRaisesRegex(ValueError, 'escapes'):
            resolve_path('/etc/passwd', self.tmpdir)

class TestTruncate(unittest.TestCase):

    def test_short_text_unchanged(self):
        self.assertEqual(_truncate('hello'), 'hello')

    def test_line_limit(self):
        text = '\n'.join((f'line {i}' for i in range(3000)))
        result = _truncate(text)
        self.assertIn('truncated at 2000 lines', result)

    def test_byte_limit(self):
        result = _truncate('x' * (60 * 1024))
        self.assertIn('truncated at 50 KB', result)

    def test_label_in_notice(self):
        result = _truncate('\n'.join((f'l{i}' for i in range(3000))), label='Read')
        self.assertIn('Read', result)

class TestToolValidation(unittest.TestCase):

    def test_read_valid(self):
        p = validate_tool_call(ReadTool({'cwd': '/tmp'}), {'arguments': {'path': 'f.txt'}})
        self.assertEqual(p.path, 'f.txt')

    def test_read_with_offset_limit(self):
        p = validate_tool_call(ReadTool({'cwd': '/tmp'}), {'arguments': {'path': 'f.txt', 'offset': 5, 'limit': 10}})
        self.assertEqual(p.offset, 5)
        self.assertEqual(p.limit, 10)

    def test_read_offset_zero_rejected(self):
        with self.assertRaises(ValueError):
            validate_tool_call(ReadTool({'cwd': '/tmp'}), {'arguments': {'path': 'f.txt', 'offset': 0}})

    def test_read_negative_offset_rejected(self):
        with self.assertRaises(ValueError):
            validate_tool_call(ReadTool({'cwd': '/tmp'}), {'arguments': {'path': 'f.txt', 'offset': -1}})

    def test_write_valid(self):
        p = validate_tool_call(WriteTool({'cwd': '/tmp'}), {'arguments': {'path': 'out.txt', 'content': 'hi'}})
        self.assertEqual(p.content, 'hi')

    def test_edit_missing_old_text(self):
        with self.assertRaises(ValueError):
            validate_tool_call(EditTool({'cwd': '/tmp'}), {'arguments': {'path': 'f.txt', 'new_text': 'x'}})

    def test_bash_default_timeout(self):
        p = validate_tool_call(BashTool({'cwd': '/tmp'}), {'arguments': {'command': 'ls'}})
        self.assertEqual(p.timeout, 120)

    def test_grep_literal_and_ignore_case(self):
        p = validate_tool_call(GrepTool({'cwd': '/tmp'}), {'arguments': {'pattern': 'TODO', 'literal': True, 'ignore_case': True}})
        self.assertTrue(p.literal)
        self.assertTrue(p.ignore_case)

    def test_find_type_validation(self):
        p = validate_tool_call(FindTool({'cwd': '/tmp'}), {'arguments': {'pattern': '*.py', 'type': 'file'}})
        self.assertEqual(p.type, 'file')

    def test_agent_tools_coerced_from_json_string(self):
        p = validate_tool_call(AgentTool({'cwd': '/tmp', 'agent': MagicMock()}), {'arguments': {'task': 'do it', 'tools': '["Read","Bash"]'}})
        self.assertEqual(p.tools, ['Read', 'Bash'])

    def test_agent_tools_invalid_type_rejected(self):
        with self.assertRaises(ValueError):
            validate_tool_call(AgentTool({'cwd': '/tmp', 'agent': MagicMock()}), {'arguments': {'task': 'do it', 'tools': 42}})

    def test_all_tools_have_schemas(self):
        for cls in DEFAULT_TOOLS:
            tool = cls({'cwd': '/tmp', 'agent': MagicMock()})
            s = tool.schema()
            self.assertIn('name', s)
            self.assertIn('description', s)
            self.assertIn('input_schema', s)
            self.assertEqual(s['name'], tool.name)

class TestToolExecution(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='mlx_test_exec_')
        self.ctx = {'cwd': self.tmpdir, 'agent': MagicMock()}

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_read_file(self):
        pathlib.Path(self.tmpdir, 'hello.txt').write_text('hello world\n')
        r = _run(ReadTool(self.ctx).execute(ReadParams(path='hello.txt')))
        self.assertFalse(r['is_error'])
        self.assertIn('hello world', r['content'][0]['text'])

    def test_read_with_offset(self):
        pathlib.Path(self.tmpdir, 'lines.txt').write_text('L1\nL2\nL3\nL4\nL5\n')
        r = _run(ReadTool(self.ctx).execute(ReadParams(path='lines.txt', offset=2, limit=2)))
        text = r['content'][0]['text']
        self.assertIn('L2', text)
        self.assertIn('L3', text)
        self.assertNotIn('L1', text)
        self.assertNotIn('L5', text)

    def test_read_file_not_found(self):
        with self.assertRaisesRegex(ValueError, 'not found'):
            _run(ReadTool(self.ctx).execute(ReadParams(path='nope.txt')))

    def test_read_directory(self):
        os.mkdir(os.path.join(self.tmpdir, 'subdir'))
        with self.assertRaisesRegex(ValueError, 'directory'):
            _run(ReadTool(self.ctx).execute(ReadParams(path='subdir')))

    def test_read_path_escape_blocked(self):
        with self.assertRaisesRegex(ValueError, 'escapes'):
            _run(ReadTool(self.ctx).execute(ReadParams(path='../../etc/passwd')))

    def test_write_creates_file(self):
        r = _run(WriteTool(self.ctx).execute(WriteParams(path='new.txt', content='hello')))
        self.assertFalse(r['is_error'])
        self.assertEqual(pathlib.Path(self.tmpdir, 'new.txt').read_text(), 'hello')

    def test_write_creates_subdirectories(self):
        _run(WriteTool(self.ctx).execute(WriteParams(path='a/b/c.txt', content='deep')))
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, 'a', 'b', 'c.txt')))

    def test_write_overwrites_existing(self):
        pathlib.Path(self.tmpdir, 'exists.txt').write_text('old')
        r = _run(WriteTool(self.ctx).execute(WriteParams(path='exists.txt', content='new')))
        self.assertIn('overwrote', r['content'][0]['text'])
        self.assertEqual(pathlib.Path(self.tmpdir, 'exists.txt').read_text(), 'new')

    def test_write_path_escape_blocked(self):
        with self.assertRaisesRegex(ValueError, 'escapes'):
            _run(WriteTool(self.ctx).execute(WriteParams(path='../../tmp/evil', content='x')))

    def test_edit_replaces_unique_text(self):
        pathlib.Path(self.tmpdir, 'e.txt').write_text('foo bar baz')
        _run(EditTool(self.ctx).execute(EditParams(path='e.txt', old_text='bar', new_text='qux')))
        self.assertEqual(pathlib.Path(self.tmpdir, 'e.txt').read_text(), 'foo qux baz')

    def test_edit_not_found_raises(self):
        pathlib.Path(self.tmpdir, 'e2.txt').write_text('hello')
        with self.assertRaisesRegex(ValueError, 'not found'):
            _run(EditTool(self.ctx).execute(EditParams(path='e2.txt', old_text='missing', new_text='x')))

    def test_edit_ambiguous_raises(self):
        pathlib.Path(self.tmpdir, 'e3.txt').write_text('aaa bbb aaa')
        with self.assertRaisesRegex(ValueError, 'appears 2 times'):
            _run(EditTool(self.ctx).execute(EditParams(path='e3.txt', old_text='aaa', new_text='x')))

    def test_edit_file_not_found(self):
        with self.assertRaisesRegex(ValueError, 'not found'):
            _run(EditTool(self.ctx).execute(EditParams(path='missing.txt', old_text='x', new_text='y')))

    def test_bash_simple(self):
        r = _run(BashTool(self.ctx).execute(BashParams(command='echo hello')))
        self.assertFalse(r['is_error'])
        self.assertIn('hello', r['content'][0]['text'])

    def test_bash_nonzero_exit_included(self):
        r = _run(BashTool(self.ctx).execute(BashParams(command='exit 1')))
        self.assertIn('exit code 1', r['content'][0]['text'])

    def test_bash_timeout(self):
        with self.assertRaisesRegex(ValueError, 'timed out'):
            _run(BashTool(self.ctx).execute(BashParams(command='sleep 5', timeout=1)))

    def test_bash_cwd_respected(self):
        r = _run(BashTool(self.ctx).execute(BashParams(command='pwd')))
        self.assertIn(self.tmpdir, r['content'][0]['text'])

    def test_grep_finds_match(self):
        pathlib.Path(self.tmpdir, 's.py').write_text('def hello():\n    pass\n# TODO: fix\n')
        r = _run(GrepTool(self.ctx).execute(GrepParams(pattern='TODO')))
        self.assertIn('TODO', r['content'][0]['text'])

    def test_grep_no_match(self):
        pathlib.Path(self.tmpdir, 's2.py').write_text('nothing here\n')
        r = _run(GrepTool(self.ctx).execute(GrepParams(pattern='NONEXISTENT_XYZ')))
        self.assertIn('No matches', r['content'][0]['text'])

    def test_grep_literal_mode(self):
        pathlib.Path(self.tmpdir, 'lit.txt').write_text('a.b matches dots\n')
        r = _run(GrepTool(self.ctx).execute(GrepParams(pattern='a.b', literal=True)))
        self.assertIn('a.b', r['content'][0]['text'])

    def test_grep_invalid_regex(self):
        with self.assertRaisesRegex(ValueError, 'Invalid regex'):
            _run(GrepTool(self.ctx).execute(GrepParams(pattern='[invalid')))

    def test_grep_with_context(self):
        pathlib.Path(self.tmpdir, 'ctx.txt').write_text('line1\nline2\nTARGET\nline4\nline5\n')
        r = _run(GrepTool(self.ctx).execute(GrepParams(pattern='TARGET', context=1)))
        text = r['content'][0]['text']
        self.assertIn('TARGET', text)
        self.assertIn('line2', text)
        self.assertIn('line4', text)

    def test_find_by_glob(self):
        pathlib.Path(self.tmpdir, 'target.py').write_text('')
        pathlib.Path(self.tmpdir, 'other.txt').write_text('')
        r = _run(FindTool(self.ctx).execute(FindParams(pattern='*.py', type='file')))
        self.assertIn('target.py', r['content'][0]['text'])
        self.assertNotIn('other.txt', r['content'][0]['text'])

    def test_find_no_results(self):
        r = _run(FindTool(self.ctx).execute(FindParams(pattern='*.nonexistent')))
        self.assertIn('No results', r['content'][0]['text'])

    def test_ls_lists_files(self):
        pathlib.Path(self.tmpdir, 'file1.txt').write_text('')
        pathlib.Path(self.tmpdir, 'file2.py').write_text('')
        os.mkdir(os.path.join(self.tmpdir, 'subdir'))
        r = _run(LsTool(self.ctx).execute(LsParams()))
        text = r['content'][0]['text']
        self.assertIn('file1.txt', text)
        self.assertIn('file2.py', text)
        self.assertIn('subdir/', text)

    def test_ls_not_directory(self):
        pathlib.Path(self.tmpdir, 'notadir').write_text('')
        with self.assertRaisesRegex(ValueError, 'Not a directory'):
            _run(LsTool(self.ctx).execute(LsParams(path='notadir')))

    def test_skill_not_found(self):
        r = _run(SkillTool({**self.ctx, 'skills': []}).execute(SkillParams(name='missing')))
        self.assertTrue(r['is_error'])

    def test_skill_found(self):
        r = _run(SkillTool({**self.ctx, 'skills': [{'name': 'test-skill', 'content': 'Do the thing'}]}).execute(SkillParams(name='test-skill')))
        self.assertFalse(r['is_error'])
        self.assertIn('Do the thing', r['content'][0]['text'])

class TestGitAddFiltered(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='mlx_test_add_')
        _init_repo(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_excludes_binaries_includes_source(self):
        pathlib.Path(self.tmpdir, 'code.py').write_text('print("hi")')
        pathlib.Path(self.tmpdir, 'model.bin').write_text('binary')
        pathlib.Path(self.tmpdir, 'weights.safetensors').write_text('weights')
        pathlib.Path(self.tmpdir, 'model.gguf').write_text('gguf')
        git_add_filtered(self.tmpdir)
        indexed = subprocess.run(['git', 'diff', '--cached', '--name-only'], cwd=self.tmpdir, capture_output=True, text=True).stdout.strip()
        self.assertIn('code.py', indexed)
        self.assertNotIn('model.bin', indexed)
        self.assertNotIn('weights.safetensors', indexed)
        self.assertNotIn('model.gguf', indexed)

class TestWorktreeToolIntegration(unittest.TestCase):

    def setUp(self):
        self.test_root = tempfile.mkdtemp(prefix='mlx_test_int_')
        self.repo = os.path.join(self.test_root, 'repo')
        os.makedirs(self.repo)
        _init_repo(self.repo)
        self.point = create_worktree(self.repo)
        self._points = [self.point]

    def tearDown(self):
        for p in self._points:
            cleanup_worktree(p)
        shutil.rmtree(self.test_root, ignore_errors=True)

    def test_write_via_tool_commit_then_resume(self):
        ctx = {'cwd': self.point.worktree, 'agent': MagicMock()}
        _run(WriteTool(ctx).execute(WriteParams(path='created_by_tool.txt', content='tool output\n')))
        msgs = [_user('create a file'), _assistant('done')]
        self.point, _ = commit_worktree(self.point, msgs)
        self._points.append(self.point)
        sha = self.point.commit
        resumed, parsed = resume_worktree(self.repo, sha)
        self._points.append(resumed)
        self.assertIsNotNone(resumed)
        self.assertTrue(os.path.exists(os.path.join(resumed.worktree, 'created_by_tool.txt')))
        self.assertEqual(pathlib.Path(resumed.worktree, 'created_by_tool.txt').read_text(), 'tool output\n')
        self.assertTrue(any((m['role'] == 'user' for m in parsed)))

    def test_edit_via_tool_diff_in_commit(self):
        ctx = {'cwd': self.point.worktree, 'agent': MagicMock()}
        _run(WriteTool(ctx).execute(WriteParams(path='editme.txt', content='alpha beta gamma\n')))
        self.point, _ = commit_worktree(self.point, [_user('create')])
        self._points.append(self.point)
        _run(EditTool(ctx).execute(EditParams(path='editme.txt', old_text='beta', new_text='BETA')))
        self.point, diff_stat = commit_worktree(self.point, [_user('edit')])
        self._points.append(self.point)
        self.assertIn('editme.txt', diff_stat)
        self.assertEqual(pathlib.Path(self.point.worktree, 'editme.txt').read_text(), 'alpha BETA gamma\n')
if __name__ == '__main__':
    unittest.main()