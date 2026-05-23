"""CLI runner for the Device Connect Docker host driver."""

from __future__ import annotations

import argparse
import asyncio

from dcd.logging_setup import configure_driver_logging
from dcd.runtime_launcher import gather_cli_run_params, run_device_connect

configure_driver_logging()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Device Connect driver for Docker — provision and control containers.",
    )
    parser.add_argument("--device-id", default=None, help="Device Connect device id")
    parser.add_argument("--tenant", default=None, help="Device Connect tenant")
    parser.add_argument(
        "--sim",
        action="store_true",
        help="Use simulated Docker backend (no docker.sock required).",
    )
    parser.add_argument(
        "--docker-host",
        default=None,
        help="Docker Engine URL (default: DOCKER_HOST or local socket).",
    )
    parser.add_argument(
        "--state-poll-hz",
        type=float,
        default=None,
        help="Container state poll rate for events (0 disables).",
    )
    parser.add_argument("--messaging-backend", default=None)
    parser.add_argument("--messaging-url", action="append", default=None)
    parser.add_argument("--nats-credentials-file", default=None)
    parser.add_argument(
        "--portal",
        action="store_true",
        help="Connect via Device Connect Portal (NATS + registry).",
    )
    parser.add_argument("--portal-credentials", default=None)
    parser.add_argument("--portal-credentials-glob", default=None)
    parser.add_argument("--portal-credentials-dir", default=None)
    parser.add_argument(
        "--allow-insecure",
        action="store_true",
        help="Allow insecure Device Connect (D2D dev only).",
    )
    parser.add_argument(
        "--discovery-mode",
        default=None,
        choices=["d2d", "p2p", "infra"],
        help="Override DEVICE_CONNECT_DISCOVERY_MODE.",
    )
    return parser


async def _run_cli(args: argparse.Namespace) -> None:
    params = gather_cli_run_params(args)
    await run_device_connect(params)


def main() -> None:
    asyncio.run(_run_cli(build_parser().parse_args()))


if __name__ == "__main__":
    main()
