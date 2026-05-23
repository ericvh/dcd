"""Unit tests for CLI parameter gathering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from dcd.runtime_launcher import gather_cli_run_params


def _args(**kwargs: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "device_id": None,
        "tenant": None,
        "sim": False,
        "docker_host": None,
        "state_poll_hz": None,
        "messaging_backend": None,
        "messaging_url": None,
        "nats_credentials_file": None,
        "portal": False,
        "portal_credentials": None,
        "portal_credentials_glob": None,
        "portal_credentials_dir": None,
        "allow_insecure": False,
        "discovery_mode": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_gather_cli_d2d_sim() -> None:
    params = gather_cli_run_params(_args(sim=True, allow_insecure=True, device_id="host-a"))

    assert params.driver_config.simulate is True
    assert params.driver_config.allow_insecure is True
    assert params.driver_config.device_id == "host-a"
    assert params.driver_config.portal is False


def test_gather_cli_portal_with_credentials(tmp_path: Path) -> None:
    creds_path = tmp_path / "device.creds.json"
    creds_path.write_text(
        json.dumps(
            {
                "device_id": "dcd-portal",
                "tenant": "lab",
                "nats": {"urls": ["nats://portal.test:4222"]},
            }
        ),
        encoding="utf-8",
    )

    params = gather_cli_run_params(
        _args(
            portal=True,
            portal_credentials=str(creds_path),
            nats_credentials_file=str(creds_path),
        )
    )

    assert params.driver_config.portal is True
    assert params.driver_config.device_id == "dcd-portal"
    assert params.driver_config.tenant == "lab"
    assert params.driver_config.messaging_backend == "nats"
    assert params.driver_config.messaging_urls == ("nats://portal.test:4222",)
    assert params.driver_config.discovery_mode == "infra"
    assert params.portal_credentials is not None


def test_gather_cli_portal_missing_credentials_exits() -> None:
    with pytest.raises(SystemExit) as exc:
        gather_cli_run_params(
            _args(
                portal=True,
                portal_credentials_dir=str(Path("/nonexistent-dcd-creds-dir")),
            )
        )
    assert exc.value.code == 2
