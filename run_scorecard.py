"""
Scorecard self-test  —  runs with ZERO dependencies (no pydantic, no network).

Proves the core (DoD item #1): the scorecard produces ~1.0 for a compliant draft and
a low score for a degraded one. Uses SimpleNamespace stand-ins that match the
contracts schema, since the scorecard is duck-typed.

Run: python run_scorecard.py
"""

from types import SimpleNamespace
from eval.scorecard import score_output

BRAND = SimpleNamespace(
    niche="skincare", required_cta="Follow for more", required_hashtag="#glowroutine",
    banned_words=["miracle", "cure", "guaranteed"], voice_note="warm",
)
TREND = SimpleNamespace(
    id="t1", platform="instagram", trend_label="POV: my 5am morning routine",
    trend_keyword="POV", source="apify:snapshot",
)

# A compliant draft (should score 1.0)
GOOD = SimpleNamespace(
    hook="POV: your 5am glow-up starts here",
    caption="Follow for more easy steps to glowing skin every morning. #glowroutine",
    hashtags=["#glowroutine", "#skincare", "#morningroutine"],
)

# A degraded draft: too long, no CTA, no keyword, bad hashtags, a banned word (still valid JSON)
DEGRADED = SimpleNamespace(
    hook="This absolutely incredible jaw-dropping morning skincare secret will change your entire life forever",
    caption="Our miracle serum is guaranteed to transform your skin overnight in ways you never imagined possible, trust us!!!",
    hashtags=["skincare"],
)

# A parse failure (worker returned junk -> None)
INVALID = None


def main():
    for label, draft in [("GOOD", GOOD), ("DEGRADED", DEGRADED), ("INVALID", INVALID)]:
        score, checks = score_output(draft, BRAND, TREND)
        print(f"\n{label}: score = {score:.2f}")
        for name, ok in checks.items():
            print(f"   {'PASS' if ok else 'FAIL'}  {name}")

    assert score_output(GOOD, BRAND, TREND)[0] == 1.0, "healthy draft should be 1.0"
    assert score_output(DEGRADED, BRAND, TREND)[0] < 0.5, "degraded draft should be low"
    assert score_output(None, BRAND, TREND)[0] == 0.0, "parse failure should be 0.0"
    print("\nAll core assertions passed. Scorecard is the source of truth.")


if __name__ == "__main__":
    main()
