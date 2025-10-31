"""
Symbol normalization utilities.
Consolidated from multiple implementations across the codebase.
"""

from typing import List, Set, Dict


def normalize_symbol(symbol: str) -> str:
    """
    Canonicalize an incoming symbol string by trimming whitespace, removing
    exchange prefixes and squashing spaces. Known aliases (e.g. NIFTY50) are
    folded into their canonical counterparts, but other symbols are left as-is
    once normalized.

    Args:
        symbol: Raw symbol string (e.g., "NSE:NIFTY", "NIFTY 50", "^NSEI")

    Returns:
        Normalized symbol (e.g., "NIFTY50")

    Examples:
        >>> normalize_symbol("NSE:NIFTY")
        'NIFTY50'
        >>> normalize_symbol("^NSEI")
        'NIFTY50'
        >>> normalize_symbol("  nifty 50  ")
        'NIFTY50'
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

    # Remove spaces
    s = s.replace(" ", "")

    # Apply known aliases
    aliases = {
        "NSEI": "NIFTY50",
        "NIFTY": "NIFTY50",
    }

    return aliases.get(s, s)


def get_symbol_variants(symbol: str) -> List[str]:
    """
    Return the canonical symbol alongside any common aliases so we can
    gracefully query mixed historical datasets (e.g., FO tables that still
    use NIFTY while the canonical minute bars now use NIFTY50).

    Args:
        symbol: Symbol to get variants for

    Returns:
        List of symbol variants including the canonical form

    Examples:
        >>> get_symbol_variants("NIFTY")
        ['NIFTY50', 'NIFTY']
        >>> get_symbol_variants("NIFTY50")
        ['NIFTY50', 'NIFTY']
    """
    primary = normalize_symbol(symbol)

    # Define reverse aliases (canonical -> variants)
    aliases: Dict[str, Set[str]] = {
        "NIFTY50": {"NIFTY"},
        "NIFTY": {"NIFTY50"},
    }

    variants = {primary}
    variants.update(aliases.get(primary, set()))

    return list(variants)
