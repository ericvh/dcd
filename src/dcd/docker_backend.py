"""Docker Engine access — real socket client and in-memory simulator."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dcd.models import (
    ComposeProvisionSpec,
    ContainerProvisionSpec,
    ContainerSummary,
)

logger = logging.getLogger(__name__)

DCD_LABEL_PREFIX = "deviceconnect.dev/"
DCD_MANAGED_LABEL = f"{DCD_LABEL_PREFIX}managed"
DCD_DRIVER_LABEL = f"{DCD_LABEL_PREFIX}driver"
DCD_DRIVER_VALUE = "dcd"


@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str


class DockerBackend(ABC):
    """Abstract Docker operations used by the Device Connect driver."""

    @abstractmethod
    async def ping(self) -> dict[str, Any]: ...

    @abstractmethod
    async def list_containers(self, *, all_containers: bool = False) -> list[ContainerSummary]: ...

    @abstractmethod
    async def get_container(self, container_id: str) -> ContainerSummary: ...

    @abstractmethod
    async def create_container(self, spec: ContainerProvisionSpec) -> ContainerSummary: ...

    @abstractmethod
    async def start_container(self, container_id: str) -> ContainerSummary: ...

    @abstractmethod
    async def stop_container(
        self, container_id: str, *, timeout_s: int = 10
    ) -> ContainerSummary: ...

    @abstractmethod
    async def restart_container(
        self, container_id: str, *, timeout_s: int = 10
    ) -> ContainerSummary: ...

    @abstractmethod
    async def remove_container(self, container_id: str, *, force: bool = False) -> None: ...

    @abstractmethod
    async def container_logs(
        self,
        container_id: str,
        *,
        tail: int = 100,
        since: str | None = None,
        stdout: bool = True,
        stderr: bool = True,
    ) -> str: ...

    @abstractmethod
    async def exec_in_container(
        self,
        container_id: str,
        command: list[str],
        *,
        environment: dict[str, str] | None = None,
        workdir: str | None = None,
    ) -> ExecResult: ...

    @abstractmethod
    async def pull_image(self, image: str) -> dict[str, Any]: ...

    @abstractmethod
    async def list_images(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def compose_up(self, spec: ComposeProvisionSpec) -> dict[str, Any]: ...

    @abstractmethod
    async def compose_down(
        self,
        *,
        project_dir: str | None = None,
        compose_file: str | None = None,
        remove_volumes: bool = False,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def stream_container_logs(
        self,
        container_id: str,
        *,
        tail: int = 100,
        since: str | None = None,
        stop: asyncio.Event,
        on_line: Callable[[str, str], Awaitable[None]],
    ) -> None:
        """Stream log lines to on_line(stream, line) until stop is set."""


def _managed_labels(spec: ContainerProvisionSpec) -> dict[str, str]:
    labels = dict(spec.labels)
    if spec.device_connect_labels:
        labels[DCD_MANAGED_LABEL] = "true"
        labels[DCD_DRIVER_LABEL] = DCD_DRIVER_VALUE
    return labels


def _summary_from_docker(container: Any) -> ContainerSummary:
    attrs = container.attrs
    labels = attrs.get("Config", {}).get("Labels") or {}
    state = attrs.get("State", {})
    return ContainerSummary(
        id=container.short_id,
        name=(container.name or "").lstrip("/"),
        image=attrs.get("Config", {}).get("Image", ""),
        status=container.status,
        state=state.get("Status", container.status),
        labels=labels,
        ports=attrs.get("NetworkSettings", {}).get("Ports") or {},
        created=attrs.get("Created"),
        managed_by_dcd=labels.get(DCD_MANAGED_LABEL) == "true",
    )


class DockerEngineBackend(DockerBackend):
    """Talk to a local or remote Docker Engine via the official Python SDK."""

    def __init__(self, *, base_url: str | None = None, timeout_s: int = 120) -> None:
        self._base_url = base_url
        self._timeout_s = timeout_s
        self._client: Any = None
        self._inline_compose_dirs: dict[str, tempfile.TemporaryDirectory[str]] = {}

    def _get_client(self) -> Any:
        if self._client is None:
            import docker

            kwargs: dict[str, Any] = {"timeout": self._timeout_s}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = docker.from_env(**kwargs)
        return self._client

    async def ping(self) -> dict[str, Any]:
        def _ping() -> dict[str, Any]:
            client = self._get_client()
            client.ping()
            version = client.version()
            info = client.info()
            return {
                "connected": True,
                "docker_version": version.get("Version"),
                "api_version": version.get("ApiVersion"),
                "os": info.get("OperatingSystem"),
                "arch": info.get("Architecture"),
                "containers": info.get("Containers"),
                "images": info.get("Images"),
                "server_version": info.get("ServerVersion"),
            }

        return await asyncio.to_thread(_ping)

    async def list_containers(self, *, all_containers: bool = False) -> list[ContainerSummary]:
        def _list() -> list[ContainerSummary]:
            client = self._get_client()
            return [_summary_from_docker(c) for c in client.containers.list(all=all_containers)]

        return await asyncio.to_thread(_list)

    async def get_container(self, container_id: str) -> ContainerSummary:
        def _get() -> ContainerSummary:
            client = self._get_client()
            return _summary_from_docker(client.containers.get(container_id))

        return await asyncio.to_thread(_get)

    async def create_container(self, spec: ContainerProvisionSpec) -> ContainerSummary:
        def _create() -> ContainerSummary:
            client = self._get_client()
            host_config_kwargs: dict[str, Any] = {}
            port_bindings = spec.docker_port_bindings()
            if port_bindings:
                host_config_kwargs["port_bindings"] = port_bindings
            if spec.restart_policy:
                host_config_kwargs["restart_policy"] = {"Name": spec.restart_policy}
            if spec.mem_limit:
                host_config_kwargs["mem_limit"] = spec.mem_limit

            host_config = (
                client.api.create_host_config(**host_config_kwargs) if host_config_kwargs else None
            )

            kwargs: dict[str, Any] = {
                "image": spec.image,
                "labels": _managed_labels(spec),
                "environment": spec.environment or None,
                "auto_remove": spec.auto_remove,
            }
            if spec.name:
                kwargs["name"] = spec.name
            if spec.command is not None:
                kwargs["command"] = spec.command
            if spec.entrypoint is not None:
                kwargs["entrypoint"] = spec.entrypoint
            if port_bindings:
                kwargs["ports"] = list(port_bindings.keys())
            volumes = spec.docker_volumes()
            if volumes:
                kwargs["volumes"] = volumes
            if spec.network:
                kwargs["network"] = spec.network
            if host_config is not None:
                kwargs["host_config"] = host_config

            if spec.detach:
                container = client.containers.run(detach=True, **kwargs)
            else:
                container = client.containers.create(**kwargs)
                container.start()
            return _summary_from_docker(container)

        return await asyncio.to_thread(_create)

    async def start_container(self, container_id: str) -> ContainerSummary:
        def _start() -> ContainerSummary:
            container = self._get_client().containers.get(container_id)
            container.start()
            container.reload()
            return _summary_from_docker(container)

        return await asyncio.to_thread(_start)

    async def stop_container(self, container_id: str, *, timeout_s: int = 10) -> ContainerSummary:
        def _stop() -> ContainerSummary:
            container = self._get_client().containers.get(container_id)
            container.stop(timeout=timeout_s)
            container.reload()
            return _summary_from_docker(container)

        return await asyncio.to_thread(_stop)

    async def restart_container(
        self, container_id: str, *, timeout_s: int = 10
    ) -> ContainerSummary:
        def _restart() -> ContainerSummary:
            container = self._get_client().containers.get(container_id)
            container.restart(timeout=timeout_s)
            container.reload()
            return _summary_from_docker(container)

        return await asyncio.to_thread(_restart)

    async def remove_container(self, container_id: str, *, force: bool = False) -> None:
        def _remove() -> None:
            self._get_client().containers.get(container_id).remove(force=force)

        await asyncio.to_thread(_remove)

    async def container_logs(
        self,
        container_id: str,
        *,
        tail: int = 100,
        since: str | None = None,
        stdout: bool = True,
        stderr: bool = True,
    ) -> str:
        def _logs() -> str:
            container = self._get_client().containers.get(container_id)
            raw = container.logs(
                tail=tail,
                since=since,
                stdout=stdout,
                stderr=stderr,
                timestamps=True,
            )
            if isinstance(raw, bytes):
                return raw.decode("utf-8", errors="replace")
            return str(raw)

        return await asyncio.to_thread(_logs)

    async def exec_in_container(
        self,
        container_id: str,
        command: list[str],
        *,
        environment: dict[str, str] | None = None,
        workdir: str | None = None,
    ) -> ExecResult:
        def _exec() -> ExecResult:
            container = self._get_client().containers.get(container_id)
            result = container.exec_run(
                cmd=command,
                environment=environment,
                workdir=workdir,
                demux=True,
            )
            out, err = result.output if isinstance(result.output, tuple) else (result.output, b"")
            stdout = (out or b"").decode("utf-8", errors="replace")
            stderr = (err or b"").decode("utf-8", errors="replace")
            return ExecResult(exit_code=result.exit_code, stdout=stdout, stderr=stderr)

        return await asyncio.to_thread(_exec)

    async def pull_image(self, image: str) -> dict[str, Any]:
        def _pull() -> dict[str, Any]:
            lines = []
            for chunk in self._get_client().api.pull(image, stream=True, decode=True):
                if isinstance(chunk, dict) and "status" in chunk:
                    lines.append(chunk["status"])
            return {"status": "success", "image": image, "progress": lines[-5:]}

        return await asyncio.to_thread(_pull)

    async def list_images(self) -> list[dict[str, Any]]:
        def _list() -> list[dict[str, Any]]:
            client = self._get_client()
            return [
                {
                    "id": img.short_id,
                    "tags": img.tags,
                    "size": img.attrs.get("Size"),
                    "created": img.attrs.get("Created"),
                }
                for img in client.images.list()
            ]

        return await asyncio.to_thread(_list)

    async def compose_up(self, spec: ComposeProvisionSpec) -> dict[str, Any]:
        return await asyncio.to_thread(self._compose_up_sync, spec)

    async def compose_down(
        self,
        *,
        project_dir: str | None = None,
        compose_file: str | None = None,
        remove_volumes: bool = False,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._compose_down_sync,
            project_dir,
            compose_file,
            remove_volumes,
        )

    async def stream_container_logs(
        self,
        container_id: str,
        *,
        tail: int = 100,
        since: str | None = None,
        stop: asyncio.Event,
        on_line: Callable[[str, str], Awaitable[None]],
    ) -> None:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()

        def _reader() -> None:
            try:
                container = self._get_client().containers.get(container_id)
                for chunk in container.logs(
                    stream=True,
                    follow=True,
                    tail=tail,
                    since=since,
                    stdout=True,
                    stderr=True,
                    timestamps=False,
                ):
                    if stop.is_set():
                        break
                    if isinstance(chunk, bytes):
                        text = chunk.decode("utf-8", errors="replace")
                    else:
                        text = str(chunk)
                    for line in text.splitlines():
                        loop.call_soon_threadsafe(queue.put_nowait, ("stdout", line))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        reader = asyncio.to_thread(_reader)
        try:
            while not stop.is_set():
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.5)
                except TimeoutError:
                    continue
                if item is None:
                    break
                stream, line = item
                await on_line(stream, line)
        finally:
            await reader

    def _compose_up_sync(self, spec: ComposeProvisionSpec) -> dict[str, Any]:
        workdir: Path | None = None
        compose_path: Path | None = None
        temp_dir: tempfile.TemporaryDirectory[str] | None = None

        if spec.compose_yaml:
            temp_dir = tempfile.TemporaryDirectory(prefix="dcd-compose-")
            workdir = Path(temp_dir.name)
            compose_path = workdir / "compose.yaml"
            compose_path.write_text(spec.compose_yaml, encoding="utf-8")
            self._inline_compose_dirs[str(workdir)] = temp_dir
            temp_dir = None
        elif spec.project_dir:
            workdir = Path(spec.project_dir).expanduser().resolve()
            if spec.compose_file:
                compose_path = workdir / spec.compose_file
        else:
            raise ValueError("compose_up requires project_dir or compose_yaml")

        cmd = _compose_command()
        if compose_path:
            cmd.extend(["-f", str(compose_path)])
        cmd.append("up")
        if spec.detach:
            cmd.append("-d")
        if spec.pull:
            cmd.append("--pull")
        if spec.build:
            cmd.append("--build")
        if spec.remove_orphans:
            cmd.append("--remove-orphans")
        if spec.services:
            cmd.extend(spec.services)

        result = subprocess.run(
            cmd,
            cwd=workdir,
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        if result.returncode != 0:
            if workdir is not None:
                self._cleanup_inline_compose(str(workdir))
            raise RuntimeError(result.stderr or result.stdout or "compose up failed")
        return {
            "status": "success",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "project_dir": str(workdir),
        }

    def _compose_down_sync(
        self,
        project_dir: str | None,
        compose_file: str | None,
        remove_volumes: bool,
    ) -> dict[str, Any]:
        if not project_dir:
            raise ValueError("compose_down requires project_dir")
        workdir = Path(project_dir).expanduser().resolve()
        cmd = _compose_command()
        if compose_file:
            cmd.extend(["-f", str(workdir / compose_file)])
        cmd.append("down")
        if remove_volumes:
            cmd.append("-v")
        result = subprocess.run(
            cmd,
            cwd=workdir,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        self._cleanup_inline_compose(str(workdir))
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout or "compose down failed")
        return {"status": "success", "stdout": result.stdout, "stderr": result.stderr}

    def _cleanup_inline_compose(self, project_dir: str) -> None:
        temp_dir = self._inline_compose_dirs.pop(project_dir, None)
        if temp_dir is not None:
            temp_dir.cleanup()


@dataclass
class _SimContainer:
    id: str
    name: str
    image: str
    status: str
    state: str
    labels: dict[str, str] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    created: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class SimDockerBackend(DockerBackend):
    """In-memory Docker simulator for CI and offline development."""

    def __init__(self) -> None:
        self._containers: dict[str, _SimContainer] = {}
        self._images: set[str] = {"alpine:latest", "busybox:latest"}

    async def ping(self) -> dict[str, Any]:
        return {
            "connected": True,
            "simulated": True,
            "docker_version": "sim-0.1.0",
            "api_version": "1.45",
            "os": "simulated",
            "arch": "arm64",
            "containers": len(self._containers),
            "images": len(self._images),
        }

    async def list_containers(self, *, all_containers: bool = False) -> list[ContainerSummary]:
        items = list(self._containers.values())
        if not all_containers:
            items = [c for c in items if c.state not in {"exited", "dead"}]
        return [self._to_summary(c) for c in items]

    async def get_container(self, container_id: str) -> ContainerSummary:
        container = self._resolve(container_id)
        return self._to_summary(container)

    async def create_container(self, spec: ContainerProvisionSpec) -> ContainerSummary:
        cid = uuid.uuid4().hex[:12]
        name = spec.name or f"dcd-{cid}"
        labels = _managed_labels(spec)
        sim = _SimContainer(
            id=cid,
            name=name,
            image=spec.image,
            status="running" if spec.detach else "created",
            state="running" if spec.detach else "created",
            labels=labels,
        )
        sim.logs.append(f"[sim] created {name} from {spec.image}")
        self._containers[cid] = sim
        self._images.add(spec.image)
        return self._to_summary(sim)

    async def start_container(self, container_id: str) -> ContainerSummary:
        sim = self._resolve(container_id)
        sim.status = "running"
        sim.state = "running"
        sim.logs.append(f"[sim] started {sim.name}")
        return self._to_summary(sim)

    async def stop_container(self, container_id: str, *, timeout_s: int = 10) -> ContainerSummary:
        sim = self._resolve(container_id)
        sim.status = "exited"
        sim.state = "exited"
        sim.logs.append(f"[sim] stopped {sim.name} (timeout={timeout_s})")
        return self._to_summary(sim)

    async def restart_container(
        self, container_id: str, *, timeout_s: int = 10
    ) -> ContainerSummary:
        sim = self._resolve(container_id)
        sim.status = "running"
        sim.state = "running"
        sim.logs.append(f"[sim] restarted {sim.name}")
        return self._to_summary(sim)

    async def remove_container(self, container_id: str, *, force: bool = False) -> None:
        sim = self._resolve(container_id)
        if sim.state == "running" and not force:
            raise ValueError(f"container {sim.name} is running; use force=true")
        del self._containers[sim.id]

    async def container_logs(
        self,
        container_id: str,
        *,
        tail: int = 100,
        since: str | None = None,
        stdout: bool = True,
        stderr: bool = True,
    ) -> str:
        sim = self._resolve(container_id)
        lines = sim.logs[-tail:] if tail else sim.logs
        return "\n".join(lines)

    async def exec_in_container(
        self,
        container_id: str,
        command: list[str],
        *,
        environment: dict[str, str] | None = None,
        workdir: str | None = None,
    ) -> ExecResult:
        sim = self._resolve(container_id)
        joined = " ".join(command)
        sim.logs.append(f"[sim] exec: {joined}")
        return ExecResult(exit_code=0, stdout=f"simulated exec: {joined}\n", stderr="")

    async def pull_image(self, image: str) -> dict[str, Any]:
        self._images.add(image)
        return {"status": "success", "image": image, "progress": ["Pull complete (simulated)"]}

    async def list_images(self) -> list[dict[str, Any]]:
        return [
            {"id": f"sim-{i}", "tags": [img], "size": 0}
            for i, img in enumerate(sorted(self._images))
        ]

    async def compose_up(self, spec: ComposeProvisionSpec) -> dict[str, Any]:
        service = (spec.services or ["app"])[0]
        summary = await self.create_container(
            ContainerProvisionSpec(image=f"compose/{service}:latest", name=f"compose-{service}")
        )
        return {
            "status": "success",
            "simulated": True,
            "services": spec.services or ["app"],
            "containers": [summary.model_dump()],
            "project_dir": spec.project_dir or "/tmp/dcd-sim-compose",
        }

    async def compose_down(
        self,
        *,
        project_dir: str | None = None,
        compose_file: str | None = None,
        remove_volumes: bool = False,
    ) -> dict[str, Any]:
        del compose_file
        removed = []
        for cid, sim in list(self._containers.items()):
            if sim.name.startswith("compose-"):
                del self._containers[cid]
                removed.append(sim.name)
        return {
            "status": "success",
            "simulated": True,
            "removed": removed,
            "remove_volumes": remove_volumes,
        }

    async def stream_container_logs(
        self,
        container_id: str,
        *,
        tail: int = 100,
        since: str | None = None,
        stop: asyncio.Event,
        on_line: Callable[[str, str], Awaitable[None]],
    ) -> None:
        del since
        sim = self._resolve(container_id)
        lines = sim.logs[-tail:] if tail else sim.logs
        for line in lines:
            if stop.is_set():
                return
            await on_line("stdout", line)
        while not stop.is_set():
            await asyncio.sleep(0.2)

    def _resolve(self, container_id: str) -> _SimContainer:
        if container_id in self._containers:
            return self._containers[container_id]
        for sim in self._containers.values():
            if sim.name == container_id or sim.name == container_id.lstrip("/"):
                return sim
        raise KeyError(f"container not found: {container_id}")

    @staticmethod
    def _to_summary(sim: _SimContainer) -> ContainerSummary:
        return ContainerSummary(
            id=sim.id,
            name=sim.name,
            image=sim.image,
            status=sim.status,
            state=sim.state,
            labels=sim.labels,
            managed_by_dcd=sim.labels.get(DCD_MANAGED_LABEL) == "true",
            created=sim.created,
        )


def build_docker_backend(
    *, simulate: bool = False, docker_host: str | None = None
) -> DockerBackend:
    if simulate:
        return SimDockerBackend()
    return DockerEngineBackend(base_url=docker_host)


def _parse_mem_limit(value: str) -> int:
    normalized = value.strip().lower()
    multipliers = {"k": 1024, "m": 1024**2, "g": 1024**3}
    if normalized[-1] in multipliers:
        return int(float(normalized[:-1]) * multipliers[normalized[-1]])
    return int(normalized)


def _compose_command() -> list[str]:
    if shutil.which("docker"):
        return ["docker", "compose"]
    raise RuntimeError("docker compose CLI not found on PATH")
