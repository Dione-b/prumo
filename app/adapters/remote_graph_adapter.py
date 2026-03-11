# Copyright (C) 2026 Dione Bastos
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


from __future__ import annotations

import time
from collections.abc import Callable

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.config import settings
from app.ports.graph_port import ClusterEdge, ClusterNode, ClusterResult, GraphClusteringPort

logger = structlog.get_logger()


class ClusterNodePayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(..., min_length=1)


class ClusterEdgePayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    weight: float = 1.0


class ClusterRequestPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    nodes: list[ClusterNodePayload]
    edges: list[ClusterEdgePayload]


class ClusterResponsePayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    assignments: dict[str, int]
    num_communities: int
    processed_nodes: int
    processed_edges: int


class RemoteGraphAdapter(GraphClusteringPort):
    """ACL over the remote graph worker HTTP contract."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        client_factory: Callable[..., httpx.AsyncClient] | None = None,
    ) -> None:
        self._base_url = (base_url or settings.graph_worker_url).rstrip("/")
        self._timeout_seconds = (
            timeout_seconds or settings.graph_worker_timeout_seconds
        )
        self._max_retries = (
            settings.graph_worker_max_retries if max_retries is None else max_retries
        )
        self._client_factory = client_factory or httpx.AsyncClient

    async def cluster(
        self,
        nodes: list[ClusterNode],
        edges: list[ClusterEdge],
    ) -> ClusterResult:
        payload = ClusterRequestPayload(
            nodes=[ClusterNodePayload(id=node.id) for node in nodes],
            edges=[
                ClusterEdgePayload(
                    source=edge.source,
                    target=edge.target,
                    weight=edge.weight,
                )
                for edge in edges
            ],
        )
        start_time = time.monotonic()

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_fixed(0.5),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)
            ),
            reraise=True,
        ):
            with attempt:
                response_payload = await self._post_cluster_request(payload)
                logger.info(
                    "graph_worker_cluster_success",
                    attempt=attempt.retry_state.attempt_number,
                    processed_nodes=response_payload.processed_nodes,
                    processed_edges=response_payload.processed_edges,
                    elapsed_ms=round((time.monotonic() - start_time) * 1000, 2),
                )
                return ClusterResult(
                    assignments=response_payload.assignments,
                    num_communities=response_payload.num_communities,
                    processed_nodes=response_payload.processed_nodes,
                    processed_edges=response_payload.processed_edges,
                )

        raise RuntimeError("Graph worker retry loop exited unexpectedly")

    async def _post_cluster_request(
        self,
        payload: ClusterRequestPayload,
    ) -> ClusterResponsePayload:
        timeout = httpx.Timeout(self._timeout_seconds)
        async with self._client_factory(base_url=self._base_url, timeout=timeout) as client:
            response = await client.post(
                "/api/v1/cluster",
                json=payload.model_dump(),
            )
            response.raise_for_status()
            return ClusterResponsePayload.model_validate(response.json())
