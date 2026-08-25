"""Pure-Python MATLAB expression fallbacks that do not start MATLAB or MCR."""

from __future__ import annotations


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
