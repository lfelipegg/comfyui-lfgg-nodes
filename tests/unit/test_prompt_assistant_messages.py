import base64
import io

import numpy
import pytest
import torch
from PIL import Image

import lfgg_nodes.prompt_assistant as prompt_assistant
from lfgg_nodes.prompt_assistant import (
    PromptAssistantError,
    build_messages,
    build_request_body,
    collect_frames,
    encode_frame,
    encode_images,
)


def decode(part):
    header, payload = part["image_url"]["url"].split(",", 1)
    return header, Image.open(io.BytesIO(base64.b64decode(payload)))


def test_encodes_one_three_and_four_channel_frames_with_real_tensors():
    gray = torch.rand(1, 20, 30, 1)
    rgb = torch.rand(2, 16, 24, 3, dtype=torch.float16)
    rgba = torch.rand(1, 12, 10, 4)
    originals = [gray.clone(), rgb.clone(), rgba.clone()]

    encoded = encode_images([gray, rgb, None, rgba])

    assert [(image.media_type, image.width, image.height) for image in encoded] == [
        ("image/jpeg", 30, 20),
        ("image/jpeg", 24, 16),
        ("image/jpeg", 24, 16),
        ("image/png", 10, 12),
    ]
    with Image.open(io.BytesIO(encoded[0].data)) as decoded:
        assert decoded.mode == "L"
    with Image.open(io.BytesIO(encoded[3].data)) as decoded:
        assert decoded.mode == "RGBA"
        expected = (rgba[0].clamp(0, 1) * 255).round().to(torch.uint8).numpy()
        assert numpy.array_equal(numpy.asarray(decoded), expected)
    for tensor, original in zip((gray, rgb, rgba), originals):
        assert torch.equal(tensor, original)
        assert tensor.device.type == "cpu"
        assert tensor.dtype == original.dtype


def test_downscales_long_side_with_lanczos_geometry():
    wide = torch.zeros(1, 1024, 2048, 3)
    tall = torch.zeros(1, 3000, 999, 3)
    small = torch.zeros(1, 1024, 1024, 3)

    assert (encode_frame(wide[0]).width, encode_frame(wide[0]).height) == (1024, 512)
    assert (encode_frame(tall[0]).width, encode_frame(tall[0]).height) == (341, 1024)
    assert (encode_frame(small[0]).width, encode_frame(small[0]).height) == (1024, 1024)


def test_rejects_too_many_frames_before_encoding(monkeypatch):
    calls = []
    monkeypatch.setattr(
        prompt_assistant, "encode_frame", lambda frame: calls.append(frame)
    )
    with pytest.raises(PromptAssistantError, match="9 images are connected"):
        encode_images([torch.zeros(5, 2, 2, 3), None, torch.zeros(4, 2, 2, 3), None])
    assert calls == []

    assert len(collect_frames([torch.zeros(4, 2, 2, 3), torch.zeros(4, 2, 2, 1)])) == 8
    assert collect_frames([None, None, None, None]) == []


@pytest.mark.parametrize(
    ("image", "message"),
    [
        (torch.zeros(2, 2, 3), "shaped \\[B,H,W,C\\]"),
        (torch.zeros(1, 2, 2, 2), "shaped \\[B,H,W,C\\]"),
        (torch.zeros(1, 2, 2, 3, dtype=torch.uint8), "float dtype"),
        (torch.zeros(1, 0, 2, 3), "at least one pixel"),
        ("text", "shaped \\[B,H,W,C\\]"),
    ],
)
def test_rejects_invalid_image_tensors(image, message):
    with pytest.raises(PromptAssistantError, match=message) as caught:
        collect_frames([None, image])
    assert "image_2" in str(caught.value)


def test_rejects_frames_over_the_pixel_limit(monkeypatch):
    monkeypatch.setattr(prompt_assistant, "IMAGE_PIXEL_LIMIT", 15)
    with pytest.raises(PromptAssistantError, match="must contain at most 15"):
        collect_frames([torch.zeros(1, 4, 4, 3)])


def test_message_assembly_orders_captions_and_omits_empty_system():
    encoded = encode_images([torch.rand(2, 4, 4, 3)])

    messages = build_messages("Sys", "  Write it  ", encoded)
    assert messages[0] == {"role": "system", "content": "Sys"}
    user = messages[1]["content"]
    assert [part["type"] for part in user] == [
        "text", "image_url", "text", "image_url", "text",
    ]
    assert user[0]["text"] == "Image 1 of 2"
    assert user[2]["text"] == "Image 2 of 2"
    assert user[4]["text"] == "Write it"
    header, decoded = decode(user[1])
    assert header == "data:image/jpeg;base64"
    assert decoded.size == (4, 4)

    only_images = build_messages(None, "", encoded)
    assert [message["role"] for message in only_images] == ["user"]
    assert [part["type"] for part in only_images[0]["content"]] == [
        "text", "image_url", "text", "image_url",
    ]

    text_only = build_messages(None, "Write", [])
    assert text_only == [
        {"role": "user", "content": [{"type": "text", "text": "Write"}]}
    ]

    with pytest.raises(PromptAssistantError, match="request is empty and no image"):
        build_messages("Sys", " \n", [])
    with pytest.raises(PromptAssistantError, match="request must be a string"):
        build_messages("Sys", 3, [])
    with pytest.raises(PromptAssistantError, match="request exceeds the 1 MiB"):
        build_messages("Sys", "x" * (1024 * 1024 + 1), [])


def test_request_body_validates_sampling_and_masks_the_seed():
    messages = [{"role": "user", "content": []}]
    body = build_request_body(messages, "server default", 2**64 - 1, 0.7, 1024)
    assert body == {
        "messages": messages,
        "stream": True,
        "seed": 2**32 - 1,
        "temperature": 0.7,
        "max_tokens": 1024,
    }
    assert build_request_body(messages, " my-model ", 0, 0, 1)["model"] == "my-model"

    for seed in (-1, 2**64, 1.5, True):
        with pytest.raises(PromptAssistantError, match="seed"):
            build_request_body(messages, "m", seed, 0.7, 10)
    for temperature in (-0.1, 2.1, "1", True):
        with pytest.raises(PromptAssistantError, match="temperature"):
            build_request_body(messages, "m", 1, temperature, 10)
    for max_tokens in (0, 32769, 1.0, True):
        with pytest.raises(PromptAssistantError, match="max_tokens"):
            build_request_body(messages, "m", 1, 0.7, max_tokens)
    with pytest.raises(PromptAssistantError, match="model must be"):
        build_request_body(messages, "", 1, 0.7, 10)
