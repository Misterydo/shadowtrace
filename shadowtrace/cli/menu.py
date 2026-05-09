from __future__ import annotations

import os
import shlex
import sys

from shadowtrace.cli.arguments import build_parser
from shadowtrace.cli.banner import banner
from shadowtrace.core.async_manager import async_manager
from shadowtrace.core.config import CONFIG, save_config
from shadowtrace.core.engine import correlation_score, engine
from shadowtrace.core.logger import console
from shadowtrace.modules.passive import PassiveIntelEngine
from shadowtrace.output.html_export import export_html
from shadowtrace.output.json_export import export_json
from shadowtrace.output.txt_export import export_csv, export_graphml
from shadowtrace.utils.formatter import profile_table


def help_menu() -> None:
    console.print("""
[bold cyan]Commands:[/bold cyan]
- scan <username>                  Scan username at all platforms
- scan -v <username>               Scan username variants
- scan --passive <username>        Passive search with OSINT dorks (Bing)
- scan --found <username>          Show only found after scan
- scan --conf <n> <username>       Show only found with confidence n+
- export <file.json>               Export last result to JSON
- export-csv <file.csv>            Export last result to CSV
- export-html <file.html>          Export last result to HTML
- export-graphml <file.graphml>    Export nodes/edges for Gephi/Neo4j
- set mode [passive|agg]           Set scan mode
- set tor [on|off]                 Enable Tor proxy mode
- set threads <n>                  Set concurrency
- clear                            Clear terminal
- exit                             Exit
""")


async def run_scan(username: str, *, variants: bool = False, passive: bool = False, only_found: bool = False, min_conf: int = 0) -> tuple[list[dict], list[dict]]:
    mode = "variants" if variants else "single"
    profiles, passive_results = await engine.scan_username(username, mode=mode, passive=passive)
    if not profiles or all(profile.get("status") != "FOUND" for profile in profiles):
        console.print("\n[bold yellow]Nenhum perfil encontrado nas plataformas principais.[/bold yellow]\n")
        for profile in profiles:
            console.print(f" {profile['site']} → status={profile.get('status')}, meta={profile.get('metadata')}")
            if profile.get("error"):
                console.print(f"[red]Erro: {profile['error']}")
    profile_table(profiles, only_found=only_found, min_confidence=min_conf)
    if len(profiles) > 1:
        console.print(f"[yellow]Identity Correlation Score: {correlation_score(profiles)}%[/yellow]")
    if passive_results:
        PassiveIntelEngine.rich_show(passive_results)
    return profiles, passive_results


async def main() -> None:
    await engine.initialize()
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "scan":
        profiles, _ = await run_scan(
            args.username,
            variants=args.variants,
            passive=args.passive,
            only_found=args.found,
            min_conf=args.conf,
        )
        if args.json:
            export_json(profiles, args.json)
        if args.csv:
            export_csv(profiles, args.csv)
        if args.html:
            export_html(profiles, args.html)
        if args.graphml:
            export_graphml(profiles, args.graphml)
        await engine.close()
        return
    await interactive_menu()


async def interactive_menu() -> None:
    banner()
    last_profiles: list[dict] = []
    try:
        while True:
            try:
                cmdinput = console.input("[magenta]ShadowTrace > [/magenta]").strip()
                if not cmdinput:
                    continue
                args = shlex.split(cmdinput)
                if cmdinput in ("exit", "quit"):
                    await engine.close()
                    return
                if cmdinput == "help":
                    help_menu()
                elif args[0] == "scan":
                    passive = "--passive" in args
                    variants = "-v" in args or "--variants" in args
                    only_found = "--found" in args
                    min_conf = 0
                    if "--conf" in args:
                        idx = args.index("--conf")
                        min_conf = int(args[idx + 1])
                    skip_next = False
                    username = None
                    for item in args[1:]:
                        if skip_next:
                            skip_next = False
                            continue
                        if item == "--conf":
                            skip_next = True
                            continue
                        if item not in {"-v", "--variants", "--passive", "--found"}:
                            username = item
                    if not username:
                        console.print("[red]Missing username. Ex: scan --passive YOURUSER")
                        continue
                    last_profiles, _ = await run_scan(username, variants=variants, passive=passive, only_found=only_found, min_conf=min_conf)
                elif args[0] == "export" and len(args) > 1:
                    export_json(last_profiles, args[1])
                elif args[0] == "export-csv" and len(args) > 1:
                    export_csv(last_profiles, args[1])
                elif args[0] == "export-html" and len(args) > 1:
                    export_html(last_profiles, args[1])
                elif args[0] == "export-graphml" and len(args) > 1:
                    export_graphml(last_profiles, args[1])
                elif args[:2] == ["set", "mode"] and len(args) > 2:
                    CONFIG.mode = args[2]
                    save_config(CONFIG)
                    console.print(f"[cyan]Mode set to {CONFIG.mode}")
                elif args[:2] == ["set", "tor"] and len(args) > 2:
                    CONFIG.tor = args[2] == "on"
                    save_config(CONFIG)
                    console.print("[cyan]Tor mode enabled!" if CONFIG.tor else "[cyan]Tor disabled!")
                elif args[:2] == ["set", "threads"] and len(args) > 2:
                    async_manager.resize(int(args[2]))
                    save_config(CONFIG)
                    console.print(f"[cyan]Threads: {CONFIG.threads}")
                elif cmdinput == "clear":
                    os.system("clear" if os.name != "nt" else "cls")
                    banner()
                else:
                    console.print("[red]Unknown command. Type 'help'")
            except KeyboardInterrupt:
                console.print("[red]\nInterrupted!")
                await engine.close()
                sys.exit(0)
            except Exception as exc:
                console.print(f"[red][Broke] {exc}")
    finally:
        await engine.close()
