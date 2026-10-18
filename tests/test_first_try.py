"""Shapes models actually return should parse on the first try, and equations never reach the screen as LaTeX."""
from agents.critic import _screen_texts
from agents.planner import PlanLLM
from core.mathtext import clean_tree, has_raw_latex, latex_to_unicode
from providers.openrouter import extract_json


def test_planner_accepts_object_beats_and_single_strings():
    # the shapes behind most failed first planning calls in the run logs
    plan = PlanLLM.model_validate({
        "goal": "Explain rainbows", "scene_count": 5, "research_required": True, "visual_strategy": "cards",
        "narrative_structure": [{"beat": "Hook", "duration": "3s", "description": "Grab attention."},
                                {"name": "Core idea"}],
        "success_criteria": "Clear and accurate",
        "manim_scenes": [{"title": "Refraction", "purpose": "show the angle"}],
        "research_questions": None,
    })
    assert plan.narrative_structure == ["Hook: Grab attention.", "Core idea"]
    assert plan.success_criteria == ["Clear and accurate"]
    assert plan.manim_scenes == ["Refraction: show the angle"]
    assert plan.research_questions == []


def test_extract_json_tolerates_trailing_commas_and_comments():
    raw = 'Sure!\n```json\n{\n  // the plan\n  "a": [1, 2,],\n  "b": {"c": "d",},\n}\n```'
    assert extract_json(raw) == {"a": [1, 2], "b": {"c": "d"}}


def test_latex_becomes_unicode_math():
    assert latex_to_unicode(r"\sin(2\beta - \phi) = n \sin \beta") == "sin(2β − φ) = n sin β"
    assert latex_to_unicode(r"\phi = 2\beta - \arcsin(n \sin \beta)") == "φ = 2β − arcsin(n sin β)"
    assert latex_to_unicode(r"$E = mc^2$") == "E = mc²"
    assert latex_to_unicode(r"\Delta G = \Delta H - T\Delta S") == "ΔG = ΔH − TΔS"
    assert latex_to_unicode(r"x^{2} + \frac{1}{2}x") == "x² + 1/2x"
    assert latex_to_unicode("2x + 3 = 11") == "2x + 3 = 11"
    for s in (r"\lim_{x \to 0} \frac{\sin x}{x} = 1", r"\sqrt{a^2+b^2}", r"\left(\alpha \cdot \beta\right)"):
        assert not has_raw_latex(latex_to_unicode(s)), s


def test_clean_tree_keeps_identifiers():
    tpl = clean_tree({"template": "equation_steps", "look": "chalk_1",
                      "steps": [r"\sin \theta = 0", "x_1 = 2"], "boxed": r"\theta = \pi"})
    assert tpl == {"template": "equation_steps", "look": "chalk_1", "steps": ["sin θ = 0", "x₁ = 2"],
                   "boxed": "θ = π"}


def test_qa_finds_raw_latex_on_screen():
    class Props:
        def __init__(self, text):
            self.text = text

        def model_dump(self):
            return {"scenes": [{"visualType": "manim", "params": {"src": "manim/a.mp4", "heading": self.text}}],
                    "captions": [{"text": "hello"}]}

    assert any(has_raw_latex(t) for t in _screen_texts(Props(r"\phi = 2\beta")))
    assert not any(has_raw_latex(t) for t in _screen_texts(Props("φ = 2β")))
