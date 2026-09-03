"""Read-only connectivity diagnostics for OpenCascade shapes."""

from __future__ import annotations


def analyze_connectivity(shape) -> dict[str, object]:
    """Report face connectivity and boundary edges without changing *shape*."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_FORWARD, TopAbs_REVERSED
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

    edge_faces = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_faces)

    boundary_edges = 0
    manifold_edges = 0
    non_manifold_edges = 0
    oriented_forward_edges = 0
    oriented_reversed_edges = 0

    for index in range(1, edge_faces.Extent() + 1):
        edge = edge_faces.FindKey(index)
        face_uses = edge_faces.FindFromIndex(index)
        use_count = face_uses.Size()
        if use_count == 1:
            boundary_edges += 1
        elif use_count == 2:
            manifold_edges += 1
        else:
            non_manifold_edges += 1
        if edge.Orientation() == TopAbs_FORWARD:
            oriented_forward_edges += 1
        elif edge.Orientation() == TopAbs_REVERSED:
            oriented_reversed_edges += 1

    # A graph component represents faces connected through shared topology.
    components = _face_components(edge_faces)
    return {
        "unique_edges_with_face_ancestors": edge_faces.Extent(),
        "boundary_edges": boundary_edges,
        "manifold_shared_edges": manifold_edges,
        "non_manifold_edges": non_manifold_edges,
        "face_components": len(components),
        "component_face_counts": sorted((len(c) for c in components), reverse=True),
        "edge_orientations": {
            "forward": oriented_forward_edges,
            "reversed": oriented_reversed_edges,
        },
        "is_closed_by_shared_topology": boundary_edges == 0 and non_manifold_edges == 0,
    }


def _face_components(edge_faces) -> list[set[int]]:
    """Build connected face groups using shared edges as graph links."""
    adjacency: dict[int, set[int]] = {}
    known_faces: set[int] = set()
    face_ids: dict[object, int] = {}

    def face_id(face) -> int:
        key = hash(face)
        if key not in face_ids:
            face_ids[key] = len(face_ids) + 1
        return face_ids[key]

    for index in range(1, edge_faces.Extent() + 1):
        faces = edge_faces.FindFromIndex(index)
        ids = [face_id(face) for face in faces]
        known_faces.update(ids)
        for current in ids:
            adjacency.setdefault(current, set()).update(other for other in ids if other != current)

    components: list[set[int]] = []
    unseen = set(known_faces)
    while unseen:
        component: set[int] = set()
        stack = [unseen.pop()]
        while stack:
            current = stack.pop()
            component.add(current)
            for neighbor in adjacency.get(current, set()):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    stack.append(neighbor)
        components.append(component)
    return components
