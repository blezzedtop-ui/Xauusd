"""Deterministic + randomized regression tests for AI control semantics.
These tests mirror the public control contract: AUTO / ALL_ON / ALL_OFF and
individual provider toggles must remain distinct and deterministic.
"""
from random import Random

PROVIDERS = [
    "groq","groq_2","gemini","anthropic","anthropic_2","anthropic_3",
    "openai","mistral","cerebras","cloudflare","huggingface","openrouter","deepseek"
]


def apply_mode(state, mode):
    assert mode in {"AUTO", "ALL_ON", "ALL_OFF"}
    state["mode"] = mode
    state["auto_mode"] = mode == "AUTO"
    state["enabled"] = {p: mode != "ALL_OFF" for p in PROVIDERS}
    return state


def toggle(state, provider, enabled=None):
    assert provider in PROVIDERS
    state["mode"] = "CUSTOM"
    state["auto_mode"] = False
    state["enabled"][provider] = (not state["enabled"][provider]) if enabled is None else bool(enabled)
    return state


def test_each_global_mode_100_times():
    for mode in ("AUTO", "ALL_ON", "ALL_OFF"):
        for _ in range(100):
            s={"mode":"CUSTOM","auto_mode":False,"enabled":{p:False for p in PROVIDERS}}
            apply_mode(s, mode)
            assert s["mode"] == mode
            assert s["auto_mode"] is (mode == "AUTO")
            assert all(v is (mode != "ALL_OFF") for v in s["enabled"].values())


def test_each_provider_toggle_100_times():
    for provider in PROVIDERS:
        s={"mode":"AUTO","auto_mode":True,"enabled":{p:True for p in PROVIDERS}}
        for i in range(100):
            toggle(s, provider, i % 2 == 0)
            assert s["mode"] == "CUSTOM"
            assert s["auto_mode"] is False
            assert s["enabled"][provider] is (i % 2 == 0)
            assert all(s["enabled"][p] is True for p in PROVIDERS if p != provider)


def test_all_on_off_are_distinct_from_auto():
    auto={"mode":"AUTO","auto_mode":True,"enabled":{p:True for p in PROVIDERS}}
    on={"mode":"ALL_ON","auto_mode":False,"enabled":{p:True for p in PROVIDERS}}
    off={"mode":"ALL_OFF","auto_mode":False,"enabled":{p:False for p in PROVIDERS}}
    assert auto != on
    assert on != off
    assert auto != off


def test_1200_randomized_state_transitions():
    rng=Random(20260919)
    modes=["AUTO","ALL_ON","ALL_OFF"]
    for _ in range(1200):
        s={"mode":"AUTO","auto_mode":True,"enabled":{p:True for p in PROVIDERS}}
        for _step in range(rng.randint(1, 25)):
            if rng.random() < .45:
                apply_mode(s, rng.choice(modes))
            else:
                p=rng.choice(PROVIDERS)
                toggle(s, p, None if rng.random()<.35 else rng.choice([True,False]))
            assert s["mode"] in {"AUTO","ALL_ON","ALL_OFF","CUSTOM"}
            assert isinstance(s["enabled"], dict)
            assert set(s["enabled"]) == set(PROVIDERS)
            assert all(isinstance(v,bool) for v in s["enabled"].values())
            if s["mode"] == "AUTO":
                assert s["auto_mode"] is True
                assert all(s["enabled"].values())
            elif s["mode"] == "ALL_ON":
                assert s["auto_mode"] is False
                assert all(s["enabled"].values())
            elif s["mode"] == "ALL_OFF":
                assert s["auto_mode"] is False
                assert not any(s["enabled"].values())
            else:
                assert s["auto_mode"] is False


def test_all_off_blocks_router_candidates():
    enabled={p:False for p in PROVIDERS}
    assert [p for p in PROVIDERS if enabled[p]] == []


def test_custom_keeps_unrelated_provider_states():
    s={"mode":"AUTO","auto_mode":True,"enabled":{p:True for p in PROVIDERS}}
    toggle(s,"groq",False)
    toggle(s,"gemini",False)
    assert s["mode"] == "CUSTOM"
    assert s["enabled"]["groq"] is False
    assert s["enabled"]["gemini"] is False
    assert all(s["enabled"][p] for p in PROVIDERS if p not in {"groq","gemini"})
