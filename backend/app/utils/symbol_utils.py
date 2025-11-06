"""
Symbol normalization utilities.
Consolidated from multiple implementations across the codebase.

CANONICAL SYMBOLS (Post-Migration 019):
- NIFTY (not NIFTY50 or NIFTY 50)
- BANKNIFTY (not BANK NIFTY)
- FINNIFTY (not NIFTY FIN SERVICE)
- MIDCPNIFTY (not NIFTY MIDCAP SELECT)

This ensures compatibility across all brokers (Kite, Angel, Upstox, Fyers, etc.)
"""

from typing import List, Set, Dict
import re


def normalize_symbol(symbol: str) -> str:
    """
    Canonicalize symbol to database-compatible form.

    IMPORTANT: Returns canonical symbol matching database after migration 019.
    All variations (NIFTY50, NIFTY 50, NSE:NIFTY) -> "NIFTY"
    Stocks: NSE:RELIANCE-EQ, RELIANCE.NS, RELIANCE -> "RELIANCE"

    Args:
        symbol: Raw symbol string (e.g., "NSE:NIFTY", "RELIANCE.NS", "NSE:TCS-EQ")

    Returns:
        Canonical symbol (e.g., "NIFTY", "RELIANCE", "TCS")

    Examples:
        >>> normalize_symbol("NSE:NIFTY")
        'NIFTY'
        >>> normalize_symbol("NIFTY 50")
        'NIFTY'
        >>> normalize_symbol("NSE:RELIANCE-EQ")
        'RELIANCE'
        >>> normalize_symbol("TCS.NS")
        'TCS'
        >>> normalize_symbol("INFY.BO")
        'INFY'
    """
    if not symbol:
        return ""

    # Trim and uppercase
    canonical = symbol.upper().strip()

    # Remove exchange prefixes (NSE:, BSE:, MCX:)
    canonical = re.sub(r'^(NSE|BSE|MCX):', '', canonical)

    # Remove common suffixes used by different platforms
    # .NS (NSE), .BO (BSE/Bombay), -EQ (equity), .NSE, .BSE, -BE (B Group equity)
    canonical = re.sub(r'\.(NS|BO|NSE|BSE)$', '', canonical)
    canonical = re.sub(r'-(EQ|BE)$', '', canonical)

    # Remove index prefix (e.g., "^NSEI" -> "NSEI")
    if canonical.startswith("^"):
        canonical = canonical[1:]

    # Normalize internal whitespace
    canonical = " ".join(canonical.split())

    # Apply canonical mappings for indices
    mappings = {
        # NIFTY variations
        "NIFTY50": "NIFTY",
        "NIFTY 50": "NIFTY",
        "NIFTY-50": "NIFTY",
        "NSEI": "NIFTY",

        # BANKNIFTY variations
        "BANK NIFTY": "BANKNIFTY",
        "NIFTY BANK": "BANKNIFTY",
        "BANKNIFTY": "BANKNIFTY",
        "BANKNIFTY1!": "BANKNIFTY",

        # FINNIFTY variations
        "NIFTY FIN SERVICE": "FINNIFTY",
        "NIFTYFIN": "FINNIFTY",
        "FIN NIFTY": "FINNIFTY",
        "FINNIFTY": "FINNIFTY",

        # MIDCPNIFTY variations
        "NIFTY MIDCAP SELECT": "MIDCPNIFTY",
        "MIDCAP NIFTY": "MIDCPNIFTY",
        "MIDCPNIFTY": "MIDCPNIFTY",

        # SENSEX variations
        "SENSEX": "SENSEX",
        "BSE SENSEX": "SENSEX",
        "BSESN": "SENSEX",
    }

    return mappings.get(canonical, canonical)


def get_symbol_variants(symbol: str) -> List[str]:
    """
    Return the canonical symbol alongside historical aliases for backward compatibility.

    DEPRECATED: After migration 019, all data uses canonical symbols.
    This function is kept for legacy queries only.

    Args:
        symbol: Symbol to get variants for

    Returns:
        List containing only the canonical form (post-migration 019)

    Examples:
        >>> get_symbol_variants("NIFTY")
        ['NIFTY']
        >>> get_symbol_variants("NIFTY50")
        ['NIFTY']
        >>> get_symbol_variants("NIFTY 50")
        ['NIFTY']
    """
    primary = normalize_symbol(symbol)

    # Post-migration 019: All data uses canonical symbols
    # No need for variants anymore - database triggers enforce normalization
    return [primary]
