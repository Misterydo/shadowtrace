from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ShadowTrace modular OSINT toolkit")
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser("scan", help="Scan a username")
    scan.add_argument("username")
    scan.add_argument("-v", "--variants", action="store_true", help="Scan smart username variants")
    scan.add_argument("--passive", action="store_true", help="Enable passive Bing dork enrichment")
    scan.add_argument("--found", action="store_true", help="Show only found profiles")
    scan.add_argument("--conf", type=int, default=0, help="Minimum confidence")
    scan.add_argument("--json", help="Write JSON output")
    scan.add_argument("--csv", help="Write CSV output")
    scan.add_argument("--html", help="Write HTML output")
    scan.add_argument("--graphml", help="Write GraphML output")
    return parser
