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

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.ports.graph_port import ClusterResult
from app.services.community_detector import run_community_detection


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def one(self):
        return self._rows

    def all(self):
        return self._rows


class FakeGraphClusteringPort:
    def __init__(self) -> None:
        self.calls: list[tuple[list[object], list[object]]] = []

    async def cluster(self, nodes, edges) -> ClusterResult:
        self.calls.append((nodes, edges))
        return ClusterResult(
            assignments={
                "node-1": 0,
                "node-2": 0,
                "node-3": 1,
                "node-4": 1,
                "node-5": 1,
            },
            num_communities=2,
            processed_nodes=5,
            processed_edges=2,
        )


@pytest.mark.asyncio
async def test_run_community_detection_uses_remote_port_and_persists_assignments() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            FakeResult((5, 2)),
            FakeResult(
                [
                    ("node-1",),
                    ("node-2",),
                    ("node-3",),
                    ("node-4",),
                    ("node-5",),
                ]
            ),
            FakeResult(
                [
                    ("node-1", "node-2", 0.7),
                    ("node-3", "node-4", 0.9),
                ]
            ),
            FakeResult([]),
            FakeResult([]),
            FakeResult([]),
            FakeResult([]),
            FakeResult([]),
        ]
    )
    session.flush = AsyncMock()
    graph_port = FakeGraphClusteringPort()

    communities = await run_community_detection(
        session=session,
        project_id="project-1",  # type: ignore[arg-type]
        graph_clustering_port=graph_port,
    )

    assert communities == 2
    assert len(graph_port.calls) == 1
    nodes, edges = graph_port.calls[0]
    assert [node.id for node in nodes] == [
        "node-1",
        "node-2",
        "node-3",
        "node-4",
        "node-5",
    ]
    assert [(edge.source, edge.target, edge.weight) for edge in edges] == [
        ("node-1", "node-2", 0.7),
        ("node-3", "node-4", 0.9),
    ]
    assert session.execute.await_count == 8
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_community_detection_skips_when_graph_is_too_small() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=FakeResult((1, 0)))
    session.flush = AsyncMock()
    graph_port = FakeGraphClusteringPort()

    communities = await run_community_detection(
        session=session,
        project_id="project-1",  # type: ignore[arg-type]
        graph_clustering_port=graph_port,
    )

    assert communities == 0
    assert graph_port.calls == []
    session.flush.assert_not_awaited()


def test_app_directory_has_no_gpl_graph_imports() -> None:
    app_dir = Path(__file__).resolve().parents[1] / "app"
    forbidden = ("import igraph", "import leidenalg")

    for path in app_dir.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in content, f"Forbidden token {token!r} found in {path}"
