"""SignalX Order Block strategy API.

AlgoTrade V1 has been replaced by XAUUSD Order Block Pro 2026.
The endpoint is analysis-only; Signal History and MT5 execution remain managed
by the main Signal Engine.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

import main as core

router = APIRouter(tags=["Order Block"])


@router.get("/api/v1/order-block/{symbol:path}")
@router.get("/api/v1/algotrade/{symbol:path}", include_in_schema=False)
async def order_block_analysis(
    symbol: str,
    authorization: str | None = Header(default=None),
    session: Session = Depends(core.db),
) -> dict[str, Any]:
    core.require_admin(authorization, session)
    return await core.build_order_block_signals(symbol)
