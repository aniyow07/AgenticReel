"""Template variety: AI shape mistakes are repaired, and a code pass rotates and adds Manim templates."""
from agents import storyboarder, template_catalog as tc
from rendering import manim_runner
from schemas.artifacts import Facts, Script, ScriptSegment


def test_bare_template_names_are_accepted():
    sc = storyboarder.SceneLLM.model_validate({
        "segment_ids": ["N01"], "visual_type": "manim", "manim_template": "mind_map",
        "visual_parameters": {"heading": "Graphs", "center": "Graph", "branches": [{"name": "Nodes"}, {"name": "Edges"}]}})
    assert sc.manim_template["template"] == "mind_map" and sc.manim_template["title"] == "Graphs"
    manim_runner.validate(sc.manim_template)
    sc = storyboarder.SceneLLM.model_validate({"segment_ids": ["N01"], "visual_type": "roadmap",
                                               "visual_parameters": {"stops": ["Learn", "Build"]}})
    assert sc.visual_type == "manim" and sc.manim_template == {"stops": ["Learn", "Build"], "template": "roadmap"}
    sc = storyboarder.SceneLLM.model_validate({"segment_ids": ["N01"], "visual_type": "timeline",
                                               "visual_parameters": {"heading": "H", "events": []}})
    assert sc.visual_type == "timeline"  # also a Remotion visual: left alone


def test_repair_fixes_shape_mistakes_seen_in_real_runs():
    fp = tc.repair({"template": "function_plot", "functions": [{"expr": "1 − exp(-x² / 365)"}], "mark_x": [1, 2, 3, 4, 5]})
    manim_runner.validate(fp)
    assert fp["mark_x"] == [1, 2, 3] and fp["functions"][0]["expr"] == "1 - exp(-x^2 / 365)"
    sp = tc.repair({"template": "spiral_timeline_3d", "events": [{"label": "Bridges", "detail": "x"}, {"label": "Euler"}]})
    assert sp["events"] == ["Bridges", "Euler"]
    car = tc.repair({"template": "carousel_3d", "items": [f"Tip {c}" for c in "abcdefgh"]})
    assert car["items"] == [f"Tip {c}" for c in "abcdef"]
    bad = {"template": "pie_chart", "labels": ["A", "B", "C"], "values": [1, 2]}
    assert tc.repair(bad) is bad  # mismatched data is not guessed at


def _video(make_ctx):
    ctx = make_ctx(mode="og")
    lines = ["We all put things off.", "The brain wants quick rewards.", "Stress makes delay worse.",
             "Small steps break the habit.", "Timers help you start.", "Start with two minutes today."]
    script = Script(title="Why we procrastinate", segments=[
        ScriptSegment(segment_id=f"N{i + 1:02d}", text=t) for i, t in enumerate(lines)])
    return ctx, script, [s.segment_id for s in script.segments]


def test_variety_pass_swaps_generic_and_adds_manim(make_ctx):
    ctx, script, ids = _video(make_ctx)
    sb = storyboarder.StoryboardLLM(scenes=[
        storyboarder.SceneLLM(segment_ids=ids[:1], visual_type="title", visual_parameters={"title": "T"}),
        storyboarder.SceneLLM(segment_ids=ids[1:2], visual_type="manim", manim_template={
            "template": "process_diagram", "title": "Steps", "steps": ["Start", "Delay", "Stress"]}),
        storyboarder.SceneLLM(segment_ids=ids[2:3], visual_type="process",
                              visual_parameters={"heading": "Fix", "steps": ["Start small", "Use a timer"]}),
        storyboarder.SceneLLM(segment_ids=ids[3:-1], visual_type="text_reveal", visual_parameters={"text": "x"}),
        storyboarder.SceneLLM(segment_ids=ids[-1:], visual_type="end_card", visual_parameters={"text": "Bye"}),
    ])
    sb, _ = storyboarder.sanitize(ctx, storyboarder.fix_coverage(sb, script), script, Facts())
    changes = storyboarder.diversify(ctx, sb, script, Facts(), {})
    used = [s.manim_template["template"] for s in sb.scenes if s.visual_type == "manim"]
    assert used[0] != "process_diagram" and len(used) >= 2 and len(set(used)) == len(used)
    assert sum(t in manim_runner.THREE_D for t in used) <= storyboarder.MAX_3D_SCENES and changes


def test_variety_pass_rotates_away_from_recent_templates(make_ctx):
    ctx, script, ids = _video(make_ctx)
    mk = lambda: storyboarder.StoryboardLLM(scenes=[  # noqa: E731
        storyboarder.SceneLLM(segment_ids=ids[:1], visual_type="title", visual_parameters={"title": "T"}),
        storyboarder.SceneLLM(segment_ids=ids[1:-1], visual_type="manim", manim_template={
            "template": "carousel_3d", "title": "Tips", "items": ["Plan", "Act", "Rest"]}),
        storyboarder.SceneLLM(segment_ids=ids[-1:], visual_type="end_card", visual_parameters={"text": "Bye"})])
    fresh = mk()
    storyboarder.diversify(ctx, fresh, script, Facts(), {})
    tired = mk()
    storyboarder.diversify(ctx, tired, script, Facts(), {"carousel_3d": 2.5})
    assert fresh.scenes[1].manim_template["template"] == "carousel_3d"
    assert tired.scenes[1].manim_template["template"] != "carousel_3d"
    assert tired.scenes[1].manim_template.get("items", tired.scenes[1].manim_template.get("faces")) or \
        tired.scenes[1].manim_template.get("branches") or tired.scenes[1].manim_template.get("words")


def test_templates_without_source_data_are_not_offered():
    skip = tc.unusable("", "")
    assert tc.NEEDS_NUMBERS <= skip and "quote_card" in skip
    assert not tc.unusable("Oceans cover 70 percent", 'he said "hello"')
    text = tc.catalog_text(1, skip)
    assert "stat_reveal" not in text and "bar_chart_3d" not in text and "roadmap" in text
    assert "stat_reveal" not in tc.suggest("a record 50 percent statistic", exclude=skip)


def test_fields_outside_manim_template_are_gathered():
    # real runs: the AI named the template and put its fields next to it, not inside it
    for scene in ({"manim_template": {"template": "array_algorithm", "title": "Partition"},
                   "visual_parameters": {"heading": "", "algorithm": "quick_sort", "values": [5, 2, 8]}},
                  {"manim_template": "array_algorithm", "algorithm": "quick_sort", "values": [5, 2, 8]},
                  {"manim_template": {"template": "array_algorithm", "params": {"algorithm": "quick_sort",
                                                                                 "values": [5, 2, 8]}}}):
        sc = storyboarder.SceneLLM.model_validate({"segment_ids": ["N01"], "visual_type": "manim", **scene})
        assert sc.manim_template["algorithm"] == "quick_sort", scene
        manim_runner.validate(sc.manim_template)


def _sorting_video(make_ctx):
    ctx = make_ctx(mode="og", topic="Explain quick sort")
    lines = ["How does a computer sort a list so fast?", "Quick sort picks one element as the pivot.",
             "Smaller values move left and larger values move right.", "This partition puts the pivot in place.",
             "Then the same steps run on both halves.", "Soon every value is in order.", "That is quick sort."]
    script = Script(title="Quick Sort", segments=[ScriptSegment(segment_id=f"N{i + 1:02d}", text=t)
                                                  for i, t in enumerate(lines)])
    return ctx, script


def _sb(*middle):
    return storyboarder.StoryboardLLM(scenes=[
        storyboarder.SceneLLM(segment_ids=["N01"], visual_type="title", visual_parameters={"title": "T"}),
        *middle,
        storyboarder.SceneLLM(segment_ids=["N07"], visual_type="end_card", visual_parameters={"text": "Bye"})])


def test_a_bare_topic_animation_is_rebuilt_not_dropped(make_ctx):
    ctx, script = _sorting_video(make_ctx)
    sb = _sb(storyboarder.SceneLLM(segment_ids=["N02", "N03"], visual_type="manim",
                                   manim_template={"template": "array_algorithm", "title": "Partitioning"}),
             storyboarder.SceneLLM(segment_ids=["N04", "N05", "N06"], visual_type="text_reveal",
                                   visual_parameters={"text": "x"}))
    sb, notes = storyboarder.sanitize(ctx, storyboarder.fix_coverage(sb, script), script, Facts())
    mt = sb.scenes[1].manim_template
    assert sb.scenes[1].visual_type == "manim" and mt["algorithm"] == "quick_sort"
    assert mt["title"].lower().startswith("example") and any("rebuilt" in n for n in notes)


def test_variety_pass_adds_the_topic_animation_and_keeps_it(make_ctx):
    ctx, script = _sorting_video(make_ctx)
    sb = _sb(storyboarder.SceneLLM(segment_ids=["N02", "N03"], visual_type="text_reveal",
                                   visual_parameters={"text": "x"}),
             storyboarder.SceneLLM(segment_ids=["N04", "N05", "N06"], visual_type="manim", manim_template={
                 "template": "process_diagram", "title": "Steps", "steps": ["Pick a pivot", "Partition", "Repeat"]}))
    sb, _ = storyboarder.sanitize(ctx, storyboarder.fix_coverage(sb, script), script, Facts())
    # even when the user's last videos used the sorting animation a lot, it is not swapped for a general one
    storyboarder.diversify(ctx, sb, script, Facts(), {"array_algorithm": 3.0})
    used = [s.manim_template["template"] for s in sb.scenes if s.visual_type == "manim"]
    assert "array_algorithm" in used and "process_diagram" not in used
    assert sum(s.visual_type == "text_reveal" for s in sb.scenes) == 0


def test_builders_never_guess_claims_or_mislabel_topics():
    lines = ["Prices rose and people went hungry.", "The nobles paid almost no taxes."]
    for name in ("pros_cons", "myth_fact", "quote_card", "ranking", "simple_chart", "stat_reveal", "decision_tree"):
        assert tc.build(name, "Causes", tc.phrases(lines), "the french revolution", lines) is None
    assert tc.build("array_algorithm", "", [], "explain merge sort") is None  # no merge sort animation
    assert tc.build("array_algorithm", "", [], "explain the dp subsequence algorithm") is None
    assert tc.build("node_graph", "", [], "how the tcp handshake works over a connection") is None
    assert tc.build("orbit_3d", "", [], "how vaccines train cells") is None
    eq = tc.build("equation_steps", "", [], "solve for x", ["Start with 2x + 3 = 11, so 2x = 8.", "Then x = 4."])
    assert eq and eq["lines"] == ["2x + 3 = 11", "2x = 8", "x = 4"]


def test_short_keywords_match_whole_words_only():
    assert "galaxy_3d" not in tc.fits("the process starts by choosing a pivot")
    assert "array_algorithm" in tc.fits("sorting a list with quick sort")
    assert tc.suggest("explain quick sort, the sorting algorithm")[0] == "array_algorithm"


def test_numbers_said_in_the_narration_unhide_number_templates():
    assert tc.NEEDS_NUMBERS <= tc.unusable("", "", "no digits here")
    assert not tc.NEEDS_NUMBERS & tc.unusable("", "", "with legs 3 and 4 we get 9 + 16 = 25")
