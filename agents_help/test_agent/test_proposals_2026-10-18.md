# Test proposals - 2026-10-18

Branch: `feat/ssh-con`. Baseline measured with:

```
uv run --with coverage coverage run --source=src -m unittest discover -s tests
uv run --with coverage coverage report -m
```

| Module | Cover | Notes |
|---|---|---|
| transport/utils.py | 0% | new SSH pre-checks, nothing imports them in tests |
| transport/ssh.py | 0% | SSHConnection, build_ssh_base |
| slurm/cluster.py | 0% | SlurmCluster |
| config/validation.py | 20% | almost all schema rules untested |
| formatting.py | 14% | |
| job/script.py | 46% | render_script never executed |
| job/validation.py | 52% | regexes never exercised |
| config/loader.py | 50% | `read_config`, `_parse_config` untested |
| `__init__.py` (CLI `main`) | 33% | |
| job/state.py | 89% | only import-time lines, behaviour untested |
| **TOTAL** | **41%** | 3 tests, 2 failing |

## 0. Existing failures (I did not fix them)

`uv run make test` → 3 tests, 2 FAIL in `tests/test_config.py`:

- `YamlLoadingConfigTest.test_load_valid_config`
- `YamlLoadingConfigTest.test_load_empty_config`

Both expected dicts contain `"yaml_config_filaneme": "<file>"`, which
`_load_raw_config` does not return (the loader returns `{}` for an empty file and
the plain YAML mapping otherwise). The test and the loader docstring disagree,
and the docstring also still says "Returns a dict with the source filename when
the file is empty". Someone needs to decide which one is correct. The rest of
this document assumes the current loader behaviour (no filename key).

## 1. Bugs these proposals will expose

I confirmed each of these with mocks only (no subprocess or network was used).
Tests marked **[RED]** below fail against the current code because of them.

| # | Where | Symptom |
|---|---|---|
| B1 | `ssh.py:74` `connect()` | `_show_ssh_setup()` called without `config, ssh_argv` → `TypeError` on every connect |
| B2 | `ssh.py:77` | `result_returncode is 0` → `SyntaxWarning`, ruff F632. Also, `check=True` already raises on a non-zero code, so the `else` branch is dead |
| B3 | `ssh.py:94` `__copy_files` | uses `self.config` (missing) → `AttributeError`. Uses the local relative path as the remote path |
| B4 | `ssh.py:41` `build_ssh_base` | `user=None` (allowed by schema) produces target `"None@host"` |
| B5 | `ssh.py:31` `build_ssh_base` | `@cache` returns the **same list object**, so a caller that mutates it changes all later results (confirmed: appended `"EVIL"` appeared in the next call) |
| B6 | `ssh.py:81` `disconnect` | does nothing and returns `None` despite `-> CommandExecutionResult`; ControlMaster socket is never closed (`ssh -O exit`) |
| B7 | `cluster.py:26,35,39` | `self.ssh_active_con.__execute_remote_cmd` is name-mangled to `_SlurmCluster__execute_remote_cmd` → `AttributeError`; with an inactive connection `ssh_active_con` is `None` → `AttributeError` on `NoneType` |
| B8 | `cluster.py` | `submit` returns `None` (declared `int`), `status` returns `None` (declared `JobInfo`), `scontrol {id}` is missing `show job`, remote command is not built with `shlex.join(argv)` as AGENTS.md requires |
| B9 | `script.py:97` | `_construct_command()` called without `job.commands` → `TypeError` |
| B10 | `script.py:93` | keyword `sbtach_header` vs template `$sbatch_header` → `KeyError` (hidden by B9) |
| B11 | `script.py:102` | `_render_script_file(rendered_script)` missing `filename` → `TypeError` |
| B12 | `utils.py:105` | `input()` raising `EOFError` (non-interactive run, CI, piped stdin) propagates raw instead of `SSHSetupError` |
| B13 | `utils.py:84` design | `_check_if_ssh_daemon_is_running` checks the **local** sshd. A client does not need a local daemon to connect out; on macOS with Remote Login off (the default) `connect()` will always fail. Unsupported platforms (`win32`) always raise. Worth confirming that this is intended before locking it in with tests |

Lint: `ruff check .` reports 7 errors (cluster.py, ssh.py) and `black --check .`
would reformat `ssh.py`, so CI is red as well.

Name-mangled methods (`__run_cmd`, `__copy_files`, `__fetch_files`,
`__execute_remote_cmd`) can only be tested as
`conn._SSHConnection__run_cmd(...)`. That works, but B7 shows that mangling is
also the reason SlurmCluster cannot call them. I recommend switching to a single
underscore. The sketches below use the mangled names so that they run against
the current code.

---

# Unit tests

Common rules for all sketches:
- Patch where a name is **looked up**. `ssh.py` imports the three check
  functions by name, so `connect()` tests must patch
  `hpc_con.transport.ssh._check_if_ssh_installed` and not the `utils` copy.
- `build_ssh_base` and `_load_template` are `functools.cache`d. Call
  `.cache_clear()` in `setUp`, otherwise one test's result leaks into the next.
- `sys.platform` is patched with `mock.patch.object(utils.sys, "platform", ...)`
  because `utils` reads it at call time, so no module reload is needed.

## U1. `tests/test_utils.py` (transport/utils.py) - priority HIGH

New code with no tests, and every branch depends on the environment
(PATH, OS, systemd/launchd, a TTY). Without mocks the result depends on the
developer's machine, and that is the reason to pin the behaviour now.

### `CheckIfSshInstalledTest`
| Test | Mock | Assert |
|---|---|---|
| `test_passes_when_ssh_on_path` | `shutil.which` → `"/usr/bin/ssh"` | returns `None`, `which` called with `"ssh"` |
| `test_raises_when_ssh_missing` | `which` → `None` | `SSHSetupError` |
| `test_hint_for_linux` / `test_hint_for_darwin` | `which` → `None`, platform patched | message contains `SSH_INSTALL_HINTS[platform]` |
| `test_generic_hint_on_unknown_platform` | platform `"win32"` | message contains `"see your system's OpenSSH documentation"` |

```python
from unittest import TestCase, mock
from hpc_con.transport import utils

class CheckIfSshInstalledTest(TestCase):
    @mock.patch("hpc_con.transport.utils.shutil.which", return_value=None)
    def test_hint_for_linux(self, _which):
        with mock.patch.object(utils.sys, "platform", "linux"):
            with self.assertRaises(utils.SSHSetupError) as ctx:
                utils._check_if_ssh_installed()
        self.assertIn(utils.SSH_INSTALL_HINTS["linux"], str(ctx.exception))
```

### `CheckIfSshDaemonIsRunningTest`
Patch `hpc_con.transport.utils.execute_local_cmd` (not `sp.run`), so the test
covers only the fallback loop and not result parsing.

| Test | Setup | Assert |
|---|---|---|
| `test_linux_first_check_succeeds` | returns OK | called once with `["systemctl","is-active","--quiet","sshd"]` |
| `test_linux_falls_back_to_ssh_unit` | 1st raises `CalledProcessError`, 2nd OK | 2 calls, second with `"ssh"` unit, no raise |
| `test_linux_both_fail_raises_with_reload_hint` | both raise | `SSHSetupError`, message has `SSH_RELOAD_HINTS["linux"]` |
| `test_missing_systemctl_is_treated_as_down` | `FileNotFoundError` | `SSHSetupError` (not FileNotFoundError) |
| `test_darwin_uses_launchctl` | OK | called with `["launchctl","print","system/com.openssh.sshd"]` |
| `test_unknown_platform_raises_without_running_anything` | platform `win32` | `SSHSetupError`, `execute_local_cmd` not called (documents B13) |
| `test_other_errors_propagate` | `PermissionError` | `PermissionError` propagates. This pins down that only the two listed exceptions are swallowed |

### `ShowSshSetupTest`
Patch `builtins.input` and `builtins.print`, or use `contextlib.redirect_stdout(io.StringIO())`.

| Test | Input | Assert |
|---|---|---|
| `test_accepts_y_yes_any_case_and_whitespace` | `subTest` over `"y"`, `"Y"`, `"yes"`, `" YES \n"` | no raise |
| `test_rejects_everything_else` | `subTest` over `""`, `"n"`, `"no"`, `"yeah"`, `"y y"` | `SSHSetupError("ssh setup rejected by the user")` |
| `test_prints_config_and_shell_quoted_command` | argv with a path containing a space | stdout contains `str(config)` and `shlex.join(argv)` (quoted), so the user sees what will really run |
| `test_eof_on_input` **[RED, B12]** | `input` side_effect `EOFError` | expect `SSHSetupError`. Fails today. Without a fix, CI or cron runs crash with a bare EOFError |

### `ExecuteLocalCmdTest`
| Test | Assert |
|---|---|
| `test_wraps_completed_process` | patch `hpc_con.transport.utils.sp.run` → `CompletedProcess(["x"],0,"out","err")`. Result fields map 1:1 |
| `test_calls_run_without_shell_and_with_check` | `sp.run` called with argv list, `capture_output=True, text=True, check=True`, and `"shell"` not in kwargs (AGENTS.md rule) |
| `test_kwargs_forwarded` | `timeout=5` reaches `sp.run` |
| `test_nonzero_raises` | `CalledProcessError` propagates |

### `CommandExecutionResultTest`
`result_returncode` is a `StrictInt`. Assert a `ValidationError` for `"0"` and
for `True`, so a refactor cannot silently turn the field into a coerced int.

## U2. `tests/test_ssh.py` (transport/ssh.py) - priority HIGH

### `BuildSshBaseTest` (`setUp`: `build_ssh_base.cache_clear()`)
| Test | Assert |
|---|---|
| `test_minimal_config` | `["ssh", *SSH_OPTS, "--", "u@h"]` |
| `test_port_and_key_file` | `-p 2222` and `-i /k` appear **before** `"--"` |
| `test_target_is_last_and_after_double_dash` | `argv[-2] == "--"`. Security: a host like `-oProxyCommand=x` can never be parsed as an option |
| `test_batchmode_and_controlmaster_present` | the four `-o` options are present. BatchMode prevents password prompts that would hang `capture_output` |
| `test_user_none_omits_user` **[RED, B4]** | target is `"h"`, not `"None@h"` |
| `test_returned_list_is_not_shared` **[RED, B5]** | mutate the result, call again, result unchanged |
| `test_port_zero_or_none` | `None` → no `-p` (documents the truthiness check) |

### `SSHConnectionInitTest`
`is_active` is False, `_ssh_base_args == build_ssh_base(config)`, `verbose` stored.

### `SSHConnectionConnectTest`
Patch `hpc_con.transport.ssh._check_if_ssh_installed`, `..._daemon_is_running`,
`..._show_ssh_setup`, and `hpc_con.transport.ssh.sp.run`. Use a `mock.Mock()`
manager with `attach_mock` to assert the **order**.

| Test | Assert |
|---|---|
| `test_runs_checks_in_order_before_ssh` | installed → daemon → setup → `sp.run` |
| `test_show_setup_receives_config_and_argv` **[RED, B1]** | `_show_ssh_setup.assert_called_once_with(config, conn._ssh_base_args)` |
| `test_success_sets_is_active` | returncode 0 → `is_active is True` |
| `test_check_failure_stops_before_ssh` | each check raising `SSHSetupError` → `sp.run` not called, `is_active` False |
| `test_ssh_failure_leaves_inactive` | `sp.run` raises `CalledProcessError` → propagates, `is_active` False |
| `test_ssh_argv_is_list_no_shell` | `sp.run` args[0] is a list, `shell` not in kwargs |

Also check the timeout. `connect()` runs `ssh user@host` with **no remote
command**, which starts a remote login shell that waits on stdin. It is worth
asserting that `connect` passes a harmless command (e.g. `true`) or `timeout=`
once that is decided. As written, a real run can hang.

### `SSHConnectionRemoteCmdTest`
| Test | Assert |
|---|---|
| `test_inactive_returns_none_without_running` | `sp.run` not called |
| `test_active_prefixes_ssh_base` | argv = base + cmd, kwargs (`input=`) forwarded |
| `test_remote_command_is_single_shlex_joined_string` | AGENTS.md requires `shlex.join(argv)` as **one** element after the target. Pass `["echo", "a b; rm -rf /"]` and expect the last element `"echo 'a b; rm -rf /'"`. This is the main injection guard for remote execution, so it needs a test |

### `SSHConnectionCopyFetchTest` (pyfakefs not required, `Path.absolute` is pure)
| Test | Assert |
|---|---|
| `test_copy_builds_scp_argv` **[RED, B3]** | `["scp", "/abs/a.txt", "u@h:a.txt"]` |
| `test_fetch_builds_scp_argv` | reverse order |
| `test_copy_returns_one_result_per_file` | 3 files → 3 results, 3 `sp.run` calls |
| `test_scp_uses_same_port_and_key` | scp currently **ignores** `port` and `key_file`, so against a non-22 host it fails. Expect `-P`/`-i` (proposal, also red) |

### `SSHConnectionDisconnectTest`
`test_inactive_is_noop` (passes). `test_active_closes_control_master` **[RED, B6]**
expects `ssh -O exit` and `is_active` reset.

## U3. `tests/test_state.py` (job/state.py) - priority MEDIUM

Small, pure code, but it decides when polling stops, so a wrong
`is_finished` means an endless loop or an early exit.

### `JobStateParseTest`
- every member name parses to itself (`subTest` over `JobState`)
- `"CANCELLED by 1234"` → CANCELLED
- `""`, `"   "` → UNKNOWN (covers lines 30-31)
- `"running"` (lowercase) → UNKNOWN, documents case sensitivity
- `"CANCELLED+"`, `"OUT_OF_ME+"` → currently UNKNOWN. `sacct` truncates states
  with `+` by default, so decide whether the parser should strip it or the
  caller should use `--parsable2`/`-o State%20`. This test documents that choice.

### `JobStateIsFinishedTest`
- every state in `ACTIVE_STATES` → False
- UNKNOWN → False
- COMPLETED, FAILED, CANCELLED, TIMEOUT, OUT_OF_MEMORY, NODE_FAIL, PREEMPTED → True
- `test_active_states_are_all_members`: every string in `ACTIVE_STATES` is a
  `JobState` value. This catches typos, which would otherwise make that state "finished"

### `JobInfoTest`
- `state="RUNNING"` is coerced to `JobState.RUNNING`
- `state="BOGUS"` → `ValidationError`
- frozen: assigning `info.state = ...` raises `ValidationError`
- optional fields default to `None`
- `is_finished` delegates to `state` (covers line 55)

## U4. `tests/test_script.py` (job/script.py) - priority HIGH

`render_script` currently fails on every call (B9-B11). That is the core
feature of the project, and no existing test notices it.

Don't use pyfakefs for template tests (`importlib.resources` would read from
the fake FS). Use it only for `_render_script_file`.

### `SbatchHeaderTest`
- `None` and `gpus=0` options are omitted, `gpus=2` → `#SBATCH --gpus=2`
- `workdir` maps to `--chdir`, `cpus_per_task` to `--cpus-per-task`
- order is stable (job-name first)

### `SetupSectionTest`
- no modules and no env → `""`
- modules → `module purge` then `module load <quoted>`
- env value `"a b; rm -rf ~"` → `export K='a b; rm -rf ~'`. Security: confirms shlex quoting

### `RenderScriptTest`
| Test | Assert |
|---|---|
| `test_renders_valid_job` **[RED, B9/B10]** | starts with `#!/bin/bash`, contains `#SBATCH --job-name=n`, commands in order, `DEBUG_MODE=0` |
| `test_debug_true_sets_flag` **[RED]** | `DEBUG_MODE=1` |
| `test_no_unsubstituted_placeholders` **[RED]** | `re.search(r"\$[a-z_]+\b", out)` finds nothing except `$DEBUG_MODE`. Guards against renaming template keys |
| `test_invalid_job_raises_before_rendering` | `name="a b"` → `JobValidationError`, `_load_template` not called (passes today) |
| `test_filename_writes_file` **[RED, B11]** | with pyfakefs, file content == return value |

### `LoadTemplateTest`
`_load_template()` returns a `Template` whose identifiers
(`template.get_identifiers()`, Python 3.11+) are exactly
`{"sbatch_header", "debug", "setup", "commands"}`. This would have caught B10
without rendering. Note that `requires-python >=3.10`, so guard the test with
`skipIf(sys.version_info < (3, 11))`.

## U5. `tests/test_validation.py` (job/validation.py) - priority HIGH

AGENTS.md says that every job value must pass a strict regex. These regexes
are the security boundary for the batch script, and they are 0% exercised.

### `JobPatternTest` (table-driven with `subTest`)
| Field | Must accept | Must reject |
|---|---|---|
| name/partition/account | `train_model`, `a.b-c`, 64 chars | `""`, 65 chars, `"a b"`, `"a\nb"`, `"a;b"`, `"$(x)"` |
| time | `"30"`, `"01:00:00"`, `"2-12:00"`, `"2-12:00:00"` | `"1h"`, `"01:00:00\n#SBATCH --x"`, `"::"` |
| mem | `"16G"`, `"1024"` | `"16 G"`, `"16GB"`, `"-1"` |
| module | `python/3.10`, `gcc+cuda` | `"x;rm"`, `"x y"` |
| workdir/output/error | `logs/%x-%j.out`, `/scratch/a` | `"~/x"` (not expanded in #SBATCH), `"a b"`, `"a\n"` |
| env key | `OMP_NUM_THREADS`, `_x` | `"1X"`, `"A-B"`, `"A B"` |

Use `re.fullmatch` semantics. Test `"name\n"` explicitly, because `$` in
`re.match` accepts a trailing newline, and `fullmatch` is the only thing
preventing header injection.

### `JobNumbersTest`
nodes/ntasks/cpus 0 → error, gpus -1 → error, gpus 0 → ok, `nodes="2"` → error.

### `ValidateJobAggregationTest`
A job with 3 bad fields and empty commands → exactly 4 errors in one list
(AGENTS.md: "collects all errors, does not stop at the first").
`JobValidationError(errors)` message lists every item and `.errors` is preserved.

## U6. `tests/test_validation.py` additions for config/validation.py - priority MEDIUM

(Module name clashes with job/validation. Suggest `test_config_validation.py`
and `test_job_validation.py`, a deviation from the one-name rule that avoids
two files with the same name.)

- `ValidateConfigRootTest`: non-dict root (`[]`, `"x"`, `None`) → single `<root>` error; unknown section `jobs` → suggestion `did you mean 'job'?`; missing sections reported both.
- `CheckSectionTypesTest`: `nodes: true` rejected (bool is not int); `port: "22"` → `expected integer, got str`; `mem: 16` accepted (str or int); `time: 3600` → the "put the time in quotes" message; `connection: "x"` → `must be a mapping`.
- `CheckValueTest`: `commands: ["a", 1]` → `job.commands[1]`; `env: {1: "x"}` and `env: {A: [1]}`; `key_file` missing → `file not found` (pyfakefs, create `~/.ssh/id` under `os.path.expanduser("~")`).
- `UnknownKeyTest`: `hots` → `did you mean 'host'?`; `zzz` has no suggestion.

## U7. `tests/test_loader.py` (config/loader.py) - priority MEDIUM

- `ParseConfigTest`: `key_file` `~` expanded; `mem: 16` → `"16"`; `env` values stringified (`8` → `"8"`); missing optional keys use dataclass defaults.
- `LoadRawConfigTest`: missing file → `FileNotFoundError` (the CLI relies on it being `OSError`); YAML list/scalar at root returned unchanged so `validate_config` can reject it. Move the existing three tests here once section 0 is resolved.

## U8. `tests/test_formatting.py` and `tests/test_model.py` - priority LOW

- `format_fields`: None → `missing` text, empty list/dict → `(none)`, list → `- item` lines, dict → `- k=v`, labels aligned to the longest name.
- `ConnectionConfig.__str__` shows `(ssh default)`, `HPCJob.__str__` shows `(cluster default)`, `HPC_ConConfig.__str__` joins both with a blank line.
- `ConnectionConfig` is hashable (required by `@cache` on `build_ssh_base`, so a future `list` field would break it).

## U9. `tests/test_errors.py` - priority LOW
`InvalidConfigError` message with and without `source`, one line per error, `.errors` kept.

---

# Integration tests

These cross module boundaries. Each one still mocks `subprocess.run` and uses
pyfakefs, so none of them touch a real machine.

## I1. `tests/test_cli.py` - `hpc_con.main` - priority HIGH
| Test | Assert |
|---|---|
| `test_wrong_arg_count_exits_with_usage` | `sys.argv=["hpc-con"]` → `SystemExit("usage: ...")` |
| `test_valid_config_prints_summary` | pyfakefs + `add_real_file("example.yaml")` → stdout contains `Connection:` and `Job:` |
| `test_invalid_config_exits_with_all_errors` | config with 3 problems → `SystemExit` message lists all 3 |
| `test_missing_file_exits_cleanly` | `SystemExit`, no traceback (OSError path) |

The `example.yaml` test is the automated version of the "the example config
must still load" smoke check in AGENTS.md. Right now that check is manual.

## I2. `tests/test_read_config.py` - YAML → HPC_ConConfig - priority HIGH
- Full `example.yaml`-style file in pyfakefs → `HPC_ConConfig` with expected field values.
- A file with structural errors **and** job-regex errors: structural errors are reported first and the job stage is skipped. Then a file with only regex errors (`name: "bad name"`, `time: "1h"`) → both are reported together with path `job`.
- Unquoted `time: 01:00:00` → the friendly message, end to end.

## I3. `tests/test_pipeline.py` - config → render_script - priority HIGH **[RED, B9-B11]**
`read_config(fake_yaml)` → `render_script(cfg.job, debug=False)`. Assert that every
`#SBATCH` value comes from the YAML, env is quoted, modules are loaded and
commands are present. This is the main user path, and today nothing exercises it.

## I4. `tests/test_ssh_connect_flow.py` - priority HIGH **[RED, B1]**
Patch only the outer edges: `shutil.which`, `sys.platform="linux"`,
`builtins.input` → `"y"`, and **one** `subprocess.run` mock with a
`side_effect` that records argv. Then call `SSHConnection(cfg).connect()`.
Assert the recorded calls are `systemctl is-active ...` and then the ssh argv,
and that `is_active` is True. Variant: `input` → `"n"` → `SSHSetupError` and
**no** ssh call recorded. Unlike U2, this tests the real wiring between
`ssh.py` and `utils.py`, so a wrong signature like B1 cannot hide behind
per-function mocks.

## I5. `tests/test_cluster.py` - SlurmCluster over mocked ssh - priority MEDIUM **[RED, B7/B8]**
Active `SSHConnection` (`is_active=True`, set directly) and a patched `sp.run`.
- `submit(job)`: one `sp.run` call, argv = ssh base + `"sbatch --parsable"`,
  `input=` is the rendered script; stdout `"12345\n"` → returns `12345`;
  stdout `"12345;cluster\n"` → `12345` (`--parsable` format with clusters).
- `submit` with an invalid job → `JobValidationError`, and `sp.run` not called.
- `cancel(42)`: remote command `"scancel 42"`.
- `status(42)`: remote command `scontrol show job 42`, and fake `scontrol` output
  is parsed into a `JobInfo` with `state=RUNNING`.
- `SlurmCluster(inactive_conn).submit(...)` → a clear error, not `AttributeError` on `None`.
- `job_id` that is not an int (`"1; rm -rf ~"`) → rejected. `job_id` reaches a
  remote shell, so this is an injection path.

---

# Suggested order

1. U4 + I3 (render_script is completely broken)
2. U1 + U2 + I4 (new SSH code, B1 breaks every connect)
3. U5 (security regexes)
4. I1, I2 (CLI and read_config end to end)
5. U3, I5 (state and cluster once B7/B8 are fixed)
6. U6-U9 (remaining coverage)

Rough coverage estimate once all proposals are in place and the bugs are fixed: about 90%+ (`fetch_output` is still a stub).
