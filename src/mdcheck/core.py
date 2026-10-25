"""检查与目录生成的核心逻辑。

刻意不追求「完整 Markdown 解析」——那是 cmark 的活。这里只做正则级别的检查，
好处是不依赖任何库、对大部分 README 够用，坏处是嵌套代码块里的假标题可能误报
（已经用「跳过围栏区域」规避）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

TOC_START = "<!-- toc -->"
TOC_END = "<!-- /toc -->"

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_LINK = re.compile(r"(?<!\!)\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_HTML_TAG = re.compile(r"<[^>]+>")


@dataclass
class Issue:
    line: int
    level: str      # "error" / "warn"
    message: str

    def __str__(self) -> str:
        mark = "✗" if self.level == "error" else "⚠"
        return f"  第 {self.line} 行 {mark} {self.message}"


@dataclass
class Heading:
    line: int
    level: int
    text: str

    @property
    def slug(self) -> str:
        return slugify(self.text)


def slugify(text: str) -> str:
    """按 GitHub 的规则把标题变成锚点：小写、去标点、空格变连字符。"""
    t = text.strip().lower()
    t = re.sub(r"`([^`]*)`", r"\1", t)          # 行内代码去掉反引号
    t = re.sub(r"\*\*([^*]*)\*\*", r"\1", t)     # 粗体
    t = re.sub(r"\*([^*]*)\*", r"\1", t)         # 斜体
    t = _HTML_TAG.sub("", t)                     # HTML 标签
    t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)
    t = re.sub(r"\s+", "-", t.strip())
    return t


def split_fences(lines: list[str]) -> list[bool]:
    """标出每一行是否在代码块内（含围栏本身），避免把代码里的 # 当标题。"""
    inside = [False] * len(lines)
    in_block = False
    for i, line in enumerate(lines):
        if _FENCE.match(line):
            inside[i] = True
            in_block = not in_block
            continue
        inside[i] = in_block
    return inside


def parse_headings(text: str) -> list[Heading]:
    lines = text.splitlines()
    inside = split_fences(lines)
    out: list[Heading] = []
    for i, line in enumerate(lines):
        if inside[i]:
            continue
        m = _HEADING.match(line)
        if m:
            out.append(Heading(i + 1, len(m.group(1)), m.group(2).strip()))
    return out


def check(text: str, path: Path, *, check_links: bool = True) -> list[Issue]:
    """跑一遍检查，返回问题列表。"""
    issues: list[Issue] = []
    lines = text.splitlines()
    inside = split_fences(lines)

    # 1. 围栏是否配对
    fence_lines = [i + 1 for i, l in enumerate(lines) if _FENCE.match(l)]
    if len(fence_lines) % 2:
        issues.append(Issue(fence_lines[-1], "error",
                            f"代码块围栏 ``` 没有闭合（全文共 {len(fence_lines)} 个围栏标记）"))

    # 2. 标题层级与数量
    headings = parse_headings(text)
    h1s = [h for h in headings if h.level == 1]
    if not h1s:
        issues.append(Issue(1, "warn", "没有一级标题 H1"))
    elif len(h1s) > 1:
        for h in h1s[1:]:
            issues.append(Issue(h.line, "warn", f"出现了第 {h1s.index(h) + 1} 个 H1，一个文档建议只留一个"))

    prev = None
    for h in headings:
        if prev and h.level > prev.level + 1:
            issues.append(Issue(h.line, "warn",
                                f"标题层级跳跃：H{prev.level} 直接到 H{h.level}"))
        prev = h

    if not check_links:
        return issues

    # 3. 链接与图片
    base = path.parent
    slugs = {h.slug for h in headings}
    for i, line in enumerate(lines):
        if inside[i]:
            continue
        for m in _LINK.finditer(line):
            target = m.group(2).strip()
            _check_target(target, i + 1, base, slugs, issues, kind="链接")
        for m in _IMAGE.finditer(line):
            target = m.group(2).strip()
            _check_target(target, i + 1, base, slugs, issues, kind="图片")

    return issues


def _check_target(target: str, line_no: int, base: Path, slugs: set[str],
                  issues: list[Issue], kind: str) -> None:
    if not target or target in ("#",):
        issues.append(Issue(line_no, "warn", f"{kind}地址是空的"))
        return

    # 外链不管（离线检查没法验证，也没必要）
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target) or target.startswith("mailto:"):
        return

    if target.startswith("#"):
        anchor = target[1:]
        if anchor and anchor.lower() not in slots_with_suffix(slugs):
            issues.append(Issue(line_no, "warn", f"锚点 #{anchor} 在本文档里找不到对应标题"))
        return

    # 本地文件
    file_part = target.split("#", 1)[0]
    if not file_part:
        return
    p = (base / file_part).resolve()
    if not p.exists():
        issues.append(Issue(line_no, "error", f"{kind}指向不存在的文件：{file_part}"))


def slots_with_suffix(slugs: set[str]) -> set[str]:
    """GitHub 遇到同名标题会加 -1/-2 后缀，这里放宽匹配。"""
    out = set(slugs)
    for s in slugs:
        for n in range(1, 10):
            out.add(f"{s}-{n}")
    return out


def build_toc(headings: list[Heading], *, min_level: int = 1, max_level: int = 3) -> str:
    """生成目录列表，缩进按层级走。"""
    picked = [h for h in headings if min_level <= h.level <= max_level]
    if not picked:
        return ""
    base_level = min(h.level for h in picked)
    out: list[str] = []
    for h in picked:
        indent = "  " * (h.level - base_level)
        out.append(f"{indent}- [{h.text}](#{h.slug})")
    return "\n".join(out)


def replace_toc(text: str, toc: str) -> tuple[str, bool]:
    """把目录塞进 <!-- toc --> ... <!-- /toc --> 之间。返回 (新文本, 是否改动)。"""
    if TOC_START not in text:
        return text, False

    pattern = re.compile(
        re.escape(TOC_START) + r".*?" + re.escape(TOC_END),
        re.DOTALL,
    )
    if not pattern.search(text):
        # 只有开始标记，没有结束标记
        return text, False

    new_block = f"{TOC_START}\n{toc}\n{TOC_END}"
    updated = pattern.sub(lambda _m: new_block, text, count=1)
    return updated, updated != text


def process(path: Path, *, check_links: bool = True, make_toc: bool = False,
            write: bool = False, min_level: int = 1, max_level: int = 3
            ) -> tuple[list[Issue], bool]:
    """处理单个文件，返回 (问题列表, 是否写入了文件)。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    issues = check(text, path, check_links=check_links)

    if not make_toc:
        return issues, False

    headings = parse_headings(text)
    toc = build_toc(headings, min_level=min_level, max_level=max_level)
    if not toc:
        issues.append(Issue(1, "warn", "没有标题，无法生成目录"))
        return issues, False

    new_text, changed = replace_toc(text, toc)
    if not changed:
        issues.append(Issue(1, "warn",
                            f"没有找到 {TOC_START} 和 {TOC_END} 标记，目录打印在下面，"
                            f"想自动写入请先在文件里加这两个标记"))
        print(f"\n--- {path.name} 目录 ---\n{toc}\n")
        return issues, False

    if write:
        path.write_text(new_text, encoding="utf-8", newline="\n")
        return issues, True

    print(f"\n--- {path.name} 建议的目录 ---\n{toc}\n")
    return issues, False
