from __future__ import annotations

from fastapi import FastAPI, HTTPException

from ..config import DEFAULT_CONFIG
from ..enums import Direction
from ..pricing.lmsr import probability_yes, quote_trade
from .schemas import QuoteOrderRequest, QuoteOrderResponse

app = FastAPI(title="NCAAF Synthetic Market Engine", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "specification_version": DEFAULT_CONFIG.specification_version,
        "real_money_execution": False,
        "blocked_features": [
            "independent_power_model",
            "historical_line_movement",
            "multi_book_pricing",
            "sharp_belief_adjustment",
        ],
    }


@app.post("/api/v0/amm/quote", response_model=QuoteOrderResponse)
def quote_amm_order(request: QuoteOrderRequest, q_yes: float = 0, q_no: float = 0):
    if request.quantity > DEFAULT_CONFIG.risk_limits.maximum_single_order_quantity:
        raise HTTPException(status_code=422, detail="quantity exceeds configured single-order limit")
    result = quote_trade(
        q_yes=q_yes,
        q_no=q_no,
        liquidity_b=DEFAULT_CONFIG.amm.liquidity_b,
        direction=request.direction,
        quantity=request.quantity,
    )
    return QuoteOrderResponse(
        direction=result.direction,
        quantity=result.quantity,
        quoted_cost=result.cost,
        average_price=result.average_price,
        probability_before=result.probability_before,
        probability_after=result.probability_after,
    )


@app.get("/api/v0/amm/probability")
def current_probability(q_yes: float = 0, q_no: float = 0) -> dict:
    return {
        "probability_yes": probability_yes(q_yes, q_no, DEFAULT_CONFIG.amm.liquidity_b),
        "belief_probability_yes": DEFAULT_CONFIG.initial_belief_probability,
    }
