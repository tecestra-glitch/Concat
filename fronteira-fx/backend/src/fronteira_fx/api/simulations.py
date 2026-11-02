from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException

from ..engine.positions import Position
from ..engine.routes import Fee, RouteError, StepSpec, simulate_route
from ..schemas import CycleSimulationRequest, RouteResultOut, SimulationRequest, SimulationResponse
from ..services.opportunities import run_simulation
from .deps import ApiKey, DataModeDep, DbDep

# Simulations compute (and may persist) results: they are write-like and honour API_KEY like the other
# write endpoints (B7). The dependency is a no-op when API_KEY is not configured.
router = APIRouter(prefix="/simulations", tags=["simulations"], dependencies=[ApiKey])


@router.post(
    "/routes",
    operation_id="compare_routes",
    summary="Compare routes for a capital/objective; ranked opportunities + amount search",
)
def compare_routes(body: SimulationRequest, db: DbDep, data_mode: DataModeDep) -> SimulationResponse:
    return run_simulation(db, body, data_mode=data_mode).response


@router.post(
    "/cycle",
    operation_id="simulate_cycle",
    summary="Simulate an explicit multi-step route (each step consumes the previous output)",
)
def simulate_cycle(body: CycleSimulationRequest) -> RouteResultOut:
    steps = []
    for s in body.steps:
        steps.append(
            StepSpec(
                description=s.description,
                from_position=Position(
                    currency=s.from_.currency,
                    institution=s.from_.institution,
                    account_id=s.from_.account_id,
                    location=s.from_.location,
                    modality=s.from_.modality,
                ),
                to_position=Position(
                    currency=s.to.currency,
                    institution=s.to.institution,
                    account_id=s.to.account_id,
                    location=s.to.location,
                    modality=s.to.modality,
                ),
                rate=s.rate,
                rate_note=s.rate_note,
                fees=tuple(Fee(f.label, f.amount, f.currency, f.rate_to_output) for f in s.fees),
                duration=s.duration,
                promo=s.promo,
                confidence=s.confidence,
                evidence_id=s.evidence_id,
            )
        )
    try:
        result = simulate_route(
            steps,
            Decimal(body.capital),
            valuation_currency=body.valuation_currency,
            valuation_rates={k: Decimal(v) for k, v in body.valuation_rates.items()},
        )
    except RouteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RouteResultOut.model_validate(result.to_dict())
