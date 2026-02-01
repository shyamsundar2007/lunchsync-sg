"""Bank parsers package."""

from lunchsync_sg.parsers.base import BankParser, ParserRegistry
from lunchsync_sg.parsers.citi import CitiParser
from lunchsync_sg.parsers.dbs import DBSCreditParser, DBSSavingsParser
from lunchsync_sg.parsers.hsbc import HSBCRevolutionParser
from lunchsync_sg.parsers.ocbc import OCBC360Parser, OCBCCreditParser
from lunchsync_sg.parsers.uob import UOBCreditParser

__all__ = [
    "BankParser",
    "ParserRegistry",
    "OCBCCreditParser",
    "OCBC360Parser",
    "DBSSavingsParser",
    "DBSCreditParser",
    "UOBCreditParser",
    "HSBCRevolutionParser",
    "CitiParser",
]
