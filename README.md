# hpc-con

Describe a Slurm job in one YAML file and submit it to an HPC cluster over SSH.

`hpc-con` reads a config with two sections: **`connection`** says where to connect, and **`job`** says what to run. It checks the whole file and reports every problem at once, then turns the job into a Slurm batch script (`#SBATCH` header, modules, environment, commands).

> **Status: work in progress.** Reading, validating and printing the config works, and so does generating the batch script. The SSH transport (`hpc_con.transport`) is still being fixed, and submitting jobs, checking their status and fetching their output are not implemented yet. See [Roadmap](#roadmap).
i
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
  ...
```

If the config is invalid, it exits with every problem found:

```
Invalid config 'example.yaml':
  - connection.hots: unknown key, did you mean 'host'?
  - connection.host: missing required key
  - job.commands: missing required key
  - job.time: put the time in quotes, e.g. "01:00:00"
```

From Python:

```python
from hpc_con.config import read_config
from hpc_con.job import render_script

config = read_config("example.yaml")  # raises InvalidConfigError
print(render_script(config.job))      # the Slurm batch script as a string
```

## Configuration

See [`example.yaml`](example.yaml) for a complete example.

### `connection`

| Key        | Type    | Required | Notes |
|------------|---------|----------|-------|
| `host`     | string  | yes      | Login node, e.g. `login.cluster.example.org` |
| `user`     | string  | no       | Defaults to what ssh uses (`~/.ssh/config`, then your local username) |
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

1. **Structure** (`hpc_con.config.validate_config`) checks the sections, required keys and value types. Unknown keys get a "did you mean" suggestion. `true`/`false` are not accepted as integers.
2. **Values** (`hpc_con.job.validate_job`) checks that every value is safe to put in the script, so the YAML can't inject extra shell lines:
   - `name`, `partition`, `account`: letters, digits, `_ . -`, at most 64 characters
   - `time`: Slurm format: `MM`, `MM:SS`, `HH:MM:SS`, `D-HH`, `D-HH:MM`, `D-HH:MM:SS`
   - `mem`: a number with an optional `K`/`M`/`G`/`T` suffix
   - `workdir`, `output`, `error`: letters, digits, `_ . / % -`. No spaces, and no `~`, because `#SBATCH` lines don't expand it
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
│   ├── script.py      #   render_script()
│   └── templates/slurm_job.txt
└── transport/         # SSH connection (work in progress)
    ├── ssh.py         #   SSH_RemoteHost context manager
    └── utils.py
tests/                 # unittest + pyfakefs
```

## Development

```sh
uv run make test          # run the tests (unittest)
uv run ruff check .       # lint
uv run ruff check . --fix # auto-fix lint problems
uv run black .            # format
```

`make test` runs `python`, so run it through `uv run`, or activate `.venv` first.

On every push to `master` and on every pull request, CI (`.github/workflows/lint.yml`) runs `black --check` and `ruff check`.

## Roadmap

- [x] YAML config: loading, validation with readable errors, parsing into dataclasses
- [x] Batch script generation from a template
- [x] Readable printing of the config
- [ ] Fix the SSH transport (connection sharing via ControlMaster, `scp` with the right port/key)
- [ ] Slurm operations: upload the script, `sbatch`, `squeue`/`sacct`, `scancel`, fetch logs
- [ ] CLI: `hpc-con submit | status | cancel | fetch <config.yaml>`
- [ ] Tests for validation, script rendering and transport
- [ ] Run tests in CI
