"""Device Connect docker_host RPC contract (functions + events)."""

from __future__ import annotations

REQUIRED_FUNCTIONS = frozenset(
    {
        "get_status",
        "ping_docker",
        "list_containers",
        "get_container",
        "provision_container",
        "start_container",
        "stop_container",
        "restart_container",
        "remove_container",
        "container_logs",
        "stop_container_logs",
        "exec_in_container",
        "pull_image",
        "list_images",
        "compose_up",
        "compose_down",
        "list_managed_containers",
    }
)

REQUIRED_EVENTS = frozenset(
    {
        "container_state_changed",
        "container_log_line",
    }
)

# Pinned in pyproject.toml; CI matrix may install other versions to verify compatibility.
PINNED_DEVICE_CONNECT_EDGE = "0.2.2"
