"""mdcheck 测试。"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mdcheck import cli, core  # noqa: E402


def make(tmp: Path, name: str, body: str) -> Path:
    p = tmp / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(core.slugify("Hello World"), "hello-world")
        self.assertEqual(core.slugify("安装与配置"), "安装与配置")
        self.assertEqual(core.slugify("API: v2.0"), "api-v20")
        self.assertEqual(core.slugify("`code` 用法"), "code-用法")

    def test_strips_emphasis(self):
        self.assertEqual(core.slugify("**粗体** 标题"), "粗体-标题")


class TestHeadings(unittest.TestCase):
    def test_ignores_headings_inside_fence(self):
        text = "# 真标题\n\n```\n# 这是代码里的注释\n```\n## 二级\n"
        hs = core.parse_headings(text)
        self.assertEqual([h.text for h in hs], ["真标题", "二级"])
        self.assertEqual(hs[1].level, 2)

    def test_line_numbers_are_one_based(self):
        hs = core.parse_headings("前言\n\n# 标题\n")
        self.assertEqual(hs[0].line, 3)

    def test_trailing_hashes_stripped(self):
        hs = core.parse_headings("## 标题 ##\n")
        self.assertEqual(hs[0].text, "标题")


class TestCheck(unittest.TestCase):
    def test_unclosed_fence_is_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = make(Path(td), "a.md", "# T\n\n```python\nprint(1)\n")
            issues = core.check(p.read_text(encoding="utf-8"), p)
            self.assertTrue(any("没有闭合" in i.message for i in issues))
            self.assertTrue(any(i.level == "error" for i in issues))

    def test_reports_level_jump(self):
        with tempfile.TemporaryDirectory() as td:
            p = make(Path(td), "a.md", "# T\n\n### 跳到三级\n")
            issues = core.check(p.read_text(encoding="utf-8"), p)
            self.assertTrue(any("层级跳跃" in i.message for i in issues))

    def test_warns_multiple_h1(self):
        with tempfile.TemporaryDirectory() as td:
            p = make(Path(td), "a.md", "# A\n\n# B\n")
            issues = core.check(p.read_text(encoding="utf-8"), p)
            self.assertTrue(any("第二个 H1" in i.message or "2 个 H1" in i.message for i in issues))

    def test_dead_relative_link(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            p = make(d, "a.md", "# T\n\n[坏链接](missing.md)\n")
            issues = core.check(p.read_text(encoding="utf-8"), p)
            self.assertTrue(any("不存在的文件" in i.message for i in issues))

    def test_existing_relative_link_is_fine(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            make(d, "other.md", "# Other\n")
            p = make(d, "a.md", "# T\n\n[好链接](other.md)\n")
            issues = core.check(p.read_text(encoding="utf-8"), p)
            self.assertFalse(any("不存在的文件" in i.message for i in issues))

    def test_external_links_not_checked(self):
        with tempfile.TemporaryDirectory() as td:
            p = make(Path(td), "a.md", "# T\n\n[x](https://example.com/nope)\n")
            issues = core.check(p.read_text(encoding="utf-8"), p)
            self.assertFalse(any("example.com" in i.message for i in issues))

    def test_anchor_must_match_heading(self):
        with tempfile.TemporaryDirectory() as td:
            p = make(Path(td), "a.md", "# 安装步骤\n\n[跳](#安装步骤)\n[断](#不存在)\n")
            issues = core.check(p.read_text(encoding="utf-8"), p)
            msgs = [i.message for i in issues]
            self.assertFalse(any("安装步骤" in m and "找不到" in m for m in msgs))
            self.assertTrue(any("不存在" in m for m in msgs))

    def test_missing_image_reported(self):
        with tempfile.TemporaryDirectory() as td:
            p = make(Path(td), "a.md", "# T\n\n![图](img/x.png)\n")
            issues = core.check(p.read_text(encoding="utf-8"), p)
            self.assertTrue(any("图片指向不存在的文件" in i.message for i in issues))

    def test_no_links_flag_skips_link_checks(self):
        with tempfile.TemporaryDirectory() as td:
            p = make(Path(td), "a.md", "# T\n\n[坏](nope.md)\n")
            issues = core.check(p.read_text(encoding="utf-8"), p, check_links=False)
            self.assertFalse(any("不存在的文件" in i.message for i in issues))


class TestToc(unittest.TestCase):
    def test_build_nested(self):
        text = "# 标题\n\n## 一\n\n### 一 a\n\n## 二\n"
        toc = core.build_toc(core.parse_headings(text))
        self.assertEqual(
            toc,
            "- [标题](#标题)\n  - [一](#一)\n    - [一 a](#一-a)\n  - [二](#二)",
        )

    def test_max_level_limits(self):
        text = "# A\n\n## B\n\n### C\n\n#### D\n"
        toc = core.build_toc(core.parse_headings(text), max_level=2)
        self.assertNotIn("C", toc)
        self.assertNotIn("D", toc)

    def test_replace_between_markers(self):
        text = "# T\n\n<!-- toc -->\n旧内容\n<!-- /toc -->\n\n## A\n"
        headings = core.parse_headings(text)
        new, changed = core.replace_toc(text, core.build_toc(headings))
        self.assertTrue(changed)
        self.assertIn("- [A](#a)", new)
        self.assertNotIn("旧内容", new)

    def test_no_markers_no_change(self):
        text = "# T\n\n## A\n"
        new, changed = core.replace_toc(text, "- [A](#a)")
        self.assertFalse(changed)
        self.assertEqual(new, text)


class TestCli(unittest.TestCase):
    def test_returns_1_on_error(self):
        with tempfile.TemporaryDirectory() as td:
            make(Path(td), "bad.md", "# T\n\n[死链](gone.md)\n")
            self.assertEqual(cli.main([td, "-q"]), 1)

    def test_returns_0_when_clean(self):
        with tempfile.TemporaryDirectory() as td:
            make(Path(td), "ok.md", "# T\n\n## A\n\n正文\n")
            self.assertEqual(cli.main([td, "-q"]), 0)

    def test_write_toc_updates_file(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            p = make(d, "doc.md",
                     "# 文档\n\n<!-- toc -->\n<!-- /toc -->\n\n## 第一节\n\n## 第二节\n")
            self.assertEqual(cli.main([str(p), "--toc", "--write", "-q"]), 0)
            body = p.read_text(encoding="utf-8")
            self.assertIn("- [第一节](#第一节)", body)
            self.assertIn("- [第二节](#第二节)", body)


if __name__ == "__main__":
    unittest.main()
