"""Offline: the capture must survive request bodies that are not UTF-8 (playwright raises on `.post_data`)."""

from __future__ import annotations

from fronteira_fx.discover.capture import _post_text


class _Binary:
    @property
    def post_data(self) -> str:
        raise UnicodeDecodeError("utf-8", b"\x9c", 0, 1, "invalid start byte")


class _Text:
    post_data = "a=1&b=2"


class _Empty:
    post_data = None


def test_binary_body_is_recorded_as_none_not_an_error() -> None:
    assert _post_text(_Binary()) is None


def test_text_body_is_kept_and_empty_body_is_none() -> None:
    assert _post_text(_Text()) == "a=1&b=2"
    assert _post_text(_Empty()) is None
