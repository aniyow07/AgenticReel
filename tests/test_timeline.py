from rendering.timeline import (build_captions, captions_to_frames, layout_segments, parse_srt, scene_frames,
                                to_srt)
from schemas.artifacts import SegmentAudio


def segs():
    return [
        SegmentAudio(segment_id="N01", path="a.wav", duration_s=2.0, provider="edge",
                     word_timings=[("Hello", 0.1, 0.4), ("there", 0.45, 0.8), ("friend", 0.9, 1.5)]),
        SegmentAudio(segment_id="N02", path="b.wav", duration_s=3.0, provider="sapi"),
    ]


TEXTS = {"N01": "Hello there, friend.", "N02": "This chunk has no word timings at all here."}


def test_layout_uses_measured_durations():
    lay = layout_segments(segs(), gap_s=0.1, tail_s=0.5)
    assert [(p.start, p.end) for p in lay.placements] == [(0.0, 2.0), (2.1, 5.1)]
    assert abs(lay.total_s - 5.6) < 1e-9


def test_captions_use_word_timings_and_segment_offsets():
    lay = layout_segments(segs(), gap_s=0.1)
    caps = build_captions(TEXTS, segs(), lay, max_words=4)
    first = caps[0]
    assert first.alignment == "tts_word_boundaries" and first.start == 0.1
    later = [c for c in caps if c.segment_id == "N02"]
    assert later[0].alignment == "proportional_within_measured_segment"
    assert later[0].start >= 2.1 and later[-1].end <= 5.1 + 1e-6  # stays inside its own measured chunk
    # captions never overlap and reproduce the narration text exactly
    assert all(a.end <= b.start for a, b in zip(caps, caps[1:]))
    assert " ".join(c.text for c in caps) == " ".join(TEXTS.values())


def test_no_single_word_captions():
    lay = layout_segments(segs())
    caps = build_captions(TEXTS, segs(), lay, max_words=3)
    assert all(len(c.text.split()) >= 2 for c in caps)


def test_not_even_split_of_total_duration():
    # Unequal chunk durations must produce unequal caption spans, unlike an even split.
    a = SegmentAudio(segment_id="A", path="a", duration_s=1.0, provider="sapi")
    b = SegmentAudio(segment_id="B", path="b", duration_s=6.0, provider="sapi")
    lay = layout_segments([a, b], gap_s=0)
    caps = build_captions({"A": "one two", "B": "three four"}, [a, b], lay, max_words=4)
    spans = [c.end - c.start for c in caps]
    assert spans[1] > spans[0] * 3


def test_frames_are_valid_and_clipped():
    lay = layout_segments(segs())
    caps = build_captions(TEXTS, segs(), lay)
    total = round(lay.total_s * 30)
    fr = captions_to_frames(caps, 30, total)
    assert all(0 <= c["startFrame"] < c["endFrame"] <= total for c in fr)
    assert all(a["endFrame"] <= b["startFrame"] for a, b in zip(fr, fr[1:]))


def test_scene_frames_tile_exactly():
    lay = layout_segments(segs(), gap_s=0.12)
    ranges = scene_frames([["N01"], ["N02"]], lay, 30)
    assert ranges[0][0] == 0
    assert ranges[0][0] + ranges[0][1] == ranges[1][0]
    assert ranges[1][0] + ranges[1][1] == round(lay.total_s * 30)


def test_srt_roundtrip():
    lay = layout_segments(segs())
    caps = build_captions(TEXTS, segs(), lay)
    srt = to_srt(caps)
    assert srt.startswith("1\n00:00:00,100 --> ")
    parsed = parse_srt(srt)
    assert len(parsed) == len(caps) and parsed[0][2] == caps[0].text
