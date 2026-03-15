#!/usr/bin/env python3
"""Lower a small SVA/SystemVerilog assertion subset into Yosys-compatible code.

Supported subset:
- sequence NAME; TERM [##N TERM]...; endsequence
- sequence NAME; TERM ##[M:N] TERM; endsequence
- property NAME; @(posedge CLK) [disable iff (EXPR)] SEQ; endproperty
- property NAME; @(posedge CLK) [disable iff (EXPR)] SEQ |=> SEQ; endproperty
- property NAME; @(posedge CLK) [disable iff (EXPR)] SEQ |-> SEQ; endproperty
- default clocking @(posedge CLK); endclocking
- default disable iff (EXPR);
- assert/assume/cover property (NAME);
- assert/assume/cover property (EXPR);
- `MACRO property (EXPR); where the macro expands to assert/assume
- bare cover chains using ##[+], e.g. A ##[+] B ##[+] C
- implication consequents of the form HOLD [*] ##1 DONE
- simple bounded-range implication consequents of the form ##[M:N] TERM
- bounded-repeat implication consequents including TERM [*M:N] and TERM [*M:N] ##K NEXT

This is intentionally narrow. It is a prototype frontend, not a complete
SystemVerilog parser.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


SEQUENCE_RE = re.compile(
    r"sequence\s+(?P<name>\w+)\s*;\s*(?P<body>.*?)\s*endsequence\s*",
    re.DOTALL,
)

PROPERTY_RE = re.compile(
    r"property\s+(?P<name>\w+)\s*;\s*(?P<body>.*?)\s*endproperty\s*",
    re.DOTALL,
)

PROPERTY_BODY_RE = re.compile(
    r"""
    @\(\s*posedge\s+(?P<clock>[^)]+?)\s*\)\s*
    (?:disable\s+iff\s*\(\s*(?P<disable>.*?)\s*\)\s*)?
    (?P<expr>.*?)
    \s*;?\s*$
    """,
    re.DOTALL | re.VERBOSE,
)

DEFAULT_CLOCKING_RE = re.compile(
    r"""
    ^\s*default\s+clocking
    (?:\s+\w+)?
    \s*@\(\s*posedge\s+(?P<clock>[^)]+?)\s*\)\s*;
    \s*endclocking\s*;?\s*$
    """,
    re.VERBOSE,
)

DEFAULT_DISABLE_RE = re.compile(
    r"^\s*default\s+disable\s+iff\s*\(\s*(?P<disable>.*?)\s*\)\s*;\s*$",
    re.DOTALL,
)

ACTION_LINE_RE = re.compile(
    r"""
    ^(?P<indent>\s*)
    (?P<kind>assert|assume|cover|`\w+)
    \s+property\s*\(\s*(?P<body>.*)\s*\)\s*;
    \s*$
    """,
    re.DOTALL | re.VERBOSE,
)

FIXED_HOLD_RE = re.compile(
    r"^(?P<hold>.+?)\s*\[\s*\*\s*\]\s*##\s*1\s*(?P<finish>.+)$",
    re.DOTALL,
)

BOUNDED_REPEAT_RE = re.compile(
    r"^(?P<expr>.+?)\s*\[\s*\*\s*(?P<min>\d+)\s*(?::\s*(?P<max>\d+)\s*)?\]\s*$",
    re.DOTALL,
)


@dataclass
class FixedSequence:
    terms: list[str]
    delays: list[int]

    @property
    def total_delay(self) -> int:
        return sum(self.delays)


@dataclass(frozen=True)
class DelayRange:
    min: int
    max: int


@dataclass
class TermToken:
    expr: str
    repeat_min: int = 1
    repeat_max: int = 1


@dataclass
class PatternSequence:
    terms: list[TermToken]
    delays: list[DelayRange]


@dataclass
class UntilSequence:
    hold_expr: str
    finish_expr: str


@dataclass
class EventualChainSequence:
    terms: list[str]


@dataclass
class PathMatch:
    start_offset: int
    samples: list[tuple[int, str]]


@dataclass
class PropertyDef:
    name: str
    clock: str
    disable: str | None
    sequence: FixedSequence | PatternSequence | EventualChainSequence | None = None
    antecedent: FixedSequence | PatternSequence | None = None
    consequent: FixedSequence | PatternSequence | UntilSequence | None = None
    op: str | None = None


@dataclass
class SequenceLogic:
    declarations: list[str]
    clears: list[str]
    updates: list[str]
    invariants: list[str]
    match_expr: str
    match_offsets: dict[int, str]
    max_past_depth: int


@dataclass
class HistoryLogic:
    declarations: list[str]
    clears: list[str]
    updates: list[str]
    invariants: list[str]
    mature_expr: str
    max_past_depth: int


def strip_trailing_semicolon(text: str) -> str:
    return re.sub(r";\s*$", "", text.strip(), flags=re.DOTALL)


def mask_comments(text: str) -> str:
    chars = list(text)
    index = 0
    while index < len(chars):
        if chars[index] == "/" and index + 1 < len(chars):
            nxt = chars[index + 1]
            if nxt == "/":
                chars[index] = " "
                chars[index + 1] = " "
                index += 2
                while index < len(chars) and chars[index] != "\n":
                    chars[index] = " "
                    index += 1
                continue
            if nxt == "*":
                chars[index] = " "
                chars[index + 1] = " "
                index += 2
                while index + 1 < len(chars):
                    if chars[index] == "*" and chars[index + 1] == "/":
                        chars[index] = " "
                        chars[index + 1] = " "
                        index += 2
                        break
                    if chars[index] != "\n":
                        chars[index] = " "
                    index += 1
                continue
        index += 1
    return "".join(chars)


def zero_literal(width: int) -> str:
    return "1'b0" if width == 1 else f"{width}'b0"


def declare_history_reg(name: str, depth: int) -> str:
    if depth == 1:
        return f"\treg {name};\n"
    return f"\treg [{depth - 1}:0] {name};\n"


def declare_width_reg(name: str, width: int) -> str:
    if width == 1:
        return f"\treg {name};\n"
    return f"\treg [{width - 1}:0] {name};\n"


def shift_assignment(name: str, depth: int, expr: str) -> str:
    if depth == 1:
        return f"\t\t\t{name} <= ({expr});\n"
    return f"\t\t\t{name} <= {{{name}[{depth - 2}:0], ({expr})}};\n"


def sanitize_identifier(text: str) -> str:
    sanitized = re.sub(r"\W+", "_", text).strip("_")
    return sanitized or "anon"


def strip_wrapping_parens(text: str) -> str:
    stripped = text.strip()
    while stripped.startswith("(") and stripped.endswith(")"):
        depth = 0
        balanced = True
        for index, char in enumerate(stripped):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(stripped) - 1:
                    balanced = False
                    break
        if not balanced or depth != 0:
            return stripped
        stripped = stripped[1:-1].strip()
    return stripped


def past_expr(expr: str, depth: int) -> str:
    normalized = strip_wrapping_parens(expr)
    if normalized == "1'b1":
        return "1'b1"
    if normalized == "1'b0":
        return "1'b0"
    wrapped = f"({expr})"
    if depth == 1:
        return f"$past({wrapped})"
    return f"$past({wrapped}, {depth})"


def past_valid_line(name: str, depth: int, check_expr: str) -> str:
    gate = name if depth == 1 else f"{name}[{depth - 1}]"
    return f"\t\t\tif ({gate}) assert ({check_expr});\n"


def placeholder_valid_gate(depth: int) -> str:
    if depth <= 0:
        return "1'b1"
    if depth == 1:
        return "__SVA_PAST_VALID_PLACEHOLDER__"
    return f"__SVA_PAST_VALID_PLACEHOLDER__[{depth - 1}]"


def delay_literal(delay: DelayRange) -> str:
    return str(delay.min) if delay.min == delay.max else f"[{delay.min}:{delay.max}]"


def split_top_level(expr: str, token: str) -> list[str]:
    parts: list[str] = []
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    start = 0
    index = 0
    while index < len(expr):
        char = expr[index]
        if char == "(":
            depth_paren += 1
        elif char == ")":
            depth_paren -= 1
        elif char == "{":
            depth_brace += 1
        elif char == "}":
            depth_brace -= 1
        elif char == "[":
            depth_bracket += 1
        elif char == "]":
            depth_bracket -= 1

        if (
            depth_paren == 0
            and depth_brace == 0
            and depth_bracket == 0
            and expr.startswith(token, index)
        ):
            parts.append(expr[start:index])
            index += len(token)
            start = index
            continue
        index += 1
    parts.append(expr[start:])
    return parts


def parse_delay_token(expr: str, index: int) -> tuple[DelayRange, int] | None:
    if not expr.startswith("##", index):
        return None

    cursor = index + 2
    while cursor < len(expr) and expr[cursor].isspace():
        cursor += 1

    if cursor < len(expr) and expr[cursor] == "[":
        cursor += 1
        while cursor < len(expr) and expr[cursor].isspace():
            cursor += 1

        start = cursor
        while cursor < len(expr) and expr[cursor].isdigit():
            cursor += 1
        if start == cursor:
            return None
        min_delay = int(expr[start:cursor])

        while cursor < len(expr) and expr[cursor].isspace():
            cursor += 1

        if cursor >= len(expr) or expr[cursor] != ":":
            return None
        cursor += 1

        while cursor < len(expr) and expr[cursor].isspace():
            cursor += 1

        start = cursor
        while cursor < len(expr) and expr[cursor].isdigit():
            cursor += 1
        if start == cursor:
            return None
        max_delay = int(expr[start:cursor])

        while cursor < len(expr) and expr[cursor].isspace():
            cursor += 1

        if cursor >= len(expr) or expr[cursor] != "]":
            return None
        cursor += 1
        return DelayRange(min_delay, max_delay), cursor

    start = cursor
    while cursor < len(expr) and expr[cursor].isdigit():
        cursor += 1
    if start == cursor:
        return None
    delay = int(expr[start:cursor])
    return DelayRange(delay, delay), cursor


def find_implication(expr: str) -> tuple[str, str, str] | None:
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    index = 0
    while index < len(expr):
        char = expr[index]
        if char == "(":
            depth_paren += 1
        elif char == ")":
            depth_paren -= 1
        elif char == "{":
            depth_brace += 1
        elif char == "}":
            depth_brace -= 1
        elif char == "[":
            depth_bracket += 1
        elif char == "]":
            depth_bracket -= 1

        if depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
            if expr.startswith("|=>", index):
                return expr[:index], "|=>", expr[index + 3 :]
            if expr.startswith("|->", index):
                return expr[:index], "|->", expr[index + 3 :]
        index += 1
    return None


def split_sequence_parts(expr: str) -> tuple[list[str], list[DelayRange]]:
    stripped = strip_trailing_semicolon(expr)
    terms: list[str] = []
    delays: list[DelayRange] = []
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    start = 0
    index = 0
    while index < len(stripped):
        char = stripped[index]
        if char == "(":
            depth_paren += 1
        elif char == ")":
            depth_paren -= 1
        elif char == "{":
            depth_brace += 1
        elif char == "}":
            depth_brace -= 1
        elif char == "[":
            depth_bracket += 1
        elif char == "]":
            depth_bracket -= 1

        if depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
            parsed_delay = parse_delay_token(stripped, index)
            if parsed_delay is not None:
                delay, next_index = parsed_delay
                term = stripped[start:index].strip()
                if term:
                    terms.append(term)
                elif terms:
                    raise ValueError(f"Malformed sequence expression '{expr.strip()}'")
                delays.append(delay)
                index = next_index
                start = next_index
                continue
        index += 1

    tail = stripped[start:].strip()
    if tail:
        terms.append(tail)
    if len(terms) != len(delays) + 1:
        raise ValueError(f"Malformed sequence expression '{expr.strip()}'")
    return terms, delays


def parse_term_token(expr: str) -> TermToken:
    repeat_match = BOUNDED_REPEAT_RE.fullmatch(expr.strip())
    if repeat_match:
        repeat_min = int(repeat_match.group("min"))
        repeat_max = int(repeat_match.group("max") or repeat_match.group("min"))
        if repeat_max < repeat_min:
            raise ValueError(f"Malformed repetition range '{expr.strip()}'")
        return TermToken(
            expr=strip_wrapping_parens(repeat_match.group("expr")),
            repeat_min=repeat_min,
            repeat_max=repeat_max,
        )
    return TermToken(expr=strip_wrapping_parens(expr))


def concat_pattern_sequence(
    lhs: PatternSequence,
    rhs: PatternSequence,
    bridge: DelayRange | None = None,
) -> PatternSequence:
    if not lhs.terms:
        return PatternSequence(list(rhs.terms), list(rhs.delays))
    if not rhs.terms:
        return PatternSequence(list(lhs.terms), list(lhs.delays))

    delays = list(lhs.delays)
    if bridge is not None:
        delays.append(bridge)
    delays.extend(rhs.delays)
    return PatternSequence(list(lhs.terms) + list(rhs.terms), delays)


def parse_pattern_sequence(
    expr: str,
    sequence_defs: dict[str, str],
    active: tuple[str, ...] = (),
) -> PatternSequence:
    raw_terms, raw_delays = split_sequence_parts(expr)
    pattern = PatternSequence([], [])

    for index, raw_term in enumerate(raw_terms):
        term = strip_wrapping_parens(raw_term)
        if term in sequence_defs:
            if term in active:
                cycle = " -> ".join(active + (term,))
                raise ValueError(f"Recursive sequence reference is unsupported: {cycle}")
            nested = parse_sequence_expr(sequence_defs[term], sequence_defs, active + (term,))
            if isinstance(nested, (UntilSequence, EventualChainSequence)):
                raise ValueError(f"Named sequence '{term}' uses unsupported operators")
            if isinstance(nested, FixedSequence):
                nested_pattern = PatternSequence(
                    [TermToken(expr=token) for token in nested.terms],
                    [DelayRange(delay, delay) for delay in nested.delays],
                )
            else:
                nested_pattern = nested
        else:
            nested_pattern = PatternSequence([parse_term_token(term)], [])

        bridge = raw_delays[index - 1] if index > 0 else None
        pattern = concat_pattern_sequence(pattern, nested_pattern, bridge)

    return pattern


def is_exact_pattern(pattern: PatternSequence) -> bool:
    return all(term.repeat_min == 1 and term.repeat_max == 1 for term in pattern.terms) and all(
        delay.min == delay.max for delay in pattern.delays
    )


def pattern_to_fixed(pattern: PatternSequence) -> FixedSequence:
    return FixedSequence(
        terms=[term.expr for term in pattern.terms],
        delays=[delay.min for delay in pattern.delays],
    )


def parse_sequence_expr(
    expr: str,
    sequence_defs: dict[str, str],
    active: tuple[str, ...] = (),
) -> FixedSequence | PatternSequence | UntilSequence | EventualChainSequence:
    stripped = strip_trailing_semicolon(strip_wrapping_parens(expr))

    leading_delay = parse_delay_token(stripped, 0)
    if leading_delay is not None:
        delay, next_index = leading_delay
        stripped = f"1'b1 ##{delay_literal(delay)} {stripped[next_index:].strip()}"

    plus_parts = [part.strip() for part in split_top_level(stripped, "##[+]")]
    if len(plus_parts) > 1:
        if any(not part for part in plus_parts):
            raise ValueError(f"Malformed ##[+] chain '{expr.strip()}'")
        return EventualChainSequence([strip_wrapping_parens(part) for part in plus_parts])

    hold_match = FIXED_HOLD_RE.fullmatch(stripped)
    if hold_match:
        return UntilSequence(
            hold_expr=strip_wrapping_parens(hold_match.group("hold")),
            finish_expr=strip_wrapping_parens(hold_match.group("finish")),
        )

    pattern = parse_pattern_sequence(stripped, sequence_defs, active)
    if is_exact_pattern(pattern):
        return pattern_to_fixed(pattern)
    return pattern


def parse_property_expr(
    name: str,
    expr: str,
    sequence_defs: dict[str, str],
    clock: str,
    disable: str | None,
) -> PropertyDef:
    stripped = strip_trailing_semicolon(strip_wrapping_parens(expr))
    implication = find_implication(stripped)
    if implication is not None:
        lhs, op, rhs = implication
        antecedent = parse_sequence_expr(lhs, sequence_defs)
        if isinstance(antecedent, (UntilSequence, EventualChainSequence)):
            raise ValueError(f"Unsupported antecedent sequence for '{name}'")
        consequent = parse_sequence_expr(rhs, sequence_defs)
        if isinstance(consequent, EventualChainSequence):
            raise ValueError(f"Unsupported implication consequent for '{name}'")
        return PropertyDef(
            name=name,
            clock=clock,
            disable=disable,
            antecedent=antecedent,
            consequent=consequent,
            op=op,
        )

    sequence = parse_sequence_expr(stripped, sequence_defs)
    if isinstance(sequence, UntilSequence):
        raise ValueError(f"Bare HOLD [*] ##1 DONE sequences are unsupported for '{name}'")
    return PropertyDef(name=name, clock=clock, disable=disable, sequence=sequence)


def parse_property(
    name: str,
    body: str,
    sequence_defs: dict[str, str],
    default_clock: str | None = None,
    default_disable: str | None = None,
) -> PropertyDef:
    match = PROPERTY_BODY_RE.fullmatch(body.strip())
    if match:
        clock = match.group("clock").strip()
        disable = match.group("disable").strip() if match.group("disable") else default_disable
        expr = match.group("expr")
        return parse_property_expr(name, expr, sequence_defs, clock, disable)

    if default_clock is None:
        raise ValueError(
            f"Unsupported property body for '{name}'. "
            "Supported form is @(posedge clk) [disable iff (expr)] A |=> B;"
        )

    return parse_property_expr(name, body, sequence_defs, default_clock, default_disable)


def compile_fixed_sequence(seq: FixedSequence, prefix: str) -> SequenceLogic:
    declarations: list[str] = []
    clears: list[str] = []
    updates: list[str] = []
    invariants: list[str] = []
    match_terms: list[str] = []
    max_past_depth = 0

    for index, term in enumerate(seq.terms):
        delay_to_end = sum(seq.delays[index:]) if index < len(seq.delays) else 0
        if delay_to_end == 0:
            match_terms.append(f"({term})")
            continue

        reg_name = f"{prefix}_t{index}"
        declarations.append(declare_history_reg(reg_name, delay_to_end))
        clears.append(f"\t\t\t{reg_name} <= {zero_literal(delay_to_end)};\n")
        updates.append(shift_assignment(reg_name, delay_to_end, term))
        max_past_depth = max(max_past_depth, delay_to_end)
        if delay_to_end == 1:
            invariants.append(
                past_valid_line(
                    "__SVA_PAST_VALID_PLACEHOLDER__",
                    1,
                    f"{reg_name} == {past_expr(term, 1)}",
                )
            )
        else:
            for age in range(delay_to_end):
                invariants.append(
                    past_valid_line(
                        "__SVA_PAST_VALID_PLACEHOLDER__",
                        age + 1,
                        f"{reg_name}[{age}] == {past_expr(term, age + 1)}",
                    )
                )
        match_terms.append(reg_name if delay_to_end == 1 else f"{reg_name}[{delay_to_end - 1}]")

    return SequenceLogic(
        declarations=declarations,
        clears=clears,
        updates=updates,
        invariants=invariants,
        match_expr=" && ".join(match_terms) if match_terms else "1'b1",
        match_offsets={seq.total_delay: " && ".join(match_terms) if match_terms else "1'b1"},
        max_past_depth=max_past_depth,
    )


def conjunction_expr(parts: list[str]) -> str:
    if not parts:
        return "1'b1"
    if len(parts) == 1:
        return parts[0]
    return "(" + " && ".join(parts) + ")"


def disjunction_expr(parts: list[str]) -> str:
    if not parts:
        return "1'b0"
    if len(parts) == 1:
        return parts[0]
    return "(" + " || ".join(parts) + ")"


def token_paths(token: TermToken) -> list[PathMatch]:
    paths: list[PathMatch] = []
    for length in range(token.repeat_min, token.repeat_max + 1):
        samples = [(age, token.expr) for age in range(length)]
        paths.append(PathMatch(start_offset=length - 1, samples=samples))
    return paths


def shift_path(path: PathMatch, amount: int) -> PathMatch:
    return PathMatch(
        start_offset=path.start_offset + amount,
        samples=[(offset + amount, expr) for offset, expr in path.samples],
    )


def enumerate_pattern_paths(pattern: PatternSequence) -> list[PathMatch]:
    assert pattern.terms

    paths = token_paths(pattern.terms[-1])
    for index in range(len(pattern.terms) - 2, -1, -1):
        next_paths: list[PathMatch] = []
        for suffix in paths:
            delay = pattern.delays[index]
            for gap in range(delay.min, delay.max + 1):
                shift = suffix.start_offset + gap
                for prefix_path in token_paths(pattern.terms[index]):
                    shifted = shift_path(prefix_path, shift)
                    next_paths.append(
                        PathMatch(
                            start_offset=shifted.start_offset,
                            samples=shifted.samples + suffix.samples,
                        )
                    )
        paths = next_paths
    return paths


def render_path_expr(path: PathMatch) -> str:
    body_terms: list[str] = []
    max_offset = 0
    for offset, expr in path.samples:
        normalized = strip_wrapping_parens(expr)
        max_offset = max(max_offset, offset)
        if normalized == "1'b1":
            body_terms.append("1'b1")
            continue
        if normalized == "1'b0":
            body_terms.append("1'b0")
            continue
        if offset == 0:
            body_terms.append(f"({expr})")
        else:
            body_terms.append(past_expr(expr, offset))
    body = conjunction_expr(body_terms)
    if max_offset == 0:
        return body
    return conjunction_expr([placeholder_valid_gate(max_offset), body])


def compile_pattern_sequence(seq: PatternSequence, prefix: str) -> SequenceLogic:
    del prefix
    paths = enumerate_pattern_paths(seq)
    offset_exprs: dict[int, list[str]] = {}
    max_past_depth = 0
    for path in paths:
        max_past_depth = max(max_past_depth, path.start_offset)
        offset_exprs.setdefault(path.start_offset, []).append(render_path_expr(path))

    match_offsets = {offset: disjunction_expr(exprs) for offset, exprs in offset_exprs.items()}
    return SequenceLogic(
        declarations=[],
        clears=[],
        updates=[],
        invariants=[],
        match_expr=disjunction_expr(list(match_offsets.values())),
        match_offsets=match_offsets,
        max_past_depth=max_past_depth,
    )


def compile_history(expr: str, prefix: str, depth: int) -> HistoryLogic:
    reg_name = f"{prefix}_hist"
    invariants: list[str] = []
    if depth == 1:
        invariants.append(
            past_valid_line(
                "__SVA_PAST_VALID_PLACEHOLDER__",
                1,
                f"{reg_name} == {past_expr(expr, 1)}",
            )
        )
    else:
        for age in range(depth):
            invariants.append(
                past_valid_line(
                    "__SVA_PAST_VALID_PLACEHOLDER__",
                    age + 1,
                    f"{reg_name}[{age}] == {past_expr(expr, age + 1)}",
                )
            )
    return HistoryLogic(
        declarations=[declare_history_reg(reg_name, depth)],
        clears=[f"\t\t\t{reg_name} <= {zero_literal(depth)};\n"],
        updates=[shift_assignment(reg_name, depth, expr)],
        invariants=invariants,
        mature_expr=reg_name if depth == 1 else f"{reg_name}[{depth - 1}]",
        max_past_depth=depth,
    )


def action_line(kind: str, trigger: str, check_expr: str) -> str:
    if kind == "cover":
        return f"\t\t\tif (({trigger}) && ({check_expr})) cover (1'b1);\n"
    return f"\t\t\tif ({trigger}) {kind} ({check_expr});\n"


def wrap_formal_block(
    prefix: str,
    clock: str,
    disable: str | None,
    declarations: list[str],
    clears: list[str],
    invariant_lines: list[str],
    max_past_depth: int,
    action_lines: list[str],
    updates: list[str],
) -> str:
    if max_past_depth > 0:
        past_valid_name = f"{prefix}_past_valid"
        declarations.append(declare_history_reg(past_valid_name, max_past_depth))
        clears.append(f"\t\t\t{past_valid_name} <= {zero_literal(max_past_depth)};\n")
        updates.append(shift_assignment(past_valid_name, max_past_depth, "1'b1"))
        invariant_lines = [
            line.replace("__SVA_PAST_VALID_PLACEHOLDER__", past_valid_name)
            for line in invariant_lines
        ]
        action_lines = [
            line.replace("__SVA_PAST_VALID_PLACEHOLDER__", past_valid_name)
            for line in action_lines
        ]
        updates = [line.replace("__SVA_PAST_VALID_PLACEHOLDER__", past_valid_name) for line in updates]

    initial_lines: list[str] = []
    if clears:
        initial_lines.append("\tinitial begin\n")
        initial_lines.extend(line.replace("\t\t\t", "\t\t", 1) for line in clears)
        initial_lines.append("\tend\n")

    always_lines: list[str] = [f"\talways @(posedge {clock}) begin\n"]
    if disable:
        always_lines.append(f"\t\tif ({disable}) begin\n")
        always_lines.extend(clears)
        always_lines.append("\t\tend else begin\n")
        always_lines.extend(invariant_lines)
        always_lines.extend(action_lines)
        always_lines.extend(updates)
        always_lines.append("\t\tend\n")
    else:
        always_lines.extend(invariant_lines)
        always_lines.extend(action_lines)
        always_lines.extend(updates)
    always_lines.append("\tend\n")

    return "".join(declarations + initial_lines + always_lines)


def emit_until_action(kind: str, prefix: str, prop: PropertyDef, antecedent: SequenceLogic) -> str:
    assert isinstance(prop.consequent, UntilSequence)
    declarations = list(antecedent.declarations)
    clears = list(antecedent.clears)
    updates = list(antecedent.updates)
    invariants = list(antecedent.invariants)
    max_past_depth = antecedent.max_past_depth

    start_expr = antecedent.match_expr
    if prop.op == "|=>":
        history = compile_history(start_expr, f"{prefix}_launch", 1)
        declarations.extend(history.declarations)
        clears.extend(history.clears)
        updates.extend(history.updates)
        invariants.extend(history.invariants)
        max_past_depth = max(max_past_depth, history.max_past_depth)
        start_expr = history.mature_expr

    wait_reg = f"{prefix}_wait"
    declarations.append(declare_history_reg(wait_reg, 1))
    clears.append(f"\t\t\t{wait_reg} <= 1'b0;\n")
    invariants.append(
        past_valid_line(
            "__SVA_PAST_VALID_PLACEHOLDER__",
            1,
            f"{wait_reg} == {past_expr(f'(({wait_reg}) && !({prop.consequent.finish_expr})) || ({start_expr})', 1)}",
        )
    )
    max_past_depth = max(max_past_depth, 1)

    action_lines = [
        f"\t\t\tif ({wait_reg} && !({prop.consequent.finish_expr})) "
        f"{kind} (({prop.consequent.hold_expr}));\n"
    ]
    updates.append(
        f"\t\t\t{wait_reg} <= (({wait_reg}) && !({prop.consequent.finish_expr})) || ({start_expr});\n"
    )

    return wrap_formal_block(
        prefix,
        prop.clock,
        prop.disable,
        declarations,
        clears,
        invariants,
        max_past_depth,
        action_lines,
        updates,
    )


def emit_cover_chain(prefix: str, prop: PropertyDef, sequence: EventualChainSequence) -> str:
    if len(sequence.terms) < 2:
        raise ValueError(f"Unsupported cover chain for '{prop.name}'")

    width = max(1, (len(sequence.terms) - 1).bit_length())
    stage_reg = f"{prefix}_stage"
    declarations = [declare_width_reg(stage_reg, width)]
    clears = [f"\t\t\t{stage_reg} <= {zero_literal(width)};\n"]
    invariants: list[str] = []

    action_lines: list[str] = []
    updates: list[str] = []
    next_lines: list[str] = [f"\t\t\t{stage_reg} <= {stage_reg};\n"]

    action_lines.append(
        f"\t\t\tif (({stage_reg} == {width}'d{len(sequence.terms) - 1}) && ({sequence.terms[-1]})) "
        "cover (1'b1);\n"
    )

    next_lines.append(f"\t\t\tif (({stage_reg} == {width}'d0) && ({sequence.terms[0]})) begin\n")
    next_lines.append(f"\t\t\t\t{stage_reg} <= {width}'d1;\n")
    next_lines.append("\t\t\tend\n")

    for index in range(1, len(sequence.terms) - 1):
        next_lines.append(
            f"\t\t\telse if (({stage_reg} == {width}'d{index}) && ({sequence.terms[index]})) begin\n"
        )
        next_lines.append(f"\t\t\t\t{stage_reg} <= {width}'d{index + 1};\n")
        next_lines.append("\t\t\tend\n")

    next_lines.append(
        f"\t\t\telse if (({stage_reg} == {width}'d{len(sequence.terms) - 1}) "
        f"&& ({sequence.terms[-1]})) begin\n"
    )
    next_lines.append(f"\t\t\t\t{stage_reg} <= {width}'d0;\n")
    next_lines.append("\t\t\tend\n")
    updates.extend(next_lines)

    return wrap_formal_block(
        prefix,
        prop.clock,
        prop.disable,
        declarations,
        clears,
        invariants,
        0,
        action_lines,
        updates,
    )


def simple_ranged_delay(pattern: PatternSequence) -> tuple[DelayRange, str] | None:
    if len(pattern.terms) != 2 or len(pattern.delays) != 1:
        return None
    if pattern.terms[0].repeat_min != 1 or pattern.terms[0].repeat_max != 1:
        return None
    if pattern.terms[1].repeat_min != 1 or pattern.terms[1].repeat_max != 1:
        return None
    if strip_wrapping_parens(pattern.terms[0].expr) != "1'b1":
        return None
    delay = pattern.delays[0]
    if delay.min == delay.max:
        return None
    return delay, pattern.terms[1].expr


def ranged_delay_assignment(name: str, depth: int, launch_expr: str, term_expr: str, delay: DelayRange) -> str:
    next_bits: list[str] = [f"({launch_expr})"]
    for age in range(1, depth):
        source = name if age == 1 else f"{name}[{age - 1}]"
        if delay.min <= age + 1 <= delay.max:
            next_bits.append(f"(({source}) && !({term_expr}))")
        else:
            next_bits.append(f"({source})")

    if depth == 1:
        return f"\t\t\t{name} <= {next_bits[0]};\n"
    return f"\t\t\t{name} <= {{{', '.join(reversed(next_bits))}}};\n"


def emit_simple_ranged_delay_implication(
    kind: str,
    prefix: str,
    prop: PropertyDef,
    antecedent: SequenceLogic,
    pattern: PatternSequence,
) -> str:
    parsed = simple_ranged_delay(pattern)
    assert parsed is not None
    delay, term_expr = parsed

    declarations = list(antecedent.declarations)
    clears = list(antecedent.clears)
    updates = list(antecedent.updates)
    invariants = list(antecedent.invariants)
    max_past_depth = antecedent.max_past_depth

    launch_expr = antecedent.match_expr
    if prop.op == "|=>":
        history = compile_history(launch_expr, f"{prefix}_launch", 1)
        declarations.extend(history.declarations)
        clears.extend(history.clears)
        updates.extend(history.updates)
        invariants.extend(history.invariants)
        max_past_depth = max(max_past_depth, history.max_past_depth)
        launch_expr = history.mature_expr

    pending_name = f"{prefix}_pending"
    declarations.append(declare_history_reg(pending_name, delay.max))
    clears.append(f"\t\t\t{pending_name} <= {zero_literal(delay.max)};\n")
    updates.append(ranged_delay_assignment(pending_name, delay.max, launch_expr, term_expr, delay))
    max_past_depth = max(max_past_depth, delay.max)

    oldest = pending_name if delay.max == 1 else f"{pending_name}[{delay.max - 1}]"
    action_lines = [action_line(kind, oldest, term_expr)]
    return wrap_formal_block(
        prefix,
        prop.clock,
        prop.disable,
        declarations,
        clears,
        invariants,
        max_past_depth,
        action_lines,
        updates,
    )


def emit_pattern_implication(
    kind: str,
    prefix: str,
    prop: PropertyDef,
    antecedent: SequenceLogic,
    pattern: PatternSequence,
) -> str:
    declarations = list(antecedent.declarations)
    clears = list(antecedent.clears)
    updates = list(antecedent.updates)
    invariants = list(antecedent.invariants)
    max_past_depth = antecedent.max_past_depth

    paths = enumerate_pattern_paths(pattern)
    latest = max(path.start_offset for path in paths)
    check_expr = disjunction_expr(
        [render_path_expr(shift_path(path, latest - path.start_offset)) for path in paths]
    )
    max_past_depth = max(max_past_depth, latest)

    trigger_expr = antecedent.match_expr
    trigger_base = strip_wrapping_parens(trigger_expr)
    total_offset = latest + (1 if prop.op == "|=>" else 0)

    if trigger_base == "1'b1":
        trigger = "1'b1" if total_offset == 0 else placeholder_valid_gate(total_offset)
    elif trigger_base == "1'b0":
        trigger = "1'b0"
    elif total_offset == 0:
        trigger = trigger_expr
    else:
        history = compile_history(trigger_expr, f"{prefix}_launch", total_offset)
        declarations.extend(history.declarations)
        clears.extend(history.clears)
        updates.extend(history.updates)
        invariants.extend(history.invariants)
        max_past_depth = max(max_past_depth, history.max_past_depth)
        trigger = history.mature_expr

    action_lines = [action_line(kind, trigger, check_expr)]
    return wrap_formal_block(
        prefix,
        prop.clock,
        prop.disable,
        declarations,
        clears,
        invariants,
        max_past_depth,
        action_lines,
        updates,
    )


def emit_action(kind: str, prop: PropertyDef) -> str:
    prefix = f"__sva_{sanitize_identifier(kind)}_{prop.name}"
    declarations: list[str] = []
    clears: list[str] = []
    updates: list[str] = []
    invariants: list[str] = []
    max_past_depth = 0

    def add_sequence_logic(seq: FixedSequence | PatternSequence, role: str) -> SequenceLogic:
        if isinstance(seq, FixedSequence):
            logic = compile_fixed_sequence(seq, f"{prefix}_{role}")
        else:
            logic = compile_pattern_sequence(seq, f"{prefix}_{role}")
        declarations.extend(logic.declarations)
        clears.extend(logic.clears)
        updates.extend(logic.updates)
        invariants.extend(logic.invariants)
        nonlocal max_past_depth
        max_past_depth = max(max_past_depth, logic.max_past_depth)
        return logic

    if prop.sequence is not None:
        if isinstance(prop.sequence, EventualChainSequence):
            if kind != "cover":
                raise ValueError(
                    f"{kind} property ({prop.name}) uses an unsupported ##[+] bare sequence"
                )
            return emit_cover_chain(prefix, prop, prop.sequence)

        seq_logic = add_sequence_logic(prop.sequence, "seq")
        if kind != "cover" and any(offset > 0 for offset in seq_logic.match_offsets):
            raise ValueError(
                f"{kind} property ({prop.name}) uses a multi-cycle bare sequence. "
                "Wrap it in an implication property first."
            )
        action_lines = [action_line(kind, "1'b1", seq_logic.match_expr)]
        return wrap_formal_block(
            prefix,
            prop.clock,
            prop.disable,
            declarations,
            clears,
            invariants,
            max_past_depth,
            action_lines,
            updates,
        )

    assert prop.antecedent is not None
    assert prop.consequent is not None
    antecedent_logic = add_sequence_logic(prop.antecedent, "ant")

    if isinstance(prop.consequent, UntilSequence):
        return emit_until_action(kind, prefix, prop, antecedent_logic)
    if isinstance(prop.consequent, PatternSequence):
        if simple_ranged_delay(prop.consequent) is not None:
            return emit_simple_ranged_delay_implication(
                kind,
                prefix,
                prop,
                antecedent_logic,
                prop.consequent,
            )
        return emit_pattern_implication(kind, prefix, prop, antecedent_logic, prop.consequent)

    consequent_logic = add_sequence_logic(prop.consequent, "con")
    extra_offset = 1 if prop.op == "|=>" else 0
    max_offset = max(consequent_logic.match_offsets) + extra_offset
    trigger_expr = antecedent_logic.match_expr
    trigger_base = strip_wrapping_parens(trigger_expr)
    history: HistoryLogic | None = None
    if max_offset > 0 and trigger_base not in {"1'b1", "1'b0"}:
        history = compile_history(trigger_expr, f"{prefix}_launch", max_offset)
        declarations.extend(history.declarations)
        clears.extend(history.clears)
        updates.extend(history.updates)
        invariants.extend(history.invariants)
        max_past_depth = max(max_past_depth, history.max_past_depth)
    elif max_offset > 0 and trigger_base == "1'b1":
        max_past_depth = max(max_past_depth, max_offset)

    def history_trigger(depth: int) -> str:
        if trigger_base == "1'b0":
            return "1'b0"
        if trigger_base == "1'b1":
            return "1'b1" if depth == 0 else placeholder_valid_gate(depth)
        if depth == 0:
            return antecedent_logic.match_expr
        if depth == 1:
            return history.mature_expr if max_offset == 1 else f"{prefix}_launch_hist[0]"
        return history.mature_expr if depth == max_offset else f"{prefix}_launch_hist[{depth - 1}]"

    action_lines: list[str] = []
    for offset, check_expr in sorted(consequent_logic.match_offsets.items()):
        trigger_depth = offset + extra_offset
        action_lines.append(action_line(kind, history_trigger(trigger_depth), check_expr))
    return wrap_formal_block(
        prefix,
        prop.clock,
        prop.disable,
        declarations,
        clears,
        invariants,
        max_past_depth,
        action_lines,
        updates,
    )


def lower_text(text: str) -> str:
    text = mask_comments(text)
    sequence_defs: dict[str, str] = {}
    properties: dict[str, PropertyDef] = {}
    default_clock: str | None = None
    default_disable: str | None = None

    filtered_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        clock_match = DEFAULT_CLOCKING_RE.fullmatch(line.strip())
        if clock_match:
            if default_clock is not None:
                raise ValueError("Multiple default clocking declarations are unsupported")
            default_clock = clock_match.group("clock").strip()
            filtered_lines.append(f"// sva_lower: removed default clocking {default_clock}\n")
            continue

        disable_match = DEFAULT_DISABLE_RE.fullmatch(line.strip())
        if disable_match:
            if default_disable is not None:
                raise ValueError("Multiple default disable iff declarations are unsupported")
            default_disable = disable_match.group("disable").strip()
            filtered_lines.append(f"// sva_lower: removed default disable iff ({default_disable})\n")
            continue

        filtered_lines.append(line)

    transformed = "".join(filtered_lines)

    def collect_sequence(match: re.Match[str]) -> str:
        name = match.group("name")
        sequence_defs[name] = match.group("body").strip()
        return f"// sva_lower: removed sequence {name}\n"

    transformed = SEQUENCE_RE.sub(collect_sequence, transformed)

    def collect_property(match: re.Match[str]) -> str:
        name = match.group("name")
        body = match.group("body")
        properties[name] = parse_property(name, body, sequence_defs, default_clock, default_disable)
        return f"// sva_lower: removed property {name}\n"

    transformed = PROPERTY_RE.sub(collect_property, transformed)

    emitted_blocks: list[str] = []
    unsupported_error: str | None = None
    action_index = 0
    rewritten_lines: list[str] = []

    for line in transformed.splitlines(keepends=True):
        match = ACTION_LINE_RE.fullmatch(line.rstrip("\n"))
        if not match:
            rewritten_lines.append(line)
            continue

        kind = match.group("kind")
        body = match.group("body").strip()
        comment_name = body
        try:
            if body in properties:
                prop = properties[body]
                comment_name = body
            else:
                anon_name = f"anon_{action_index}"
                action_index += 1
                prop = parse_property(
                    anon_name,
                    body,
                    sequence_defs,
                    default_clock,
                    default_disable,
                )
                comment_name = anon_name
            emitted_blocks.append(emit_action(kind, prop))
            rewritten_lines.append(f"// sva_lower: lowered {kind} property ({comment_name})\n")
        except ValueError as exc:
            if unsupported_error is None:
                unsupported_error = str(exc)
            rewritten_lines.append(line)

    transformed = "".join(rewritten_lines)

    if unsupported_error is not None:
        raise ValueError(unsupported_error)
    if not emitted_blocks:
        raise ValueError("No supported property statements were found")

    formal_block = "\n`ifdef FORMAL\n" + "\n".join(emitted_blocks) + "`endif\n"
    endmodule_match = list(re.finditer(r"^\s*endmodule\b", transformed, re.MULTILINE))
    if len(endmodule_match) != 1:
        raise ValueError("Prototype lowerer expects exactly one module per file")

    insert_at = endmodule_match[0].start()
    return transformed[:insert_at] + formal_block + transformed[insert_at:]


def lower_file(input_path: Path, output_path: Path) -> None:
    lowered = lower_text(input_path.read_text())
    output_path.write_text(lowered)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input SystemVerilog file")
    parser.add_argument("output", type=Path, help="Output lowered file")
    args = parser.parse_args()

    try:
        lower_file(args.input, args.output)
    except ValueError as exc:
        print(f"sva_lower: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
