# -*- coding: utf-8 -*-
# Copyright (C) 2020 Greenbone Networks GmbH
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# Squarified Treemap Layout
# Implements algorithm from Bruls, Huizing, van Wijk, "Squarified Treemaps"
#   (but not using their pseudocode)

# It is a simplified, adapted version of squarify:
# https://github.com/laserson/squarify
# For more information see:
# https://www.win.tue.nl/~vanwijk/stm.pdf
# pylint: disable=C0103
import math as m
import numbers
from dataclasses import dataclass
from typing import Dict, List

from django.utils.safestring import mark_safe

from pheme.templatetags.charts import _severity_class_colors, register

__ELEMENT_TEMPLATE = """
<g>
    <rect x="{x}" y="{y}" width="{width}" height="{height}" fill="{color}" stroke="{border_color}" strokeWidth="1" />
    <text x="{label_x}" y="{label_y}" width="{width}" height="{height}" dominant-baseline="central">{label}</text>
</g>
"""

__TEMPLATE = """
<svg version="1.1"
     baseProfile="full"
     width="{width}" height="{height}"
     viewBox="0 0 {width} {height}"
     xmlns="http://www.w3.org/2000/svg">
     {rects}
</svg>
"""


@dataclass
class Rect:
    x: float
    y: float
    dx: float
    dy: float


def __create_rectangle(x, y, dx, dy) -> Rect:
    # add spacing of 1px
    if dx > 2:
        x += 1
        dx -= 2
    if dy > 2:
        y += 1
        dy -= 2
    return Rect(x, y, dx, dy)


def __layoutrow(sizes, x, y, _, dy) -> List[Rect]:
    covered_area = sum(sizes)
    width = covered_area / dy
    rects = []
    for size in sizes:
        rects.append(__create_rectangle(x, y, width, size / width))
        y += size / width
    return rects


def __layoutcol(sizes, x, y, dx, _) -> List[Rect]:
    covered_area = sum(sizes)
    height = covered_area / dx
    rects = []
    for size in sizes:
        rects.append(__create_rectangle(x, y, size / height, height))
        x += size / height
    return rects


def __layout(sizes, x, y, dx, dy) -> List[Rect]:
    if dx >= dy:
        return __layoutrow(sizes, x, y, dx, dy)
    return __layoutcol(sizes, x, y, dx, dy)


def __leftoverrow(sizes, x, y, dx, dy):
    covered_area = sum(sizes)
    width = covered_area / dy
    leftover_x = x + width
    leftover_y = y
    leftover_dx = dx - width
    leftover_dy = dy
    return leftover_x, leftover_y, leftover_dx, leftover_dy


def __leftovercol(sizes, x, y, dx, dy):
    covered_area = sum(sizes)
    height = covered_area / dx
    leftover_x = x
    leftover_y = y + height
    leftover_dx = dx
    leftover_dy = dy - height
    return leftover_x, leftover_y, leftover_dx, leftover_dy


def __leftover(sizes, x, y, dx, dy):
    if dx >= dy:
        return __leftoverrow(sizes, x, y, dx, dy)
    return __leftovercol(sizes, x, y, dx, dy)


def __find_split(sizes, x, y, dx, dy) -> int:
    """
    returns the index to split the sizes based on worst ratio to get the
    remaining and current space.

    For an example the area ratio of 5, 3, 2, 1 with the area of 90 * 50
    >>> test_data = [2045.5, 1227.3, 818.2, 409.0 ]
    >>> __find_split(test_data, 0, 0, 90, 50)
    1

    The first two elements can be put into the first space and the rest needs to
    calculated for the remaining space.

    """

    def worst(i: int) -> float:
        return max(
            [
                max(rect.dx / rect.dy, rect.dy / rect.dx)
                for rect in __layout(sizes[:i], x, y, dx, dy)
            ]
        )

    for i in range(1, len(sizes)):
        if worst(i) < worst(i + 1):
            return i
    return len(sizes) - 1


def __squarify(sizes, x, y, dx, dy) -> List[Rect]:
    """
    calculates treemap rectangles using an algorithm based on Bruls, Huizing,
    van Wijk, "Squarified Treemaps" and "squarify":
    https://github.com/laserson/squarify

    >>> __squarify([5, 1], 0, 0, 90, 50)
    [Rect(x=1, y=1, dx=73.0, dy=48.0), Rect(x=76.0, y=1, dx=13.0, dy=48.0)]

    Parameters:
        sizes : list-like of numeric values
            The set of values to compute a treemap for. `sizes` must be sorted,
            positive values
        x, y : numeric
            The coordinates of the "origin".
        dx, dy : numeric
            The full width (`dx`) and height (`dy`) of the treemap.

    Returns:
        List[Rect]
            Each dict in the returned list represents a single rectangle in the
            treemap. The order corresponds to the input order.
    """

    if len(sizes) == 0:
        return []

    total_size = sum(sizes)
    total_area = dx * dy

    sizes = list([size * total_area / total_size for size in sizes])

    if len(sizes) == 1:
        return __layout(sizes, x, y, dx, dy)

    i = __find_split(sizes, x, y, dx, dy)
    current = sizes[:i]
    remaining = sizes[i:]

    return __layout(current, x, y, dx, dy) + __squarify(
        remaining, *__leftover(current, x, y, dx, dy)
    )


def __transform_to_tree_data(data) -> List[Dict]:
    """
    tansforms given data to treemap compatible format.
    The support types are:
    >>> example_host_data = dict(
    ...     host1=dict(high=12, medium=4, low=0),
    ...     host2=dict(high=0, medium=4, low=0),
    ... )
    >>> __transform_to_tree_data(example_host_data)
    ([16, 4], ['host1', 'host2'], ['high', 'medium'])

    On unsupported input data it returns empty lists:
    >>> __transform_to_tree_data(dict(k="hello", v="world"))
    ([], [], [])
    >>> __transform_to_tree_data(12)
    ([], [], [])
    """
    values = []
    labels = []
    color_keys = []
    if isinstance(data, dict):
        for key, val in data.items():
            color = None
            val_sum = 0
            if isinstance(val, dict):
                for item_key, item_val in val.items():
                    if isinstance(item_val, numbers.Number):
                        val_sum += item_val
                        if color is None and item_val > 0:
                            color = item_key
            if color is not None and val_sum > 0:
                values.append(val_sum)
                labels.append(key)
                color_keys.append(color)
    return values, labels, color_keys


@register.filter
def treemap(
    data: List[Dict],
    width=1024,
    height=768,
    fontsize=11,
    border_color="#ffffff",
    title_color=None,
) -> str:
    """
    Expects a sorted dict containing a str, and a dict with values in it.

    An example can be:

    {
        'host1': {'high': 12, 'medium': 4, 'low': 0},
        'host2': {'high': 0, 'medium': 4, 'low': 0},
    }

    With that host1 and host2 will be used as a label, high and medium will be
    used to find the color and values will be summed for the rectangle
    calculation.

    Data will be transformed to lits of labels, color_keys and the actual
    values.

    The color key within the data  must be consistant with title_color.

    Parameters:
        data: needs to be an dict containing label, color_key and values.
        width: width of the svg (default 1024)
        height: height of the svg (default 768)
        fontsize: used fontsize (default 11)
        border_color: color of the rectangle border (default white)
        title_color: the color_key to color lookup map
            (default _severity_class_colors)

    Returns:
        the treemap in svg as a SafeString.
    """
    if not title_color:
        title_color = _severity_class_colors
    sizes, label, color_keys = __transform_to_tree_data(data)
    sizes = __squarify(sizes, 0, 0, width, height)
    elements = ""
    for i, d in enumerate(sizes):
        label_size_in_px = len(label[i]) * fontsize
        label_x = d.x + 1
        # move half of the font size down and add a buffer for different
        # heights of characters (depends on font) to display the label
        # on the upper left corner of an rectangle.
        label_y = d.y + fontsize / 2 + 5
        max_label_len = m.ceil(d.dx / label_size_in_px * len(label[i]))
        if d.dy <= fontsize:
            max_label_len = 0

        elements += __ELEMENT_TEMPLATE.format(
            x=d.x,
            y=d.y,
            width=d.dx,
            height=d.dy,
            color=title_color.get(color_keys[i]),
            border_color=border_color,
            label_x=label_x,
            label_y=label_y,
            label=label[i][:max_label_len],
        )
    return mark_safe(
        __TEMPLATE.format(width=width, height=height, rects=elements)
    )
