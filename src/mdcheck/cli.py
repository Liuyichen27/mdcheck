"""mdcheck 命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, _update, core


def collect(paths: list[str]) -> list[Path]:
    """把目录里的 markdown 收进来。"""
    out: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_file():
            out.append(p)
            continue
        if p.is_dir():
            skip = {".git", "node_modules", "__pycache__", ".venv", "venv"}
            for f in sorted(p.rglob("*.md")):
                if any(part in skip for part in f.parts):
                    continue
                out.append(f)
            for f in sorted(p.rglob("*.markdown")):
                if any(part in skip for part in f.parts):
                    continue
                out.append(f)
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mdcheck",
        description="Markdown 体检：代码块、标题层级、死链；可选生成目录。",
        epilog="例子：mdcheck . --toc --write",
    )
    p.add_argument("paths", nargs="+", help="markdown 文件或目录")
    p.add_argument("-t", "--toc", action="store_true", help="生成目录")
    p.add_argument("-w", "--write", action="store_true",
                   help="配合 --toc，把目录写回 <!-- toc --> 与 <!-- /toc --> 之间")
    p.add_argument("--no-links", action="store_true", help="跳过链接检查")
    p.add_argument("--min-level", type=int, default=1, help="目录收录的最小标题层级")
    p.add_argument("--max-level", type=int, default=3, help="目录收录的最大标题层级")
    p.add_argument("-q", "--quiet", action="store_true", help="只输出有问题的文件")
    p.add_argument("-V", "--version", action="version", version=f"mdcheck {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    files = collect(args.paths)
    if not files:
        print("没有找到 markdown 文件", file=sys.stderr)
        return 2

    total_errors = 0
    total_warns = 0
    touched = 0

    for f in files:
        issues, wrote = core.process(
            f,
            check_links=not args.no_links,
            make_toc=args.toc,
            write=args.write,
            min_level=args.min_level,
            max_level=args.max_level,
        )
        if wrote:
            touched += 1
            print(f"{f}  目录已更新")

        errors = [i for i in issues if i.level == "error"]
        warns = [i for i in issues if i.level == "warn"]
        total_errors += len(errors)
        total_warns += len(warns)

        if issues:
            print(f"\n{f}")
            for i in sorted(issues, key=lambda x: x.line):
                print(i)
        elif not args.quiet:
            print(f"{f}  ✓ 通过")

    print()
    parts = []
    if touched:
        parts.append(f"更新了 {touched} 个文件的目录")
    parts.append(f"{len(files)} 个文件")
    parts.append(f"{total_errors} 个错误")
    parts.append(f"{total_warns} 个提醒")
    print("，".join(parts))

    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
