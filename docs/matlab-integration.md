# MATLAB 调用实现说明

本文档说明本项目中 MATLAB 调用部分的实现方式、GUI 调用链、运行时依赖、错误处理和维护注意点。

## 总体架构

项目中的 MATLAB 功能主要用于曲线拟合。当前实现不是通过 `matlab.engine.start_matlab()` 启动 MATLAB Engine 会话，而是通过 MATLAB Compiler SDK 生成的 Python 部署包调用 MATLAB Runtime。

核心模块如下：

- `code/widgets/fig_control_window/py_matlab_window.py`：MATLAB 面板、连接按钮、拟合参数 UI、异步任务调度。
- `code/database/matlab_adapter.py`：MATLAB Runtime 检测、子进程隔离调用、数据类型转换、日志和超时控制。
- `code/database/py_matlab_fit.py`：可选拟合类型配置。
- `code/database/matlab_func/get_func`：MATLAB Compiler 生成的函数表达式获取包。
- `code/database/matlab_func/curve_fitting`：MATLAB Compiler 生成的曲线拟合包。
- `code/widgets/fig_control_window/all_mod_widgets/py_chart_mod_widgets.py`：接收拟合结果并更新曲线对象。

整体调用链是：

1. 用户在 MATLAB 面板点击 `Connect Matlab`。
2. GUI 用 `QThread` 启动后台任务，调用 `matlab_adapter.ensure_matlab_available_isolated()`。
3. `matlab_adapter` 启动独立 Python 子进程。
4. 子进程导入 MATLAB Runtime 和 MATLAB Compiler 生成的 Python 包。
5. 用户选择拟合类型和数据后点击 `Fit`。
6. GUI 再次通过后台任务调用 `matlab_adapter.fit_curve_isolated()`。
7. 子进程调用 `curve_fitting.curve_fitting(...)` 执行 MATLAB 拟合逻辑。
8. 拟合表达式通过 JSON 返回 GUI 主进程。
9. GUI 更新当前 MATLAB 拟合曲线控件和 matplotlib 曲线。

## MATLAB 面板和异步任务

MATLAB 面板定义在 `PyMatlabWindow` 中。为了避免 MATLAB Runtime 初始化或拟合过程阻塞界面，代码封装了 `MatlabTaskWorker` 和 `start_matlab_task()`。

`MatlabTaskWorker` 是一个 `QObject`，会被移动到独立 `QThread` 中执行。它接收一个普通 Python 函数和参数，执行成功后发出 `finished` 信号，失败后发出 `failed` 信号。`start_matlab_task()` 负责创建线程、连接信号、清理线程和 worker，并记录活动任务。

该层解决的是 GUI 响应性问题：即使 MATLAB 调用耗时较长，PySide6 主线程仍能继续处理界面事件。

## 子进程隔离

真正的 MATLAB 调用没有直接在 GUI 进程内完成，而是由 `matlab_adapter._run_isolated()` 启动一个新的 Python 子进程执行。

子进程的输入是 JSON payload，例如：

- `{"op": "ensure_matlab_available"}`
- `{"op": "get_func_exp", "func_name": "poly2"}`
- `{"op": "fit_curve", "x": [...], "y": [...], "fit_type": "poly1", ...}`

子进程执行完成后，会在 stdout 输出一行带固定前缀的 JSON：

```text
__MATLAB_ADAPTER_RESULT__{"ok": true, "result": ...}
```

主进程只解析带该前缀的最后一行输出。这样即使 MATLAB Runtime 或部署包在 stdout/stderr 打印额外诊断信息，也不会破坏主进程和子进程之间的结果协议。

使用子进程隔离的主要原因：

- MATLAB Runtime 初始化失败不会拖垮 GUI 主进程。
- 可以通过 `subprocess.run(..., timeout=...)` 设置硬超时。
- 每次调用可以使用独立的 `MCR_CACHE_ROOT`，减少 MATLAB Runtime 缓存冲突。
- 子进程 stderr 会被统一写入 MATLAB 日志，便于诊断。

## MATLAB Runtime 检测

`matlab_adapter._import_matlab_runtime()` 负责导入 MathWorks 的 `matlab` Python 包。

检测逻辑不仅要求 `import matlab` 成功，还要求导入的模块存在可调用的 `matlab.double`。如果导入到的是其他同名模块，例如源码目录中的普通 `matlab` 文件夹，会被拒绝并抛出 `RuntimeError`。

连接按钮触发的检测流程是：

1. `PyMatlabWindow.matlab_connect_click()` 禁用按钮并显示 `Connecting...`。
2. 后台线程调用 `matlab_adapter.ensure_matlab_available_isolated()`。
3. 子进程执行 `check_matlab_connection()`。
4. 默认只检查 MATLAB Runtime 和两个部署包是否可以导入。
5. 如果环境变量 `MYGUI_MATLAB_CONNECT_INITIALIZE_PACKAGES` 为真，则连接检测还会初始化并释放两个部署包。
6. 成功后调用 `PyMatlabWindow.init()` 初始化拟合 UI。
7. 失败后恢复 `Connect Matlab` 按钮并弹出警告。

这一设计让 MATLAB 保持懒加载：程序启动时不会立刻加载 MATLAB Runtime，只有用户进入 MATLAB 工作流并点击连接时才检测。

## MATLAB Compiler 部署包

仓库中包含两个 MATLAB Compiler 生成的 Python 包：

- `code/database/matlab_func/get_func`
- `code/database/matlab_func/curve_fitting`

它们目录下分别包含 `.ctf` 文件：

- `code/database/matlab_func/get_func/get_func.ctf`
- `code/database/matlab_func/curve_fitting/curve_fitting.ctf`

这些包的 `__init__.py` 是 MathWorks 自动生成代码，负责：

- 判断当前平台和 Python 版本。
- 从系统环境变量中查找 MATLAB Runtime 25.1。
- 在 Windows 上检查 `PATH` 是否包含运行库目录。
- 导入 `matlab_pysdk.runtime` 和 `matlab` 模块。
- 提供 `initialize()`、`initialize_runtime()`、`terminate_runtime()` 等入口。

在 Windows 上，部署包会查找类似 `mclmcrrt25_1.dll` 的运行库。运行环境需要正确安装 MATLAB Runtime 或 MATLAB，并保证相关 runtime 路径在 `PATH` 中。

## 表达式获取

拟合类型和阶数定义在 `code/database/py_matlab_fit.py`，包括：

- 多项式：`poly1` 到 `poly9`
- 指数：`exp1`、`exp2`
- 对数：`log`
- 傅里叶：`fourier1` 到 `fourier8`
- 高斯：`gauss1` 到 `gauss8`
- 幂函数：`power1`、`power2`
- 有理函数：`rat01` 到 `rat55`
- 正弦：`sin1` 到 `sin8`
- Weibull：`weibull`
- S 型函数：`logistic`、`logistic4`、`gompertz`

`PyFitWindow` 创建或阶数切换时，会调用 `load_expression()` 异步获取当前拟合函数的表达式和系数名。

底层流程是：

1. GUI 调用 `matlab_adapter.get_func_exp_isolated(func_name)`。
2. 子进程进入 `matlab_adapter.get_func_exp(func_name)`。
3. 初始化 `code.database.matlab_func.get_func` 部署包。
4. 调用 `get_func.get_func(func_name, nargout=2)`。
5. 返回 MATLAB 表达式和系数名列表。
6. GUI 更新表达式文本框和高级参数表格。

如果 MATLAB Runtime 初始化不可用，`get_func_exp()` 对常见拟合类型提供 Python fallback 表达式。例如 `poly2` 会退化为：

```text
p1*x^2 + p2*x + p3
```

这个 fallback 只用于表达式展示和系数名生成，不能替代真正的 MATLAB 拟合计算。

## 曲线拟合流程

用户点击 `Fit` 后，`PyMatlabWindow.fit_curve()` 执行以下步骤：

1. 检查当前是否已选中一个 MATLAB 拟合曲线控件。
2. 从 `PyDataChoiceWidget` 读取 X/Y 数据名称。
3. 通过 `PyDatabase.get_data()` 获取实际数据。
4. 检查 X/Y 数据非空。
5. 检查 X/Y 数据长度一致。
6. 读取当前拟合类型、是否使用默认参数、上限、下限和起始点。
7. 禁用按钮并显示 `Fitting...`。
8. 异步调用 `matlab_adapter.fit_curve_isolated()`。

`matlab_adapter.fit_curve()` 会将 Python 数据转换成 MATLAB 类型：

- X 数据转换为 MATLAB 列向量：`matlab.double(values, size=(len(values), 1))`
- Y 数据转换为 MATLAB 列向量。
- 上限、下限、起始点转换为 MATLAB 行向量。
- 未提供的高级参数转换为空 MATLAB double。

随后初始化 `curve_fitting` 部署包，并调用：

```python
fitting.curve_fitting(
    x_data,
    y_data,
    fit_type,
    isdefault,
    upper,
    lower,
    start,
    nargout=4,
)
```

返回值包含：

- `exp`：带系数名的 MATLAB 表达式。
- `coeff_name`：系数名列表。
- `coeff_value`：拟合得到的系数值。
- `_gof`：拟合优度，目前代码接收但没有展示或使用。

拟合完成后，代码会把表达式中的系数名替换成具体数值，并把 MATLAB 的 `^` 替换成 Python 表达式使用的 `**`：

```python
value_exp = _replace_coefficients(exp, coeff_name, coeff_value[0])
show_exp = _replace_coefficients(exp, coeff_name, coeff_value[0])
return value_exp.replace("^", "**"), show_exp.replace("^", "**")
```

当前 `value_exp` 和 `show_exp` 实际相同，并没有对展示表达式做单独格式化或四舍五入。

## 拟合结果如何更新图形

拟合成功后，`PyMatlabWindow._fit_succeeded()` 会调用当前连接的 `PyFitMatlabModWidget.update_curve()`。

`PyFitMatlabModWidget.update_curve()` 做三件事：

1. 把展示表达式写入只读表达式文本框。
2. 把 X 起点和终点设置为数据范围。
3. 调用 `PyCurveModify.update_all(x_start, x_stop, value_expression)` 更新 matplotlib 曲线。

`PyMatlabWindow` 本身不直接创建曲线，它只负责更新当前选中的 MATLAB 拟合曲线控件。拟合曲线是在 `FigureCanvas.add_fit_curve()` 中创建的，创建后会通过 `matlab_widget.set_connect_widget(fitting_mod_widget)` 注册给 MATLAB 面板。

当用户在拟合曲线工具箱中切换当前曲线时，`PyModBox.change_widget()` 也会把当前 `PyFitMatlabModWidget` 设置为 MATLAB 面板的连接目标。

## 高级参数

`PyFitWindow` 中的高级选项用于设置系数约束。

默认情况下，高级选项关闭，拟合调用参数为：

```python
fit_type_order, True, None, None, None
```

开启高级选项后：

- 每个系数都有上限和下限。
- `poly` 和 `log` 只有上限、下限。
- 其他拟合类型还会提供起始点。
- 上限默认显示为 `inf`。
- 下限默认显示为 `-inf`。
- 起始点默认用 `numpy.random.rand(1)` 生成一个 0 到 1 之间的小数。

高级参数最终会传给 MATLAB 部署函数，让 MATLAB 拟合逻辑按指定约束执行。

## 日志和超时配置

MATLAB 相关日志由 `matlab_adapter.matlab_logger()` 统一管理，默认写入：

```text
logs/matlab.log
```

日志使用 `RotatingFileHandler`：

- 单个日志文件最大约 1 MB。
- 默认保留 3 个备份。

可用环境变量：

- `MYGUI_MATLAB_CONNECT_TIMEOUT_SECONDS`：连接检测超时，默认 180 秒。
- `MYGUI_MATLAB_EXPRESSION_TIMEOUT_SECONDS`：表达式获取超时，默认 120 秒。
- `MYGUI_MATLAB_FIT_TIMEOUT_SECONDS`：拟合超时，默认 180 秒。
- `MYGUI_MATLAB_CONNECT_INITIALIZE_PACKAGES`：连接检测时是否初始化部署包，默认关闭。
- `MYGUI_MATLAB_LOG_LEVEL`：日志等级，默认 `INFO`。
- `MYGUI_MATLAB_LOG_DIR`：日志目录，默认仓库下 `logs`。
- `MYGUI_MATLAB_MCR_CACHE_ROOT`：自定义 MATLAB Runtime 缓存目录。

如果没有显式配置 `MYGUI_MATLAB_MCR_CACHE_ROOT` 或 `MCR_CACHE_ROOT`，程序会根据部署包输入文件生成缓存 key，并使用仓库下的 `.matlab_runtime_cache/runtime/<key>` 作为 MATLAB Runtime 缓存目录。

缓存 key 会受这些文件影响：

- `code/database/matlab_func/get_func/__init__.py`
- `code/database/matlab_func/get_func/get_func.ctf`
- `code/database/matlab_func/curve_fitting/__init__.py`
- `code/database/matlab_func/curve_fitting/curve_fitting.ctf`

这些文件变化后，缓存 key 会变化，从而避免旧 runtime 缓存和新部署包混用。

## 错误处理策略

MATLAB 调用失败时，程序不会让 GUI 崩溃，而是：

- 在日志中记录失败信息。
- 恢复按钮状态。
- 通过 `QMessageBox.warning()` 提示用户。
- 对过期的异步结果使用 request id 忽略，避免快速切换时旧结果覆盖新状态。
- 如果 owner 窗口已销毁，后台任务结果不会再投递给已销毁对象。

常见失败包括：

- 未安装 MATLAB Runtime。
- `PATH` 中没有 MATLAB Runtime 目录。
- Python 版本不在部署包支持范围内。
- 部署包 `.ctf` 缺失或版本不匹配。
- 拟合数据为空或 X/Y 长度不一致。
- 高级参数无法转换为浮点数。
- MATLAB Runtime 初始化或释放失败。
- 子进程超时。

## 最小稳定性保障

当前 MATLAB 面板对连接、表达式加载和拟合请求都使用 request id 处理异步结果。每次发起新请求都会递增对应 id，回调返回时如果发现结果属于旧请求，就只写入调试日志并忽略，不再更新 UI 或弹窗。

连接流程的成功和失败回调也会执行该检查。这样可以避免极端情况下旧的 `Connect Matlab` 结果覆盖当前面板状态，例如用户快速重试连接时，较早的失败结果不会把较新的连接状态重置回按钮。

按钮状态恢复遵循以下规则：

- 连接失败时，面板恢复为 `Connect Matlab` 按钮，并弹出错误提示。
- 拟合开始后，`Fit` 按钮禁用并显示 `Fitting...`。
- 拟合成功或失败后，`Fit` 按钮恢复可点击并显示 `Fit`。
- 数据为空、X/Y 长度不一致、参数非法等本地校验失败会提前提示，不会禁用 `Fit` 按钮，也不会进入 MATLAB 子进程调用。

相关测试位于 `tests/test_optional_dependencies.py`，覆盖 MATLAB 可选依赖缺失、连接失败、过期连接回调、表达式加载失败、拟合失败按钮恢复，以及非法拟合参数不会调用 `fit_curve_isolated()`。

当前验证命令：

```powershell
python -m compileall -q .
```

该编译检查已通过。GUI 单测和手动启动需要当前 Python 环境安装 `PySide6`；如果环境缺少该依赖，`python -m unittest tests.test_optional_dependencies` 和 `python main.py` 会在导入 `Qt_core.py` 时失败，错误为 `ModuleNotFoundError: No module named 'PySide6'`。

## 当前实现限制

- `_gof` 拟合优度已从 MATLAB 返回，但暂未展示给用户。
- `value_exp` 和 `show_exp` 当前内容相同，没有区分计算表达式和展示表达式。
- 表达式获取有 fallback，但拟合计算本身没有 Python fallback。

## 维护建议

- 修改 MATLAB 调用逻辑时优先改 `matlab_adapter.py`，保持 GUI 层只负责交互和状态更新。
- 不要在 GUI 主线程中直接调用 MATLAB Runtime 或部署包。
- 新增 MATLAB 操作时应通过 `_run_isolated()` 增加新的 `op`，并继续使用 JSON 协议返回结果。
- 调整部署包或 `.ctf` 文件后，应确认 MCR 缓存 key 逻辑是否仍覆盖所有影响 runtime 缓存的输入文件。
- 如果要展示拟合优度，可以从 `fit_curve()` 返回 `_gof` 中的有效字段，并在 `PyFitMatlabModWidget` 或 MATLAB 面板中增加只读显示区域。
