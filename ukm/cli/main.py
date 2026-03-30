"""
ukm — Universal Kernel Manager CLI

Usage:
  ukm list [--family=<family>] [--installed] [--json] [--refresh]
  ukm search <pattern> [--json] [--refresh]
  ukm install <version> [--provider=<id>] [--flavor=<flavor>] [--yes]
  ukm remove  <version> [--provider=<id>] [--purge] [--yes]
  ukm hold    <version> [--provider=<id>]
  ukm unhold  <version> [--provider=<id>]
  ukm note    <version> <text> [--provider=<id>]
  ukm remove-old [--keep=<n>] [--purge] [--yes]
  ukm providers
  ukm info
  ukm notify [--provider=<id>]
  ukm notify-enable
  ukm notify-disable
  ukm notify-shell-install [--shell=<shell>]
  ukm notify-shell-uninstall [--shell=<shell>]
  ukm cpu
  ukm dkms [--json]
  ukm changelog <version> [--provider=<id>] [--flavor=<flavor>] [--json]
  ukm gentoo compile <src-path> [--genkernel] [--make] [--jobs=<n>]
  ukm gentoo configure <src-path> [--target=<target>]
  ukm gentoo sources
  ukm (-h | --help)
  ukm --version

Options:
  -h --help            Show this help.
  --version            Show version.
  --family=<family>    Filter by kernel family: mainline, xanmod, liquorix,
                       distro, gentoo, local [default: all].
  --installed          Show only installed kernels.
  --json               Output as JSON.
  --refresh            Force refresh of kernel index/cache.
  --provider=<id>      Specify provider ID explicitly.
  --flavor=<flavor>    Kernel flavor (generic, lowlatency, rt, v3, etc.).
  --yes                Skip confirmation prompts.
  --purge              Also remove config files on removal.
  --keep=<n>           Number of recent kernels to keep with remove-old [default: 1].
  --genkernel          Use genkernel for compilation (default if available).
  --make               Use raw make for compilation.
  --jobs=<n>           Parallel make jobs [default: auto].
  --target=<target>    Kernel config target [default: menuconfig].
  --shell=<shell>      Shell rc file to modify: bash, zsh, or path [default: auto].
"""

from __future__ import annotations

import sys
from pathlib import Path

from ukm import __version__
from ukm.cli import output as out
from ukm.core.kernel import KernelEntry, KernelFamily
from ukm.core.manager import KernelManager
from ukm.core.system import system_info


def main(argv: list[str] | None = None) -> int:
    try:
        from docopt import docopt
    except ImportError:
        print("docopt is required: pip install docopt", file=sys.stderr)
        return 1

    args = docopt(__doc__, argv=argv, version=__version__)

    out.set_quiet(False)
    out.set_json(bool(args.get("--json")))

    # Warn about secure boot before doing anything
    mgr = KernelManager()
    sb_warn = mgr.secure_boot_warning()
    if sb_warn:
        out.warn(sb_warn)

    # ------------------------------------------------------------------ info
    if args["info"]:
        return cmd_info(mgr)

    # ------------------------------------------------------------ providers
    if args["providers"]:
        return cmd_providers(mgr)

    # --------------------------------------------------------------- list
    if args["list"]:
        return cmd_list(mgr, args)

    # ------------------------------------------------------------- search
    if args["search"]:
        return cmd_search(mgr, args)

    # ------------------------------------------------------------ install
    if args["install"]:
        return cmd_install(mgr, args)

    # ------------------------------------------------------------- remove
    if args["remove"] and not args["remove-old"]:
        return cmd_remove(mgr, args)

    # --------------------------------------------------------- remove-old
    if args["remove-old"]:
        return cmd_remove_old(mgr, args)

    # --------------------------------------------------------------- hold
    if args["hold"]:
        return cmd_hold(mgr, args, hold=True)

    # ------------------------------------------------------------- unhold
    if args["unhold"]:
        return cmd_hold(mgr, args, hold=False)

    # --------------------------------------------------------------- note
    if args["note"]:
        return cmd_note(mgr, args)

    # ------------------------------------------------------------ notify
    if args["notify"]:
        return cmd_notify(args)

    if args["notify-enable"]:
        return cmd_notify_enable()

    if args["notify-disable"]:
        return cmd_notify_disable()

    if args["notify-shell-install"]:
        return cmd_notify_shell_install(args)

    if args["notify-shell-uninstall"]:
        return cmd_notify_shell_uninstall(args)

    # --------------------------------------------------------------- cpu
    if args["cpu"]:
        return cmd_cpu()

    # -------------------------------------------------------------- dkms
    if args["dkms"]:
        return cmd_dkms()

    # --------------------------------------------------------- changelog
    if args["changelog"]:
        return cmd_changelog(mgr, args)

    # ------------------------------------------------------------- gentoo
    if args["gentoo"]:
        return cmd_gentoo(mgr, args)

    return 0


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def _dkms_summary() -> str:
    from ukm.core.dkms import status_summary

    return status_summary()


def cmd_info(mgr: KernelManager) -> int:
    info = system_info()
    from ukm.core.cpu import recommended_xanmod_level

    xanmod_level = recommended_xanmod_level() if info.arch == "amd64" else "n/a"
    data = {
        "distro": info.distro.name,
        "distro_id": info.distro.id,
        "distro_family": info.distro.family.value,
        "arch": info.arch,
        "arch_raw": info.arch_raw,
        "package_manager": info.package_manager.value,
        "running_kernel": info.running_kernel,
        "secure_boot": info.has_secure_boot,
        "pkexec": info.has_pkexec,
        "sudo": info.has_sudo,
        "recommended_xanmod": xanmod_level,
        "dkms": _dkms_summary(),
    }
    if out._json_mode:
        out.print_json(data)
    else:
        col_w = max(len(k) for k in data) + 2
        for k, v in data.items():
            out.info(f"  {k:<{col_w}} {v}")
    return 0


def cmd_providers(mgr: KernelManager) -> int:
    rows = []
    for p in mgr.providers:
        avail = p.is_available()
        rows.append(
            {
                "id": p.id,
                "name": p.display_name,
                "family": p.family.value,
                "arches": ", ".join(p.supported_arches),
                "available": "yes" if avail else "no",
                "reason": "" if avail else p.availability_reason(),
            }
        )
    if out._json_mode:
        out.print_json(rows)
    else:
        out.print_table(
            rows,
            [
                ("id", "ID"),
                ("name", "Name"),
                ("family", "Family"),
                ("arches", "Arches"),
                ("available", "Available"),
            ],
        )
        for r in rows:
            if r["reason"]:
                out.warn(f"{r['id']}: {r['reason']}")
    return 0


def cmd_list(mgr: KernelManager, args: dict) -> int:
    refresh = bool(args.get("--refresh"))
    family_str = args.get("--family")
    installed_only = bool(args.get("--installed"))

    entries = mgr.list_all(refresh=refresh)

    if family_str:
        try:
            family = KernelFamily(family_str.lower())
            entries = [e for e in entries if e.family == family]
        except ValueError:
            out.error(
                f"Unknown family '{family_str}'. Valid: {', '.join(f.value for f in KernelFamily)}"
            )
            return 1

    if installed_only:
        entries = [e for e in entries if e.is_installed]

    rows = [_entry_to_row(e) for e in entries]

    if out._json_mode:
        out.print_json(rows)
    else:
        out.print_table(
            rows,
            [
                ("version", "Version"),
                ("flavor", "Flavor"),
                ("family", "Family"),
                ("arch", "Arch"),
                ("status", "Status"),
                ("held", "Held"),
                ("provider", "Provider"),
                ("notes", "Notes"),
            ],
        )
        out.info(f"\n  {len(entries)} kernel(s) listed.")
    return 0


def cmd_search(mgr: KernelManager, args: dict) -> int:
    pattern = args["<pattern>"]
    refresh = bool(args.get("--refresh"))

    entries = mgr.search(pattern, refresh=refresh)

    rows = [_entry_to_row(e) for e in entries]

    if out._json_mode:
        out.print_json(rows)
    else:
        out.print_table(
            rows,
            [
                ("version", "Version"),
                ("flavor", "Flavor"),
                ("family", "Family"),
                ("arch", "Arch"),
                ("status", "Status"),
                ("provider", "Provider"),
            ],
        )
        out.info(f"\n  {len(entries)} kernel(s) matched '{pattern}'.")
    return 0


def cmd_install(mgr: KernelManager, args: dict) -> int:
    version = args["<version>"]
    provider_id = args.get("--provider")
    flavor = args.get("--flavor") or ""
    yes = bool(args.get("--yes"))

    entry = _find_entry(mgr, version, provider_id, flavor)
    if entry is None:
        out.error(f"Kernel '{version}' not found. Run 'ukm list' to see available kernels.")
        return 1

    if entry.is_installed:
        out.warn(f"Kernel {entry.display_name} is already installed.")
        return 0

    if not yes:
        answer = input(f"Install {entry.display_name} from {entry.provider_id}? [y/N] ")
        if answer.lower() not in ("y", "yes"):
            out.info("Aborted.")
            return 0

    try:
        for line in mgr.install(entry):
            out.log(line)
        out.success(f"Kernel {entry.display_name} installed.")
    except RuntimeError as e:
        out.error(str(e))
        return 1
    return 0


def cmd_remove(mgr: KernelManager, args: dict) -> int:
    version = args["<version>"]
    provider_id = args.get("--provider")
    purge = bool(args.get("--purge"))
    yes = bool(args.get("--yes"))

    entry = _find_installed(mgr, version, provider_id)
    if entry is None:
        out.error(f"Installed kernel '{version}' not found.")
        return 1

    if entry.is_running:
        out.error("Cannot remove the currently running kernel.")
        return 1

    if entry.held:
        out.error(f"Kernel {entry.display_name} is locked. Run 'ukm unhold {version}' first.")
        return 1

    if not yes:
        answer = input(f"Remove {entry.display_name}? [y/N] ")
        if answer.lower() not in ("y", "yes"):
            out.info("Aborted.")
            return 0

    try:
        for line in mgr.remove(entry, purge=purge):
            out.log(line)
        out.success(f"Kernel {entry.display_name} removed.")
    except RuntimeError as e:
        out.error(str(e))
        return 1
    return 0


def cmd_remove_old(mgr: KernelManager, args: dict) -> int:
    keep = int(args.get("--keep") or 1)
    purge = bool(args.get("--purge"))
    yes = bool(args.get("--yes"))

    if not yes:
        answer = input(f"Remove all old kernels (keeping {keep} most recent + running)? [y/N] ")
        if answer.lower() not in ("y", "yes"):
            out.info("Aborted.")
            return 0

    try:
        for line in mgr.remove_old(keep=keep, purge=purge):
            out.log(line)
        out.success("Old kernels removed.")
    except RuntimeError as e:
        out.error(str(e))
        return 1
    return 0


def cmd_hold(mgr: KernelManager, args: dict, hold: bool) -> int:
    version = args["<version>"]
    provider_id = args.get("--provider")

    entry = _find_installed(mgr, version, provider_id)
    if entry is None:
        out.error(f"Installed kernel '{version}' not found.")
        return 1

    if hold:
        rc, out_s, err = mgr.hold(entry)
        verb = "held"
    else:
        rc, out_s, err = mgr.unhold(entry)
        verb = "unheld"

    if out_s:
        out.log(out_s)
    if err:
        out.warn(err)
    if rc != 0:
        out.error(f"Operation failed (exit {rc})")
        return 1
    out.success(f"Kernel {entry.display_name} {verb}.")
    return 0


def cmd_note(mgr: KernelManager, args: dict) -> int:
    version = args["<version>"]
    text = args["<text>"]
    provider_id = args.get("--provider")

    entry = _find_entry(mgr, version, provider_id, "")
    if entry is None:
        out.error(f"Kernel '{version}' not found.")
        return 1

    mgr.set_note(entry, text)
    out.success(f"Note saved for {entry.display_name}.")
    return 0


def cmd_cpu() -> int:
    from ukm.core.cpu import cpu_summary

    data = cpu_summary()
    if out._json_mode:
        out.print_json(data)
    else:
        out.info(f"  Recommended XanMod level : {data['recommended_xanmod_level']}")
        out.info(f"  Description              : {data['description']}")
        out.info(f"  AVX-512                  : {'yes' if data['has_avx512'] else 'no'}")
        out.info(f"  AVX2                     : {'yes' if data['has_avx2'] else 'no'}")
        out.info(f"  SSE4.2                   : {'yes' if data['has_sse4_2'] else 'no'}")
        out.info(f"  CPU flags detected       : {data['flag_count']}")
    return 0


def cmd_changelog(mgr: KernelManager, args: dict) -> int:
    from ukm.core.changelog import fetch

    version = args["<version>"]
    provider_id = args.get("--provider") or ""
    flavor = args.get("--flavor") or ""

    # Try to resolve provider_id from the kernel list if not given
    if not provider_id:
        entry = _find_entry(mgr, version, None, flavor)
        if entry:
            provider_id = entry.provider_id
            flavor = flavor or entry.flavor

    if not provider_id:
        out.error(f"Cannot determine provider for '{version}'. Use --provider=<id>.")
        return 1

    out.info(f"Fetching changelog for {version} ({provider_id})…")
    text = fetch(provider_id, version, flavor)
    if not text:
        out.warn("No changelog available for this kernel.")
        return 0

    if out._json_mode:
        out.print_json({"version": version, "provider": provider_id, "changelog": text})
    else:
        out.info(text)
    return 0


def cmd_dkms() -> int:
    from ukm.core import dkms

    if not dkms.is_available():
        out.warn("dkms is not installed. Install it to enable automatic module rebuilds.")
        return 0
    modules = dkms.status()
    if not modules:
        out.info("No DKMS modules registered.")
        return 0
    rows = [
        {
            "name": m.name,
            "version": m.version,
            "kernel": m.kernel,
            "arch": m.arch,
            "status": m.status,
        }
        for m in modules
    ]
    if out._json_mode:
        out.print_json(rows)
    else:
        out.print_table(
            rows,
            [
                ("name", "Module"),
                ("version", "Version"),
                ("kernel", "Kernel"),
                ("arch", "Arch"),
                ("status", "Status"),
            ],
        )
    return 0


def cmd_notify(args: dict) -> int:
    from ukm.core.notify import check_and_notify

    provider_id = args.get("--provider") or "mainline_ppa"
    sent = check_and_notify(provider_id=provider_id)
    if sent:
        out.success("Notification sent.")
    else:
        out.info("No notification sent (no newer kernel found or cooldown active).")
    return 0


def cmd_notify_enable() -> int:
    """Install and enable the systemd user timer for background notifications."""
    import shutil
    import subprocess

    systemd_user_dir = Path.home() / ".config" / "systemd" / "user"
    systemd_user_dir.mkdir(parents=True, exist_ok=True)

    share_dir = Path(__file__).parent.parent.parent / "share" / "systemd"
    units = ["ukm-notify.service", "ukm-notify.timer"]

    for unit in units:
        src = share_dir / unit
        dst = systemd_user_dir / unit
        if not src.exists():
            out.error(f"Unit file not found: {src}")
            return 1
        shutil.copy2(src, dst)
        out.info(f"  Installed {dst}")

    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "--user", "enable", "--now", "ukm-notify.timer"], check=False)
        out.success("ukm-notify.timer enabled and started.")
        out.info("  ukm will check for new kernels every 12 hours.")
    else:
        out.warn("systemctl not found. Add ukm-notify.timer to your session startup manually.")
    return 0


def cmd_notify_disable() -> int:
    """Disable and remove the systemd user timer."""
    import shutil
    import subprocess

    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "disable", "--now", "ukm-notify.timer"], check=False)

    systemd_user_dir = Path.home() / ".config" / "systemd" / "user"
    for unit in ["ukm-notify.service", "ukm-notify.timer"]:
        f = systemd_user_dir / unit
        if f.exists():
            f.unlink()
            out.info(f"  Removed {f}")

    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)

    out.success("ukm notifications disabled.")
    return 0


def _shell_rc_files(shell_hint: str | None) -> list:
    """
    Return the list of shell rc files to modify.
    shell_hint can be 'bash', 'zsh', 'fish', or an explicit path.
    When None/'auto', all present rc files are returned.
    """
    home = Path.home()
    candidates = {
        "bash": [home / ".bashrc", home / ".bash_profile"],
        "zsh": [home / ".zshrc"],
        "fish": [home / ".config" / "fish" / "config.fish"],
    }

    if shell_hint and shell_hint not in ("auto", ""):
        if shell_hint in candidates:
            return [f for f in candidates[shell_hint] if f.exists() or f == candidates[shell_hint][0]]
        # Treat as explicit path
        return [Path(shell_hint)]

    # Auto: return all rc files that exist
    result = []
    for files in candidates.values():
        result.extend(f for f in files if f.exists())
    return result


_SHELL_MARKER_BEGIN = "# >>> ukm login-check begin <<<"
_SHELL_MARKER_END = "# >>> ukm login-check end <<<"


def _snippet_path() -> Path:
    """Return the path to the bundled ukm-login-check.sh snippet."""
    return Path(__file__).parent.parent.parent / "share" / "shell" / "ukm-login-check.sh"


def cmd_notify_shell_install(args: dict) -> int:
    """
    Append a login-time kernel update check snippet to the user's shell rc file(s).
    Uses a begin/end marker so it can be cleanly removed later.
    """
    shell_hint = args.get("--shell") or "auto"
    snippet_src = _snippet_path()

    if not snippet_src.exists():
        out.error(f"Snippet file not found: {snippet_src}")
        return 1

    rc_files = _shell_rc_files(shell_hint)
    if not rc_files:
        out.warn("No shell rc files found. Pass --shell=bash or --shell=zsh explicitly.")
        return 1

    snippet_line = f'. "{snippet_src}"'
    block = f"\n{_SHELL_MARKER_BEGIN}\n{snippet_line}\n{_SHELL_MARKER_END}\n"

    installed_any = False
    for rc in rc_files:
        content = rc.read_text() if rc.exists() else ""
        if _SHELL_MARKER_BEGIN in content:
            out.info(f"  {rc}: already installed, skipping.")
            continue
        rc.parent.mkdir(parents=True, exist_ok=True)
        with rc.open("a") as f:
            f.write(block)
        out.success(f"  Installed login check in {rc}")
        installed_any = True

    if installed_any:
        out.info("  Restart your shell or run: source ~/.bashrc")
        out.info("  To remove: ukm notify-shell-uninstall")
    return 0


def cmd_notify_shell_uninstall(args: dict) -> int:
    """Remove the ukm login-check snippet from shell rc file(s)."""
    shell_hint = args.get("--shell") or "auto"
    rc_files = _shell_rc_files(shell_hint)

    removed_any = False
    for rc in rc_files:
        if not rc.exists():
            continue
        content = rc.read_text()
        if _SHELL_MARKER_BEGIN not in content:
            continue
        # Strip the block between markers (inclusive)
        import re
        new_content = re.sub(
            rf"\n?{re.escape(_SHELL_MARKER_BEGIN)}.*?{re.escape(_SHELL_MARKER_END)}\n?",
            "",
            content,
            flags=re.DOTALL,
        )
        rc.write_text(new_content)
        out.success(f"  Removed login check from {rc}")
        removed_any = True

    if not removed_any:
        out.info("No ukm login-check snippet found in any shell rc file.")
    return 0


def cmd_gentoo(mgr: KernelManager, args: dict) -> int:
    from ukm.core.providers.gentoo import GentooProvider

    provider = next((p for p in mgr.providers if isinstance(p, GentooProvider)), None)
    if provider is None:
        out.error("Gentoo provider is not available on this system.")
        return 1

    if args["sources"]:
        sources = provider._portage.list_kernel_sources()
        if not sources:
            out.info("No kernel source trees found under /usr/src/.")
        for s in sources:
            out.info(f"  {s}")
        return 0

    if args["configure"]:
        src = args["<src-path>"]
        target = args.get("--target") or "menuconfig"
        cmd = provider.configure_cmd(src, target)
        out.info(f"Run this command in a terminal:\n  {' '.join(cmd)}")
        return 0

    if args["compile"]:
        src = args["<src-path>"]
        use_make = bool(args.get("--make"))
        use_genkernel = not use_make
        jobs = int(args.get("--jobs") or 0)
        try:
            for line in provider.compile(src, use_genkernel=use_genkernel, jobs=jobs):
                out.log(line)
            out.success("Compilation complete.")
        except RuntimeError as e:
            out.error(str(e))
            return 1
        return 0

    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry_to_row(e: KernelEntry) -> dict:
    return {
        "version": str(e.version),
        "flavor": e.flavor,
        "family": e.family.value,
        "arch": e.arch,
        "status": e.status.name.lower(),
        "held": "yes" if e.held else "",
        "provider": e.provider_id,
        "notes": e.notes[:40] + "…" if len(e.notes) > 40 else e.notes,
    }


def _find_entry(
    mgr: KernelManager,
    version: str,
    provider_id: str | None,
    flavor: str,
) -> KernelEntry | None:
    entries = mgr.list_all()
    candidates = [
        e
        for e in entries
        if version in str(e.version)
        and (not provider_id or e.provider_id == provider_id)
        and (not flavor or e.flavor == flavor)
    ]
    if not candidates:
        return None
    # Prefer exact version match
    exact = [e for e in candidates if str(e.version) == version]
    return exact[0] if exact else candidates[0]


def _find_installed(
    mgr: KernelManager,
    version: str,
    provider_id: str | None,
) -> KernelEntry | None:
    entries = [e for e in mgr.list_installed() if version in str(e.version)]
    if provider_id:
        entries = [e for e in entries if e.provider_id == provider_id]
    if not entries:
        return None
    exact = [e for e in entries if str(e.version) == version]
    return exact[0] if exact else entries[0]


if __name__ == "__main__":
    sys.exit(main())
