"""Turn LaTeX that models write into plain Unicode math (no LaTeX install needed).

    latex_to_unicode(r"\\phi = 2\\beta - \\arcsin(n \\sin \\beta)")  ->  "φ = 2β − arcsin(n sin β)"

Used on every piece of on-screen text and narration so raw backslash commands never reach a video.
"""
from __future__ import annotations

import re

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ",
    "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν",
    "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ",
    "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ",
    "Psi": "Ψ", "Omega": "Ω",
}
SYMBOLS = {
    "times": "×", "cdot": "·", "div": "÷", "pm": "±", "mp": "∓", "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥",
    "neq": "≠", "ne": "≠", "approx": "≈", "sim": "∼", "equiv": "≡", "propto": "∝", "infty": "∞",
    "to": "→", "rightarrow": "→", "Rightarrow": "⇒", "leftarrow": "←", "leftrightarrow": "↔", "implies": "⇒",
    "iff": "⇔", "in": "∈", "notin": "∉", "subset": "⊂", "subseteq": "⊆", "cup": "∪", "cap": "∩",
    "forall": "∀", "exists": "∃", "partial": "∂", "nabla": "∇", "sum": "Σ", "prod": "Π", "int": "∫",
    "degree": "°", "circ": "°", "angle": "∠", "perp": "⊥", "parallel": "∥", "ldots": "…", "cdots": "⋯",
    "dots": "…", "therefore": "∴", "because": "∵", "neg": "¬", "land": "∧", "lor": "∨", "oplus": "⊕",
    "hbar": "ħ", "ell": "ℓ", "prime": "′",
}
FUNCS = ("arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "sin", "cos", "tan", "sec", "csc", "cot",
         "log", "ln", "exp", "lim", "max", "min", "det", "gcd", "mod")
SUP = str.maketrans("0123456789+-=()niax", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱᵃˣ")
SUB = str.maketrans("0123456789+-=()aeoxn", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₙ")
# identifiers, not display text: template names like "equation_steps" must stay as they are
KEEP_KEYS = {"template", "look", "kind", "src", "id", "style", "backdrop", "transition", "visual_type"}
RAW_LATEX = re.compile(r"\\[A-Za-z]+|\\[{}()\[\]]|\$")


def _script(text: str, table: dict, mark: str) -> str:
    out = text.translate(table)
    # anything without a Unicode super/subscript form stays readable as ^(...) / _(...)
    return out if all(ord(c) in table or c in " " for c in text) and out else f"{mark}({text})"


def _grp(x: str) -> str:
    return x if re.fullmatch(r"[\w.]+", x) else f"({x})"


def latex_to_unicode(s: str) -> str:
    if not s or not any(c in s for c in "\\$^_"):
        return s
    t = s.replace("$$", "").replace("$", "")
    t = re.sub(r"\\(left|right|big|Big|bigg|Bigg)\b\s*", "", t)
    t = re.sub(r"\\(text|mathrm|mathbf|mathit|operatorname|textbf|mathcal)\s*\{([^{}]*)\}", r"\2", t)
    for _ in range(3):  # nested \frac / \sqrt
        t = re.sub(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}",
                   lambda m: f"{_grp(m.group(1))}/{_grp(m.group(2))}", t)
        t = re.sub(r"\\sqrt\s*\[([^\]]*)\]\s*\{([^{}]*)\}", lambda m: f"{m.group(1).translate(SUP)}√({m.group(2)})", t)
        t = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"√(\1)", t)
    t = re.sub(r"\\lim\s*_\{([^{}]*)\}\s*", r"lim(\1) ", t)  # \lim_{x \to 0} -> lim(x → 0)
    t = re.sub(r"\\(" + "|".join(FUNCS) + r")\b\s*", r"\1 ", t)
    # a Greek letter directly before a variable reads as one symbol: \Delta G -> ΔG
    t = re.sub(r"\\([A-Za-z]+) ?(?=[A-Za-z(])", lambda m: GREEK[m.group(1)] if m.group(1) in GREEK else m.group(0), t)
    t = re.sub(r"\\([A-Za-z]+)", lambda m: GREEK.get(m.group(1), SYMBOLS.get(m.group(1), m.group(1))), t)
    t = re.sub(r"\^\{([^{}]*)\}", lambda m: _script(m.group(1), SUP, "^"), t)
    t = re.sub(r"_\{([^{}]*)\}", lambda m: _script(m.group(1), SUB, "_"), t)
    t = re.sub(r"\^([0-9n+\-])", lambda m: m.group(1).translate(SUP), t)
    t = re.sub(r"_([0-9])", lambda m: m.group(1).translate(SUB), t)
    t = re.sub(r"(?<=[A-Za-z)])_([aeoxn])\b", lambda m: m.group(1).translate(SUB), t)
    t = t.replace("\\,", " ").replace("\\;", " ").replace("\\!", "").replace("\\ ", " ")
    t = t.replace("\\{", "{").replace("\\}", "}").replace("{", "").replace("}", "").replace("\\", "")
    t = re.sub(r"(?<=\w)\s+-\s+(?=\w)", " − ", t)
    t = re.sub(r"(\b(?:" + "|".join(FUNCS) + r")) (?=\()", r"\1", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def has_raw_latex(s: str) -> bool:
    return bool(RAW_LATEX.search(s or ""))


def clean_tree(value):
    """latex_to_unicode applied to every string inside dicts and lists (storyboard parameters)."""
    if isinstance(value, str):
        return latex_to_unicode(value)
    if isinstance(value, list):
        return [clean_tree(v) for v in value]
    if isinstance(value, dict):
        return {k: v if k in KEEP_KEYS else clean_tree(v) for k, v in value.items()}
    return value
