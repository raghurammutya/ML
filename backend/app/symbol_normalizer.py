"""
Symbol Normalization Layer

Provides consistent symbol naming across all services and brokers.
Supports multi-broker integration by mapping broker-specific symbols to canonical forms.

Canonical Symbols:
- NIFTY (not NIFTY50 or NIFTY 50)
- BANKNIFTY (not BANK NIFTY)
- FINNIFTY (not NIFTY FIN SERVICE)
- MIDCPNIFTY (not NIFTY MIDCAP SELECT)
"""

from functools import lru_cache
from typing import Optional
import re


# Canonical symbol mappings
CANONICAL_MAPPINGS = {
    # NIFTY variations
    "NIFTY50": "NIFTY",
    "NIFTY 50": "NIFTY",
    "NIFTY-50": "NIFTY",
    "NSE:NIFTY": "NIFTY",
    "NSE:NIFTY50": "NIFTY",
    "NSEI": "NIFTY",

    # BANKNIFTY variations
    "BANK NIFTY": "BANKNIFTY",
    "NIFTY BANK": "BANKNIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "BANKNIFTY1!": "BANKNIFTY",
    "NSE:BANKNIFTY": "BANKNIFTY",

    # FINNIFTY variations
    "FINNIFTY": "FINNIFTY",
    "NIFTY FIN SERVICE": "FINNIFTY",
    "NIFTYFIN": "FINNIFTY",
    "FIN NIFTY": "FINNIFTY",
    "NSE:FINNIFTY": "FINNIFTY",

    # MIDCPNIFTY variations
    "MIDCPNIFTY": "MIDCPNIFTY",
    "NIFTY MIDCAP SELECT": "MIDCPNIFTY",
    "MIDCAP NIFTY": "MIDCPNIFTY",
    "NSE:MIDCPNIFTY": "MIDCPNIFTY",

    # SENSEX variations
    "SENSEX": "SENSEX",
    "BSE SENSEX": "SENSEX",
    "BSESN": "SENSEX",
}


# Broker-specific symbol formats
BROKER_FORMATS = {
    "zerodha": {
        "NIFTY 50": "NIFTY",
        "BANK NIFTY": "BANKNIFTY",
    },
    "angel": {
        "NIFTY": "NIFTY",
        "NIFTY50": "NIFTY",
        "BANKNIFTY": "BANKNIFTY",
    },
    "upstox": {
        "NIFTY 50": "NIFTY",
        "BANK NIFTY": "BANKNIFTY",
    },
    "fyers": {
        "NSE:NIFTY50": "NIFTY",
        "NSE:BANKNIFTY": "BANKNIFTY",
    },
    "iifl": {
        "Nifty": "NIFTY",
        "BankNifty": "BANKNIFTY",
    },
}


@lru_cache(maxsize=1000)
def normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol to canonical form.

    Fast client-side normalization with LRU cache for hot path.
    Handles both indices and individual stocks.

    Args:
        symbol: Input symbol (any variation)

    Returns:
        Canonical symbol (NIFTY, BANKNIFTY, RELIANCE, TCS, etc.)

    Examples:
        >>> normalize_symbol("NIFTY50")
        'NIFTY'
        >>> normalize_symbol("NIFTY 50")
        'NIFTY'
        >>> normalize_symbol("NSE:NIFTY")
        'NIFTY'
        >>> normalize_symbol("NSE:RELIANCE-EQ")
        'RELIANCE'
        >>> normalize_symbol("TCS.NS")
        'TCS'
        >>> normalize_symbol("INFY.BO")
        'INFY'
    """
    if not symbol:
        return symbol

    # Trim and uppercase
    canonical = symbol.upper().strip()

    # Remove common exchange prefixes (NSE:, BSE:, MCX:)
    canonical = re.sub(r'^(NSE|BSE|MCX):', '', canonical)

    # Remove common suffixes used by different platforms
    # .NS (NSE), .BO (BSE/Bombay), -EQ (equity), .NSE, .BSE, -BE (B Group equity)
    canonical = re.sub(r'\.(NS|BO|NSE|BSE)$', '', canonical)
    canonical = re.sub(r'-(EQ|BE)$', '', canonical)

    # Remove index prefix (e.g., "^NSEI" -> "NSEI")
    if canonical.startswith('^'):
        canonical = canonical[1:]

    # Direct lookup in mappings
    if canonical in CANONICAL_MAPPINGS:
        return CANONICAL_MAPPINGS[canonical]

    # Return as-is if no mapping found (works for all stocks)
    return canonical


@lru_cache(maxsize=1000)
def normalize_symbol_for_broker(symbol: str, broker: str = "zerodha") -> str:
    """
    Normalize symbol and return broker-specific format if needed.

    Args:
        symbol: Input symbol
        broker: Broker name (zerodha, angel, upstox, fyers, iifl)

    Returns:
        Broker-specific symbol format

    Examples:
        >>> normalize_symbol_for_broker("NIFTY50", "fyers")
        'NSE:NIFTY50'
        >>> normalize_symbol_for_broker("NIFTY 50", "angel")
        'NIFTY'
    """
    canonical = normalize_symbol(symbol)

    # Get broker-specific format
    if broker.lower() in BROKER_FORMATS:
        broker_mapping = BROKER_FORMATS[broker.lower()]
        for broker_sym, canon in broker_mapping.items():
            if canon == canonical:
                return broker_sym

    return canonical


def get_canonical_symbol(symbol: str) -> str:
    """
    Alias for normalize_symbol for clarity.

    Use this when you specifically want the canonical form.
    """
    return normalize_symbol(symbol)


def is_nifty_index(symbol: str) -> bool:
    """
    Check if symbol is a NIFTY index (not individual stock).

    Args:
        symbol: Symbol to check

    Returns:
        True if symbol is a NIFTY index

    Examples:
        >>> is_nifty_index("NIFTY50")
        True
        >>> is_nifty_index("BANKNIFTY")
        True
        >>> is_nifty_index("RELIANCE")
        False
    """
    canonical = normalize_symbol(symbol)
    return canonical in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]


def get_display_name(symbol: str) -> str:
    """
    Get user-friendly display name for symbol.

    Args:
        symbol: Canonical symbol

    Returns:
        Display-friendly name

    Examples:
        >>> get_display_name("NIFTY")
        'NIFTY 50'
        >>> get_display_name("BANKNIFTY")
        'BANK NIFTY'
    """
    display_names = {
        "NIFTY": "NIFTY 50",
        "BANKNIFTY": "BANK NIFTY",
        "FINNIFTY": "NIFTY FINANCIAL SERVICES",
        "MIDCPNIFTY": "NIFTY MIDCAP SELECT",
    }

    canonical = normalize_symbol(symbol)
    return display_names.get(canonical, canonical)


def register_broker_symbol(canonical: str, broker: str, broker_symbol: str) -> None:
    """
    Register a new broker-specific symbol mapping.

    Useful for adding support for new brokers dynamically.

    Args:
        canonical: Canonical symbol (NIFTY, BANKNIFTY, etc.)
        broker: Broker name
        broker_symbol: Broker's symbol format

    Example:
        >>> register_broker_symbol("NIFTY", "newbroker", "NIFTY_50")
    """
    if broker.lower() not in BROKER_FORMATS:
        BROKER_FORMATS[broker.lower()] = {}

    BROKER_FORMATS[broker.lower()][broker_symbol] = canonical

    # Clear cache to pick up new mapping
    normalize_symbol_for_broker.cache_clear()


# Pre-populate cache with common symbols
for common_symbol in ["NIFTY", "NIFTY50", "NIFTY 50", "BANKNIFTY", "BANK NIFTY", "FINNIFTY", "MIDCPNIFTY"]:
    normalize_symbol(common_symbol)
