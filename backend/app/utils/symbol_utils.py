"""
Symbol normalization utilities.
Consolidated from multiple implementations across the codebase.
"""

from typing import List, Set, Dict


def normalize_symbol(symbol: str) -> str:
    """
    Canonicalize an incoming symbol string by trimming whitespace, removing
    exchange prefixes. Known aliases (e.g. NIFTY50, NIFTY) are folded into
    their canonical counterparts matching Kite API format.

    Args:
        symbol: Raw symbol string (e.g., "NSE:NIFTY", "NIFTY 50", "^NSEI")

    Returns:
        Normalized symbol (e.g., "NIFTY 50")

    Examples:
        >>> normalize_symbol("NSE:NIFTY")
        'NIFTY 50'
        >>> normalize_symbol("^NSEI")
        'NIFTY 50'
        >>> normalize_symbol("  nifty 50  ")
        'NIFTY 50'
        >>> normalize_symbol("NIFTY50")
        'NIFTY 50'
    """
    s = (symbol or "").strip().upper()
    if not s:
        return ""

    # Remove exchange prefix (e.g., "NSE:NIFTY" -> "NIFTY")
    if ":" in s:
        s = s.split(":")[-1]

    # Remove index prefix (e.g., "^NSEI" -> "NSEI")
    if s.startswith("^"):
        s = s[1:]

    # Normalize internal whitespace (multiple spaces -> single space)
    s = " ".join(s.split())

    # Apply known aliases - map to Kite API format (with space for indices)
    aliases = {
        "NSEI": "NIFTY 50",
        "NIFTY": "NIFTY 50",
        "NIFTY50": "NIFTY 50",  # Legacy format without space
    }

    return aliases.get(s, s)


def get_symbol_variants(symbol: str) -> List[str]:
    """
    Return the canonical symbol alongside any common aliases so we can
    gracefully query mixed historical datasets (e.g., FO tables that may use
    NIFTY, NIFTY50, or "NIFTY 50" depending on data source).

    Args:
        symbol: Symbol to get variants for

    Returns:
        List of symbol variants including the canonical form

    Examples:
        >>> get_symbol_variants("NIFTY")
        ['NIFTY 50', 'NIFTY', 'NIFTY50']
        >>> get_symbol_variants("NIFTY50")
        ['NIFTY 50', 'NIFTY', 'NIFTY50']
        >>> get_symbol_variants("NIFTY 50")
        ['NIFTY 50', 'NIFTY', 'NIFTY50']
    """
    primary = normalize_symbol(symbol)

    # Define reverse aliases (canonical -> variants)
    # Include all common formats for backward compatibility
    aliases: Dict[str, Set[str]] = {
        "NIFTY 50": {"NIFTY", "NIFTY50"},
        "NIFTY": {"NIFTY 50", "NIFTY50"},
        "NIFTY50": {"NIFTY 50", "NIFTY"},
    }

    variants = {primary}
    variants.update(aliases.get(primary, set()))

    return list(variants)
