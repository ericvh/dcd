"""Unit tests for portal and environment configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dcd.config import (
    DriverConfig,
    apply_portal_config,
    load_portal_credentials,
    resolve_portal_credentials_file,
)


def test_driver_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DCD_DEVICE_ID", "env-host")
    monkeypatch.setenv("DCD_TENANT", "env-tenant")
    monkeypatch.setenv("DCD_SIM", "true")
    monkeypatch.setenv("DOCKER_HOST", "tcp://127.0.0.1:2375")
    monkeypatch.setenv("DEVICE_CONNECT_ALLOW_INSECURE", "true")
    monkeypatch.setenv("MESSAGING_URLS", "nats://broker:4222,nats://broker2:4222")

    cfg = DriverConfig.from_env()

    assert cfg.device_id == "env-host"
    assert cfg.tenant == "env-tenant"
    assert cfg.simulate is True
    assert cfg.docker_host == "tcp://127.0.0.1:2375"
    assert cfg.allow_insecure is True
    assert cfg.messaging_urls == ("nats://broker:4222", "nats://broker2:4222")


def test_load_portal_credentials(tmp_path: Path) -> None:
    creds_path = tmp_path / "device.creds.json"
    creds_path.write_text(
        json.dumps(
            {
                "device_id": "portal-docker-1",
                "tenant": "acme",
                "nats": {"urls": ["nats://portal.example:4222"]},
            }
        ),
        encoding="utf-8",
    )

    creds = load_portal_credentials(creds_path)

    assert creds.device_id == "portal-docker-1"
    assert creds.tenant == "acme"
    assert creds.messaging_urls == ("nats://portal.example:4222",)


def test_apply_portal_config_sets_nats_and_discovery() -> None:
    from dcd.config import PortalCredentials

    base = DriverConfig(device_id="fallback", tenant="fallback", portal=True)
    portal_creds = PortalCredentials(
        path=Path("/tmp/x.json"),
        device_id="from-creds",
        tenant="from-tenant",
        messaging_urls=("nats://custom:4222",),
    )
    updated = apply_portal_config(
        base,
        portal_credentials=portal_creds,
        explicit_device_id=None,
        explicit_tenant=None,
    )

    assert updated.messaging_backend == "nats"
    assert updated.messaging_urls == ("nats://custom:4222",)
    assert updated.device_id == "from-creds"
    assert updated.tenant == "from-tenant"
    assert updated.discovery_mode == "infra"


def test_apply_portal_config_keeps_explicit_ids() -> None:
    base = DriverConfig(portal=True)
    from dcd.config import PortalCredentials

    portal_creds = PortalCredentials(
        path=Path("/tmp/x.json"),
        device_id="from-creds",
        tenant="from-tenant",
    )
    updated = apply_portal_config(
        base,
        portal_credentials=portal_creds,
        explicit_device_id="cli-id",
        explicit_tenant="cli-tenant",
    )

    assert updated.device_id == "cli-id"
    assert updated.tenant == "cli-tenant"


def test_resolve_portal_credentials_explicit_path(tmp_path: Path) -> None:
    creds = tmp_path / "mine.creds.json"
    creds.write_text("{}", encoding="utf-8")

    resolved = resolve_portal_credentials_file(
        explicit_path=str(creds),
        portal=True,
        pattern="*.json",
        search_dir=str(tmp_path),
    )

    assert resolved == str(creds)


def test_resolve_portal_credentials_skips_when_not_portal() -> None:
    assert (
        resolve_portal_credentials_file(
            explicit_path=None,
            portal=False,
            pattern="*.json",
            search_dir="/tmp",
        )
        is None
    )
