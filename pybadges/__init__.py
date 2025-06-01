# Copyright 2018 The pybadge Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Creates a github-style badge as a SVG image.

This package seeks to generate semantically-identical output to the JavaScript
gh-badges library
(https://github.com/badges/shields/blob/master/doc/gh-badges.md)

>>> badge(left_text='coverage', right_text='23%', right_color='red')
'<svg...</svg>'
>>> badge(left_text='build', right_text='green', right_color='green',
...       whole_link="http://www.example.com/")
'<svg...</svg>'
>>> # base64-encoded PNG image
>>> image_data = 'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAD0lEQVQI12P4zwAD/xkYAA/+Af8iHnLUAAAAAElFTkSuQmCC'
>>> badge(left_text='build', right_text='green', right_color='green',
...       logo="data:image/png;base64," + image_data)
'<svg...</svg>'
"""

import base64
import filetype
import mimetypes
from typing import Optional
import urllib.parse
from xml.dom import minidom
import importlib.resources as resources

import jinja2
import requests

from pybadges import text_measurer
from pybadges import precalculated_text_measurer


def load_template(name):
    return resources.read_text("pybadges", name)


# Create Jinja2 environment
_JINJA2_ENVIRONMENT = jinja2.Environment(
    trim_blocks=True,
    lstrip_blocks=True,
    loader=jinja2.ChoiceLoader(
        [jinja2.FunctionLoader(load_template), jinja2.FileSystemLoader(".")]
    ),
    autoescape=jinja2.select_autoescape(["svg"]),
)

# Use the same color scheme as describe in:
# https://github.com/badges/shields/blob/master/lib/colorscheme.json

_NAME_TO_COLOR = {
    "brightgreen": "#4c1",
    "green": "#97CA00",
    "yellow": "#dfb317",
    "yellowgreen": "#a4a61d",
    "orange": "#fe7d37",
    "red": "#e05d44",
    "blue": "#007ec6",
    "grey": "#555",
    "gray": "#555",
    "lightgrey": "#9f9f9f",
    "lightgray": "#9f9f9f",
    "critical": "#e05d44",
    "important": "#fe7d37",
    "success": "#4c1",
    "informational": "#007ec6",
    "inactive": "#9f9f9f",
}


def _remove_blanks(node):
    for x in node.childNodes:
        if x.nodeType == minidom.Node.TEXT_NODE:
            if x.nodeValue:
                x.nodeValue = x.nodeValue.strip()
        elif x.nodeType == minidom.Node.ELEMENT_NODE:
            _remove_blanks(x)


def _embed_image(url: str) -> str:
    """
    Given a URL (data-URI, http(s), or local path), return a
    data:image/...;base64,... string or raise ValueError if
    the file is not a valid image.
    """
    # 1) If it’s already a data URL, return immediately
    if url.startswith("data:"):
        return url

    parsed = urllib.parse.urlparse(url)

    # 2) Remote HTTP/HTTPS
    if parsed.scheme in ("http", "https"):
        image_data, mime = _fetch_remote_image(url)

    # 3) Any other non-empty scheme is unsupported (e.g. “ftp:” or “file:”)
    elif parsed.scheme:
        raise ValueError(f'unsupported scheme "{parsed.scheme}"')

    # 4) No scheme → treat as local filesystem path
    else:
        image_data, mime = _fetch_local_image_and_mime(url)

    # 5) Base64-encode and return
    encoded = base64.b64encode(image_data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _fetch_remote_image(url: str) -> tuple[bytes, str]:
    """
    Downloads the URL, checks Content-Type, and returns (bytes, mime‐string).
    Raises ValueError if Content-Type is missing or not an image.
    """
    resp = requests.get(url)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type")
    if not content_type:
        raise ValueError('no "Content-Type" header')

    major, minor = content_type.split("/", 1)
    if major.lower() != "image":
        raise ValueError(f'expected an image, got "{major}"')

    return resp.content, content_type


def _fetch_local_image_and_mime(path: str) -> tuple[bytes, str]:
    """
    Reads the file at `path` and tries to figure out a valid image MIME.
    Priority:
       1) filetype.guess(...) on raw bytes
       2) “<svg…” check for inline SVG
       3) mimetypes.guess_type(path) fallback by extension
       4) else → raise ValueError
    """
    with open(path, "rb") as f:
        data = f.read()

    # 1) Try to let `filetype` detect a binary image (PNG, JPEG, etc.)
    kind = filetype.guess(data)
    if kind:
        if not kind.mime.startswith("image/"):
            major = kind.mime.split("/", 1)[0]
            raise ValueError(f'expected an image, got "{major}"')
        return data, kind.mime

    # 2) If filetype didn’t detect anything, maybe it’s an SVG (text/XML)
    head = data[:500].lower()
    if b"<svg" in head:
        return data, "image/svg+xml"

    # 3) Finally, try to guess by file extension via `mimetypes`
    guessed_mime, _ = mimetypes.guess_type(path)
    if guessed_mime:
        major = guessed_mime.split("/", 1)[0]
        if major != "image":
            # e.g. “text/plain” for .txt → treat as wrong type
            raise ValueError(f'expected an image, got "{major}"')
        return data, guessed_mime

    # 4) If we still don’t know, give up
    raise ValueError("not able to determine file type")


def badge(
    left_text: str,
    right_text: Optional[str] = None,
    left_link: Optional[str] = None,
    right_link: Optional[str] = None,
    center_link: Optional[str] = None,
    whole_link: Optional[str] = None,
    logo: Optional[str] = None,
    left_color: str = "#555",
    right_color: str = "#007ec6",
    center_color: Optional[str] = None,
    measurer: Optional[text_measurer.TextMeasurer] = None,
    left_title: Optional[str] = None,
    right_title: Optional[str] = None,
    center_title: Optional[str] = None,
    whole_title: Optional[str] = None,
    right_image: Optional[str] = None,
    center_image: Optional[str] = None,
    embed_logo: bool = False,
    embed_right_image: bool = False,
    embed_center_image: bool = False,
    id_suffix: str = "",
) -> str:
    """Creates a github-style badge as an SVG image.

    >>> badge(left_text='coverage', right_text='23%', right_color='red')
    '<svg...</svg>'
    >>> badge(left_text='build', right_text='green', right_color='green',
    ...       whole_link="http://www.example.com/")
    '<svg...</svg>'

    Args:
        left_text: The text that should appear on the left-hand-side of the
            badge e.g. "coverage".
        right_text: The text that should appear on the right-hand-side of the
            badge e.g. "23%".
        left_link: The URL that should be redirected to when the left-hand text
            is selected.
        right_link: The URL that should be redirected to when the right-hand
            text is selected.
        whole_link: The link that should be redirected to when the badge is
            selected. If set then left_link and right_right may not be set.
        logo: A url representing a logo that will be displayed inside the
            badge. Can be a data URL e.g. "data:image/svg+xml;utf8,<svg..."
        left_color: The color of the part of the badge containing the left-hand
            text. Can be an valid CSS color
            (see https://developer.mozilla.org/en-US/docs/Web/CSS/color) or a
            color name defined here:
            https://github.com/badges/shields/blob/master/badge-maker/lib/color.js
        right_color: The color of the part of the badge containing the
            right-hand text. Can be an valid CSS color
            (see https://developer.mozilla.org/en-US/docs/Web/CSS/color) or a
            color name defined here:
            https://github.com/badges/shields/blob/master/badge-maker/lib/color.js
        measurer: A text_measurer.TextMeasurer that can be used to measure the
            width of left_text and right_text.
        embed_logo: If True then embed the logo image directly in the badge.
            This can prevent an HTTP request and some browsers will not render
            external image referenced. When True, `logo` must be a HTTP/HTTPS
            URI or a filesystem path. Also, the `badge` call may raise an
            exception if the logo cannot be loaded, is not an image, etc.
        whole_title: The title attribute to associate with the entire badge.
            See https://developer.mozilla.org/en-US/docs/Web/SVG/Element/title.
        left_title: The title attribute to associate with the left part of the
            badge.
            See https://developer.mozilla.org/en-US/docs/Web/SVG/Element/title.
        right_title: The title attribute to associate with the right part of
            the badge.
            See https://developer.mozilla.org/en-US/docs/Web/SVG/Element/title.
        id_suffix: The suffix of the id attributes used in the SVG's elements.
            Use to prevent duplicate ids if several badges are embedded on the
            same page.
    """
    if measurer is None:
        measurer = precalculated_text_measurer.PrecalculatedTextMeasurer.default()

    if (left_link or right_link or center_link) and whole_link:
        raise ValueError(
            "whole_link may not bet set with left_link, right_link, or center_link"
        )

    if center_image and not (right_image or right_text):
        raise ValueError("cannot have a center_image without a right element")

    if (center_image and not center_color) or (not center_image and center_color):
        raise ValueError("must have both a center_image and a center_color")

    if logo and embed_logo:
        logo = _embed_image(logo)

    if right_image and embed_right_image:
        right_image = _embed_image(right_image)

    if center_image and embed_center_image:
        center_image = _embed_image(center_image)

    if center_color:
        center_color = _NAME_TO_COLOR.get(center_color, center_color)

    right_text_width = None
    if right_text:
        right_text_width = measurer.text_width(right_text) / 10.0

    template = _JINJA2_ENVIRONMENT.get_template("badge-template-full.svg")

    svg = template.render(
        left_text=left_text,
        right_text=right_text,
        left_text_width=measurer.text_width(left_text) / 10.0,
        right_text_width=right_text_width,
        left_link=left_link,
        right_link=right_link,
        whole_link=whole_link,
        center_link=center_link,
        logo=logo,
        left_color=_NAME_TO_COLOR.get(left_color, left_color),
        right_color=_NAME_TO_COLOR.get(right_color, right_color),
        center_color=center_color,
        left_title=left_title,
        right_title=right_title,
        center_title=center_title,
        whole_title=whole_title,
        right_image=right_image,
        center_image=center_image,
        id_suffix=id_suffix,
    )
    xml = minidom.parseString(svg)
    _remove_blanks(xml)
    xml.normalize()
    return xml.documentElement.toxml()
