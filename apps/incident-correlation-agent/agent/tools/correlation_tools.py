from datetime import UTC, timedelta

from models.correlation import CorrelationResult
from models.incident import ServiceNowIncident
from models.trace import DynatraceProblem

from core.config import get_settings
from core.logging_config import get_logger
from core.metrics import correlations_total

logger = get_logger(__name__)


def _normalize(name: str) -> str:
    return name.lower().replace("-", "").replace("_", "").replace(" ", "")


def _service_name_match(incident: ServiceNowIncident, problem: DynatraceProblem) -> bool:
    inc_service = _normalize(incident.service_name)
    if not inc_service:
        # fall back to short_description keyword search
        inc_service = _normalize(incident.short_description)

    for svc in problem.service_names:
        if _normalize(svc) in inc_service or inc_service in _normalize(svc):
            return True

    # also check problem title vs incident description
    prob_title_normalized = _normalize(problem.title)
    return inc_service and inc_service in prob_title_normalized


def _time_overlap(
    incident: ServiceNowIncident, problem: DynatraceProblem, window_minutes: int
) -> bool:
    if incident.opened_at is None:
        return False

    inc_time = incident.opened_at
    if inc_time.tzinfo is None:
        inc_time = inc_time.replace(tzinfo=UTC)

    prob_start = problem.start_time
    prob_end = problem.end_time or inc_time  # treat open problems as ongoing

    window = timedelta(minutes=window_minutes)
    return (prob_start - window) <= inc_time <= (prob_end + window)


def correlate(
    incidents: list[ServiceNowIncident],
    problems: list[DynatraceProblem],
) -> list[CorrelationResult]:
    settings = get_settings()
    window = settings.correlation_time_window_minutes
    results: list[CorrelationResult] = []

    for incident in incidents:
        matched: list[DynatraceProblem] = []
        reasons: list[str] = []
        score = 0.0

        for problem in problems:
            name_match = _service_name_match(incident, problem)
            time_match = _time_overlap(incident, problem, window)

            if name_match and time_match:
                matched.append(problem)
                score += 1.0
                reasons.append(
                    f"Service name and timestamp matched with DT problem"
                    f" {problem.display_id}: {problem.title}"
                )
            elif name_match:
                matched.append(problem)
                score += 0.5
                reasons.append(
                    f"Service name matched (no time overlap) with DT problem {problem.display_id}"
                )
            elif time_match:
                score += 0.2
                reasons.append(
                    f"Timestamp overlap with DT problem {problem.display_id}"
                    " (no service name match)"
                )

        result = CorrelationResult(
            incident=incident,
            matched_problems=matched,
            correlation_score=round(score, 2),
            correlation_reasons=reasons,
        )
        results.append(result)

        if matched:
            correlations_total.inc()
            logger.info(
                "correlation_found",
                incident=incident.number,
                problems=[p.display_id for p in matched],
                score=score,
            )

    return results
