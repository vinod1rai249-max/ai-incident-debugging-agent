from datetime import timedelta

from agent.tools.correlation_tools import _normalize, _service_name_match, _time_overlap, correlate


def test_normalize():
    assert _normalize("Payment-API") == "paymentapi"
    assert _normalize("auth_service") == "authservice"


def test_service_name_match_hit(sample_incident, sample_problem):
    assert _service_name_match(sample_incident, sample_problem) is True


def test_service_name_match_miss(sample_incident, unrelated_problem):
    assert _service_name_match(sample_incident, unrelated_problem) is False


def test_time_overlap_within_window(sample_incident, sample_problem):
    assert _time_overlap(sample_incident, sample_problem, window_minutes=60) is True


def test_time_overlap_outside_window(sample_incident, sample_problem):
    # incident opened 2h after problem started (and problem ended 1h after start)
    sample_problem.end_time = sample_problem.start_time + timedelta(hours=1)
    late_incident = sample_incident.model_copy(
        update={"opened_at": sample_problem.start_time + timedelta(hours=2)}
    )
    assert _time_overlap(late_incident, sample_problem, window_minutes=30) is False


def test_correlate_match(sample_incident, sample_problem):
    results = correlate([sample_incident], [sample_problem])
    assert len(results) == 1
    r = results[0]
    assert len(r.matched_problems) == 1
    assert r.correlation_score >= 1.0
    assert r.matched_problems[0].problem_id == "P-12345"


def test_correlate_no_match(sample_incident, unrelated_problem):
    results = correlate([sample_incident], [unrelated_problem])
    assert len(results) == 1
    r = results[0]
    assert len(r.matched_problems) == 0


def test_correlate_empty_inputs():
    results = correlate([], [])
    assert results == []


def test_correlate_multiple_problems(sample_incident, sample_problem, unrelated_problem):
    results = correlate([sample_incident], [sample_problem, unrelated_problem])
    assert len(results) == 1
    r = results[0]
    assert len(r.matched_problems) == 1
    assert r.matched_problems[0].problem_id == "P-12345"
