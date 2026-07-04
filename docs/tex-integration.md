# TeX/LaTeX 渲染说明

本文档说明 MyGUI 中 TeX 渲染的启用逻辑、单个文本元素的 TeX 开关、可用 TeX 包建议、已知限制和维护注意事项。

## 总体行为

MyGUI 的 TeX 功能基于 matplotlib 的 `text.usetex`。它只负责把图中的文本交给本机 TeX 工具链渲染，不是完整的 `.tex` 文档编译器。

当前实现涉及这些文件：

- `code/tex_config.py`：TeX 运行时检查、默认 preamble、日志、全局 TeX 状态通知。
- `code/widgets/fig_control_window/py_tex_window.py`：TeX 面板、启用/禁用、preamble 更新。
- `code/figuremodify/py_text_modify.py`：单个 matplotlib `Text` 对象的内容更新、TeX 渲染切换和失败回滚。
- `code/widgets/fig_control_window/all_mod_widgets/py_elements_mod_widgets.py`：文本元素编辑面板中的 `TeX` 复选按钮。
- `code/widgets/figure_canvas/py_figure_canves.py` 和 `code/widgets/figure_canvas/py_figure_window.py`：文本对象创建、项目保存/加载。

TeX 是可选依赖。没有 TeX、TeX 包不完整或文本无法被 TeX 处理时，基础 GUI、普通绘图和普通图片保存仍应可用。

## 启用流程

用户在 TeX 面板勾选 `Use Latex Engine` 时，程序不会直接提交 `text.usetex=True`，而是先做检查：

1. 读取 preamble 编辑框内容。
2. 用 `tex_config.normalize_preamble()` 规范化：保留非空行，去掉空白行和行首行尾空白。
3. 检查 PATH 中是否存在 TeX 可执行文件。
4. 用当前 preamble 创建一个极小 matplotlib figure，并尝试渲染 PNG。
5. 成功后才设置 `mpl.rcParams["text.usetex"] = True`。
6. 失败时保持 `text.usetex=False`，取消 TeX 面板勾选。

结果通过 bottom bar 返回：

- 成功：绿色消息，例如 `TeX runtime check passed; TeX rendering is enabled.`
- 失败：红色消息，例如 `No TeX executable was found on PATH.` 或 `TeX rendering failed: ...`

日志写入 `logs/tex.log`，logger 名称是 `mygui.tex`。可以通过环境变量调整：

- `MYGUI_TEX_LOG_DIR`：TeX 日志目录。
- `MYGUI_TEX_LOG_LEVEL`：日志级别，默认 `INFO`。

## 单个文本元素的 TeX 开关

文本元素编辑面板中有一个 `Render: TeX` 复选按钮。

行为如下：

- 全局 TeX 未启用时，按钮禁用且不勾选。
- 全局 TeX 已启用时，按钮可用。
- 全局 TeX 已启用时，新建 text 元素默认勾选并尝试使用 TeX 渲染。
- 单个 text 元素可以取消勾选，改回普通 matplotlib 文本渲染。
- 全局 TeX 关闭时，已经使用 TeX 的 text 元素会自动切回普通渲染，按钮禁用并取消勾选。

单个 text 的渲染状态保存在项目记录字段 `usetex` 中：

```json
{
  "scope": "axes",
  "x": 0.5,
  "y": 0.5,
  "text": "$x^2$",
  "fontfamily": "DejaVu Sans",
  "fontsize": 14.0,
  "usetex": true
}
```

旧项目没有 `usetex` 字段时，迁移时默认补为 `false`。

## 失败回滚策略

文本输入和渲染方式切换都属于高风险路径，因为 TeX 可能因为一个字符或一个宏失败。

当前策略是：

- 用户输入不可渲染文本时，图中 artist 和项目记录回滚到上一次可渲染文本。
- 编辑框保留用户当前输入，方便继续修改。
- bottom bar 用红色显示简短原因。
- 切换单个 text 到 TeX 渲染失败时，回滚到之前的渲染方式。
- matplotlib 普通渲染出现缺字 warning 时，例如缺少 `U+FFE5`，bottom bar 也会显示简短提示。

典型错误示例：

```text
Unicode character ￥ (U+FFE5) not set up for use with LaTeX.
```

这表示当前 TeX 路径不能处理该 Unicode 字符。可以改用 LaTeX 命令、换成普通渲染，或使用 TeX 能处理的字符组合。

## 默认 preamble

默认 preamble 在 `code/tex_config.py` 中：

```tex
\usepackage{amsmath}
\usepackage{newtxtext,newtxmath}
```

含义：

- `amsmath`：常用数学环境和数学命令。
- `newtxtext,newtxmath`：Times 风格的文本和数学字体。

preamble 更新按钮会在全局 TeX 已启用时重新验证运行时。验证失败时不会提交新 preamble。

## 推荐使用的 TeX 包

推荐包必须满足两个条件：

- 本机 TeX 发行版已经安装该包。
- 该包兼容 matplotlib 当前的 `text.usetex` 路径。

常用推荐：

| 包 | 用途 | 建议 |
| --- | --- | --- |
| `amsmath` | 基础数学排版 | 默认已启用，推荐保留 |
| `amssymb` | 额外数学符号 | 常用，可加入 preamble |
| `mathtools` | `amsmath` 扩展 | 可用，但注意不要重复定义命令 |
| `bm` | 粗体数学符号 | 推荐用于 `\bm{x}` |
| `xcolor` | 颜色命令 | 可用，但图中文字颜色通常优先用 GUI 控件控制 |
| `siunitx` | 单位和数值排版 | 可用，适合轴标签、单位文本 |
| `newtxtext,newtxmath` | Times 风格字体 | 默认已启用 |

示例 preamble：

```tex
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{bm}
\usepackage{siunitx}
\usepackage{newtxtext,newtxmath}
```

文本内容示例：

```tex
$\int_0^1 x^2\,dx$
$\bm{F}=m\bm{a}$
\SI{12.5}{\micro\meter}
```

## 谨慎使用的包

这些包不一定不能用，但容易引入字体、宏冲突或 TeX 工具链问题：

| 包 | 风险 |
| --- | --- |
| `fontenc` / `inputenc` | matplotlib 可能已经生成相关输入设置，重复或不兼容配置可能破坏渲染 |
| `textcomp` | 一些符号有帮助，但字体组合不完整时仍可能失败 |
| `underscore` | matplotlib/TeX 路径中可能已经加载；重复加载通常没必要 |
| `mhchem` | 适合化学式，但要求本机 TeX 安装完整 |
| `physics` | 命令方便，但包维护和宏冲突风险较高 |
| `cancel` | 可用于公式标记，但与字体和宏包组合有关 |

建议每次只增加一个包，点击 `Update` 验证成功后再继续添加。

## 当前限制

当前 TeX 功能有明确边界：

- 不是完整 TeX 文档编译，不支持 `\documentclass`、`\begin{document}`、`\section`、交叉引用、目录、参考文献等文档级功能。
- 不支持把用户输入作为独立 `.tex` 文件编译。
- 不支持项目级 TeX 设置持久化；当前只保存单个 text 是否使用 TeX。
- 不支持每个 text 使用不同 preamble；preamble 是全局 matplotlib rcParam。
- 不支持不受限 shell escape。不要依赖需要外部命令执行的包或命令。
- 不支持 `minted`、外部图片插入、TikZ/PGFPlots 等重型绘图工作流作为 text 内容。
- 不支持 `fontspec`、`unicode-math`、`xeCJK` 等 XeLaTeX/LuaLaTeX 专用方案；当前 matplotlib `usetex` 路径按默认 LaTeX/pdfLaTeX 工作流验证。
- Unicode 支持有限。中文、全角符号、emoji、很多特殊 Unicode 字符可能失败。需要这些字符时，优先关闭单个 text 的 TeX 渲染，改用普通 matplotlib 字体渲染。
- `latex`、`pdflatex`、`xelatex`、`tectonic` 中任一命令存在只代表 PATH 中有 TeX 相关程序；实际 matplotlib 渲染仍以当前 `text.usetex` 后端能否成功为准。
- 保存图片时也会触发 matplotlib 重绘；如果某个 TeX text 后续变得不可渲染，保存可能失败。当前文本编辑路径会尽量在输入时提前发现并回滚。

## 不推荐或当前不可用的包/功能

| 功能或包 | 原因 |
| --- | --- |
| `\documentclass` / `\begin{document}` | matplotlib text 只接收片段，不是完整文档 |
| `fontspec` | 需要 XeLaTeX/LuaLaTeX，不适合当前默认 `usetex` 路径 |
| `unicode-math` | 需要 Unicode TeX 引擎 |
| `xeCJK` / `ctex` | 中文 TeX 方案依赖 XeLaTeX/LuaLaTeX 或复杂字体配置 |
| `minted` | 需要 shell escape 和外部 `pygmentize` |
| `tikz` / `pgfplots` | 不是 text 渲染的目标场景，编译慢且失败面大 |
| `biblatex` / `natbib` | 参考文献功能在图中文字中没有意义 |
| `hyperref` | 链接和 PDF 文档结构功能在图片 text 渲染中没有意义 |
| `graphicx` 插图 | text 元素不应用来嵌入外部图片 |

## 推荐输入方式

优先使用简单、局部、数学片段式输入：

```tex
$E=mc^2$
$\alpha+\beta=\gamma$
$\frac{d}{dx}\sin x=\cos x$
```

避免把普通 Unicode 字符直接混进 TeX 文本。例如：

```tex
$\int$￥
```

这类输入容易失败。可选处理方式：

- 关闭该 text 的 `TeX` 按钮，用普通字体渲染。
- 改成 TeX 命令，例如使用可用包提供的符号命令。
- 换成 TeX 能处理的 ASCII 或 LaTeX 宏。

## 维护注意事项

- TeX 依赖必须保持可选，失败不能阻塞 GUI 启动。
- 不要把用户输入送入不受限制的 `eval` 或 shell 命令。
- `validate_tex_runtime()` 只能证明当前 preamble 能渲染最小测试文本，不能证明所有未来用户输入都可渲染。
- 修改 TeX 状态、文本渲染回滚、项目 `usetex` 字段时，应补充 focused tests。
- 修改后至少运行：

```powershell
& 'E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe' -m compileall -q .
& 'E:\PycharmProjects\ven\pyside6_env\Scripts\python.exe' -m unittest discover -s tests -v
```

涉及 GUI 行为时，建议额外做 offscreen GUI smoke，确认基础窗口能启动、TeX 面板失败路径不阻塞 GUI、文本元素的 `TeX` 按钮启用/禁用状态正确。
