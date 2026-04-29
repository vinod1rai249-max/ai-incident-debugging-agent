from core.cost import CostAccumulator, TokenUsage


def test_cost_calculation_known_model() -> None:
    usage = TokenUsage(
        model="claude-sonnet-4-6",
        input_tokens=1_000,
        output_tokens=500,
        cached_tokens=0,
    )
    # (1000 * 3.00 + 500 * 15.00) / 1_000_000
    expected = (1000 * 3.00 + 500 * 15.00) / 1_000_000
    assert abs(usage.cost_usd - expected) < 1e-9


def test_cached_tokens_use_lower_rate() -> None:
    full = TokenUsage(model="claude-sonnet-4-6", input_tokens=1000, output_tokens=0)
    cached = TokenUsage(
        model="claude-sonnet-4-6", input_tokens=1000, output_tokens=0, cached_tokens=1000
    )
    assert cached.cost_usd < full.cost_usd


def test_unknown_model_returns_zero() -> None:
    usage = TokenUsage(model="gpt-999", input_tokens=1000, output_tokens=500)
    assert usage.cost_usd == 0.0


def test_accumulator_sums_across_calls() -> None:
    acc = CostAccumulator()
    acc.add(TokenUsage(model="claude-sonnet-4-6", input_tokens=1000, output_tokens=200))
    acc.add(TokenUsage(model="claude-sonnet-4-6", input_tokens=500, output_tokens=100))
    assert acc.total_input_tokens == 1500
    assert acc.total_output_tokens == 300
    assert acc.total_cost_usd > 0


def test_accumulator_summary_keys() -> None:
    acc = CostAccumulator()
    acc.add(TokenUsage(model="claude-sonnet-4-6", input_tokens=100, output_tokens=50))
    summary = acc.summary()
    assert set(summary) == {"calls", "total_input_tokens", "total_output_tokens", "total_cost_usd"}
    assert summary["calls"] == 1
