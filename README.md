# hpc-con

Describe a Slurm job in one YAML file and submit it to an HPC cluster over SSH.

`hpc-con` reads a config with two sections: **`connection`** says where to connect, and **`job`** says what to run. It checks the whole file and reports every problem at once, then turns the job into a Slurm batch script (`#SBATCH` header, modules, environment, commands).

> **Status: work in progress.** Reading, validating and printing the config works. Generating the batch script does **not** work yet: `render_script()` raises `TypeError`. The SSH transport (`hpc_con.transport`) exists but has known bugs and was not tested against a real cluster. `SlurmCluster` (`hpc_con.slurm`) is a draft: submitting jobs, checking their status and fetching their output do not work yet. See [Roadmap](#roadmap).

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- Later, for talking to a cluster: an `ssh` / `scp` client and an account on a Slurm cluster

## Installation

```sh
git clone <repo-url> slurm-ssh
cd slurm-ssh
uv sync
```

`uv sync` creates `.venv`, installs the package with its dev tools, and puts the `hpc-con` command in the environment.

## Usage

```sh
uv run hpc-con example.yaml
```

For now the command validates the config and prints what it parsed:

```
Connection:
  host:     login.cluster.example.org
  user:     jdoe
  port:     22
  key_file: (ssh default)

Job:
  name:          train_model
  commands:
    - python train.py --epochs 10
    - python evaluate.py
  partition:     gpu
  account:       my_project
  time:          02:30:00
  nodes:         1
  ntasks:        1
  cpus_per_task: 8
  mem:           16G
  gpus:          1
  modules:
    - python/3.10
    - cuda/12.1
  env:
    - OMP_NUM_THREADS=8
    - WANDB_MODE=offline
  workdir:       /scratch/jdoe/train_model
  output:        logs/%x-%j.out
  error:         logs/%x-%j.err
```

If the config is invalid, it exits with code 1 and prints every problem found:

```yaml
# bad.yaml
connection:
  hots: login.cluster.example.org
job:
  name: train_model
  time: 10:00:00
```

```
Invalid config 'bad.yaml':
  - connection.hots: unknown key, did you mean 'host'?
  - connection.host: missing required key
  - job.commands: missing required key
  - job.time: put the time in quotes, e.g. "01:00:00"
```

Values that are not safe for the batch script are reported with a `job:` prefix:

```
Invalid config 'bad_values.yaml':
  - job: name: invalid value 'bad name'
  - job: time: invalid value '1 hour'
  - job: mem: invalid value '16GB'
  - job: module: invalid value 'a b'
  - job: env key: invalid value '1BAD'
  - job: nodes: must be an integer >= 1
  - job: commands: at least one command is required
```

From Python:

```python
from hpc_con.config import read_config

config = read_config("example.yaml")  # raises InvalidConfigError
print(config.job.name)                # train_model
```

`hpc_con.job.render_script(job, debug, filename=None)` is meant to return the batch script, but it currently raises `TypeError`, so it is not shown here.

### SSH transport (not finished)

`hpc_con.transport.SSHConnection` builds the ssh command from the `connection` section:

```python
import shlex
from hpc_con.config import read_config
from hpc_con.transport import SSHConnection

config = read_config("example.yaml")
print(shlex.join(SSHConnection(config.connection)._ssh_base_args))
```

```
ssh -o ControlMaster=auto -o 'ControlPath=~/.ssh/cm-%C' -o ControlPersist=10m -o BatchMode=yes -p 22 -- jdoe@login.cluster.example.org
```

`SSHConnection.connect()` does these steps before it runs ssh:

1. Checks that `ssh` is on `PATH`. If not, it raises `SSHSetupError` with an install hint for your platform.
2. Checks that a **local** ssh daemon (`sshd`) is running: `systemctl is-active` on Linux, `launchctl print system/com.openssh.sshd` on macOS. If not, it raises `SSHSetupError` with a restart hint. On other platforms this check always fails.
3. Prints the connection settings and the ssh command, then asks `Are these settings correct? [y/N]`. Any answer other than `y`/`yes` raises `SSHSetupError`.

`copy_files()` and `fetch_files()` run `scp`. Connecting to a cluster is **not verified**.

## Configuration

See [`example.yaml`](example.yaml) for a complete example.

### `connection`

| Key        | Type    | Required | Notes |
|------------|---------|----------|-------|
| `host`     | string  | yes      | Login node, e.g. `login.cluster.example.org` |
| `user`     | string  | no       | Meant to default to what ssh uses. Known bug: the transport currently builds `None@host` when it is not set |
| `port`     | integer | no       | Defaults to ssh's port (22) |
| `key_file` | string  | no       | Path to a private key, `~` is expanded. The file must exist |

### `job`

| Key             | Type             | Default     | Rendered as |
|-----------------|------------------|-------------|-------------|
| `name`          | string           | required    | `--job-name` |
| `commands`      | list of strings  | required    | lines at the end of the script |
| `partition`     | string           | cluster's   | `--partition` |
| `account`       | string           | cluster's   | `--account` |
| `time`          | string (quoted!) | `"01:00:00"`| `--time` |
| `nodes`         | integer          | `1`         | `--nodes` |
| `ntasks`        | integer          | `1`         | `--ntasks` |
| `cpus_per_task` | integer          | `1`         | `--cpus-per-task` |
| `mem`           | string / integer | cluster's   | `--mem` (memory per node), e.g. `16G` |
| `gpus`          | integer          | `0`         | `--gpus` (left out when 0) |
| `modules`       | list of strings  | none        | `module purge` + `module load ...` |
| `env`           | mapping          | none        | `export KEY=value` |
| `workdir`       | string           | submit dir  | `--chdir` |
| `output`        | string           | `%x-%j.out` | `--output` (`%x` = job name, `%j` = job id) |
| `error`         | string           | `%x-%j.err` | `--error` |

### Validation rules

Validation runs in two steps, and each step reports all of its errors together:

1. **Structure** (`hpc_con.config.validate_config`) checks the sections, required keys and value types. Unknown keys get a "did you mean" suggestion. `true`/`false` are not accepted as integers. Items of `commands` and `modules` must be strings, `env` values must be strings or numbers, and `key_file` must exist.
2. **Values** (`hpc_con.job.validate_job`) checks that every value is safe to put in the script, so the YAML can't inject extra shell lines:
   - `name`, `partition`, `account`: letters, digits, `_ . -`, at most 64 characters
   - `time`: Slurm format: `MM`, `MM:SS`, `HH:MM:SS`, `D-HH`, `D-HH:MM`, `D-HH:MM:SS`
   - `mem`: a number with an optional `K`/`M`/`G`/`T` suffix
   - `workdir`, `output`, `error`: letters, digits, `_ . / % -`. No spaces, and no `~`, because `#SBATCH` lines don't expand it
   - `modules` items: letters, digits, `_ . + / -`
   - `env` keys: a letter or `_`, then letters, digits or `_`
   - `nodes`, `ntasks`, `cpus_per_task` ≥ 1, `gpus` ≥ 0, and at least one command

Gotchas:
- **Quote `time`.** YAML reads unquoted times that start with a non-zero digit as numbers in base 60: `10:00:00` becomes 36000 and `30:00` becomes 1800. (`01:00:00` happens to stay a string.) The validator catches the number and tells you to add quotes.
- **Slurm does not create the `output`/`error` folders.** If `output: logs/%x-%j.out` points to a folder that doesn't exist, the job fails without writing a log.

## Project layout

```
src/hpc_con/
├── __init__.py        # hpc-con entry point (main)
├── formatting.py      # readable printing of the dataclasses
├── config/            # YAML config
│   ├── loader.py      #   read_config(): load -> validate -> parse
│   ├── validation.py  #   validate_config(): sections, keys, types
│   ├── consts.py      #   schema of the config
│   ├── model.py       #   ConnectionConfig, HPC_ConConfig
│   ├── errors.py      #   ConfigError, InvalidConfigError
│   └── types.py
├── job/               # Slurm job
│   ├── model.py       #   HPCJob
│   ├── validation.py  #   validate_job(): values safe for the script
│   ├── script.py      #   render_script() (broken, see Status)
│   ├── state.py       #   JobState, JobInfo (what Slurm reports about a job)
│   └── templates/slurm_job.txt
├── slurm/             # Slurm operations (draft, does not work yet)
│   └── cluster.py     #   SlurmCluster: submit, status, cancel, fetch_output
└── transport/         # SSH connection (work in progress)
    ├── _ssh.py        #   SSHConnection: connect, copy_files, fetch_files
    └── utils.py       #   ssh argv (SSH_OPTS, _build_ssh_base), pre-connect checks,
                       #   CommandExecutionResult, SSHSetupError
tests/                 # unittest, mocked subprocess, pyfakefs
├── test_loader.py
├── test_ssh.py
└── test_transport_utils.py
```

## Development

```sh
uv run make test          # run the tests (unittest)
uv run ruff check .       # lint
uv run ruff check . --fix # auto-fix lint problems
uv run black .            # format
```

`make test` runs `python`, so run it through `uv run`, or activate `.venv` first.

The suite has 59 tests. 4 of them are marked `expectedFailure` for known bugs:

```
Ran 59 tests in 0.040s

OK (expected failures=4)
```

On every push to `master` or `main` and on every pull request, CI (`.github/workflows/lint.yml`) runs `black --check` and `ruff check`. CI does not run the tests.

## Roadmap

- [x] YAML config: loading, validation with readable errors, parsing into dataclasses
- [ ] Batch script generation from a template (template exists, `render_script()` raises `TypeError`)
- [x] Readable printing of the config
- [ ] Fix the SSH transport (`None@host` when `user` is unset, `scp` with the right port/key, remote commands as one `shlex.join` string)
- [ ] Slurm operations: upload the script, `sbatch`, `squeue`/`sacct`, `scancel`, fetch logs
- [ ] CLI: `hpc-con submit | status | cancel | fetch <config.yaml>`
- [x] Tests for config loading and the SSH transport
- [ ] Tests for job validation and script rendering
- [ ] Run tests in CI
