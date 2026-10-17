"""Display-independent placement and stable window snapshots."""

import math

from .models import Bounds, Layout


def place_windows(area, count, style=Layout.OVERLAP, size=(620, 390)):
    """Return bounded display coordinates, including displays left of or above main."""
    if not isinstance(count, int) or count < 0 or not isinstance(style, Layout):
        raise ValueError("Supply a nonnegative count and a Layout")
    if len(size) != 2 or any(not math.isfinite(v) or v <= 0 for v in size):
        raise ValueError("Window size must be positive and finite")
    if not count:
        return ()
    margin = min(24, area.width / 20, area.height / 20)
    width = min(size[0], area.width - 2 * margin)
    height = min(size[1], area.height - 2 * margin)
    if style is Layout.TILE:
        columns = math.ceil(math.sqrt(count * area.width / area.height))
        rows = math.ceil(count / columns)
        width, height = (
            (area.width - 2 * margin) / columns,
            (area.height - 2 * margin) / rows,
        )
    result = []
    offsets = ((0, 0), (0.25, 0.07), (0.10, 0.40), (0.53, 0.36))
    for index in range(count):
        w = (
            min(area.width - 2 * margin, max(1, width + (index % 3 - 1) * 10))
            if style is Layout.OVERLAP
            else width
        )
        h = (
            min(area.height - 2 * margin, max(1, height + (index % 4 - 1) * 5))
            if style is Layout.OVERLAP
            else height
        )
        if style is Layout.TILE:
            dx, dy = index % columns * width, index // columns * height
        elif style is Layout.CASCADE:
            dx = dy = index * 32
        else:
            ox, oy = (
                offsets[index]
                if index < 4
                else ((index * 0.381966) % 0.7, (index * 0.618034) % 0.7)
            )
            dx, dy = area.width * ox, area.height * oy
        x = min(area.x + area.width - margin - w, area.x + margin + dx)
        y = min(area.y + area.height - margin - h, area.y + margin + dy)
        result.append(Bounds(round(x), round(y), round(w), round(h)))
    return tuple(result)
