import pytest

from agents import planner, scriptwriter, storyboarder
from agents.storyboarder import check_general_text
from rendering import manim_runner
from retrieval.index import tokenize
from schemas.artifacts import Facts

OK = [
    {"template": "before_after", "mode": "before_after", "left_points": ["Slow"], "right_points": ["Fast"]},
    {"template": "domino_chain", "links": ["Less rain", "Dry soil"], "effect": "Crop failure"},
    {"template": "stat_reveal", "value": 71, "suffix": "%", "label": "of Earth is water", "style": "ring"},
    {"template": "quote_card", "quote": "Stay hungry, stay foolish.", "author": "Steve Jobs", "highlight": "hungry"},
    {"template": "pros_cons", "pros": ["Cheap"], "cons": ["Slow", "Loud"], "verdict": "cons"},
    {"template": "ranking", "items": ["A", "B", "C"], "values": [3, 1, 2]},
    {"template": "ranking", "items": ["A", "B"]},
    {"template": "funnel", "stages": ["Visitors", "Buyers"], "values": [100, 5]},
    {"template": "myth_fact", "pairs": [{"myth": "Bats are blind", "fact": "Bats can see"}]},
    {"template": "spotlight", "words": ["Wages", "Oil", "Demand"], "focus": "oil"},
    {"template": "roadmap", "stops": ["Learn", "Build"], "goal": "Job"},
    {"template": "decision_tree", "question": "Rent or buy?", "options": [{"choice": "Rent"}, {"choice": "Buy"}],
     "picked": 1},
    {"template": "carousel_3d", "items": ["a", "b", "c"]},
    {"template": "podium_3d", "places": ["Gold", "Silver", "Bronze"]},
    {"template": "cube_faces_3d", "faces": ["People", "Planet"]},
    {"template": "spiral_timeline_3d", "events": ["Start", "Middle", "End"]},
]


def test_general_templates_validate_and_are_registered():
    for params in OK:
        manim_runner.validate(params)
    assert manim_runner.GENERAL <= set(manim_runner.TEMPLATES)
    assert {"carousel_3d", "podium_3d", "cube_faces_3d", "spiral_timeline_3d"} <= manim_runner.THREE_D
    for name, (file, _, _) in manim_runner.TEMPLATES.items():
        assert (manim_runner.TEMPLATE_DIR / file).exists(), name


@pytest.mark.parametrize("bad", [
    {"template": "domino_chain", "links": ["only one"]},
    {"template": "stat_reveal", "value": -5},
    {"template": "stat_reveal", "value": 5, "style": "__import__('os')"},
    {"template": "pros_cons", "pros": ["a"], "cons": []},
    {"template": "ranking", "items": ["A", "B"], "values": [1]},
    {"template": "funnel", "stages": ["a", "b"], "values": [1, float("nan")]},
    {"template": "spotlight", "words": ["a", "b", "c"], "focus": "z"},
    {"template": "decision_tree", "question": "q", "options": [{"choice": "a"}, {"choice": "b"}], "picked": 2},
    {"template": "podium_3d", "places": ["a", "b", "c", "d"]},
    {"template": "before_after"},
])
def test_general_templates_reject_bad_params(bad):
    with pytest.raises(Exception):
        manim_runner.validate(bad)


def test_quote_highlight_must_be_in_the_quote():
    m = manim_runner.validate({"template": "quote_card", "quote": "Knowledge is power.", "highlight": "money"})
    assert m.highlight == ""


def _g(src: str) -> dict:
    return {"text": src.lower(), "tokens": set(tokenize(src)), "numbers": src.replace(",", "")}


def test_general_text_needs_source_numbers_and_quotes():
    g = _g("The Moon landing happened in 1969. Armstrong said: one small step for man, one giant leap.")
    check_general_text({"template": "spiral_timeline_3d", "events": ["Moon landing 1969"]}, g, "")
    with pytest.raises(ValueError):
        check_general_text({"template": "spiral_timeline_3d", "events": ["Moon landing 1972"]}, g, "")
    check_general_text({"template": "quote_card", "quote": "One small step for man, one giant leap",
                        "author": "Armstrong"}, g, "")
    with pytest.raises(ValueError):
        check_general_text({"template": "quote_card", "quote": "Houston we have a problem"}, g, "")
    with pytest.raises(ValueError):
        check_general_text({"template": "quote_card", "quote": "One small step for man", "author": "Aldrin"}, g, "")


def test_numbers_in_general_templates_must_be_supported(make_ctx):
    ctx = make_ctx(mode="og")
    plan = planner.run(ctx)
    facts = Facts()
    script = scriptwriter.run(ctx, plan, facts)
    ids = [s.segment_id for s in script.segments]
    sb = storyboarder.StoryboardLLM(scenes=[
        storyboarder.SceneLLM(segment_ids=ids[:1], visual_type="manim",
                              manim_template={"template": "stat_reveal", "value": 4242, "label": "x"}),
        storyboarder.SceneLLM(segment_ids=ids[1:], visual_type="manim",
                              manim_template={"template": "ranking", "items": ["A", "B"], "values": [77, 88]})])
    fixed, notes = storyboarder.sanitize(ctx, storyboarder.fix_coverage(sb, script), script, facts)
    assert "manim" not in [s.visual_type for s in fixed.scenes]
    assert len(notes) == 2


def test_remotion_fallbacks_fit_remotion_params():
    from schemas.render_props import PARAM_MODELS
    for params in OK:
        alt = manim_runner.remotion_fallback(manim_runner.validate(params).model_dump())
        if alt:
            PARAM_MODELS[alt[0]].model_validate(alt[1])
