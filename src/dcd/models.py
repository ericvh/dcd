"""Pydantic models for container provisioning and inspection."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PortBinding(BaseModel):
    container_port: int | str
    host_port: int | str | None = None
    protocol: str = "tcp"


class VolumeMount(BaseModel):
    source: str
    target: str
    read_only: bool = False


class ContainerProvisionSpec(BaseModel):
    """Specification for creating a container via Device Connect RPC."""

    image: str
    name: str | None = None
    command: list[str] | str | None = None
    entrypoint: list[str] | str | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    ports: list[PortBinding] = Field(default_factory=list)
    volumes: list[VolumeMount] = Field(default_factory=list)
    network: str | None = None
    detach: bool = True
    auto_remove: bool = False
    restart_policy: str | None = None
    mem_limit: str | None = None
    cpu_quota: int | None = None
    device_connect_labels: bool = True

    def docker_port_bindings(self) -> dict[str, list[dict[str, str]]] | None:
        if not self.ports:
            return None
        bindings: dict[str, list[dict[str, str]]] = {}
        for port in self.ports:
            key = f"{port.container_port}/{port.protocol}"
            host = str(port.host_port) if port.host_port is not None else None
            bindings[key] = [{"HostPort": host}] if host else [{}]
        return bindings

    def docker_volumes(self) -> dict[str, dict[str, str]] | None:
        if not self.volumes:
            return None
        return {
            mount.target: {"bind": mount.source, "mode": "ro" if mount.read_only else "rw"}
            for mount in self.volumes
        }


class ContainerSummary(BaseModel):
    id: str
    name: str
    image: str
    status: str
    state: str
    labels: dict[str, str] = Field(default_factory=dict)
    ports: dict[str, Any] = Field(default_factory=dict)
    created: str | None = None
    managed_by_dcd: bool = False


class ComposeProvisionSpec(BaseModel):
    """Run `docker compose up` for a project directory or inline compose file."""

    project_dir: str | None = None
    compose_file: str | None = None
    compose_yaml: str | None = None
    services: list[str] | None = None
    detach: bool = True
    pull: bool = False
    build: bool = False
    remove_orphans: bool = False
