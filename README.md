# mdcheck · Markdown 体检

[![Python](https://img.shields.io/badge/python-3.8%2B-3776AB)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-12B76A)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-0-12B76A)](#)

写完 README 心里没底？跑一下。

```bash
mdcheck .              # 体检
mdcheck . --toc --write # 顺手把目录更新了
```

## 查什么

| 检查项 | 级别 | 说明 |
| --- | --- | --- |
| 代码块围栏未闭合 | ✗ 错误 | 少写一个 ` ``` ` 会让后面全文变成代码块 |
| 本地链接失效 | ✗ 错误 | 指向的文件不存在，点开是 404 |
| 图片路径失效 | ✗ 错误 | 同上 |
| 标题层级跳跃 | ⚠ 提醒 | H2 直接跳到 H4，目录结构会歪 |
| 多个 H1 | ⚠ 提醒 | 一个文档只该有一个一级标题 |
| 锚点找不到对应标题 | ⚠ 提醒 | `[跳转](#不存在的标题)` |
| 空链接地址 | ⚠ 提醒 | `[文字]()` |

外链（`https://...`）不检查——离线跑没法验证，硬查反而会误报。

## 安装

```bash
pip install git+https://github.com/Liuyichen27/mdcheck.git
```

零依赖，纯标准库，正则级别实现，不引入 cmark。

## 输出

```
README.md
  第 12 行 ⚠ 标题层级跳跃：H2 直接到 H4
  第 30 行 ✗ 链接指向不存在的文件：docs/missing.md

2 个文件，1 个错误，1 个提醒
```

退出码：有错误返回 `1`，干净返回 `0`。可以直接挂到 CI 或 pre-commit：

```bash
mdcheck . && git commit -m "docs: 更新"
```

## 目录生成

在文件里加一对标记：

```markdown
# 我的文档

<!-- toc -->
<!-- /toc -->

## 第一节
```

然后：

```bash
mdcheck README.md --toc --write
```

目录会按标题层级自动缩进，链接用 GitHub 的锚点规则（小写、去标点、空格变连字符、中文保留）：

```markdown
<!-- toc -->
- [我的文档](#我的文档)
  - [第一节](#第一节)
<!-- /toc -->
```

不加 `--write` 就只在终端打印建议的目录，不改文件。

层级控制：`--min-level 1 --max-level 3`（默认就收到 H3，README 一般不需要更细的目录）。

## 参数

| 参数 | 说明 |
| --- | --- |
| `-t, --toc` | 生成目录 |
| `-w, --write` | 把目录写回文件 |
| `--no-links` | 跳过链接检查（只想查格式时） |
| `--min-level` / `--max-level` | 目录收录的标题层级范围 |
| `-q, --quiet` | 只输出有问题的文件 |

传目录会自动递归找 `*.md` 和 `*.markdown`，跳过 `.git` / `node_modules` / `.venv`。

## 一个刻意的取舍

它**不是**完整的 Markdown 解析器。代码块里的 `# 注释` 会被正确跳过（用围栏配对判断），但嵌套引用块（`> ``` `）里的内容可能误判。

换来的是：零依赖、启动快（几百个文件也就 0.1 秒）、不会因为某个冷门语法就崩。

## 作为库调用

```python
from pathlib import Path
from mdcheck import core

text = Path("README.md").read_text(encoding="utf-8")
for issue in core.check(text, Path("README.md")):
    print(issue.line, issue.level, issue.message)
```

## 测试

```bash
python -m unittest discover -s tests -v
```

21 个用例，覆盖围栏配对、代码块内假标题、层级跳跃、多 H1、死链、外链放行、锚点匹配、图片、目录嵌套与写回。

## 许可

MIT License，详见 [LICENSE](LICENSE)。

---

<sub>English: mdcheck lints Markdown for unclosed code fences, dead relative links and images, heading level jumps, multiple H1s and broken anchors, and can generate or update a table of contents between `<!-- toc -->` markers. Zero dependencies, regex-based (not a full parser) — fast enough to lint a whole docs folder in a fraction of a second. Returns exit code 1 on errors so it drops straight into CI.</sub>
