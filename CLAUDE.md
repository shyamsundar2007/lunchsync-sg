# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LunchSync SG is a Python CLI tool that normalizes bank transaction exports from multiple Singapore banks (OCBC, DBS, UOB, HSBC, Citibank) into a unified CSV format. It uses a plugin-based parser architecture with auto-detection of bank formats.

## Commands

```bash
# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest                                  # All tests
pytest tests/test_parsers.py -k "ocbc"  # Single test/pattern
pytest --cov=lunchsync_sg               # With coverage

# Code quality
ruff check src tests                    # Linting
mypy src                                # Type checking (strict mode)

# CLI usage
lunchsync-sg ~/Downloads/ -o output.csv
lunchsync-sg --list-parsers
```

## Architecture

### Parser Registry Pattern

All bank parsers extend `BankParser` (abstract base class) and register via decorator:

```python
@ParserRegistry.register
class NewBankParser(BankParser):
    bank_name = "New Bank"
    file_patterns = ["newbank_*.csv"]

    def can_parse(self, content: str, filepath: Path) -> bool: ...
    def parse(self, content: str) -> list[Transaction]: ...
```

The `ParserRegistry` auto-detects the appropriate parser for each file based on content inspection.

### Core Components

- `src/lunchsync_sg/parsers/base.py` - `BankParser` ABC and `ParserRegistry`
- `src/lunchsync_sg/parsers/*.py` - Bank-specific parsers (ocbc, dbs, uob, hsbc, citi)
- `src/lunchsync_sg/models.py` - `Transaction` (frozen dataclass) and `AccountMapping`
- `src/lunchsync_sg/normalizer.py` - `BankNormalizer` orchestrator
- `src/lunchsync_sg/utils/parsing.py` - `parse_date`, `parse_amount`, `clean_description` helpers

### Adding a New Bank Parser

1. Create `src/lunchsync_sg/parsers/newbank.py`
2. Implement class with `@ParserRegistry.register` decorator
3. Import in `src/lunchsync_sg/parsers/__init__.py`
4. Add test fixtures in `tests/fixtures/` and tests in `tests/test_parsers.py`

## Code Quality Requirements

- **mypy strict mode** - All code must be properly typed
- **ruff** - Line length 100, rules: E, F, I, N, W, UP, B, C4, SIM
- **Python 3.11+** compatibility required

## Git Commits

- Use conventional commits format (e.g., `feat:`, `fix:`, `refactor:`)
- Do NOT add `Co-Authored-By` lines to commits
