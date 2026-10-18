# AGENTS.md

hpc-con reads a YAML config, generates a Slurm batch script from it and submits it
to an HPC cluster over SSH. See README.md for the config format and project layout.

## Commands
Run every command from the repo root.
- "uv sync", Installs the project and dev tools
- "uv run make test", Runs all tests (plain "make test" fails without the venv)
- "uv run ruff check ." and "uv run black --check .", Lint and format checks, CI runs both
- "uv run hpc-con example.yaml", Smoke test, the example config must still load

## Rules
- Code must pass ruff and black before a change is done.
- Never use shell=True. Pass commands to subprocess as lists.
- Remote commands sent over ssh are one string built with shlex.join(argv).
- Every job value must pass a strict regex in src/hpc_con/job/validation.py before
  it is placed in the batch script.
- Validation collects all errors and reports them together, it does not stop at the
  first one.
- Constants live next to the code that uses them, not in a global settings module.
- Tests must never contact a real machine. Mock subprocess.run, use pyfakefs for files.
- Never edit uv.lock by hand and never add dependencies without asking.

## Subagents
Defined in .claude/agents/, each one runs in its own context:
- security-agent - security review, report in agents_help/security_agent
- test-agent - test proposals, saved in agents_help/test_agent
- docs-agent - keeps README.md in sync with the code
