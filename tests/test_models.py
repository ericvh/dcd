"""Unit tests for provisioning models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dcd.models import ContainerProvisionSpec, PortBinding


def test_container_provision_spec_port_bindings() -> None:
    spec = ContainerProvisionSpec(
        image="nginx:alpine",
        ports=[PortBinding(container_port=80, host_port=8080, protocol="tcp")],
    )

    bindings = spec.docker_port_bindings()
    assert bindings == {"80/tcp": [{"HostPort": "8080"}]}


def test_container_provision_spec_port_without_host() -> None:
    spec = ContainerProvisionSpec(
        image="redis:alpine",
        ports=[PortBinding(container_port=6379)],
    )

    bindings = spec.docker_port_bindings()
    assert bindings == {"6379/tcp": [{}]}


def test_container_provision_spec_volumes() -> None:
    from dcd.models import VolumeMount

    spec = ContainerProvisionSpec(
        image="busybox",
        volumes=[VolumeMount(source="/data", target="/mnt", read_only=True)],
    )

    volumes = spec.docker_volumes()
    assert volumes == {"/mnt": {"bind": "/data", "mode": "ro"}}


def test_container_provision_spec_requires_image() -> None:
    with pytest.raises(ValidationError):
        ContainerProvisionSpec.model_validate({"name": "no-image"})
