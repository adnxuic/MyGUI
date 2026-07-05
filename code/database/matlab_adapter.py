from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import importlib
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Iterator

from code.database import fit_result as shared_fit_result
from code.database.py_matlab_fit import fit_type as FIT_TYPES


GET_FUNC_PACKAGE = "code.database.matlab_func.get_func"
CURVE_FITTING_PACKAGE = "code.database.matlab_func.curve_fitting"
_RESULT_PREFIX = "__MATLAB_ADAPTER_RESULT__"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_MCR_CACHE_PARENT = _REPO_ROOT / ".matlab_runtime_cache"
_DEFAULT_LOG_DIR = _REPO_ROOT / "logs"
_LOG_FILE_NAME = "matlab.log"
_LOG_MAX_BYTES = 1_000_000
_LOG_BACKUP_COUNT = 3
LOGGER_NAME = "mygui.matlab"
_LOG_TO_FILE = True
_LOG_TO_STDERR = False
_MCR_CACHE_SCHEMA_VERSION = "v1"
_FILE_HANDLER_MARKER = "_mygui_matlab_file_handler"
_STDERR_HANDLER_MARKER = "_mygui_matlab_stderr_handler"
_LOGGER_SIGNATURE = None


def _timeout_from_env(name: str, default: float) -> float:
    configured = os.environ.get(name)
    if not configured:
        return default
    try:
        timeout = float(configured)
    except ValueError:
        return default
    return timeout if timeout > 0 else default


def _bool_from_env(name: str, default: bool) -> bool:
    configured = os.environ.get(name)
    if configured is None:
        return default
    return configured.strip().lower() in {"1", "true", "yes", "on"}


DEFAULT_CONNECT_TIMEOUT_SECONDS = _timeout_from_env("MYGUI_MATLAB_CONNECT_TIMEOUT_SECONDS", 180)
DEFAULT_EXPRESSION_TIMEOUT_SECONDS = _timeout_from_env("MYGUI_MATLAB_EXPRESSION_TIMEOUT_SECONDS", 120)
DEFAULT_FIT_TIMEOUT_SECONDS = _timeout_from_env("MYGUI_MATLAB_FIT_TIMEOUT_SECONDS", 180)
CONNECT_INITIALIZE_PACKAGES = _bool_from_env("MYGUI_MATLAB_CONNECT_INITIALIZE_PACKAGES", False)
CONFIDENCE_LEVEL = shared_fit_result.CONFIDENCE_LEVEL
GOODNESS_FIELDS = shared_fit_result.GOODNESS_FIELDS
LINEAR_LEAST_SQUARES_FIT_PREFIXES = ("poly",)
LINEAR_LEAST_SQUARES_FIT_NAMES = {"log"}
NONLINEAR_ALGORITHMS = ("Trust-Region", "Levenberg-Marquardt", "Interior-Point")


@dataclass(frozen=True)
class MatlabStatus:
    available: bool
    message: str = ""


MatlabStateListener = Callable[[bool], None]
_MATLAB_ENABLED = False
_MATLAB_STATE_LISTENERS: list[MatlabStateListener] = []


def is_matlab_enabled() -> bool:
    return _MATLAB_ENABLED


def register_matlab_state_listener(listener: MatlabStateListener) -> None:
    if listener not in _MATLAB_STATE_LISTENERS:
        _MATLAB_STATE_LISTENERS.append(listener)


def unregister_matlab_state_listener(listener: MatlabStateListener) -> None:
    try:
        _MATLAB_STATE_LISTENERS.remove(listener)
    except ValueError:
        pass


def clear_matlab_state_listeners() -> None:
    _MATLAB_STATE_LISTENERS.clear()


def _notify_matlab_state_listeners(enabled: bool) -> None:
    for listener in list(_MATLAB_STATE_LISTENERS):
        try:
            listener(enabled)
        except RuntimeError:
            unregister_matlab_state_listener(listener)


def set_matlab_enabled(enabled: bool, notify: bool = True) -> None:
    global _MATLAB_ENABLED
    previous = _MATLAB_ENABLED
    _MATLAB_ENABLED = bool(enabled)
    if notify and previous != _MATLAB_ENABLED:
        _notify_matlab_state_listeners(_MATLAB_ENABLED)


def fit_method_for_name(func_name: str) -> str:
    if func_name in LINEAR_LEAST_SQUARES_FIT_NAMES:
        return "LinearLeastSquares"
    if any(func_name.startswith(prefix) for prefix in LINEAR_LEAST_SQUARES_FIT_PREFIXES):
        suffix = func_name[4:] if func_name.startswith("poly") else ""
        if suffix.isdigit():
            return "LinearLeastSquares"
    return "NonlinearLeastSquares"


def _default_lower_bounds(func_name: str, coefficients: list[str]) -> list[float]:
    lower = [float("-inf")] * len(coefficients)
    if func_name.startswith("gauss"):
        for index, coefficient in enumerate(coefficients):
            if coefficient.startswith("c"):
                lower[index] = 0.0
    return lower


def _default_upper_bounds(coefficients: list[str]) -> list[float]:
    return [float("inf")] * len(coefficients)


def _empty_start_points(method: str, coefficients: list[str]) -> list[float | None]:
    if method != "NonlinearLeastSquares":
        return []
    return [None] * len(coefficients)


def default_fit_options(func_name: str, coefficients: list[str]) -> dict[str, Any]:
    method = fit_method_for_name(func_name)
    options: dict[str, Any] = {
        "Method": method,
        "Normalize": "off",
        "Robust": "Off",
        "Lower": _default_lower_bounds(func_name, coefficients),
        "Upper": _default_upper_bounds(coefficients),
        "TolCon": 1e-6,
        "StartPoint": _empty_start_points(method, coefficients),
    }
    if method == "NonlinearLeastSquares":
        options.update({
            "Algorithm": "Trust-Region",
            "DiffMinChange": 1e-8,
            "DiffMaxChange": 0.1,
            "Display": "Notify",
            "MaxFunEvals": 600,
            "MaxIter": 400,
            "TolFun": 1e-6,
            "TolX": 1e-6,
        })
    return options


def fallback_func_info(func_name: str) -> dict[str, Any]:
    expression, coefficients = _fallback_func_exp(func_name)
    coefficients = [str(coefficient) for coefficient in coefficients]
    return {
        "expression": str(expression),
        "coefficients": coefficients,
        "options": default_fit_options(func_name, coefficients),
    }


def _configured_log_level() -> int:
    configured = os.environ.get("MYGUI_MATLAB_LOG_LEVEL", "INFO").upper()
    return getattr(logging, configured, logging.INFO)


def _configured_log_dir() -> Path:
    configured = os.environ.get("MYGUI_MATLAB_LOG_DIR")
    return Path(configured) if configured else _DEFAULT_LOG_DIR


def _remove_marked_handlers(logger: logging.Logger, marker: str) -> None:
    for handler in list(logger.handlers):
        if getattr(handler, marker, False):
            logger.removeHandler(handler)
            handler.close()


def _handler_path(handler: logging.Handler) -> Path | None:
    base_filename = getattr(handler, "baseFilename", None)
    return Path(base_filename) if base_filename else None


def _has_marked_handler(
    logger: logging.Logger,
    marker: str,
    path: Path | None = None,
) -> bool:
    for handler in logger.handlers:
        if not getattr(handler, marker, False):
            continue
        if path is None or _handler_path(handler) == path:
            return True
    return False


def _logger_has_expected_sinks(
    logger: logging.Logger,
    include_file: bool,
    include_stderr: bool,
    log_file: Path,
) -> bool:
    has_file = _has_marked_handler(logger, _FILE_HANDLER_MARKER, log_file)
    has_stderr = _has_marked_handler(logger, _STDERR_HANDLER_MARKER)
    return (has_file if include_file else not has_file) and (has_stderr if include_stderr else not has_stderr)


def configure_matlab_logging(
    include_file: bool | None = None,
    include_stderr: bool | None = None,
) -> logging.Logger:
    global _LOGGER_SIGNATURE
    if include_file is None:
        include_file = _LOG_TO_FILE
    if include_stderr is None:
        include_stderr = _LOG_TO_STDERR

    logger = logging.getLogger(LOGGER_NAME)
    level = _configured_log_level()
    log_file = _configured_log_dir() / _LOG_FILE_NAME
    signature = (include_file, include_stderr, level, str(log_file))
    logger.setLevel(level)
    logger.propagate = False
    if _LOGGER_SIGNATURE == signature and _logger_has_expected_sinks(
        logger,
        include_file,
        include_stderr,
        log_file,
    ):
        return logger

    _remove_marked_handlers(logger, _FILE_HANDLER_MARKER)
    _remove_marked_handlers(logger, _STDERR_HANDLER_MARKER)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(process)d:%(threadName)s] %(message)s"
    )

    if include_file:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=_LOG_MAX_BYTES,
                backupCount=_LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(level)
            setattr(file_handler, _FILE_HANDLER_MARKER, True)
            logger.addHandler(file_handler)
        except OSError as exc:
            if include_stderr:
                sys.stderr.write(f"MATLAB log file setup failed: {exc}\n")

    if include_stderr:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(formatter)
        stderr_handler.setLevel(level)
        setattr(stderr_handler, _STDERR_HANDLER_MARKER, True)
        logger.addHandler(stderr_handler)

    for handler in logger.handlers:
        if getattr(handler, _FILE_HANDLER_MARKER, False) or getattr(handler, _STDERR_HANDLER_MARKER, False):
            handler.setLevel(level)
    _LOGGER_SIGNATURE = signature
    return logger


def set_matlab_log_sinks(include_file: bool, include_stderr: bool) -> logging.Logger:
    global _LOG_TO_FILE, _LOG_TO_STDERR
    _LOG_TO_FILE = include_file
    _LOG_TO_STDERR = include_stderr
    return configure_matlab_logging()


def matlab_logger() -> logging.Logger:
    return configure_matlab_logging()


def _module_origin(module: Any) -> str:
    module_file = getattr(module, "__file__", None)
    if module_file:
        return str(module_file)
    module_path = getattr(module, "__path__", None)
    if module_path:
        return os.pathsep.join(str(path) for path in module_path)
    return repr(module)


def _import_matlab_runtime() -> Any:
    try:
        matlab = importlib.import_module("matlab")
    except Exception as exc:
        matlab_logger().warning("MATLAB runtime import failed: %s", exc)
        raise RuntimeError(f"MATLAB runtime unavailable: {exc}") from exc

    if not callable(getattr(matlab, "double", None)):
        origin = _module_origin(matlab)
        message = f"imported matlab module is not MathWorks runtime: {origin}"
        matlab_logger().warning("MATLAB runtime rejected: %s", message)
        raise RuntimeError(f"MATLAB runtime unavailable: {message}")

    matlab_logger().debug("MATLAB runtime import succeeded origin=%s", _module_origin(matlab))
    return matlab


def ensure_matlab_available() -> MatlabStatus:
    _import_matlab_runtime()
    return MatlabStatus(True)


def check_matlab_connection(initialize_packages: bool = CONNECT_INITIALIZE_PACKAGES) -> MatlabStatus:
    matlab_logger().debug(
        "MATLAB connection smoke check started initialize_packages=%s",
        initialize_packages,
    )
    ensure_matlab_available()
    for package_name in (GET_FUNC_PACKAGE, CURVE_FITTING_PACKAGE):
        _import_package(package_name)
        matlab_logger().debug("MATLAB package import smoke check succeeded package=%s", package_name)
        if initialize_packages:
            with _initialized_package(package_name):
                matlab_logger().debug("MATLAB package initialize smoke check succeeded package=%s", package_name)
    matlab_logger().debug("MATLAB connection smoke check succeeded")
    return MatlabStatus(True)


def matlab_status() -> MatlabStatus:
    try:
        return ensure_matlab_available()
    except RuntimeError as exc:
        return MatlabStatus(False, str(exc))


def _subprocess_env(mcr_cache_root: str | Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    repo_path = str(_REPO_ROOT)
    env["PYTHONPATH"] = repo_path if not existing_pythonpath else repo_path + os.pathsep + existing_pythonpath
    if mcr_cache_root is not None:
        cache_root = str(mcr_cache_root)
        env["MCR_CACHE_ROOT"] = cache_root
        env["TEMP"] = cache_root
        env["TMP"] = cache_root
    return env


def _cache_input_paths() -> list[Path]:
    matlab_func_root = _REPO_ROOT / "code" / "database" / "matlab_func"
    return [
        matlab_func_root / "get_func" / "__init__.py",
        matlab_func_root / "get_func" / "get_func.ctf",
        matlab_func_root / "curve_fitting" / "__init__.py",
        matlab_func_root / "curve_fitting" / "curve_fitting.ctf",
    ]


def _file_digest(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = path.stat()
    return {
        "path": str(path.relative_to(_REPO_ROOT)),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": digest.hexdigest(),
    }


def _mcr_cache_manifest() -> dict[str, Any]:
    return {
        "schema": _MCR_CACHE_SCHEMA_VERSION,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "packages": [_file_digest(path) for path in _cache_input_paths()],
    }


def _mcr_cache_key() -> str:
    manifest = _mcr_cache_manifest()
    encoded = json.dumps(manifest, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _mcr_cache_root() -> Path:
    configured = os.environ.get("MYGUI_MATLAB_MCR_CACHE_ROOT") or os.environ.get("MCR_CACHE_ROOT")
    if configured:
        return Path(configured)
    return _MCR_CACHE_PARENT / "runtime" / _mcr_cache_key()


def _write_mcr_cache_manifest(cache_root: Path) -> None:
    if os.environ.get("MYGUI_MATLAB_MCR_CACHE_ROOT") or os.environ.get("MCR_CACHE_ROOT"):
        return
    manifest_path = cache_root / "mygui-cache-manifest.json"
    try:
        manifest_path.write_text(
            json.dumps(_mcr_cache_manifest(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
    except OSError as exc:
        matlab_logger().warning("MATLAB MCR cache manifest write failed path=%s error=%s", manifest_path, exc)


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    op = payload.get("op")
    if op == "fit_curve":
        return {
            "op": op,
            "x_len": len(payload.get("x") or []),
            "y_len": len(payload.get("y") or []),
            "fit_type": payload.get("fit_type"),
            "has_fit_options": bool(payload.get("fit_options")),
        }
    if op == "get_func_exp":
        return {"op": op, "func_name": payload.get("func_name")}
    if op == "ensure_matlab_available":
        return {"op": op, "initialize_packages": payload.get("initialize_packages")}
    return {"op": op}


def _log_subprocess_stderr(logger: logging.Logger, op: str, stderr: str | bytes | None) -> None:
    if not stderr:
        return
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    for line in stderr.splitlines():
        line = line.strip()
        if line:
            upper_line = line.upper()
            level = logging.WARNING if any(
                token in upper_line for token in ("WARNING", "ERROR", "TRACEBACK", "EXCEPTION")
            ) else logging.DEBUG
            logger.log(level, "MATLAB subprocess log op=%s %s", op, line)


def _run_isolated(payload: dict[str, Any], timeout: float, failure_prefix: str) -> Any:
    script = f"""
import json
import sys
from code.database import matlab_adapter

PREFIX = {json.dumps(_RESULT_PREFIX)}
payload = json.loads(sys.stdin.read() or "{{}}")
matlab_adapter.set_matlab_log_sinks(include_file=False, include_stderr=True)

try:
    op = payload["op"]
    if op == "ensure_matlab_available":
        status = matlab_adapter.check_matlab_connection(
            initialize_packages=payload.get("initialize_packages", False)
        )
        result = {{"available": status.available, "message": status.message}}
    elif op == "get_func_exp":
        result = matlab_adapter.get_func_exp(payload["func_name"])
    elif op == "get_func_info":
        result = matlab_adapter.get_func_info(payload["func_name"])
    elif op == "fit_curve":
        result = matlab_adapter.fit_curve(
            payload["x"],
            payload["y"],
            payload["fit_type"],
            payload.get("fit_options"),
        )
    else:
        raise RuntimeError(f"unknown MATLAB adapter operation: {{op}}")
    print(PREFIX + json.dumps({{"ok": True, "result": result}}, ensure_ascii=True), flush=True)
except Exception as exc:
    print(PREFIX + json.dumps({{"ok": False, "error": str(exc)}}, ensure_ascii=True), flush=True)
    sys.exit(1)
"""
    logger = matlab_logger()
    op = str(payload.get("op", "unknown"))
    start_time = time.monotonic()
    logger.debug(
        "MATLAB isolated operation started timeout=%s summary=%s",
        timeout,
        _payload_summary(payload),
    )
    mcr_cache_root = _mcr_cache_root()
    mcr_cache_root.mkdir(parents=True, exist_ok=True)
    _write_mcr_cache_manifest(mcr_cache_root)
    logger.debug("MATLAB isolated operation using MCR cache root=%s", mcr_cache_root)
    try:
        completed = subprocess.run(
            [sys.executable, "-B", "-c", script],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=str(_REPO_ROOT),
            env=_subprocess_env(mcr_cache_root),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        _log_subprocess_stderr(logger, op, getattr(exc, "stderr", None))
        elapsed = time.monotonic() - start_time
        logger.warning(
            "MATLAB isolated operation timed out op=%s elapsed=%.3fs timeout=%s",
            op,
            elapsed,
            timeout,
        )
        raise RuntimeError(f"{failure_prefix}: timed out after {timeout:g} seconds") from exc

    elapsed = time.monotonic() - start_time
    _log_subprocess_stderr(logger, op, completed.stderr)
    result_line = None
    for line in reversed((completed.stdout or "").splitlines()):
        if line.startswith(_RESULT_PREFIX):
            result_line = line[len(_RESULT_PREFIX):]
            break

    if result_line is None:
        detail = (completed.stderr or completed.stdout or f"exit code {completed.returncode}").strip()
        if detail:
            detail = detail.splitlines()[-1]
        else:
            detail = "no result from MATLAB subprocess"
        logger.warning(
            "MATLAB isolated operation produced no result op=%s elapsed=%.3fs returncode=%s detail=%s",
            op,
            elapsed,
            completed.returncode,
            detail,
        )
        raise RuntimeError(f"{failure_prefix}: {detail}")

    try:
        result = json.loads(result_line)
    except json.JSONDecodeError as exc:
        logger.warning(
            "MATLAB isolated operation returned invalid JSON op=%s elapsed=%.3fs result=%s",
            op,
            elapsed,
            result_line[:200],
        )
        raise RuntimeError(f"{failure_prefix}: invalid result from MATLAB subprocess") from exc
    if not result.get("ok"):
        error = result.get("error") or failure_prefix
        logger.warning(
            "MATLAB isolated operation failed op=%s elapsed=%.3fs error=%s",
            op,
            elapsed,
            error,
        )
        if error.startswith("MATLAB "):
            raise RuntimeError(error)
        raise RuntimeError(f"{failure_prefix}: {error}")

    logger.debug("MATLAB isolated operation succeeded op=%s elapsed=%.3fs", op, elapsed)
    return result["result"]


def ensure_matlab_available_isolated(
    timeout: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    initialize_packages: bool | None = None,
) -> MatlabStatus:
    if initialize_packages is None:
        initialize_packages = CONNECT_INITIALIZE_PACKAGES
    result = _run_isolated(
        {
            "op": "ensure_matlab_available",
            "initialize_packages": initialize_packages,
        },
        timeout,
        "MATLAB runtime unavailable",
    )
    status = MatlabStatus(bool(result.get("available")), result.get("message", ""))
    if not status.available:
        message = status.message or "not available"
        if not message.startswith("MATLAB "):
            message = f"MATLAB runtime unavailable: {message}"
        raise RuntimeError(message)
    return status


def get_func_exp_isolated(
    func_name: str,
    timeout: float = DEFAULT_EXPRESSION_TIMEOUT_SECONDS,
) -> tuple[str, list[str]]:
    result = _run_isolated(
        {"op": "get_func_exp", "func_name": func_name},
        timeout,
        "MATLAB function extraction failed",
    )
    return result[0], list(result[1])


def get_func_info_isolated(
    func_name: str,
    timeout: float = DEFAULT_EXPRESSION_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    result = _run_isolated(
        {"op": "get_func_info", "func_name": func_name},
        timeout,
        "MATLAB function metadata extraction failed",
    )
    if not isinstance(result, dict):
        raise RuntimeError("MATLAB function metadata extraction failed: invalid metadata result")
    return result


def fit_curve_isolated(
    x: list[float],
    y: list[float],
    fit_type: str,
    fit_options: dict[str, Any] | None = None,
    timeout: float = DEFAULT_FIT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    result = _run_isolated(
        {
            "op": "fit_curve",
            "x": x,
            "y": y,
            "fit_type": fit_type,
            "fit_options": fit_options,
        },
        timeout,
        "MATLAB fitting failed",
    )
    if not isinstance(result, dict):
        raise RuntimeError("MATLAB fitting failed: invalid fitting result")
    return result


def _import_package(package_name: str) -> Any:
    try:
        package = importlib.import_module(package_name)
    except Exception as exc:
        matlab_logger().warning("MATLAB package import failed package=%s error=%s", package_name, exc)
        raise RuntimeError(f"MATLAB package import failed: {exc}") from exc
    matlab_logger().debug("MATLAB package import succeeded package=%s", package_name)
    return package


def _poly_fallback(order: int) -> tuple[str, list[str]]:
    coeffs = [f"p{i}" for i in range(1, order + 2)]
    terms = []
    for index, coeff in enumerate(coeffs):
        power = order - index
        if power > 1:
            terms.append(f"{coeff}*x^{power}")
        elif power == 1:
            terms.append(f"{coeff}*x")
        else:
            terms.append(coeff)
    return " + ".join(terms), coeffs


def _sum_fallback(parts: list[str]) -> str:
    return " + ".join(parts) if parts else ""


def _rat_fallback(numerator_order: int, denominator_order: int) -> tuple[str, list[str]]:
    p_coeffs = [f"p{i}" for i in range(1, numerator_order + 2)]
    q_coeffs = [f"q{i}" for i in range(1, denominator_order + 1)]
    numerator_terms = []
    for index, coeff in enumerate(p_coeffs):
        power = numerator_order - index
        if power > 1:
            numerator_terms.append(f"{coeff}*x^{power}")
        elif power == 1:
            numerator_terms.append(f"{coeff}*x")
        else:
            numerator_terms.append(coeff)

    denominator_terms = []
    for index in range(denominator_order + 1):
        power = denominator_order - index
        if index == 0 and power > 1:
            denominator_terms.append(f"x^{power}")
        elif index == 0 and power == 1:
            denominator_terms.append("x")
        else:
            coeff = f"q{index}"
            if power > 1:
                denominator_terms.append(f"{coeff}*x^{power}")
            elif power == 1:
                denominator_terms.append(f"{coeff}*x")
            else:
                denominator_terms.append(coeff)
    return (
        f"({_sum_fallback(numerator_terms)})/({_sum_fallback(denominator_terms)})",
        p_coeffs + q_coeffs,
    )


def _fallback_func_exp(func_name: str) -> tuple[str, list[str]]:
    if func_name.startswith("poly") and func_name[4:].isdigit():
        return _poly_fallback(int(func_name[4:]))
    if func_name.startswith("exp") and func_name[3:].isdigit():
        order = int(func_name[3:])
        if order == 1:
            return "a*exp(b*x)", ["a", "b"]
        if order == 2:
            return "a*exp(b*x) + c*exp(d*x)", ["a", "b", "c", "d"]
    if func_name == "log":
        return "a*log(x) + b", ["a", "b"]
    if func_name.startswith("fourier") and func_name[7:].isdigit():
        order = int(func_name[7:])
        parts = ["a0"]
        coeffs = ["a0"]
        for index in range(1, order + 1):
            parts.append(f"a{index}*cos({index}*w*x)")
            parts.append(f"b{index}*sin({index}*w*x)")
            coeffs.extend([f"a{index}", f"b{index}"])
        coeffs.append("w")
        return _sum_fallback(parts), coeffs
    if func_name.startswith("gauss") and func_name[5:].isdigit():
        order = int(func_name[5:])
        parts = []
        coeffs = []
        for index in range(1, order + 1):
            parts.append(f"a{index}*exp(-((x-b{index})/c{index})^2)")
            coeffs.extend([f"a{index}", f"b{index}", f"c{index}"])
        return _sum_fallback(parts), coeffs
    if func_name == "power1":
        return "a*x^b", ["a", "b"]
    if func_name == "power2":
        return "a*x^b + c", ["a", "b", "c"]
    if func_name.startswith("rat") and len(func_name) == 5 and func_name[3:].isdigit():
        return _rat_fallback(int(func_name[3]), int(func_name[4]))
    if func_name.startswith("sin") and func_name[3:].isdigit():
        order = int(func_name[3:])
        parts = []
        coeffs = []
        for index in range(1, order + 1):
            parts.append(f"a{index}*sin(b{index}*x+c{index})")
            coeffs.extend([f"a{index}", f"b{index}", f"c{index}"])
        return _sum_fallback(parts), coeffs
    if func_name == "weibull":
        return "a*b*x^(b-1)*exp(-a*x^b)", ["a", "b"]
    if func_name == "logistic":
        return "a/(1+exp(-b*(x-c)))", ["a", "b", "c"]
    if func_name == "logistic4":
        return "d + (a-d)/(1+(x/c)^b)", ["a", "b", "c", "d"]
    if func_name == "gompertz":
        return "a*exp(-b*exp(-c*x))", ["a", "b", "c"]
    raise RuntimeError(f"MATLAB function extraction failed: no fallback expression for {func_name}")


@contextmanager
def _initialized_package(package_name: str) -> Iterator[Any]:
    package = _import_package(package_name)
    try:
        matlab_logger().debug("MATLAB package initialize started package=%s", package_name)
        handle = package.initialize()
    except Exception as exc:
        matlab_logger().warning("MATLAB package initialize failed package=%s error=%s", package_name, exc)
        raise RuntimeError(f"MATLAB runtime unavailable: {exc}") from exc
    matlab_logger().debug("MATLAB package initialize succeeded package=%s", package_name)

    error_raised = False
    try:
        yield handle
    except Exception:
        error_raised = True
        raise
    finally:
        try:
            matlab_logger().debug("MATLAB package terminate started package=%s", package_name)
            handle.terminate()
        except Exception as exc:
            matlab_logger().warning("MATLAB package terminate failed package=%s error=%s", package_name, exc)
            if not error_raised:
                raise RuntimeError(f"MATLAB runtime release failed: {exc}") from exc
        else:
            matlab_logger().debug("MATLAB package terminate succeeded package=%s", package_name)


def _loads_json_object(value: Any) -> dict[str, Any]:
    return shared_fit_result.loads_json_object(value)


def _normalize_func_info(func_name: str, expression: Any, coefficients: Any,
                         option_json: Any | None = None) -> dict[str, Any]:
    coefficient_names = [str(coefficient) for coefficient in list(coefficients or [])]
    options = default_fit_options(func_name, coefficient_names)
    try:
        parsed_options = _loads_json_object(option_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed_options = {}
    if parsed_options:
        options.update(parsed_options)
        options.setdefault("Method", fit_method_for_name(func_name))
        options.setdefault("Normalize", "off")
        options.setdefault("Robust", "Off")
        options.setdefault("Lower", _default_lower_bounds(func_name, coefficient_names))
        options.setdefault("Upper", _default_upper_bounds(coefficient_names))
        options.setdefault("StartPoint", _empty_start_points(options["Method"], coefficient_names))
    return {
        "expression": str(expression),
        "coefficients": coefficient_names,
        "options": options,
    }


def get_func_info(func_name: str) -> dict[str, Any]:
    matlab_logger().debug("MATLAB function metadata extraction started func_name=%s", func_name)
    try:
        with _initialized_package(GET_FUNC_PACKAGE) as get_func:
            try:
                func_exp, func_coefs, option_json = get_func.get_func(func_name, nargout=3)
            except Exception as exc:
                matlab_logger().warning(
                    "MATLAB function metadata extraction failed func_name=%s error=%s",
                    func_name,
                    exc,
                )
                raise RuntimeError(f"MATLAB function metadata extraction failed: {exc}") from exc
    except RuntimeError as exc:
        if not str(exc).startswith("MATLAB runtime unavailable"):
            raise
        info = fallback_func_info(func_name)
        matlab_logger().warning(
            "MATLAB function metadata extraction used fallback func_name=%s reason=%s",
            func_name,
            exc,
        )
        return info
    info = _normalize_func_info(func_name, func_exp, func_coefs, option_json)
    matlab_logger().debug(
        "MATLAB function metadata extraction succeeded func_name=%s coefficient_count=%s",
        func_name,
        len(info["coefficients"]),
    )
    return info


def get_func_exp(func_name: str) -> tuple[str, list[str]]:
    try:
        info = get_func_info(func_name)
    except RuntimeError as exc:
        message = str(exc)
        if message.startswith("MATLAB function metadata extraction failed"):
            message = message.replace(
                "MATLAB function metadata extraction failed",
                "MATLAB function extraction failed",
                1,
            )
            raise RuntimeError(message) from exc
        raise
    return info["expression"], list(info["coefficients"])


def _column_double(matlab: Any, values) -> Any:
    values = [float(value) for value in values]
    return matlab.double(values, size=(len(values), 1))


def _replace_coefficients(expression: str, coefficient_names, coefficient_values) -> str:
    return shared_fit_result.replace_coefficients(expression, coefficient_names, coefficient_values)


def _matlab_text(value: Any) -> str:
    if isinstance(value, (list, tuple)) and len(value) == 1:
        return _matlab_text(value[0])
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _matlab_formula_to_python_expression(formula: Any) -> str:
    expression = _matlab_text(formula).strip()
    expression = re.sub(r"^\s*\w+\s*\([^)]*\)\s*=\s*", "", expression)
    expression = re.sub(r"\.\s*\^", "**", expression)
    expression = re.sub(r"\.\s*\*", "*", expression)
    expression = re.sub(r"\.\s*/", "/", expression)
    return expression.replace("^", "**")


def _as_list(value: Any) -> list[Any]:
    return shared_fit_result.as_list(value)


def _to_float_or_none(value: Any) -> float | None:
    return shared_fit_result.to_float_or_none(value)


def _coefficient_values(coeff_value: Any) -> list[float]:
    return shared_fit_result.coefficient_values(coeff_value)


def _confidence_rows(confidence_bounds: Any, coefficient_count: int) -> tuple[list[float | None], list[float | None]]:
    return shared_fit_result.confidence_rows(confidence_bounds, coefficient_count)


def _goodness_to_dict(gof_value: Any) -> dict[str, float | None]:
    return shared_fit_result.goodness_to_dict(gof_value)


def _build_fit_result(
    fit_type: str,
    formula: Any,
    coefficient_names: Any,
    coefficient_values: Any,
    gof_value: Any = None,
    confidence_bounds: Any = None,
) -> dict[str, Any]:
    formula_text = _matlab_text(formula)
    python_formula = _matlab_formula_to_python_expression(formula_text)
    return shared_fit_result.build_fit_result(
        fit_type,
        formula_text,
        coefficient_names,
        coefficient_values,
        gof_value,
        confidence_bounds,
        python_formula=python_formula,
        confidence_level=CONFIDENCE_LEVEL,
        engine="Matlab",
    )


def _json_fit_option_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_json_fit_option_value(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            return "Inf" if value > 0 else "-Inf"
    return value


def _fit_options_json(fit_options: dict[str, Any] | None) -> str:
    if not fit_options:
        return ""
    fields = (
        "Normalize",
        "Robust",
        "Algorithm",
        "DiffMinChange",
        "DiffMaxChange",
        "Display",
        "MaxFunEvals",
        "MaxIter",
        "TolFun",
        "TolX",
        "TolCon",
        "Lower",
        "Upper",
        "StartPoint",
    )
    payload = {}
    for field in fields:
        value = fit_options.get(field)
        if value is not None and value != "":
            payload[field] = _json_fit_option_value(value)
    return json.dumps(payload, ensure_ascii=True, allow_nan=False)


def _looks_like_signature_mismatch(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(token in message for token in (
        "too many",
        "not enough",
        "number of input",
        "number of output",
        "nargout",
        "positional argument",
        "input arguments",
        "output arguments",
        "\u8f93\u5165\u53c2\u6570\u592a\u591a",
        "\u8f93\u5165\u53c2\u6570\u7684\u6570\u76ee\u592a\u591a",
        "\u8f93\u51fa\u53c2\u6570\u592a\u591a",
        "\u8f93\u51fa\u53c2\u6570\u7684\u6570\u76ee\u592a\u591a",
    ))


def fit_curve(
    x: list[float],
    y: list[float],
    fit_type: str,
    fit_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    matlab_logger().debug(
        "MATLAB fitting started fit_type=%s x_len=%s y_len=%s has_fit_options=%s",
        fit_type,
        len(x),
        len(y),
        bool(fit_options),
    )
    matlab = _import_matlab_runtime()

    with _initialized_package(CURVE_FITTING_PACKAGE) as fitting:
        try:
            x_data = _column_double(matlab, x)
            y_data = _column_double(matlab, y)
            options_json = _fit_options_json(fit_options)
            try:
                exp, coeff_name, coeff_value, gof_json, confidence_bounds, _option_json = fitting.curve_fitting(
                    x_data,
                    y_data,
                    fit_type,
                    options_json,
                    nargout=6,
                )
            except Exception as exc:
                if _looks_like_signature_mismatch(exc):
                    raise RuntimeError(
                        "MATLAB curve_fitting package must be regenerated for the current interface"
                    ) from exc
                raise
        except Exception as exc:
            matlab_logger().warning(
                "MATLAB fitting failed fit_type=%s error=%s",
                fit_type,
                exc,
            )
            raise RuntimeError(f"MATLAB fitting failed: {exc}") from exc

    result = _build_fit_result(fit_type, exp, coeff_name, coeff_value, gof_json, confidence_bounds)

    matlab_logger().debug(
        "MATLAB fitting succeeded fit_type=%s coefficient_count=%s",
        fit_type,
        len(result["coefficients"]),
    )
    return result
