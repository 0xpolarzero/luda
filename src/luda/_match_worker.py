"""Optional system-OpenCV worker; inputs are bounded PNG bytes, never paths."""

import json
import os
import resource
import struct
import sys

MAX_BYTES = 33 * 1024 * 1024
MAX_PIXELS = 2560 * 2560


def main():
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[key] = "1"
    try:
        import cv2
        import numpy as np
    except ImportError:
        print(json.dumps({"error": "MATCH_UNAVAILABLE"}))
        return
    try:
        cv2.setNumThreads(1)
        threshold, limit = float(sys.argv[1]), int(sys.argv[2])
        if not 0 <= threshold <= 1 or not 1 <= limit <= 100:
            raise ValueError()
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or len(raw) < 8:
            raise ValueError()
        size = struct.unpack("!Q", raw[:8])[0]
        if not 1 <= size <= 2 * 1024 * 1024 or 8 + size >= len(raw):
            raise ValueError()
        for encoded in (raw[8 : 8 + size], raw[8 + size :]):
            if (
                encoded[:8] != b"\x89PNG\r\n\x1a\n"
                or encoded[12:16] != b"IHDR"
                or len(encoded) < 24
            ):
                raise ValueError()
            pw, ph = struct.unpack("!II", encoded[16:24])
            if not pw or not ph or pw * ph > MAX_PIXELS:
                raise ValueError()
        template = cv2.imdecode(
            np.frombuffer(raw[8 : 8 + size], np.uint8), cv2.IMREAD_COLOR
        )
        image = cv2.imdecode(np.frombuffer(raw[8 + size :], np.uint8), cv2.IMREAD_COLOR)
        if template is None or image is None:
            raise ValueError()
        h, w = template.shape[:2]
        ih, iw = image.shape[:2]
        if (
            not 8 <= w <= 512
            or not 8 <= h <= 512
            or iw * ih > MAX_PIXELS
            or w > iw
            or h > ih
        ):
            raise ValueError()
        # Channel differences alone are not texture: a solid red crop is flat.
        if float(template.std(axis=(0, 1)).max()) < 2:
            print(json.dumps({"error": "MATCH_FLAT_TEMPLATE"}))
            return
        scores = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
        if not np.isfinite(scores).all():
            raise ValueError()
        candidates = []
        truncated = False
        # At most 101 C-level scans; no all-pixel sort or Python candidate list.
        for index in range(limit + 1):
            _, score, _, point = cv2.minMaxLoc(scores)
            if score < threshold:
                break
            if index == limit:
                truncated = True
                break
            x, y = point
            candidates.append(
                {
                    "image_bounds": {"x": x, "y": y, "width": w, "height": h},
                    "score": min(1.0, float(score)),
                }
            )
            # Deliberately return non-overlapping placements, not every local peak.
            scores[
                max(0, y - h + 1) : min(scores.shape[0], y + h),
                max(0, x - w + 1) : min(scores.shape[1], x + w),
            ] = -2
        print(
            json.dumps(
                {
                    "candidates": candidates,
                    "truncated": truncated,
                    "engine_version": cv2.__version__,
                }
            )
        )
    except (ValueError, OverflowError, MemoryError, cv2.error):
        print(json.dumps({"error": "MATCH_FAILED"}))


if __name__ == "__main__":
    main()
