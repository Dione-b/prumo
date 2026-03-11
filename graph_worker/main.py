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

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field


class ClusterNodeInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(..., min_length=1)


class ClusterEdgeInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    weight: float = 1.0


class ClusterRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    nodes: list[ClusterNodeInput]
    edges: list[ClusterEdgeInput]


class ClusterResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    assignments: dict[str, int]
    num_communities: int
    processed_nodes: int
    processed_edges: int


app = FastAPI(
    title="Prumo Graph Worker",
    version="0.1.0",
    description="Stateless Leiden clustering worker isolated from the Prumo core.",
)


def _cluster_graph(payload: ClusterRequest) -> ClusterResponse:
    import igraph as ig  # type: ignore[import-untyped]
    import leidenalg  # type: ignore[import-untyped]

    node_ids = [node.id for node in payload.nodes]
    id_to_idx = {node_id: index for index, node_id in enumerate(node_ids)}

    graph = ig.Graph(directed=False)
    graph.add_vertices(len(node_ids))

    edge_list: list[tuple[int, int]] = []
    weights: list[float] = []

    for edge in payload.edges:
        source_idx = id_to_idx.get(edge.source)
        target_idx = id_to_idx.get(edge.target)
        if source_idx is None or target_idx is None:
            continue
        edge_list.append((source_idx, target_idx))
        weights.append(edge.weight)

    if edge_list:
        graph.add_edges(edge_list)
        graph.es["weight"] = weights  # type: ignore[index]

    partition = leidenalg.find_partition(
        graph,
        leidenalg.ModularityVertexPartition,
        weights=weights if weights else None,
    )

    assignments = {
        node_ids[index]: community_id
        for community_id, members in enumerate(partition)
        for index in members
    }

    return ClusterResponse(
        assignments=assignments,
        num_communities=len(set(assignments.values())),
        processed_nodes=len(node_ids),
        processed_edges=len(edge_list),
    )


@app.post("/api/v1/cluster", response_model=ClusterResponse)
async def cluster(payload: ClusterRequest) -> ClusterResponse:
    return _cluster_graph(payload)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
