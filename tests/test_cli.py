"""CLI smoke tests."""

from __future__ import annotations

from dcd.__main__ import build_parser


def test_build_parser_has_expected_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["--sim", "--portal", "--allow-insecure", "--discovery-mode", "d2d"])

    assert args.sim is True
    assert args.portal is True
    assert args.allow_insecure is True
    assert args.discovery_mode == "d2d"
