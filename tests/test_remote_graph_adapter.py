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

import httpx
import pytest

from app.adapters.remote_graph_adapter import RemoteGraphAdapter
from app.ports.graph_port import ClusterEdge, ClusterNode


class FakeAsyncClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout: httpx.Timeout,
        outcomes: list[object],
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self._outcomes = outcomes

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, path: str, json: dict[str, object]) -> httpx.Response:
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _response(
    status_code: int,
    payload: dict[str, object],
) -> httpx.Response:
    request = httpx.Request("POST", "http://graph-worker/api/v1/cluster")
    return httpx.Response(status_code, json=payload, request=request)


@pytest.mark.asyncio
async def test_remote_graph_adapter_clusters_successfully() -> None:
    outcomes: list[object] = [
        _response(
            200,
            {
                "assignments": {"n1": 0, "n2": 1},
                "num_communities": 2,
                "processed_nodes": 2,
                "processed_edges": 1,
            },
        )
    ]
    adapter = RemoteGraphAdapter(
        base_url="http://graph-worker",
        timeout_seconds=5.0,
        max_retries=0,
        client_factory=lambda **kwargs: FakeAsyncClient(outcomes=outcomes, **kwargs),
    )

    result = await adapter.cluster(
        nodes=[ClusterNode(id="n1"), ClusterNode(id="n2")],
        edges=[ClusterEdge(source="n1", target="n2", weight=0.8)],
    )

    assert result.assignments == {"n1": 0, "n2": 1}
    assert result.num_communities == 2


@pytest.mark.asyncio
async def test_remote_graph_adapter_retries_on_timeout() -> None:
    outcomes: list[object] = [
        httpx.ReadTimeout("timeout"),
        _response(
            200,
            {
                "assignments": {"n1": 0},
                "num_communities": 1,
                "processed_nodes": 1,
                "processed_edges": 0,
            },
        ),
    ]
    adapter = RemoteGraphAdapter(
        base_url="http://graph-worker",
        timeout_seconds=5.0,
        max_retries=1,
        client_factory=lambda **kwargs: FakeAsyncClient(outcomes=outcomes, **kwargs),
    )

    result = await adapter.cluster(
        nodes=[ClusterNode(id="n1")],
        edges=[],
    )

    assert result.num_communities == 1
    assert outcomes == []


@pytest.mark.asyncio
async def test_remote_graph_adapter_raises_for_invalid_payload() -> None:
    outcomes: list[object] = [
        _response(
            200,
            {
                "assignments": {"n1": 0},
                "processed_nodes": 1,
                "processed_edges": 0,
            },
        )
    ]
    adapter = RemoteGraphAdapter(
        base_url="http://graph-worker",
        timeout_seconds=5.0,
        max_retries=0,
        client_factory=lambda **kwargs: FakeAsyncClient(outcomes=outcomes, **kwargs),
    )

    with pytest.raises(Exception):
        await adapter.cluster(
            nodes=[ClusterNode(id="n1")],
            edges=[],
        )
