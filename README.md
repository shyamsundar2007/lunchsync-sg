# LunchSync SG

Normalize bank transaction exports from multiple Singapore banks into a unified CSV format.

## Supported Banks

- **OCBC**: Credit Card, 360 Account
- **DBS**: Savings Account, Credit Card (MasterCard World)
- **UOB**: Lady's Solitaire, Preferred Platinum VISA
- **HSBC**: Revolution Card
- **Citibank**: Rewards, Prestige

## Installation

```bash
# Using uv (recommended)
uv pip install -e .

# Or with dev dependencies
uv pip install -e ".[dev]"
```

## Usage

### Command Line

```bash
# Process a directory of bank exports
lunchsync-sg ~/Downloads/bank-exports/ -o transactions.csv

# Process specific files
lunchsync-sg ocbc.csv dbs.xls uob.xls -o output.csv

# List available parsers
lunchsync-sg --list-parsers

# Full output with all fields
lunchsync-sg --full input.csv -o output.csv
```

### As a Library

```python
from pathlib import Path
from lunchsync_sg import BankNormalizer

normalizer = BankNormalizer()

# Process files
transactions = normalizer.process_files([
    Path("ocbc.csv"),
    Path("dbs.csv"),
])

# Or process a directory
transactions = normalizer.process_directory(Path("./exports"))

# Write output
normalizer.write_csv(transactions, Path("output.csv"))

# Access individual transactions
for tx in transactions:
    print(f"{tx.date} | {tx.description} | {tx.amount} | {tx.account}")
```

## Output Format

The normalized output contains:

| Field | Description |
|-------|-------------|
| Date | Transaction date (YYYY-MM-DD) |
| Description | Cleaned transaction description |
| Amount | Amount in SGD (negative = expense, positive = income/credit) |
| Account | Friendly account name |

With `--full` flag, additional fields are included:
- `original_currency`: Original transaction currency
- `original_amount`: Amount in original currency
- `category`: Transaction category (if available)
- `reference`: Reference number (if available)

## Adding New Banks

The project uses a plugin architecture. To add a new bank:

1. Create a new file in `src/lunchsync_sg/parsers/`
2. Implement a parser class extending `BankParser`
3. Register with `@ParserRegistry.register`

Example:

```python
from lunchsync_sg.parsers.base import BankParser, ParserRegistry
from lunchsync_sg.models import Transaction

@ParserRegistry.register
class NewBankParser(BankParser):
    bank_name = "NewBank"
    file_patterns = ["NewBank Statement"]

    @classmethod
    def can_parse(cls, content: str, filepath=None) -> bool:
        return "NewBank Statement" in content

    def parse(self, content: str) -> list[Transaction]:
        transactions = []
        # Parse logic here
        return transactions
```

4. Import in `src/lunchsync_sg/parsers/__init__.py`
5. Add tests in `tests/test_parsers.py`

## Configuration

Copy `.env.example` to `.env` to customize account mappings:

```bash
cp .env.example .env
```

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=lunchsync_sg

# Lint
ruff check src tests

# Type check
mypy src
```

## License

MIT
