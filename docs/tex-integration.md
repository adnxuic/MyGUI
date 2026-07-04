# TeX/LaTeX 当前限制

本文档只记录 MyGUI 当前 TeX/LaTeX 功能的已知边界和限制。

## 基础边界

- TeX 功能基于 matplotlib 的 `text.usetex`，只用于图中 `Text` 文本片段渲染。
- 当前功能不是完整 `.tex` 文档编译器，不支持把用户输入作为完整 TeX 文档处理。
- TeX 是可选本地依赖；缺少 TeX、TeX 包不完整或 TeX 文本不可渲染时，不应影响基础 GUI、普通绘图和普通图片保存。
- matplotlib 真正调用外部 TeX 的时机通常发生在画布重绘或 `fig.savefig()` 保存图片时，而不是用户输入文本的瞬间。
- 当前运行时检查只验证当前 preamble 能否渲染一个极小测试文本 `$x$`，不保证所有后续用户输入都能被 TeX 处理。

## 当前默认包

当前默认 preamble 只包含：

```tex
\usepackage{amsmath}
\usepackage{newtxtext,newtxmath}
```

这些包的当前含义：

- `amsmath`：提供常用数学排版命令和环境。
- `newtxtext,newtxmath`：提供 Times 风格文本和数学字体。

除默认包以外，用户在 preamble 中输入的其他 `\usepackage{...}` 只受本机 TeX 发行版和 matplotlib `usetex` 路径实际兼容性约束。MyGUI 当前不内置 TeX 包管理，不下载 TeX 包，也不保证任何额外包一定可用。

## 包和功能限制

当前不支持或不保证以下 TeX 文档级功能：

- `\documentclass`
- `\begin{document}` / `\end{document}`
- `\section` 等文档结构命令
- 目录、交叉引用、参考文献、BibTeX/Biber 工作流
- `hyperref` 这类依赖 PDF 文档结构的功能
- 把用户输入编译成独立 `.tex` 文件

当前不支持或不保证以下引擎专用功能：

- `fontspec`
- `unicode-math`
- `xeCJK`
- `ctex`
- 依赖 XeLaTeX 或 LuaLaTeX 的字体和 Unicode 工作流

当前不支持或不保证以下外部命令或重型绘图工作流：

- shell escape
- `minted`
- 依赖外部 `pygmentize` 等程序的代码高亮
- `tikz`
- `pgfplots`
- 在 text 元素中通过 TeX 插入外部图片

## Unicode 限制

当前 TeX 路径对 Unicode 支持有限。中文、全角符号、emoji 和部分特殊 Unicode 字符可能无法渲染。

典型错误示例：

```text
Unicode character ￥ (U+FFE5) not set up for use with LaTeX.
```

这表示当前 matplotlib `usetex` 使用的 LaTeX 路径无法处理该字符。类似 `$\\int$￥` 这种把 TeX 数学片段和全角人民币符号直接混排的输入，属于当前不保证范围。

## 引擎检测限制

- 当前会检查 PATH 中是否存在 `latex`、`pdflatex`、`xelatex` 或 `tectonic` 等 TeX 相关命令。
- PATH 中存在上述任一命令只表示本机有 TeX 相关程序，不表示 matplotlib 本次渲染会使用该具体引擎。
- 当前 matplotlib `text.usetex` 路径仍以 matplotlib 后端实际调用结果为准。

## 状态和持久化限制

- 全局 TeX 启用状态不作为项目设置持久化；每次启动进程时默认不启用 TeX。
- 单个 text 元素的 `usetex` 状态可以随项目记录保存和加载。
- 当前不支持每个 text 元素使用不同 preamble；`text.latex.preamble` 是全局 matplotlib rcParam。
- 关闭全局 TeX 时，text 元素会回到普通 matplotlib 文本渲染路径。

## 保存和回滚限制

- 保存图片会触发 matplotlib 重绘；如果某个 TeX text 在保存前处于不可渲染状态，保存可能失败。
- 当前文本编辑路径会尽量在输入或切换 TeX 渲染时提前发现错误并回滚到上一份可渲染内容。
- 回滚不能覆盖所有绕过 GUI 编辑路径直接修改 matplotlib artist 的情况。

## 日志限制

TeX 日志默认写入：

```text
logs/tex.log
```

日志只用于诊断 TeX 运行时检查、启用失败和渲染异常。当前 GUI 不提供日志查看器，也不会把完整 LaTeX 编译输出长期展示在界面中。
