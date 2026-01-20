# Tambour

An agent harness for [beads](https://github.com/steveyegge/beads) issue tracking.

Tambour orchestrates AI agents working on beads issues using git worktree isolation.

## Features

- **Worktree isolation**: Each agent works in an isolated git worktree
- **Merge lock**: Distributed locking prevents race conditions when multiple agents merge
- **Metrics collection**: Track agent tool usage and file access patterns
- **Session management**: Automatic session notes and context recovery

## Installation

```bash
pip install -e .
```

## Usage

Tambour is typically invoked via a justfile in your project:

```bash
just tambour agent              # Auto-picks next ready task by priority
just tambour agent-for <id>     # Work on specific issue
just tambour finish <id>        # Merge completed work
just tambour abort <id>         # Cancel work in progress
```

## Development

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v
```

## License

MIT
