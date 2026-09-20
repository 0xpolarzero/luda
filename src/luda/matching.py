"""Bounded historical screenshot matching, with no filesystem image input."""

import io
import math
import struct
import json
from pathlib import Path
from PIL import Image
from .common import DesktopError, run


def match(source, target, bounds, threshold, limit):
    if (
        type(threshold) not in (int, float)
        or not math.isfinite(threshold)
        or not 0 <= threshold <= 1
        or type(limit) is not int
        or not 1 <= limit <= 100
    ):
        raise DesktopError(
            "INVALID_ARGUMENT",
            "threshold must be finite from 0 to 1; limit must be an integer from 1 to 100.",
        )
    if (
        not isinstance(bounds, dict)
        or set(bounds) != {"x", "y", "width", "height"}
        or any(type(v) is not int for v in bounds.values())
    ):
        raise DesktopError(
            "INVALID_ARGUMENT",
            "template_bounds requires integer x, y, width and height in source image pixels.",
        )
    x, y, w, h = (bounds[key] for key in ("x", "y", "width", "height"))
    sw, sh = source["image"]
    tw, th = target["image"]
    if (
        not 8 <= w <= 512
        or not 8 <= h <= 512
        or min(x, y) < 0
        or x + w > sw
        or y + h > sh
        or w > tw
        or h > th
    ):
        raise DesktopError(
            "MATCH_LIMIT",
            "Choose an in-image template 8–512 pixels per dimension that fits the target.",
        )
    if any(
        source["native"][i] * target["image"][i]
        != target["native"][i] * source["image"][i]
        for i in (0, 1)
    ):
        raise DesktopError(
            "MATCH_SCALE_MISMATCH",
            "Screenshot scales differ; explicitly observe at the same scale. No automatic resizing is performed.",
        )
    if (
        max(sw * sh, tw * th) > 2560 * 2560
        or max(len(source["png"]), len(target["png"])) > 32 * 1024 * 1024
    ):
        raise DesktopError(
            "MATCH_LIMIT", "Screenshot exceeds local matching pixel or byte limits."
        )
    with Image.open(io.BytesIO(source["png"])) as image:
        if image.size != (sw, sh):
            raise DesktopError(
                "MATCH_FAILED", "Retained screenshot dimensions are inconsistent."
            )
        cropped = image.convert("RGB").crop((x, y, x + w, y + h))
        output = io.BytesIO()
        cropped.save(output, format="PNG")
    template = output.getvalue()
    payload = struct.pack("!Q", len(template)) + template + target["png"]
    if len(payload) > 33 * 1024 * 1024:
        raise DesktopError("MATCH_LIMIT", "Encoded matching request exceeds 33 MiB.")
    try:
        raw = run(
            [
                "/usr/bin/python3",
                str(Path(__file__).with_name("_match_worker.py")),
                str(threshold),
                str(limit),
            ],
            data=payload,
            timeout=3,
            max_output_bytes=65536,
        )
    except DesktopError as exc:
        if exc.code in ("BACKEND_ERROR", "DEPENDENCY_MISSING"):
            raise DesktopError(
                "MATCH_FAILED", "Local matching engine failed; no candidates returned."
            ) from exc
        raise
    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
        error = result.get("error")
        if error in ("MATCH_UNAVAILABLE", "MATCH_FLAT_TEMPLATE", "MATCH_FAILED"):
            messages = {
                "MATCH_UNAVAILABLE": "Optional system Python OpenCV is unavailable; other desktop tools remain usable.",
                "MATCH_FLAT_TEMPLATE": "Template lacks spatial texture; select a crop containing distinct visual structure.",
                "MATCH_FAILED": "Local matching failed; no candidates returned.",
            }
            raise DesktopError(error, messages[error])
        candidates = result["candidates"]
        if (
            not isinstance(candidates, list)
            or len(candidates) > limit
            or type(result["truncated"]) is not bool
        ):
            raise ValueError()
        for item in candidates:
            box = item["image_bounds"]
            score = item["score"]
            if (
                set(item) != {"image_bounds", "score"}
                or set(box) != {"x", "y", "width", "height"}
                or any(type(v) is not int for v in box.values())
            ):
                raise ValueError()
            if (
                (box["width"], box["height"]) != (w, h)
                or min(box["x"], box["y"]) < 0
                or box["x"] + w > tw
                or box["y"] + h > th
            ):
                raise ValueError()
            if (
                type(score) not in (int, float)
                or not math.isfinite(score)
                or not threshold <= score <= 1
            ):
                raise ValueError()
        return {"candidates": candidates, "truncated": result["truncated"]}
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise DesktopError(
            "MATCH_FAILED",
            "Local matching returned invalid metadata; no candidates returned.",
        ) from exc
