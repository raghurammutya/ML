"""
Dependency Injection Module

Provides FastAPI dependency injection functions for all application components.
This module eliminates global singletons and enables proper testing with mocked dependencies.

Usage:
    from fastapi import Depends
    from app.dependencies import get_orchestrator_dep

    @app.get("/endpoint")
    async def endpoint(orchestrator: SessionOrchestrator = Depends(get_orchestrator_dep)):
        # Use orchestrator
        pass
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from app.accounts import SessionOrchestrator
    from app.crypto import CredentialEncryption
    from app.generator import MultiAccountTickerLoop
    from app.greeks_calculator import GreeksCalculator
    from app.instrument_registry import InstrumentRegistry
    from app.order_executor import OrderExecutor
    from app.redis_publisher_v2 import ResilientRedisPublisher
    from app.subscription_store import SubscriptionStore


# ==================================================================
# DEPENDENCY INJECTION FUNCTIONS
# ==================================================================

def get_orchestrator_dep(request: Request) -> SessionOrchestrator:
    """
    Get SessionOrchestrator instance from application state.

    Args:
        request: FastAPI request object

    Returns:
        SessionOrchestrator instance

    Example:
        @app.get("/status")
        async def get_status(orchestrator: SessionOrchestrator = Depends(get_orchestrator_dep)):
            return orchestrator.get_status()
    """
    return request.app.state.orchestrator


def get_encryption_dep(request: Request) -> CredentialEncryption:
    """
    Get CredentialEncryption instance from application state.

    Args:
        request: FastAPI request object

    Returns:
        CredentialEncryption instance
    """
    return request.app.state.encryption


def get_ticker_loop_dep(request: Request) -> MultiAccountTickerLoop:
    """
    Get MultiAccountTickerLoop instance from application state.

    Args:
        request: FastAPI request object

    Returns:
        MultiAccountTickerLoop instance
    """
    return request.app.state.ticker_loop


def get_greeks_calculator_dep(request: Request) -> GreeksCalculator:
    """
    Get GreeksCalculator instance from application state.

    Args:
        request: FastAPI request object

    Returns:
        GreeksCalculator instance
    """
    return request.app.state.greeks_calculator


def get_instrument_registry_dep(request: Request) -> InstrumentRegistry:
    """
    Get InstrumentRegistry instance from application state.

    Args:
        request: FastAPI request object

    Returns:
        InstrumentRegistry instance
    """
    return request.app.state.instrument_registry


def get_executor_dep(request: Request) -> OrderExecutor:
    """
    Get OrderExecutor instance from application state.

    Args:
        request: FastAPI request object

    Returns:
        OrderExecutor instance
    """
    return request.app.state.executor


def get_redis_publisher_dep(request: Request) -> ResilientRedisPublisher:
    """
    Get ResilientRedisPublisher instance from application state.

    Args:
        request: FastAPI request object

    Returns:
        ResilientRedisPublisher instance
    """
    return request.app.state.redis_publisher


def get_subscription_store_dep(request: Request) -> SubscriptionStore:
    """
    Get SubscriptionStore instance from application state.

    Args:
        request: FastAPI request object

    Returns:
        SubscriptionStore instance
    """
    return request.app.state.subscription_store


# ==================================================================
# TYPE ALIASES FOR CONVENIENCE
# ==================================================================

# These type aliases can be used as annotations to reduce boilerplate:
#
# Instead of:
#   async def endpoint(orchestrator: SessionOrchestrator = Depends(get_orchestrator_dep))
#
# Use:
#   from app.dependencies import OrchestratorDep
#   async def endpoint(orchestrator: OrchestratorDep)
#
# Note: FastAPI's Annotated support requires Python 3.9+

from typing import Annotated

OrchestratorDep = Annotated[SessionOrchestrator, Depends(get_orchestrator_dep)]
EncryptionDep = Annotated[CredentialEncryption, Depends(get_encryption_dep)]
TickerLoopDep = Annotated[MultiAccountTickerLoop, Depends(get_ticker_loop_dep)]
GreeksCalculatorDep = Annotated[GreeksCalculator, Depends(get_greeks_calculator_dep)]
InstrumentRegistryDep = Annotated[InstrumentRegistry, Depends(get_instrument_registry_dep)]
ExecutorDep = Annotated[OrderExecutor, Depends(get_executor_dep)]
RedisPublisherDep = Annotated[ResilientRedisPublisher, Depends(get_redis_publisher_dep)]
SubscriptionStoreDep = Annotated[SubscriptionStore, Depends(get_subscription_store_dep)]
