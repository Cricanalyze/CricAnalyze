import sys
sys.path.insert(0, "/app/backend")
import action_window
from analysis_routes import extract_frames


def test_short_clip_analysed_in_full():
    t0, t1, m = action_window.find("/app/backend/tests/media/bat2.mp4")
    assert (t0, m) == (0.0, "full_clip") and t1 > 6


def test_long_clip_window_finds_movement():
    t0, t1, m = action_window.find("/app/backend/tests/media/bat_long.mp4")
    assert m == "most_movement" and t0 <= 40.5 and t1 >= 45.5 and t1 - t0 <= 10.01


def test_frames_inside_span_keep_absolute_timestamps():
    fr = extract_frames("/app/backend/tests/media/bat_long.mp4", 10, (41.0, 43.4))
    assert len(fr) == 10 and all(41.0 <= f["t"] <= 43.4 for f in fr)
    assert sorted(f["t"] for f in fr) == [f["t"] for f in fr]
