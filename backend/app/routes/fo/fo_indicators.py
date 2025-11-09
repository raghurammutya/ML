"""
F&O Indicators API endpoints.
"""
from fastapi import APIRouter

router = APIRouter()

# Indicator registry defining available F&O indicators
INDICATOR_REGISTRY = [
    {
        "id": "iv_panel",
        "label": "IV (ATM/OTM/ITM)",
        "indicator": "iv",
        "orientation": "horizontal",
        "option_side": "both",
        "default": True,
    },
    {
        "id": "delta_panel",
        "label": "Delta (Calls/Puts)",
        "indicator": "delta",
        "orientation": "horizontal",
        "option_side": "both",
        "default": True,
    },
    {
        "id": "gamma_panel",
        "label": "Gamma (Calls/Puts)",
        "indicator": "gamma",
        "orientation": "horizontal",
        "option_side": "both",
        "default": False,
    },
    {
        "id": "theta_panel",
        "label": "Theta (Calls/Puts)",
        "indicator": "theta",
        "orientation": "horizontal",
        "option_side": "both",
        "default": False,
    },
    {
        "id": "vega_panel",
        "label": "Vega (Calls/Puts)",
        "indicator": "vega",
        "orientation": "horizontal",
        "option_side": "both",
        "default": False,
    },
    {
        "id": "oi_panel",
        "label": "Open Interest (Calls/Puts)",
        "indicator": "oi",
        "orientation": "horizontal",
        "option_side": "both",
        "default": True,
    },
    {
        "id": "pcr_panel",
        "label": "PCR by Moneyness",
        "indicator": "pcr",
        "orientation": "horizontal",
        "option_side": "both",
        "default": True,
    },
    {
        "id": "max_pain_panel",
        "label": "Max Pain (per expiry)",
        "indicator": "max_pain",
        "orientation": "horizontal",
        "default": True,
    },
    {
        "id": "iv_strike_panel",
        "label": "IV by Strike",
        "indicator": "iv",
        "orientation": "vertical",
        "default": True,
    },
    {
        "id": "delta_strike_panel",
        "label": "Delta by Strike",
        "indicator": "delta",
        "orientation": "vertical",
        "default": False,
    },
    {
        "id": "gamma_strike_panel",
        "label": "Gamma by Strike",
        "indicator": "gamma",
        "orientation": "vertical",
        "default": False,
    },
    {
        "id": "theta_strike_panel",
        "label": "Theta by Strike",
        "indicator": "theta",
        "orientation": "vertical",
        "default": False,
    },
    {
        "id": "vega_strike_panel",
        "label": "Vega by Strike",
        "indicator": "vega",
        "orientation": "vertical",
        "default": False,
    },
    {
        "id": "oi_strike_panel",
        "label": "Open Interest by Strike",
        "indicator": "oi",
        "orientation": "vertical",
        "default": False,
    },
    {
        "id": "pcr_strike_panel",
        "label": "PCR by Strike",
        "indicator": "pcr",
        "orientation": "vertical",
        "default": True,
    },
]


@router.get("/indicators")
async def list_fo_indicators():
    """
    List all available F&O indicators.

    Returns registry of indicators that can be used for analysis.
    """
    return {
        "status": "ok",
        "indicators": INDICATOR_REGISTRY,
    }
