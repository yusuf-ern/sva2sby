#!/usr/bin/env python3
"""Lower a small SVA subset and run sby on the lowered output."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OSS_CAD_BIN = Path("/tool/formal_tools/oss-cad-suite/bin")
sys.path.insert(0, str(SCRIPT_DIR))

from sva_lower import lower_file, lower_text  # noqa: E402

SECTION_RE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")
SVA_HINT_RE = re.compile(
    r"""
    ^\s*(?:sequence\b|property\b|(?:assert|assume|cover)[ \t]+property\b|`\w+[ \t]+property\b)
    |^\s*default\s+clocking\b
    |^\s*default\s+disable\s+iff\b
    |^\s*bind\b
    """,
    re.MULTILINE | re.VERBOSE,
)
MUST_LOWER_RE = re.compile(
    r"""
    ^\s*(?:sequence\b|property\b|`\w+[ \t]+property\b)
    |^\s*default\s+clocking\b
    |^\s*default\s+disable\s+iff\b
    |^\s*bind\b
    |\#\#\[\+\]
    |\[\s*\*\s*\]
    """,
    re.MULTILINE | re.VERBOSE,
)
TASK_PREFIX_RE = re.compile(r"^(?P<indent>\s*)(?P<tag>~?[^:\s]+:\s*)?(?P<body>.*)$")
TRAILING_COMMENT_RE = re.compile(r"^(?P<content>.*?)(?P<comment>\s+#.*)?$")
LOWERABLE_SUFFIXES = {".sv", ".v"}
VERIFIC_READ_RE = re.compile(r"^\s*read\s+-verific(?:\s+.*)?$")
READ_SV_RE = re.compile(r"\bread\b.*\B-sv\b(?P<rest>.*)$")
PREP_TOP_RE = re.compile(r"\bprep\b.*\B-top\s+(?P<top>\S+)")
HIER_TOP_RE = re.compile(r"\bhierarchy\b.*\B-top\s+(?P<top>\S+)")
EBMC_REQUIRED_RE = re.compile(
    r"""
    \[\s*(?:->|=)\s*\d
    |\bwithin\b
    |\bthroughout\b
    |\bintersect\b
    |\bfirst_match\b
    |\buntil_with\b
    |\buntil\b
    |\baccept_on\b
    |\breject_on\b
    |\bsync_accept_on\b
    |\bsync_reject_on\b
    |\bs_eventually\b
    |\bs_nexttime\b
    |\bnexttime\b
    |\bimplies\b
    """,
    re.MULTILINE | re.VERBOSE,
)
BIND_RE = re.compile(
    r"""
    ^(?P<indent>\s*)bind\s+
    (?P<target>\w+)\s+
    (?P<bound>\w+)\s+
    (?P<instance>\w+)\s*
    \(\s*(?P<connections>\.\*)\s*\)\s*;
    \s*$
    """,
    re.MULTILINE | re.VERBOSE,
)
MODULE_HEADER_RE = re.compile(
    r"module\s+(?P<name>\w+)\s*\((?P<ports>.*?)\)\s*;",
    re.DOTALL,
)
PORT_DECL_RE = re.compile(
    r"\b(?:input|output|inout)\b(?P<decl>.*?)(?=(?:\binput\b|\boutput\b|\binout\b)|\Z)",
    re.DOTALL,
)


@dataclass
class SbySection:
    name: str | None
    args: str | None
    header: str | None
    body: list[str]


@dataclass
class BindSpec:
    target_module: str
    bound_module: str
    instance_name: str
    connections: str
    source_dest: str = ""


@dataclass
class PreparedSv:
    staged_rel: Path
    text: str
    original_text: str
    modules: dict[str, list[str]]
    binds: list[BindSpec]


@dataclass
class EbmcTaskConfig:
    name: str
    mode: str
    depth: int
    top: str
    sources: list[Path]
    solver_flags: list[str]
    method_flags: list[str]


def write_sby(path: Path, source_name: str, top: str, mode: str, depth: int, engine: str) -> None:
    path.write_text(
        "\n".join(
            [
                "[options]",
                f"mode {mode}",
                f"depth {depth}",
                "",
                "[engines]",
                engine,
                "",
                "[script]",
                f"read -formal -sv {source_name}",
                f"prep -top {top}",
                "",
                "[files]",
                f"{source_name} {source_name}",
                "",
            ]
        )
    )


def parse_sby_sections(text: str) -> list[SbySection]:
    sections: list[SbySection] = []
    current: SbySection | None = None

    for line in text.splitlines(keepends=True):
        match = SECTION_RE.match(line)
        if match:
            if current is not None:
                sections.append(current)
            entries = match.group("name").strip().split(maxsplit=1)
            if not entries:
                raise ValueError(f"sva_sby: malformed section header '{line.rstrip()}'")
            current = SbySection(
                name=entries[0].lower(),
                args=entries[1] if len(entries) > 1 else None,
                header=line,
                body=[],
            )
            continue

        if current is None:
            if sections and sections[-1].name is None:
                sections[-1].body.append(line)
            else:
                sections.append(SbySection(name=None, args=None, header=None, body=[line]))
            continue

        current.body.append(line)

    if current is not None:
        sections.append(current)

    return sections


def stage_relative_path(entry: str) -> Path:
    entry_path = Path(entry)
    if entry_path.is_absolute() or ".." in entry_path.parts:
        raise ValueError(
            f"sva_sby: invalid [files] destination '{entry}'. "
            "Destinations must be relative paths without '..'."
        )
    return Path("files") / entry_path


def resolve_source_path(source_dir: Path, entry: str) -> Path:
    source_path = Path(os.path.expandvars(entry)).expanduser()
    if not source_path.is_absolute():
        source_path = source_dir / source_path
    return source_path


def source_requires_ebmc(text: str) -> bool:
    return bool(EBMC_REQUIRED_RE.search(text))


def stage_source_path_raw(source_path: Path, staged_path: Path) -> None:
    staged_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.is_dir():
        shutil.copytree(source_path, staged_path, dirs_exist_ok=True)
        return
    shutil.copy2(source_path, staged_path)


def lower_or_keep_text(text: str, origin: str) -> str:
    if not SVA_HINT_RE.search(text):
        return text

    try:
        return lower_text(text)
    except ValueError as exc:
        if str(exc) in {
            "No supported property statements were found",
            "Prototype lowerer expects exactly one module per file",
        }:
            return text
        if not MUST_LOWER_RE.search(text):
            return text
        raise ValueError(f"sva_sby: failed to lower {origin}: {exc}") from exc


def stage_source_path(source_path: Path, staged_path: Path) -> None:
    staged_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.suffix in LOWERABLE_SUFFIXES and source_path.is_file():
        staged_path.write_text(lower_or_keep_text(source_path.read_text(), str(source_path)))
        return
    if source_path.is_dir():
        shutil.copytree(source_path, staged_path, dirs_exist_ok=True)
        return
    shutil.copy2(source_path, staged_path)


def parse_module_ports(text: str) -> dict[str, list[str]]:
    modules: dict[str, list[str]] = {}
    for match in MODULE_HEADER_RE.finditer(text):
        ports: list[str] = []
        for decl_match in PORT_DECL_RE.finditer(match.group("ports")):
            decl = decl_match.group("decl").strip().strip(",")
            if not decl:
                continue
            for entry in decl.split(","):
                candidate = entry.strip()
                if not candidate:
                    continue
                candidate = candidate.split("=")[0].strip()
                tokens = candidate.split()
                if not tokens:
                    continue
                ports.append(tokens[-1])
        modules[match.group("name")] = ports
    return modules


def applicable_body(line: str, task: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped == "--":
        return None

    prefix_match = TASK_PREFIX_RE.match(line.rstrip("\r\n"))
    assert prefix_match is not None
    tag = prefix_match.group("tag")
    body = prefix_match.group("body").strip()
    if not body or body.startswith("#"):
        return None
    if tag is None:
        return body
    return body if tag.rstrip().rstrip(":") == task else None


def iter_task_section_lines(section: SbySection, task: str) -> list[str]:
    lines: list[str] = []
    active_block: str | None = None

    for line in section.body:
        stripped = line.strip()
        if active_block is not None:
            if stripped == "--":
                active_block = None
                continue
            if active_block == task and stripped and not stripped.startswith("#"):
                lines.append(stripped)
            continue

        prefix_match = TASK_PREFIX_RE.match(line.rstrip("\r\n"))
        assert prefix_match is not None
        tag = prefix_match.group("tag")
        body = prefix_match.group("body").strip()
        if tag is None:
            if not body or body.startswith("#"):
                continue
            lines.append(body)
            continue
        task_name = tag.rstrip().rstrip(":")
        if task_name != task:
            continue
        if not body:
            active_block = task_name
        elif not body.startswith("#"):
            lines.append(body)

    return lines


def parse_files_entry(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped == "--":
        return None

    prefix_match = TASK_PREFIX_RE.match(line.rstrip("\r\n"))
    assert prefix_match is not None
    body = prefix_match.group("body")
    if not body.strip() or body.lstrip().startswith("#"):
        return None

    comment_match = TRAILING_COMMENT_RE.match(body)
    assert comment_match is not None
    content = comment_match.group("content").strip()
    entries = content.split()

    if len(entries) == 1:
        source_entry = entries[0]
        dest_entry = Path(source_entry).name
    elif len(entries) == 2:
        dest_entry, source_entry = entries
    else:
        raise ValueError(
            f"sva_sby: unsupported [files] entry '{content}'. Expected one or two fields."
        )

    return dest_entry, source_entry


def strip_bind_lines(text: str) -> tuple[str, list[BindSpec]]:
    binds: list[BindSpec] = []

    def replace(match: re.Match[str]) -> str:
        binds.append(
            BindSpec(
                target_module=match.group("target"),
                bound_module=match.group("bound"),
                instance_name=match.group("instance"),
                connections=match.group("connections"),
            )
        )
        return (
            f"{match.group('indent')}// sva_sby: removed bind "
            f"{match.group('target')} {match.group('bound')} {match.group('instance')}\n"
        )

    return BIND_RE.sub(replace, text), binds


def make_instance(bound_module: str, instance_name: str, ports: list[str]) -> str:
    if not ports:
        return f"\t{bound_module} {instance_name} ();\n"
    connections = ",\n".join(f"\t\t.{port}({port})" for port in ports)
    return f"\t{bound_module} {instance_name} (\n{connections}\n\t);\n"


def inject_formal_instances(text: str, instances: list[str]) -> str:
    endmodule_match = list(re.finditer(r"^\s*endmodule\b", text, re.MULTILINE))
    if len(endmodule_match) != 1:
        raise ValueError("sva_sby: expected exactly one module when applying bind lowering")
    insert_at = endmodule_match[0].start()
    block = "\n`ifdef FORMAL\n" + "\n".join(instances) + "`endif\n"
    return text[:insert_at] + block + text[insert_at:]


def prepare_sv_source(text: str, origin: str) -> PreparedSv:
    lowered = lower_or_keep_text(text, origin)
    stripped, binds = strip_bind_lines(lowered)
    return PreparedSv(
        staged_rel=Path(),
        text=stripped,
        original_text=lowered,
        modules=parse_module_ports(stripped),
        binds=binds,
    )


def rewrite_files_line(
    line: str,
    source_dir: Path,
    workdir: Path,
    script_rewrites: dict[str, str],
    prepared_sv: dict[str, PreparedSv],
) -> str:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped == "--":
        return line

    newline = line[len(line.rstrip("\r\n")) :]
    core = line[: len(line) - len(newline)] if newline else line
    prefix_match = TASK_PREFIX_RE.match(core)
    assert prefix_match is not None
    prefix = prefix_match.group("indent") + (prefix_match.group("tag") or "")
    body = prefix_match.group("body")

    if not body.strip() or body.lstrip().startswith("#"):
        return line

    comment_match = TRAILING_COMMENT_RE.match(body)
    assert comment_match is not None
    comment = comment_match.group("comment") or ""
    parsed = parse_files_entry(line)
    if parsed is None:
        return line
    dest_entry, source_entry = parsed

    staged_rel = stage_relative_path(dest_entry)
    source_path = resolve_source_path(source_dir, source_entry)
    if source_path.suffix in LOWERABLE_SUFFIXES and source_path.is_file():
        prepared = prepare_sv_source(source_path.read_text(), str(source_path))
        prepared.staged_rel = staged_rel
        for bind in prepared.binds:
            bind.source_dest = dest_entry
        prepared_sv[dest_entry] = prepared
    else:
        stage_source_path(source_path, workdir / staged_rel)
    script_rewrites[source_entry] = dest_entry
    return f"{prefix}{dest_entry} {staged_rel.as_posix()}{comment}{newline}"


def rewrite_script_line(
    line: str,
    ordered_rewrites: list[tuple[str, str]],
    strip_verific: bool,
    formal_reads: set[str],
) -> str:
    updated = line
    for old, new in ordered_rewrites:
        updated = updated.replace(old, new)

    newline = updated[len(updated.rstrip("\r\n")) :]
    core = updated[: len(updated) - len(newline)] if newline else updated
    prefix_match = TASK_PREFIX_RE.match(core)
    assert prefix_match is not None
    indent = prefix_match.group("indent")
    tag = prefix_match.group("tag") or ""
    body = prefix_match.group("body").strip()

    if strip_verific and VERIFIC_READ_RE.fullmatch(body):
        return f"{indent}# sva_sby: stripped {body}{newline}"

    comment_match = TRAILING_COMMENT_RE.match(prefix_match.group("body"))
    assert comment_match is not None
    content = comment_match.group("content")
    comment = comment_match.group("comment") or ""
    stripped_content = content.strip()

    if (
        stripped_content.startswith("read ")
        and "-sv" in stripped_content
        and "-formal" not in stripped_content
        and any(re.search(rf"(^|\s){re.escape(target)}(?=\s|$)", stripped_content) for target in formal_reads)
    ):
        content = re.sub(
            r"\bread(?P<opts>(?:\s+\S+)*)\s+-sv\b",
            lambda match: f"read{match.group('opts')} -formal -sv",
            content,
            count=1,
        )
        return f"{indent}{tag}{content}{comment}{newline}"

    return updated


def override_engines(
    sections: list[SbySection],
    engine_override: str | None,
    selected_tasks: list[str],
) -> None:
    if engine_override is None:
        return

    targets = set(selected_tasks)
    for section in sections:
        if section.name != "engines":
            continue

        rewritten: list[str] = []
        skip_block_for: str | None = None
        replaced: set[str] = set()

        for line in section.body:
            if skip_block_for is not None:
                stripped = line.strip()
                if stripped == "--":
                    rewritten.append(line)
                    skip_block_for = None
                continue

            prefix_match = TASK_PREFIX_RE.match(line.rstrip("\n"))
            assert prefix_match is not None
            tag = prefix_match.group("tag")
            body = prefix_match.group("body")
            newline = line[len(line.rstrip("\r\n")) :]
            indent = prefix_match.group("indent")

            if tag is None:
                if not targets and body.strip() and body.strip() != "--" and not body.lstrip().startswith("#"):
                    rewritten.append(f"{indent}{engine_override}{newline}")
                    replaced.add("")
                else:
                    rewritten.append(line)
                continue

            task_name = tag.rstrip().rstrip(":")
            if task_name not in targets:
                rewritten.append(line)
                continue

            if body.strip():
                rewritten.append(f"{indent}{task_name}: {engine_override}{newline}")
                replaced.add(task_name)
                continue

            rewritten.append(line)
            rewritten.append(f"{engine_override}{newline}")
            replaced.add(task_name)
            skip_block_for = task_name

        section.body = rewritten


def prepare_sby(
    input_path: Path,
    workdir: Path,
    strip_verific: bool = False,
    engine_override: str | None = None,
    selected_tasks: list[str] | None = None,
) -> Path:
    source_dir = input_path.resolve().parent
    sections = parse_sby_sections(input_path.read_text())
    override_engines(sections, engine_override, selected_tasks or [])
    script_sections = [section for section in sections if section.name == "script"]
    if not script_sections:
        raise ValueError("sva_sby: input .sby file has no [script] section")

    source_section_seen = False
    script_rewrites: dict[str, str] = {}
    prepared_sv: dict[str, PreparedSv] = {}
    formal_reads: set[str] = set()
    for section in sections:
        if section.name == "files":
            source_section_seen = True
            section.body = [
                rewrite_files_line(line, source_dir, workdir, script_rewrites, prepared_sv)
                for line in section.body
            ]
            continue

        if section.name != "file" or section.args is None:
            continue

        source_section_seen = True
        if Path(section.args).suffix not in LOWERABLE_SUFFIXES:
            continue
        lowered_text = lower_or_keep_text("".join(section.body), section.args)
        if "`ifdef FORMAL" in lowered_text:
            formal_reads.add(section.args)
        section.body = lowered_text.splitlines(keepends=True)

    if not source_section_seen:
        raise ValueError("sva_sby: input .sby file has no [files] or [file ...] sections")

    module_to_dest: dict[str, str] = {}
    module_to_ports: dict[str, list[str]] = {}
    bind_injections: dict[str, list[str]] = {}
    pending_binds: list[BindSpec] = []
    passthrough_bind_sources: set[str] = set()

    for dest_entry, prepared in prepared_sv.items():
        for module_name, ports in prepared.modules.items():
            if module_name in module_to_dest and module_to_dest[module_name] != dest_entry:
                raise ValueError(f"sva_sby: duplicate module '{module_name}' across staged sources")
            module_to_dest[module_name] = dest_entry
            module_to_ports[module_name] = ports
        pending_binds.extend(prepared.binds)

    for bind in pending_binds:
        if bind.connections != ".*":
            passthrough_bind_sources.add(bind.source_dest)
            continue
        if bind.target_module not in module_to_dest:
            passthrough_bind_sources.add(bind.source_dest)
            continue
        if bind.bound_module not in module_to_ports:
            passthrough_bind_sources.add(bind.source_dest)
            continue
        target_dest = module_to_dest[bind.target_module]
        bind_injections.setdefault(target_dest, []).append(
            make_instance(bind.bound_module, bind.instance_name, module_to_ports[bind.bound_module])
        )

    for dest_entry in passthrough_bind_sources:
        prepared_sv[dest_entry].text = prepared_sv[dest_entry].original_text

    for dest_entry, instances in bind_injections.items():
        prepared_sv[dest_entry].text = inject_formal_instances(prepared_sv[dest_entry].text, instances)

    for prepared in prepared_sv.values():
        if "`ifdef FORMAL" in prepared.text:
            formal_reads.add(prepared.staged_rel.name)
        staged_file = workdir / prepared.staged_rel
        staged_file.parent.mkdir(parents=True, exist_ok=True)
        staged_file.write_text(prepared.text)

    ordered_rewrites = sorted(script_rewrites.items(), key=lambda item: len(item[0]), reverse=True)
    for section in script_sections:
        section.body = [
            rewrite_script_line(line, ordered_rewrites, strip_verific, formal_reads)
            for line in section.body
        ]

    generated = workdir / "run.sby"
    with generated.open("w") as handle:
        for section in sections:
            if section.header is not None:
                handle.write(section.header)
            handle.writelines(section.body)

    return generated


def collect_declared_tasks(sections: list[SbySection]) -> list[str]:
    tasks_section = next((section for section in sections if section.name == "tasks"), None)
    if tasks_section is None:
        return []

    tasks: list[str] = []
    for line in tasks_section.body:
        body = applicable_body(line, "")
        if body is None:
            continue
        task_name = body.split()[0]
        if task_name not in tasks:
            tasks.append(task_name)
    return tasks


def stage_raw_sby_sources(input_path: Path, workdir: Path) -> tuple[list[SbySection], dict[str, Path]]:
    source_dir = input_path.resolve().parent
    sections = parse_sby_sections(input_path.read_text())
    staged_sources: dict[str, Path] = {}

    for section in sections:
        if section.name == "files":
            for line in section.body:
                parsed = parse_files_entry(line)
                if parsed is None:
                    continue
                dest_entry, source_entry = parsed
                staged_rel = stage_relative_path(dest_entry)
                stage_source_path_raw(resolve_source_path(source_dir, source_entry), workdir / staged_rel)
                staged_sources[source_entry] = staged_rel
                staged_sources[dest_entry] = staged_rel
            continue

        if section.name != "file" or section.args is None:
            continue

        staged_rel = stage_relative_path(section.args)
        staged_file = workdir / staged_rel
        staged_file.parent.mkdir(parents=True, exist_ok=True)
        staged_file.write_text("".join(section.body))
        staged_sources[section.args] = staged_rel
        staged_sources[Path(section.args).name] = staged_rel

    return sections, staged_sources


def sby_requires_ebmc(input_path: Path) -> bool:
    source_dir = input_path.resolve().parent
    sections = parse_sby_sections(input_path.read_text())

    for section in sections:
        if section.name == "files":
            for line in section.body:
                parsed = parse_files_entry(line)
                if parsed is None:
                    continue
                _, source_entry = parsed
                source_path = resolve_source_path(source_dir, source_entry)
                if source_path.suffix in LOWERABLE_SUFFIXES and source_path.is_file():
                    if source_requires_ebmc(source_path.read_text()):
                        return True
            continue

        if section.name == "file" and section.args is not None:
            if Path(section.args).suffix in LOWERABLE_SUFFIXES and source_requires_ebmc("".join(section.body)):
                return True

    return False


def extract_task_mode_depth(sections: list[SbySection], task: str) -> tuple[str, int]:
    mode = "bmc"
    depth = 5
    for section in sections:
        if section.name != "options":
            continue
        for line in iter_task_section_lines(section, task):
            if line.startswith("mode "):
                mode = line.split(None, 1)[1].strip()
            elif line.startswith("depth "):
                depth = int(line.split(None, 1)[1].strip())
    return mode, depth


def extract_task_top_and_sources(
    sections: list[SbySection],
    task: str,
    staged_sources: dict[str, Path],
    workdir: Path,
) -> tuple[str, list[Path]]:
    top: str | None = None
    source_paths: list[Path] = []

    for section in sections:
        if section.name != "script":
            continue
        for line in iter_task_section_lines(section, task):
            top_match = PREP_TOP_RE.search(line) or HIER_TOP_RE.search(line)
            if top_match is not None:
                top = top_match.group("top")

            read_match = READ_SV_RE.search(line)
            if read_match is None:
                continue
            for token in re.findall(r"[^\s]+?\.(?:sv|v)", read_match.group("rest")):
                staged_rel = staged_sources.get(token)
                if staged_rel is not None:
                    staged_path = workdir / staged_rel
                    if staged_path not in source_paths:
                        source_paths.append(staged_path)

    if not source_paths:
        for staged_rel in dict.fromkeys(staged_sources.values()):
            staged_path = workdir / staged_rel
            if staged_path.suffix in LOWERABLE_SUFFIXES:
                source_paths.append(staged_path)

    if top is None:
        raise ValueError("sva_sby: could not determine top module from .sby [script] section")

    return top, source_paths


def ebmc_flags_for_engine(engine: str | None, mode: str) -> tuple[list[str], list[str]]:
    solver_flags: list[str] = []
    method_flags: list[str] = []
    tokens = set((engine or "").split())

    for solver in ("boolector", "cvc4", "mathsat", "yices", "z3"):
        if solver in tokens:
            solver_flags = [f"--{solver}"]
            break

    del mode

    return solver_flags, method_flags


def build_ebmc_task_configs(
    input_path: Path,
    workdir: Path,
    selected_tasks: list[str],
    engine_override: str | None,
) -> list[EbmcTaskConfig]:
    sections, staged_sources = stage_raw_sby_sources(input_path, workdir)
    declared_tasks = collect_declared_tasks(sections)
    task_names = selected_tasks or declared_tasks or [""]
    configs: list[EbmcTaskConfig] = []

    for task in task_names:
        mode, depth = extract_task_mode_depth(sections, task)
        top, sources = extract_task_top_and_sources(sections, task, staged_sources, workdir)
        engine_lines: list[str] = []
        if engine_override is None:
            for section in sections:
                if section.name == "engines":
                    engine_lines.extend(iter_task_section_lines(section, task))
        solver_flags, method_flags = ebmc_flags_for_engine(
            engine_override or " ".join(engine_lines),
            mode,
        )
        configs.append(
            EbmcTaskConfig(
                name=task or "default",
                mode=mode,
                depth=depth,
                top=top,
                sources=sources,
                solver_flags=solver_flags,
                method_flags=method_flags,
            )
        )

    return configs


def run_ebmc_task(config: EbmcTaskConfig, workdir: Path, env: dict[str, str]) -> int:
    task_dir = workdir / f"run_{config.name}"
    task_dir.mkdir(parents=True, exist_ok=True)
    vcd_path = task_dir / "trace.vcd"
    cmd = [
        "ebmc",
        *[str(path) for path in config.sources],
        "--top",
        config.top,
        "--bound",
        str(config.depth),
        *config.method_flags,
        *config.solver_flags,
        "--trace",
        "--vcd",
        str(vcd_path),
    ]
    print(
        f"sva_sby: using ebmc backend for task '{config.name}' "
        f"(mode={config.mode}, depth={config.depth}, top={config.top})"
    )
    result = subprocess.run(cmd, cwd=task_dir, env=env, check=False)
    return result.returncode


def make_env() -> dict[str, str]:
    env = os.environ.copy()
    if OSS_CAD_BIN.is_dir():
        env["PATH"] = str(OSS_CAD_BIN) + os.pathsep + env.get("PATH", "")
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input SystemVerilog or .sby file")
    parser.add_argument("tasks", nargs="*", help="Optional task names when input is a .sby file")
    parser.add_argument("--top", help="Top module name for direct .sv mode")
    parser.add_argument("--workdir", type=Path, default=Path("build/sva_sby"))
    parser.add_argument("--mode", default="bmc", choices=["bmc", "prove", "cover"])
    parser.add_argument("--depth", type=int, default=5)
    parser.add_argument(
        "--backend",
        choices=["auto", "sby", "ebmc"],
        default="auto",
        help="Backend selection: lower-to-sby, direct ebmc, or auto-detect",
    )
    parser.add_argument(
        "--strip-verific",
        action="store_true",
        help="Comment out 'read -verific' lines in generated .sby files",
    )
    parser.add_argument(
        "--engine",
        help="Engine override, for example 'smtbmc yices'",
    )
    args = parser.parse_args()

    env = make_env()
    args.workdir.mkdir(parents=True, exist_ok=True)

    if args.backend in {"auto", "ebmc"} and shutil.which("ebmc", path=env.get("PATH")) is None:
        if args.backend == "ebmc":
            print("sva_sby: ebmc not found on PATH", file=sys.stderr)
            return 2
        args.backend = "sby"

    if args.input.suffix == ".sby":
        use_ebmc = args.backend == "ebmc"
        if args.backend == "auto":
            use_ebmc = sby_requires_ebmc(args.input)

        if use_ebmc:
            task_configs = build_ebmc_task_configs(args.input, args.workdir, args.tasks, args.engine)
            result_code = 0
            for config in task_configs:
                rc = run_ebmc_task(config, args.workdir, env)
                if rc != 0 and result_code == 0:
                    result_code = rc
            return result_code

        if shutil.which("sby", path=env.get("PATH")) is None:
            print("sva_sby: sby not found on PATH", file=sys.stderr)
            return 2
        try:
            sby_path = prepare_sby(
                args.input,
                args.workdir,
                strip_verific=args.strip_verific,
                engine_override=args.engine,
                selected_tasks=args.tasks,
            )
        except ValueError:
            if args.backend != "auto" or shutil.which("ebmc", path=env.get("PATH")) is None:
                raise
            task_configs = build_ebmc_task_configs(args.input, args.workdir, args.tasks, args.engine)
            result_code = 0
            for config in task_configs:
                rc = run_ebmc_task(config, args.workdir, env)
                if rc != 0 and result_code == 0:
                    result_code = rc
            return result_code
    else:
        if args.tasks:
            print("sva_sby: task names are only valid when input is a .sby file", file=sys.stderr)
            return 2
        if args.strip_verific:
            print("sva_sby: --strip-verific is only valid when input is a .sby file", file=sys.stderr)
            return 2
        if not args.top:
            print("sva_sby: --top is required when input is a .sv file", file=sys.stderr)
            return 2
        source_text = args.input.read_text()
        use_ebmc = args.backend == "ebmc" or source_requires_ebmc(source_text)
        lowered = args.workdir / "lowered.sv"
        if args.backend == "auto" and not use_ebmc:
            try:
                lower_file(args.input, lowered)
            except ValueError:
                use_ebmc = True
        if use_ebmc:
            solver_flags, method_flags = ebmc_flags_for_engine(args.engine, args.mode)
            config = EbmcTaskConfig(
                name="direct",
                mode=args.mode,
                depth=args.depth,
                top=args.top,
                sources=[args.input.resolve()],
                solver_flags=solver_flags,
                method_flags=method_flags,
            )
            return run_ebmc_task(config, args.workdir, env)
        if shutil.which("sby", path=env.get("PATH")) is None:
            print("sva_sby: sby not found on PATH", file=sys.stderr)
            return 2
        sby_path = args.workdir / "run.sby"
        lower_file(args.input, lowered)
        write_sby(sby_path, lowered.name, args.top, args.mode, args.depth, args.engine or "smtbmc")

    result = subprocess.run(
        ["sby", "-f", sby_path.name, *args.tasks],
        cwd=args.workdir,
        env=env,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
