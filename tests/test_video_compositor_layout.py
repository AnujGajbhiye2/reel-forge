from reelforge.video_compositor import VideoCompositor


def _make_config(inactive_mode="hidden"):
    return {
        "video": {
            "resolution": {"width": 1080, "height": 1920},
            "fps": 30,
            "duration": 60,
            "layout": {"top_reserved_px": 420},
            "characters": {
                "left_x_ratio": 0.08,
                "right_x_ratio": 0.60,
                "bottom_y_px": 460,
                "active_opacity": 1.0,
                "inactive_opacity": 0.05,
                "inactive_mode": inactive_mode,
            },
        },
        "assets": {
            "backgrounds": ["assets/backgrounds/subway_surfer.mp4"],
            "characters": ["assets/characters/character.png"],
            "fonts": {"main": "assets/fonts/Poppins/Poppins-ExtraBold.ttf"},
        },
        "captions": {
            "font_size": 80,
            "font_color": "white",
            "stroke_color": "black",
            "stroke_width": 3,
            "position": "center",
            "safe_zone": {"top_margin_px": 140, "bottom_margin_px": 320, "side_margin_px": 90},
        },
        "output": {"codec": "libx264", "audio_codec": "aac"},
    }


def test_compute_center_crop_box_portrait_is_near_full_frame():
    x1, y1, x2, y2 = VideoCompositor._compute_center_crop_box(1080, 1918, 1080, 1920)
    assert y1 == 0
    assert y2 == 1918
    assert x2 - x1 in (1078, 1079, 1080)


def test_compute_center_crop_box_landscape_crops_width():
    x1, y1, x2, y2 = VideoCompositor._compute_center_crop_box(1920, 1080, 1080, 1920)
    assert y1 == 0
    assert y2 == 1080
    assert (x2 - x1) == 607


def test_compute_fit_size_for_landscape_into_vertical():
    w, h = VideoCompositor._compute_fit_size(1920, 1080, 1080, 1920)
    assert w == 1080
    assert h == 607


def test_caption_y_clamp_respects_bounds():
    y = VideoCompositor._clamp_caption_y(requested_y=200, text_h=120, top_bound=420, bottom_bound=1600)
    assert y == 420

    y = VideoCompositor._clamp_caption_y(requested_y=2000, text_h=150, top_bound=420, bottom_bound=1600)
    assert y == 1450


class _FakeClip:
    def __init__(self, path=None, size=None, color=None):
        self.path = path
        self.size = size
        self.color = color
        self.opacity = None
        self.start = None
        self.duration = None
        self.position = None
        self.w = 640
        self.h = 360

    def with_start(self, value):
        self.start = value
        return self

    def with_duration(self, value):
        self.duration = value
        return self

    def resized(self, **_kwargs):
        return self

    def with_position(self, value):
        self.position = value
        return self

    def with_opacity(self, value):
        self.opacity = value
        return self

    def crossfadein(self, _value):
        return self

    def crossfadeout(self, _value):
        return self


def test_dialogue_hidden_mode_only_renders_active_speaker(monkeypatch):
    import reelforge.video_compositor as vc

    monkeypatch.setattr(vc, "ImageClip", _FakeClip)
    compositor = VideoCompositor(_make_config(inactive_mode="hidden"))
    timeline = [
        {"speaker": "A", "start": 0.0, "end": 1.0},
        {"speaker": "B", "start": 1.0, "end": 2.0},
    ]

    overlays = compositor._create_dialogue_character_clips("a.png", "b.png", timeline, duration=2.0)
    assert len(overlays) == 2
    assert all(c.opacity == 1.0 for c in overlays)


def test_dialogue_dim_mode_renders_both_speakers(monkeypatch):
    import reelforge.video_compositor as vc

    monkeypatch.setattr(vc, "ImageClip", _FakeClip)
    compositor = VideoCompositor(_make_config(inactive_mode="dim"))
    timeline = [{"speaker": "A", "start": 0.0, "end": 1.0}]

    overlays = compositor._create_dialogue_character_clips("a.png", "b.png", timeline, duration=1.0)
    assert len(overlays) == 2
    opacities = sorted(c.opacity for c in overlays)
    assert opacities == [0.05, 1.0]


def test_create_screenshot_clips_creates_card_layers(monkeypatch, tmp_path):
    import reelforge.video_compositor as vc

    monkeypatch.setattr(vc, "ImageClip", _FakeClip)
    monkeypatch.setattr(vc, "ColorClip", _FakeClip)

    image = tmp_path / "ss.png"
    image.write_bytes(b"fake")

    compositor = VideoCompositor(_make_config(inactive_mode="hidden"))
    screenshots = [
        {"status": "ok", "file": str(image), "start": 1.0, "end": 4.0},
    ]
    clips = compositor.create_screenshot_clips(screenshots, duration=10.0)

    assert len(clips) == 3
    assert all(c.start == 1.0 for c in clips)
    assert all(c.duration == 3.0 for c in clips)


def test_set_position_compat_prefers_with_position():
    compositor = VideoCompositor(_make_config())
    clip = _FakeClip()
    out = compositor._set_position(clip, ("center", 100))
    assert out is clip
    assert clip.position == ("center", 100)


def test_set_position_compat_falls_back_to_legacy():
    class _LegacyClip:
        def __init__(self):
            self.position = None

        def set_position(self, value):
            self.position = value
            return self

    compositor = VideoCompositor(_make_config())
    clip = _LegacyClip()
    out = compositor._set_position(clip, ("center", 120))
    assert out is clip
    assert clip.position == ("center", 120)
