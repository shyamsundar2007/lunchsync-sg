"""Parsing utilities for bank transaction files."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


def parse_date(date_str: str) -> date | None:
    """
    Parse various date formats to date object.

    Supported formats:
    - DD/MM/YYYY (30/01/2026)
    - DD MMM YYYY (30 Jan 2026)
    - DD-MM-YYYY (30-01-2026)
    - YYYY-MM-DD (2026-01-30)

    Args:
        date_str: Date string to parse

    Returns:
        date object if successful, None otherwise
    """
    date_str = date_str.strip().strip('"').strip()

    if not date_str:
        return None

    formats = [
        "%d/%m/%Y",  # 30/01/2026
        "%d %b %Y",  # 30 Jan 2026
        "%d-%m-%Y",  # 30-01-2026
        "%Y-%m-%d",  # 2026-01-30
        "%d %B %Y",  # 30 January 2026
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    return None


def parse_amount(amount_str: str) -> Decimal | None:
    """
    Parse amount string to Decimal.

    Handles:
    - Currency symbols (SGD, $, etc.)
    - Thousands separators (commas)
    - Negative values (both -123 and (123))
    - Quoted values

    Args:
        amount_str: Amount string to parse

    Returns:
        Decimal if successful, None otherwise
    """
    if not amount_str or not amount_str.strip():
        return None

    # Remove quotes and whitespace
    amount_str = amount_str.strip().strip('"').strip()

    if not amount_str:
        return None

    # Check for parentheses (negative)
    is_negative = False
    if amount_str.startswith("(") and amount_str.endswith(")"):
        is_negative = True
        amount_str = amount_str[1:-1]

    # Remove currency symbols and whitespace
    amount_str = re.sub(r"[SGD$\s]", "", amount_str)

    # Handle thousands separator (comma)
    amount_str = amount_str.replace(",", "")

    # Check for negative sign
    if amount_str.startswith("-"):
        is_negative = True
        amount_str = amount_str[1:]

    try:
        value = Decimal(amount_str)
        return -value if is_negative else value
    except InvalidOperation:
        return None


def clean_description(desc: str) -> str:
    """
    Clean up transaction description.

    Removes:
    - Extra whitespace and newlines
    - Card number masks
    - Reference numbers
    - Trailing location codes

    Args:
        desc: Raw description string

    Returns:
        Cleaned description
    """
    # Remove extra whitespace and newlines
    desc = " ".join(desc.split())

    # Remove card number masks (various formats)
    desc = re.sub(r"[•X]{4}[-\s]*[•X]{4}[-\s]*[•X]{4}[-\s]*\d{4}", "", desc)
    desc = re.sub(r"XXXX-XXXX-XXXX-\d{4}", "", desc)

    # Remove reference numbers
    desc = re.sub(r"Ref No:\s*\d+", "", desc)

    # Remove trailing location/country codes
    desc = re.sub(r"\s+(SG|SGP|MY|GB|US|AU|IN|GBR|MYR|USD|AUD)\s*$", "", desc)

    # Clean up extra spaces
    desc = " ".join(desc.split())

    return desc.strip()


def read_file(filepath: Path) -> str:
    """
    Read file content, handling both text and Excel files.

    Args:
        filepath: Path to the file

    Returns:
        File content as string (Excel files converted to CSV format)

    Raises:
        ValueError: If file cannot be read
    """
    # Check if it's an Excel file by magic bytes
    is_xls = False
    try:
        with open(filepath, "rb") as f:
            magic = f.read(8)
            # OLE2 magic bytes (used by .xls)
            if magic[:4] == b"\xd0\xcf\x11\xe0" or magic[:4] == b"PK\x03\x04":
                is_xls = True
    except Exception:
        pass

    # Also check extension
    if filepath.suffix.lower() in [".xls", ".xlsx"]:
        is_xls = True

    if is_xls:
        return _read_excel(filepath)
    else:
        return _read_text(filepath)


def _read_text(filepath: Path) -> str:
    """Read text file with encoding detection."""
    if not filepath.exists():
        raise ValueError(f"File not found: {filepath}")

    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]

    for encoding in encodings:
        try:
            with open(filepath, encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue

    raise ValueError(f"Could not decode file {filepath} with any known encoding")


def _read_excel(filepath: Path) -> str:
    """Read Excel file and convert to CSV string."""
    try:
        import xlrd  # type: ignore[import-untyped]
    except ImportError as err:
        raise ValueError(
            "xlrd is required to read Excel files. Install with: pip install xlrd"
        ) from err

    try:
        wb = xlrd.open_workbook(str(filepath))
        sheet = wb.sheet_by_index(0)

        lines = []
        for row in range(sheet.nrows):
            row_data = []
            for col in range(sheet.ncols):
                cell = sheet.cell(row, col)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    try:
                        dt = xlrd.xldate_as_datetime(cell.value, wb.datemode)
                        row_data.append(dt.strftime("%d %b %Y"))
                    except Exception:
                        row_data.append(str(cell.value))
                else:
                    # Escape commas in values
                    value = str(cell.value)
                    if "," in value or '"' in value or "\n" in value:
                        value = '"' + value.replace('"', '""') + '"'
                    row_data.append(value)
            lines.append(",".join(row_data))

        return "\n".join(lines)

    except Exception as e:
        raise ValueError(f"Could not read Excel file {filepath}: {e}") from e
