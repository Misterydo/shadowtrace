from __future__ import annotations

from rich import box
from rich.table import Table

from shadowtrace.core.logger import console


def profile_table(profiles: list[dict], only_found: bool = False, min_confidence: int = 0) -> None:
    table = Table(title="ShadowTrace OSINT", box=box.DOUBLE)
    table.add_column("Platform")
    table.add_column("Username")
    table.add_column("Found", justify="center")
    table.add_column("Confidence")
    table.add_column("Lang")
    table.add_column("Avatar Hash")
    table.add_column("Profile Link")
    for profile in profiles:
        found = profile.get("status") == "FOUND"
        if only_found and not found:
            continue
        if profile.get("confidence", 0) < min_confidence:
            continue
        table.add_row(
            profile["site"],
            profile["username"],
            "[green]YES" if found else "[red]NO",
            f"{profile.get('confidence', 0)}%",
            profile.get("metadata", {}).get("lang_bio") or "-",
            profile.get("avatar_hash") or "-",
            f"[blue underline]{profile['url']}[/blue underline]",
        )
    console.print(table)


def filter_profiles(profiles: list[dict], only_found: bool = False, min_confidence: int = 0) -> list[dict]:
    return [
        profile for profile in profiles
        if (not only_found or profile.get("status") == "FOUND")
        and profile.get("confidence", 0) >= min_confidence
    ]
