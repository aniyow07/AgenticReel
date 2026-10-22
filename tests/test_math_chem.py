"""Equation and chemical-reaction Manim templates: parameter checks and the worked-math rule."""
import pytest

from agents.scriptwriter import MATH_WORK
from rendering import manim_runner


def test_equation_params_validate():
    m = manim_runner.validate({"template": "equation_steps", "lines": ["2x + 3 = 11", " ", "x = 4"],
                               "notes": ["subtract 3 then divide by 2"]})
    assert m.lines == ["2x + 3 = 11", "x = 4"]
    with pytest.raises(Exception):
        manim_runner.validate({"template": "equation_steps", "lines": ["x = 4"]})
    with pytest.raises(Exception):
        manim_runner.validate({"template": "equation_steps", "lines": ["x" * 60, "x = 1"]})


def test_reaction_params_only_accept_formulas():
    m = manim_runner.validate({"template": "chemical_reaction", "reactants": ["2H2", "O2"], "products": ["2H2O"],
                               "condition": "spark"})
    assert m.products == ["2H2O"]
    with pytest.raises(Exception):
        manim_runner.validate({"template": "chemical_reaction", "reactants": ["import os; os.system('x')"],
                               "products": ["H2O"]})


def test_cs_ai_security_params():
    m = manim_runner.validate({"template": "array_algorithm", "algorithm": "binary_search", "values": [1, 3, 5],
                               "target": 3})
    assert m.target == 3
    with pytest.raises(Exception):  # a search without a target
        manim_runner.validate({"template": "array_algorithm", "algorithm": "linear_search", "values": [1, 2, 3]})
    with pytest.raises(Exception):  # unknown algorithm
        manim_runner.validate({"template": "array_algorithm", "algorithm": "quantum_sort", "values": [1, 2, 3]})
    manim_runner.validate({"template": "agent_loop", "steps": ["Plan", "Act", "Observe"], "tools": ["Search"]})
    m = manim_runner.validate({"template": "security_flow", "attack": "Phishing", "defense": "MFA"})
    assert m.outcome == "blocked"


@pytest.mark.parametrize("expr,ok", [
    ("x^2 - 4", True), ("2*sin(x) + e", True), ("sqrt(abs(x))/pi", True),
    ("__import__('os').system('x')", False), ("x.real", False), ("open('f')", False), ("[x for x in ()]", False),
    ("lambda: 1", False), ("sin(x, 2)", False),
])
def test_function_plot_only_accepts_plain_math(expr, ok):
    params = {"template": "function_plot", "functions": [{"expr": expr}]}
    if ok:
        manim_runner.validate(params)
    else:
        with pytest.raises(Exception):
            manim_runner.validate(params)


def test_chart_and_graph_params():
    with pytest.raises(Exception):  # a series without one value per label
        manim_runner.validate({"template": "line_chart", "labels": ["a", "b", "c"], "series": [{"values": [1, 2]}]})
    manim_runner.validate({"template": "pie_chart", "labels": ["a", "b"], "values": [60, 40], "unit": "%"})
    manim_runner.validate({"template": "node_graph", "nodes": ["A", "B", "C"], "edges": [["A", "B"], ["B", "C"]],
                           "path": ["A", "B", "C"]})


def test_layout_templates_and_looks():
    manim_runner.validate({"template": "cycle_diagram", "stages": ["a", "b", "c"], "look": "glass"})
    manim_runner.validate({"template": "venn_diagram", "sets": [{"name": "A"}, {"name": "B"}], "shared": ["x"]})
    manim_runner.validate({"template": "pyramid", "levels": ["top", "base"]})
    manim_runner.validate({"template": "mind_map", "center": "ML", "branches": [{"name": "a"}, {"name": "b"}]})
    with pytest.raises(Exception):  # a cycle needs at least three stages
        manim_runner.validate({"template": "cycle_diagram", "stages": ["a", "b"]})
    with pytest.raises(Exception):  # unknown look
        manim_runner.validate({"template": "pyramid", "levels": ["a", "b"], "look": "comic-sans"})


def test_sort_steps_really_sort():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("array_algorithm", Path(manim_runner.TEMPLATE_DIR) / "array_algorithm.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for algo in ("bubble_sort", "selection_sort", "insertion_sort", "quick_sort"):
        a = [5, 2, 8, 1, 4]
        for ev in mod.sort_steps(algo, a):
            if ev[0] == "swap":
                a[ev[1]], a[ev[2]] = a[ev[2]], a[ev[1]]
        assert a == [1, 2, 4, 5, 8], algo
    assert mod.search_steps("binary_search", [2, 5, 8, 13], 13)[-1] == ("found", 3)
    assert mod.search_steps("linear_search", [2, 5], 9)[-1] == ("missing",)


@pytest.mark.parametrize("text,math", [
    ("2x + 3 = 11, so 2x = 8.", True),
    ("Then x equals 4.", True),
    ("Revenue grew three times to 50 percent.", False),
    ("Founded in 1998 with 12 people.", False),
])
def test_worked_math_is_recognised(text, math):
    assert bool(MATH_WORK.search(text)) is math


def test_3d_templates_validate():
    m = manim_runner.validate({"template": "orbit_3d", "kind": "atom", "orbiters": [" e1 ", "", "e2"]})
    assert m.orbiters == ["e1", "e2"]
    manim_runner.validate({"template": "surface_3d", "surface": "saddle"})
    manim_runner.validate({"template": "bar_chart_3d", "labels": ["a", "b", "c"], "values": [1, 2, 3]})
    with pytest.raises(Exception):
        manim_runner.validate({"template": "surface_3d", "surface": "__import__('os')"})
    with pytest.raises(Exception):
        manim_runner.validate({"template": "bar_chart_3d", "labels": ["a", "b"], "values": [1]})


def test_title_backdrop_follows_the_video():
    from agents.editor import assign_backdrops
    scenes = [{"visualType": "title", "backdrop": "rays"}, {"visualType": "text_reveal", "backdrop": "matrix"},
              {"visualType": "manim", "backdrop": "circuit"}, {"visualType": "chart", "backdrop": "matrix"},
              {"visualType": "manim", "backdrop": "circuit"}]
    assign_backdrops(scenes, 1, "t")
    assert scenes[0]["backdrop"] == "circuit"  # most used, and not the same as the next scene


def test_new_3d_templates_take_only_named_choices():
    ok = [{"template": "dna_helix_3d", "caption": "Base pairs"},
          {"template": "molecule_3d", "molecule": "benzene"},
          {"template": "globe_3d", "hubs": ["London", "Tokyo"]},
          {"template": "vector_field_3d", "field": "dipole"},
          {"template": "crystal_lattice_3d", "lattice": "salt"},
          {"template": "neural_net_3d", "layers": ["Input", "Hidden", "Output"]},
          {"template": "layer_stack_3d", "layers": ["App", "OS", "Hardware"]},
          {"template": "planet_layers_3d", "layers": ["Core", "Mantle", "Crust"]},
          {"template": "wave_3d", "kind": "electromagnetic"},
          {"template": "solids_3d", "shapes": ["cube", "torus"]},
          {"template": "galaxy_3d", "arms": 3}]
    for params in ok:
        manim_runner.validate(params)
    assert len(manim_runner.THREE_D) >= 14
    for bad in [{"template": "molecule_3d", "molecule": "__import__('os')"},
                {"template": "solids_3d", "shapes": ["cube", "x**2"]},
                {"template": "galaxy_3d", "arms": 40},
                {"template": "globe_3d", "hubs": ["only one"]},
                {"template": "wave_3d", "kind": "sin(x)"}]:
        with pytest.raises(Exception):
            manim_runner.validate(bad)
