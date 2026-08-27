from backend.app.models import RiskDecision, ThesisRequest


def evaluate_thesis(request: ThesisRequest) -> RiskDecision:
    vetoes: list[str] = []
    if request.max_loss_usd > 500:
        vetoes.append("max loss exceeds Phase 0 research limit")
    if request.confidence < 0.65:
        vetoes.append("insufficient committee confidence")
    if request.data_age_seconds > 60:
        vetoes.append("market data is stale")
    if not 14 <= request.days_to_expiry <= 35:
        vetoes.append("expiration is outside the Phase 0 test window")
    return RiskDecision(approved_for_research=not vetoes, vetoes=vetoes)

