# LunchSync SG

Sync bank transactions from Singapore banks to [Lunch Money](https://lunchmoney.app). Parses CSV/XLS exports from multiple banks and uploads them directly via the Lunch Money API.

## Supported Banks

- **OCBC**: Credit Card, 360 Account
- **DBS**: Savings Account, Credit Card
- **UOB**: Lady's Solitaire, Preferred Platinum VISA
- **HSBC**: Revolution Card
- **Citibank**: Rewards, Prestige

## Quick Start

### 1. Install

```bash
# Clone and install
git clone https://github.com/shyamsundar2007/lunchsync-sg.git
cd lunchsync-sg
pip install -e .
```

### 2. Run Setup

Run setup with your bank export files to auto-detect accounts and map them to Lunch Money:

```bash
lunchsync-sg --setup ~/Downloads/bank-exports/
```

The setup wizard will:
1. Scan your bank export files to auto-detect accounts
2. Fetch your Lunch Money assets
3. Prompt for your Lunch Money API key
4. Let you map each bank account to a Lunch Money asset using an interactive picker (↑/↓ to navigate, Enter to select)
5. Save configuration to `~/.config/lunchsync-sg/config.json`

### 3. Download Bank Exports

Download transaction exports from your bank's website:

| Bank | Where to Download |
|------|-------------------|
| OCBC | Internet Banking → Cards/Accounts → Download Statement (CSV) |
| DBS | digibank → Cards/Accounts → Transaction History → Download |
| UOB | Personal Internet Banking → Cards → Download Statement (XLS) |
| HSBC | Online Banking → Credit Cards → Download Transactions |
| Citi | Citibank Online → Cards → Download Transaction History |

Put all downloaded files in a folder (e.g., `~/Downloads/bank-exports/`).

### 4. Upload Transactions

```bash
# Upload all bank exports to Lunch Money
lunchsync-sg ~/Downloads/bank-exports/ --upload-lunchmoney

# Preview what would be uploaded (dry run)
lunchsync-sg ~/Downloads/bank-exports/ --upload-lunchmoney --dry-run

# Export to CSV instead
lunchsync-sg ~/Downloads/bank-exports/ -o transactions.csv
```

## Configuration

Configuration is stored in `~/.config/lunchsync-sg/config.json`:

```json
{
  "accounts": [
    {
      "card_number": "5400123456781234",
      "name": "OCBC Rewards",
      "bank": "OCBC",
      "type": "credit_card"
    },
    {
      "card_number": "695012345678",
      "name": "OCBC 360",
      "bank": "OCBC",
      "type": "savings"
    }
  ],
  "lunch_money": {
    "api_key": "your_api_key_here",
    "account_mapping": {
      "OCBC Rewards": 12345,
      "OCBC 360": 67890
    }
  }
}
```

### Managing Accounts

Re-run setup with your bank export files to detect and configure accounts:

```bash
lunchsync-sg --setup ~/Downloads/bank-exports/
```

To view current configuration:

```bash
lunchsync-sg --show-config
```

### Finding Account Identifiers

Open your bank export file and look for the account/card number. Examples:

- OCBC Credit: `5400-1234-5678-1234` (use without dashes: `5400123456781234`)
- OCBC 360: `695-012345-678`
- DBS: `020-1-23456-7`
- UOB: Full card number in the XLS file
- HSBC: Last 4 digits (e.g., `3363`)
- Citi: Full card number

## CLI Reference

```bash
# Interactive setup wizard (scans files and maps to Lunch Money)
lunchsync-sg --setup ~/Downloads/bank-exports/

# View current configuration
lunchsync-sg --show-config

# Upload to Lunch Money
lunchsync-sg ~/Downloads/bank-exports/ --upload-lunchmoney

# Dry run (preview without uploading)
lunchsync-sg ~/Downloads/bank-exports/ --upload-lunchmoney --dry-run

# Export to CSV instead (for manual import)
lunchsync-sg ~/Downloads/bank-exports/ -o transactions.csv

# Export with all fields (currency, category, reference)
lunchsync-sg ~/Downloads/bank-exports/ -o transactions.csv --full

# Lunch Money asset mapping (after accounts are configured)
lunchsync-sg --lm-setup --lm-api-key YOUR_KEY

# List available bank parsers
lunchsync-sg --list-parsers

# Verbose output
lunchsync-sg ~/Downloads/bank-exports/ --upload-lunchmoney -v
```

## Troubleshooting

### "Unknown (1234)" account names

Your account mapping is missing or incorrect. Check:
1. Run `lunchsync-sg --setup ~/Downloads/` to add/verify accounts
2. Run `lunchsync-sg --show-config` to see current configuration
3. Account identifier should match what's in your bank export
4. Run with `-v` to see which identifiers are being detected

### Duplicate transactions

The tool automatically deduplicates within a batch. Lunch Money also deduplicates based on the transaction reference. If you're seeing duplicates, they may have different reference numbers.

### Unsupported bank format

Run `lunchsync-sg --list-parsers` to see supported formats. If your bank isn't listed, the tool uses content detection - it may still work if the format is similar.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type check
mypy src

# Lint
ruff check src tests
```

## Disclaimer

This software is provided "as is" without warranty of any kind. By using this tool, you acknowledge that:

- **Not affiliated**: This project is not affiliated with, endorsed by, or connected to any bank (OCBC, DBS, UOB, HSBC, Citibank) or Lunch Money. All trademarks belong to their respective owners.
- **Your responsibility**: You are solely responsible for your financial data. Always verify transactions before relying on the output.
- **No guarantee**: Bank export formats may change at any time, which could cause parsing errors. Always review the output.
- **API keys**: Keep your Lunch Money API key secure. The tool stores it locally in your config file.
- **Data privacy**: This tool processes your data locally. No data is sent anywhere except to Lunch Money when you explicitly use the `--upload-lunchmoney` option.

Use at your own risk. The authors are not responsible for any financial discrepancies, data loss, or other issues arising from use of this software.

## License

MIT - See [LICENSE](LICENSE) for details.
