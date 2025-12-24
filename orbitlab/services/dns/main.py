import argparse
import ipaddress
import tempfile
from pathlib import Path
from typing import Final

ROOT_DIR: Final = Path("/opt/coredns")
ZONE_FILE: Final = ROOT_DIR / "orbitlab.zone"
MANAGED_HEADER = "# --- OrbitLab managed entries ---"
MANAGED_FOOTER = "# --- End OrbitLab managed entries ---"

def parse_hosts_block(lines: list[str]) -> dict[str, set[str]]:
    entries: dict[str, set[str]] = {}

    for line in lines:
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue

        parts = stripped_line.split()
        ip = parts[0]
        host_names = parts[1:]

        ipaddress.ip_address(ip)
        entries.setdefault(ip, set()).update(host_names)

    return entries


def render_hosts_block(entries: dict[str, set[str]]) -> list[str]:
    lines: list[str] = []

    for ip in sorted(entries, key=lambda x: ipaddress.ip_address(x)):
        names = sorted(entries[ip])
        lines.append(f"{ip} {' '.join(names)}")

    return lines


def load_existing() -> tuple[list[str], list[str], list[str]]:
    pre, managed, post = [], [], []
    section = "pre"

    for line in ZONE_FILE.read_text().splitlines():
        if line.strip() == MANAGED_HEADER:
            section = "managed"
            continue
        if line.strip() == MANAGED_FOOTER:
            section = "post"
            continue

        if section == "pre":
            pre.append(line)
        elif section == "managed":
            managed.append(line)
        else:
            post.append(line)

    return pre, managed, post


def write_zone(
    entries: dict[str, set[str]],
    pre: list[str],
    post: list[str],
) -> None:
    managed_lines = render_hosts_block(entries)

    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
        if pre:
            tmp.write("\n".join(pre).rstrip() + "\n")

        tmp.write(f"{MANAGED_HEADER}\n")
        for line in managed_lines:
            tmp.write(f"{line}\n")
        tmp.write(f"{MANAGED_FOOTER}\n")

        if post:
            tmp.write("\n".join(post).rstrip() + "\n")

    Path(tmp.name).replace(ZONE_FILE)


def cmd_create(args: argparse.Namespace) -> None:
    entries: dict[str, set[str]] = {}

    for ip in args.ip:
        ipaddress.ip_address(ip)
        entries[ip] = {args.hostname}

    write_zone(entries, [], [])


def cmd_update(args: argparse.Namespace) -> None:
    pre, managed, post = load_existing()
    entries = parse_hosts_block(managed)

    if args.add:
        entries.setdefault(args.ip, set()).add(args.hostname)

    if args.remove and args.ip in entries:
        entries[args.ip].discard(args.hostname)
        if not entries[args.ip]:
            del entries[args.ip]

    write_zone(entries, pre, post)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage CoreDNS hosts-style zone file for OrbitLab")

    sub = parser.add_subparsers(required=True)

    create = sub.add_parser("create", help="Create zone file")
    create.add_argument("--hostname", required=True)
    create.add_argument(
        "--ip",
        action="append",
        required=True,
    )
    create.set_defaults(func=cmd_create)

    update = sub.add_parser("update", help="Update zone file")
    update.add_argument("--ip", required=True)
    update.add_argument("--hostname", required=True)
    group = update.add_mutually_exclusive_group(required=True)
    group.add_argument("--add", action="store_true")
    group.add_argument("--remove", action="store_true")
    update.set_defaults(func=cmd_update)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
