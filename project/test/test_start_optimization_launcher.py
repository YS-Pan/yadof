from __future__ import annotations

def test_launcher_runs_optional_smoke_before_generations(monkeypatch):
    import start_optimization_from_config as launcher

    events = []
    monkeypatch.setattr(launcher.config, "OPTIMIZE_SMOKE_TEST_ENABLED", True)
    monkeypatch.setattr(launcher.config, "EVALUATION_MODE", "distributed")
    monkeypatch.setattr(launcher, "run_smoke_test", lambda **_kwargs: events.append("smoke") or ((0.1,),))
    monkeypatch.setattr(
        launcher,
        "run_generations",
        lambda *_args, **_kwargs: events.append("generations") or (),
    )
    monkeypatch.delenv("YADOF_GENERATIONS", raising=False)
    monkeypatch.delenv("YADOF_START_GENERATION", raising=False)

    assert launcher.main() == 0
    assert events == ["smoke", "generations"]


def test_launcher_can_skip_smoke_from_key_config(monkeypatch):
    import start_optimization_from_config as launcher

    monkeypatch.setattr(launcher.config, "OPTIMIZE_SMOKE_TEST_ENABLED", False)
    monkeypatch.setattr(
        launcher,
        "run_smoke_test",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("smoke must be skipped")),
    )
    monkeypatch.setattr(launcher, "run_generations", lambda *_args, **_kwargs: ())
    monkeypatch.delenv("YADOF_GENERATIONS", raising=False)
    monkeypatch.delenv("YADOF_START_GENERATION", raising=False)

    assert launcher.main() == 0
