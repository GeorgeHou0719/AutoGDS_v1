from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_FRONT_BLOCK_RE = re.compile(r"(?s)---\s*(.*?)\s*---\s*(.*)")
_KV_RE = re.compile(r"^\s*([^:#]+?)\s*:\s*(.*?)\s*$")
_ARGS_SECTION_RE = re.compile(r"(?mi)^\s*Args:\s*$")


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return path.read_text(encoding="utf-8", errors="replace")


def _parse_listish(value: str) -> List[str]:
    v = value.strip()
    if not v:
        return []
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        parts = [p.strip().strip("'\"") for p in inner.split(",")]
        return [p for p in parts if p]
    # Comma-separated fallback
    parts = [p.strip() for p in v.split(",")]
    return [p for p in parts if p]


def _coerce_scalar(value: str) -> Any:
    v = value.strip()
    if v.lower() in {"true", "false"}:
        return v.lower() == "true"
    if v.lower() in {"none", "null"}:
        return None
    # int/float if possible
    try:
        if re.fullmatch(r"[+-]?\d+", v):
            return int(v)
        if re.fullmatch(r"[+-]?(\d+\.\d*|\d*\.\d+)([eE][+-]?\d+)?", v) or re.fullmatch(
            r"[+-]?\d+([eE][+-]?\d+)", v
        ):
            return float(v)
    except Exception:
        pass
    return v


def _parse_front_matter_and_body(doc: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse YAML-like front-matter and return (meta, body).

    Supports two formats:
    1) Paired fences:    --- <front> --- <body>
    2) Single fence:     <summary>\n---\n<front>\n\n<Sections...>
       In this case, <front> ends when the first top-level section header appears
       (e.g., "Args:", "specs:", "Returns:"), or at end of docstring.
    """
    if not doc:
        return {}, ""

    # Case 1: paired fences
    m = _FRONT_BLOCK_RE.search(doc)
    if m:
        front_raw = m.group(1)
        body = m.group(2) or ""
        meta = _parse_yamlish_block(front_raw)
        return meta, body

    # Case 2: single fence line '---'
    lines = doc.splitlines()
    fence_idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == "---":
            fence_idx = i
            break
    if fence_idx is None:
        return {}, doc

    # front-matter starts after the single fence
    front_lines: List[str] = []
    body_lines: List[str] = []

    # find where front ends: the first top-level section header (no leading spaces), e.g., "Args:"
    section_re = re.compile(
        r"^(Args|specs|Specs|Returns|Raises|Notes|Examples?)\s*:\s*$"
    )
    i = fence_idx + 1
    while i < len(lines):
        ln = lines[i]
        if section_re.match(ln) and (not ln[:1].isspace()):
            # this line begins the body
            break
        front_lines.append(ln)
        i += 1

    body_lines = lines[i:] if i < len(lines) else []
    front_raw = "\n".join(front_lines).strip("\n")
    body = "\n".join(body_lines)

    meta = _parse_yamlish_block(front_raw)
    return meta, body


def _parse_yamlish_block(front_raw: str) -> Dict[str, Any]:
    """
    Parse a minimal YAML-like block:
    - top-level 'key: value'
    - top-level 'key:' with indented list '- item' or indented text lines
    """
    meta: Dict[str, Any] = {}
    if not front_raw:
        return meta

    lines = front_raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue

        # only accept top-level key lines (no leading indentation)
        if line[:1].isspace():
            i += 1
            continue

        kv = _KV_RE.match(line)
        if not kv:
            i += 1
            continue

        k = kv.group(1).strip()
        v = kv.group(2).strip()

        # Single-line scalar/list OR YAML block scalar indicator
        if v:
            # YAML block scalars: ">" (folded) or "|" (literal)
            if v in {">", "|"}:
                block_lines: List[str] = []
                i += 1
                while i < len(lines):
                    ln = lines[i]
                    if not ln.strip():
                        block_lines.append("")
                        i += 1
                        continue
                    # next top-level key begins
                    if (not ln[:1].isspace()) and _KV_RE.match(ln):
                        break
                    # consume indented content
                    block_lines.append(ln.strip())
                    i += 1
                meta[k] = "\n".join(block_lines).strip()
                continue

            if v.startswith("[") and v.endswith("]"):
                meta[k] = _parse_listish(v)
            else:
                meta[k] = _coerce_scalar(v)
            i += 1
            continue


        # Multi-line block after 'key:'
        items: List[str] = []
        text_lines: List[str] = []
        i += 1
        while i < len(lines):
            ln = lines[i]
            if not ln.strip():
                i += 1
                continue
            # next top-level key begins
            if (not ln[:1].isspace()) and _KV_RE.match(ln):
                break

            s = ln.strip()
            if s.startswith("-"):
                item = s.lstrip("-").strip().strip("'\"")
                if item:
                    items.append(item)
            else:
                text_lines.append(s)
            i += 1

        if items:
            meta[k] = items
        elif text_lines:
            meta[k] = "\n".join(text_lines).strip()
        else:
            meta[k] = ""

    return meta




def _parse_args_doc(body: str) -> List[str]:
    if not body:
        return []

    lines = body.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if _ARGS_SECTION_RE.match(ln):
            start = i + 1
            break
    if start is None:
        return []

    # Determine base indentation for argument entries under Args:
    base_indent = None
    for j in range(start, len(lines)):
        ln = lines[j]
        if not ln.strip():
            continue
        # stop if we immediately hit another top-level section
        if re.match(r"^[A-Za-z][A-Za-z0-9_ ]*:\s*$", ln) and (not ln[:1].isspace()):
            return []
        base_indent = len(ln) - len(ln.lstrip(" "))
        break
    if base_indent is None:
        return []

    args: List[str] = []
    arg_key_re = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*$")
    section_re = re.compile(r"^[A-Za-z][A-Za-z0-9_ ]*:\s*$")

    for ln in lines[start:]:
        if not ln.strip():
            continue

        indent = len(ln) - len(ln.lstrip(" "))

        # end Args block when we hit a new top-level section header
        if indent == 0 and section_re.match(ln):
            break

        # only accept keys at the base indentation level (top-level args)
        if indent == base_indent:
            m = arg_key_re.match(ln)
            if m:
                args.append(m.group(1))

    # unique preserving order
    seen = set()
    out = []
    for a in args:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out




def _const_value(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    # Python <3.8 compatibility not needed, but keep safe:
    if isinstance(node, (ast.Num, ast.Str, ast.NameConstant)):
        return getattr(node, "n", None) or getattr(node, "s", None) or getattr(node, "value", None)
    return None


def _is_gf_cell_decorator(dec: ast.AST) -> bool:
    # Accept: @gf.cell or @gdsfactory.cell (Attribute), or imported alias forms won't be detected (acceptable for v0)
    if isinstance(dec, ast.Attribute) and dec.attr == "cell":
        base = dec.value
        if isinstance(base, ast.Name) and base.id == "gf":
            return True
        if isinstance(base, ast.Name) and base.id == "gdsfactory":
            return True
        # could be something like gf.routing.cell; unlikely; ignore
        return False
    if isinstance(dec, ast.Name) and dec.id == "cell":
        # too ambiguous; treat as false to avoid false positives
        return False
    return False


def _extract_args_sig(func: ast.FunctionDef) -> Dict[str, Any]:
    names = [a.arg for a in func.args.args]
    defaults = list(func.args.defaults or [])
    # align defaults to last N args
    sig: Dict[str, Any] = {}
    if not names:
        return sig
    n_defaults = len(defaults)
    for i, name in enumerate(names):
        default_val = None
        if n_defaults > 0 and i >= len(names) - n_defaults:
            dv = defaults[i - (len(names) - n_defaults)]
            default_val = _const_value(dv)
        sig[name] = default_val
    return sig


def _extract_ports_exposed(tree: ast.AST) -> List[str]:
    ports: List[str] = []
    seen = set()

    class V(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> Any:
            try:
                if isinstance(node.func, ast.Attribute) and node.func.attr == "add_port":
                    if node.args:
                        v = _const_value(node.args[0])
                        if isinstance(v, str) and v and v not in seen:
                            seen.add(v)
                            ports.append(v)
            except Exception:
                pass
            self.generic_visit(node)

    V().visit(tree)
    return ports


@dataclass
class _Extracted:
    port_form: Optional[str]
    node_labels: List[str]
    spec: Dict[str, Any]
    args_doc: List[str]
    args_sig: Dict[str, Any]
    ports_exposed: List[str]


def _extract_contract_raw(py_path: Path, preferred_symbol: Optional[str]) -> _Extracted:
    src = _safe_read_text(py_path)
    tree = ast.parse(src, filename=str(py_path))

    # docstring
    doc = ast.get_docstring(tree) or ""
    meta, body = _parse_front_matter_and_body(doc)

    # normalized fields from front-matter
    port_form = None
    if "ports" in meta and isinstance(meta["ports"], str):
        port_form = meta["ports"].strip()
    elif "ports" in meta and meta["ports"] is not None:
        port_form = str(meta["ports"]).strip()

    node_labels: List[str] = []
    if "NodeLabels" in meta:
        if isinstance(meta["NodeLabels"], list):
            node_labels = [str(x).strip() for x in meta["NodeLabels"] if str(x).strip()]
        else:
            node_labels = _parse_listish(str(meta["NodeLabels"]))

    # spec: keep everything else from meta except the ones we elevate
    spec: Dict[str, Any] = {}
    for k, v in meta.items():
        if k in {"ports", "NodeLabels"}:
            continue
        spec[k] = v

    args_doc = _parse_args_doc(body)

    # pick a gf.cell function
    cell_funcs: List[ast.FunctionDef] = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            if any(_is_gf_cell_decorator(d) for d in n.decorator_list):
                cell_funcs.append(n)

    chosen: Optional[ast.FunctionDef] = None
    if preferred_symbol:
        for f in cell_funcs:
            if f.name == preferred_symbol:
                chosen = f
                break
    if chosen is None and cell_funcs:
        chosen = cell_funcs[0]

    args_sig: Dict[str, Any] = {}
    if chosen is not None:
        args_sig = _extract_args_sig(chosen)

    ports_exposed = _extract_ports_exposed(tree)

    return _Extracted(
        port_form=port_form,
        node_labels=node_labels,
        spec=spec,
        args_doc=args_doc,
        args_sig=args_sig,
        ports_exposed=ports_exposed,
    )


def extract_contract(py_path: Path, preferred_symbol: Optional[str] = None):
    """
    Extract a component contract from a Python source file by static analysis.
    - No imports/execution.
    - No device-type special casing.
    """
    from autogds.schema import ComponentContract  # local import to avoid cycles

    try:
        raw = _extract_contract_raw(py_path, preferred_symbol)
        return ComponentContract(
            port_form=raw.port_form,
            node_labels=raw.node_labels,
            spec={k: (v if isinstance(v, (str, int, float)) or v is None else str(v)) for k, v in raw.spec.items()},
            args_doc=raw.args_doc,
            args_sig={k: (v if isinstance(v, (str, int, float)) or v is None else None) for k, v in raw.args_sig.items()},
            ports_exposed=raw.ports_exposed,
            param_passthrough={},  # Step7 暂不做，后续 Step11/12 再补
        )
    except Exception:
        # Caller should log the exception and proceed with contract=None if desired
        raise
