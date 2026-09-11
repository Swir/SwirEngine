import pytest

from swirengine import AnimatedSprite2D, AnimationClip, SpriteSheet


def test_sprite_sheet_generates_top_row_uvs():
    sheet = SpriteSheet(columns=4, rows=2)
    assert sheet.frame(0, 0) == (0.0, 0.5, 0.25, 1.0)
    assert sheet.frame(3, 1) == (0.75, 0.0, 1.0, 0.5)
    assert len(sheet.row(1)) == 4


def test_sprite_sheet_validates_ranges():
    with pytest.raises(ValueError):
        SpriteSheet(0, 2)
    sheet = SpriteSheet(2, 2)
    with pytest.raises(IndexError):
        sheet.frame(2, 0)


def test_animation_clip_requires_frames_and_positive_fps():
    with pytest.raises(ValueError):
        AnimationClip(())
    with pytest.raises(ValueError):
        AnimationClip(((0.0, 0.0, 1.0, 1.0),), fps=0)


def test_animated_sprite_advances_and_loops():
    sheet = SpriteSheet(3, 1)
    sprite = AnimatedSprite2D("hero.png")
    sprite.add_animation("walk", sheet.row(0), fps=10)

    assert sprite.playing
    assert sprite.frame_index == 0
    sprite.update(0.11)
    assert sprite.frame_index == 1
    sprite.update(0.2)
    assert sprite.frame_index == 0


def test_non_looping_animation_stops_on_last_frame():
    sheet = SpriteSheet(2, 1)
    sprite = AnimatedSprite2D("hero.png")
    sprite.add_animation("hit", sheet.row(0), fps=10, loop=False)
    sprite.update(1.0)

    assert sprite.frame_index == 1
    assert not sprite.playing
