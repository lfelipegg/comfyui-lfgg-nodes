import pytest

from lfgg_nodes.load_and_crop_image import resolve_crop


def test_initializes_the_largest_centered_exact_ratio_crop():
    assert resolve_crop(
        source_width=1920,
        source_height=1080,
        ratio_width=4,
        ratio_height=5,
        crop_x=0,
        crop_y=0,
        crop_width=0,
        crop_height=0,
        max_resolution=16_384,
    ) == (528, 0, 864, 1080, 4, 5)


def test_reduces_ratio_components_before_fitting():
    assert resolve_crop(
        source_width=1920,
        source_height=1080,
        ratio_width=1920,
        ratio_height=1080,
        crop_x=160,
        crop_y=90,
        crop_width=1600,
        crop_height=900,
        max_resolution=16_384,
    ) == (160, 90, 1600, 900, 16, 9)


def test_changed_ratio_resets_instead_of_reusing_stale_geometry():
    assert resolve_crop(
        source_width=1920,
        source_height=1080,
        ratio_width=4,
        ratio_height=3,
        crop_x=160,
        crop_y=90,
        crop_width=1600,
        crop_height=900,
        max_resolution=16_384,
    ) == (240, 0, 1440, 1080, 4, 3)


def test_matching_ratio_rejects_out_of_bounds_geometry():
    with pytest.raises(ValueError, match="inside the source image"):
        resolve_crop(
            source_width=100,
            source_height=100,
            ratio_width=1,
            ratio_height=1,
            crop_x=50,
            crop_y=50,
            crop_width=60,
            crop_height=60,
            max_resolution=16_384,
        )


def test_centers_odd_remaining_pixels_by_rounding_down():
    assert resolve_crop(
        source_width=101,
        source_height=100,
        ratio_width=3,
        ratio_height=2,
        crop_x=0,
        crop_y=0,
        crop_width=0,
        crop_height=0,
        max_resolution=16_384,
    ) == (1, 17, 99, 66, 3, 2)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"source_width": 0}, "source_width"),
        ({"ratio_width": 0}, "ratio_width"),
        ({"ratio_width": True}, "ratio_width"),
        ({"crop_x": -1}, "crop_x"),
        ({"crop_y": 1.5}, "crop_y"),
        ({"source_height": 16_385}, "source_height"),
        ({"crop_width": 0, "crop_height": 1}, "crop dimensions"),
        ({"ratio_width": 101, "ratio_height": 1}, "does not fit"),
    ],
)
def test_rejects_invalid_or_impossible_geometry(arguments, message):
    values = {
        "source_width": 100,
        "source_height": 100,
        "ratio_width": 1,
        "ratio_height": 1,
        "crop_x": 0,
        "crop_y": 0,
        "crop_width": 100,
        "crop_height": 100,
        "max_resolution": 16_384,
    }
    values.update(arguments)

    with pytest.raises(ValueError, match=message):
        resolve_crop(**values)
