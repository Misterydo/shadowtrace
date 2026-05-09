from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from shadowtrace.core.logger import console


def export_csv(profiles: list[dict[str, Any]], path: str | Path) -> None:
    target = Path(path)
    fieldnames = ["site", "username", "url", "status", "confidence", "avatar_hash", "metadata"]
    with target.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for profile in profiles:
            row = {field: profile.get(field, "") for field in fieldnames}
            row["metadata"] = json.dumps(profile.get("metadata", {}), ensure_ascii=False)
            writer.writerow(row)
    console.print(f"[green]CSV saved at {target}")


def export_graphml(profiles: list[dict[str, Any]], path: str | Path) -> None:
    target = Path(path)
    nodes: dict[str, dict[str, str]] = {}
    edges: set[tuple[str, str, str]] = set()
    for profile in profiles:
        username, site = profile["username"], profile["site"]
        node_id = f"{username}@{site}"
        nodes[node_id] = {"label": node_id}
        nodes[site] = {"label": site}
        edges.add((node_id, site, "on"))
    for left in profiles:
        for right in profiles:
            if left is right:
                continue
            if left.get("avatar_hash") and left["avatar_hash"] == right.get("avatar_hash") and left["site"] != right["site"]:
                edges.add((f"{left['username']}@{left['site']}", f"{right['username']}@{right['site']}", "same_avatar"))
    with target.open("w", encoding="utf-8") as handle:
        handle.write('<?xml version="1.0" encoding="UTF-8"?>\n<graphml xmlns="http://graphml.graphdrawing.org/xmlns">\n')
        handle.write('<graph id="ShadowTrace" edgedefault="undirected">\n')
        for node_id, data in nodes.items():
            handle.write(f'<node id="{node_id}"><data key="label">{data["label"]}</data></node>\n')
        for source, target_node, edge_type in edges:
            handle.write(f'<edge source="{source}" target="{target_node}"><data key="type">{edge_type}</data></edge>\n')
        handle.write("</graph></graphml>")
    console.print(f"[green]GraphML export ready: {target}")
