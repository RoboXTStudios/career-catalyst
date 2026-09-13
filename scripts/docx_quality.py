"""Deterministic OOXML hygiene, parseability, and factual-parity checks."""

from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from docx import Document
from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NS = "http://purl.org/dc/elements/1.1/"
DCTERMS_NS = "http://purl.org/dc/terms/"
EP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
NS = {"w": W_NS, "r": R_NS}

COMMENT_MARKERS = {"commentRangeStart", "commentRangeEnd", "commentReference"}
REVISION_CONTAINERS = {"ins", "moveTo"}
REMOVED_REVISIONS = {"del", "moveFrom"}
PROHIBITED_METADATA = (
    "python",
    "python-docx",
    "openai",
    "chatgpt",
    "codex",
    "career catalyst generator",
)


class DocxQualityError(ValueError):
    """Raised when a candidate-facing DOCX fails a blocking quality gate."""


def _local_name(element: etree._Element) -> str:
    return etree.QName(element).localname


def _parse_xml(payload: bytes) -> etree._Element:
    return etree.fromstring(payload, parser=etree.XMLParser(resolve_entities=False))


def _visible_text(element: etree._Element) -> str:
    pieces: list[str] = []

    def visit(node: etree._Element) -> None:
        name = _local_name(node)
        if name in REMOVED_REVISIONS:
            return
        if name in {"t", "delText"} and node.text:
            pieces.append(node.text)
        elif name == "tab":
            pieces.append("\t")
        elif name in {"br", "cr"}:
            pieces.append("\n")
        for child in node:
            visit(child)

    visit(element)
    return re.sub(r"[ \t]+", " ", "".join(pieces)).strip()


def _document_parts(names: Iterable[str]) -> list[str]:
    return sorted(
        name
        for name in names
        if re.match(r"word/(?:document|header\d*|footer\d*|footnotes|endnotes)\.xml$", name)
    )


def extract_docx_structure(path: str | Path) -> dict[str, Any]:
    """Read visible OOXML content in document order without trusting metadata."""
    candidate = Path(path)
    paragraphs: list[str] = []
    table_count = 0
    textbox_count = 0
    hidden_count = 0
    with zipfile.ZipFile(candidate) as archive:
        document = _parse_xml(archive.read("word/document.xml"))
        body = document.find(f"{{{W_NS}}}body")
        for child in body if body is not None else []:
            name = _local_name(child)
            if name == "p":
                text = _visible_text(child)
                if text:
                    paragraphs.append(text)
            elif name == "tbl":
                table_count += 1
                for row in child.findall(f".//{{{W_NS}}}tr"):
                    cells = [
                        _visible_text(cell)
                        for cell in row.findall(f"{{{W_NS}}}tc")
                    ]
                    text = " | ".join(value for value in cells if value)
                    if text:
                        paragraphs.append(text)
        textbox_count = len(document.findall(f".//{{{W_NS}}}txbxContent"))
        hidden_count = len(document.findall(f".//{{{W_NS}}}vanish"))
        relationships: set[str] = set()
        referenced_relationship_ids = {
            str(link.get(f"{{{R_NS}}}id") or "")
            for link in document.findall(f".//{{{W_NS}}}hyperlink")
        }
        rel_name = "word/_rels/document.xml.rels"
        if rel_name in archive.namelist():
            rels = _parse_xml(archive.read(rel_name))
            relationships = {
                str(rel.get("Target") or "")
                for rel in rels
                if str(rel.get("TargetMode") or "").lower() == "external"
                and str(rel.get("Id") or "") in referenced_relationship_ids
            }
    return {
        "paragraphs": paragraphs,
        "text": "\n".join(paragraphs),
        "table_count": table_count,
        "textbox_count": textbox_count,
        "hidden_text_marker_count": hidden_count,
        "hyperlinks": sorted(value for value in relationships if value),
    }


def _remove_element(element: etree._Element) -> None:
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def _unwrap(element: etree._Element) -> None:
    parent = element.getparent()
    if parent is None:
        return
    index = parent.index(element)
    for child in list(element):
        parent.insert(index, child)
        index += 1
    parent.remove(element)


def _clean_word_xml(payload: bytes, *, settings: bool = False) -> bytes:
    root = _parse_xml(payload)
    for element in list(root.iter()):
        for attribute in list(element.attrib):
            if etree.QName(attribute).localname.lower().startswith("rsid"):
                del element.attrib[attribute]
        name = _local_name(element)
        if name in COMMENT_MARKERS or name in REMOVED_REVISIONS:
            _remove_element(element)
        elif name in REVISION_CONTAINERS:
            _unwrap(element)
        elif settings and name in {"trackRevisions", "revisionView", "doNotTrackMoves", "doNotTrackFormatting"}:
            _remove_element(element)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _clean_relationships(payload: bytes) -> bytes:
    root = _parse_xml(payload)
    for relationship in list(root):
        target = str(relationship.get("Target") or "").lower()
        rel_type = str(relationship.get("Type") or "").lower()
        if any(token in target or token in rel_type for token in ("comments", "people", "customxml", "custom-properties")):
            root.remove(relationship)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _clean_content_types(payload: bytes) -> bytes:
    root = _parse_xml(payload)
    for child in list(root):
        part = str(child.get("PartName") or "").lower()
        content_type = str(child.get("ContentType") or "").lower()
        if any(token in part or token in content_type for token in ("comments", "/people", "customxml", "custom-properties")):
            root.remove(child)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _neutralize_properties(payload: bytes, *, core: bool) -> bytes:
    root = _parse_xml(payload)
    if core:
        removable = {
            f"{{{DC_NS}}}creator",
            f"{{{CP_NS}}}lastModifiedBy",
            f"{{{DCTERMS_NS}}}created",
            f"{{{DCTERMS_NS}}}modified",
            f"{{{CP_NS}}}revision",
            f"{{{CP_NS}}}keywords",
            f"{{{DC_NS}}}description",
        }
    else:
        removable = {
            f"{{{EP_NS}}}Application",
            f"{{{EP_NS}}}AppVersion",
            f"{{{EP_NS}}}Company",
            f"{{{EP_NS}}}Manager",
            f"{{{EP_NS}}}Template",
        }
    for child in list(root):
        if child.tag in removable:
            root.remove(child)
    if core:
        for tag in (f"{{{DC_NS}}}creator", f"{{{CP_NS}}}lastModifiedBy"):
            etree.SubElement(root, tag).text = "Trisha Lynch"
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _excluded_part(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered.startswith("customxml/")
        or lowered == "docprops/custom.xml"
        or lowered.startswith("word/comments")
        or lowered.startswith("word/people")
    )


def inspect_docx_hygiene(path: str | Path) -> dict[str, Any]:
    """Inspect the OOXML package for comments, revisions, and generator identity."""
    candidate = Path(path)
    comments = revisions = revision_sessions = 0
    prohibited: set[str] = set()
    core_properties = {
        "creator": "",
        "last_modified_by": "",
        "created": "",
        "modified": "",
    }
    package_names: list[str]
    with zipfile.ZipFile(candidate) as archive:
        package_names = archive.namelist()
        for name in package_names:
            payload = archive.read(name)
            lowered = payload.lower()
            for identifier in PROHIBITED_METADATA:
                if identifier.encode("utf-8") in lowered and (
                    name.startswith("docProps/") or name.endswith("settings.xml")
                ):
                    prohibited.add(identifier)
            if name.endswith(".xml"):
                try:
                    root = _parse_xml(payload)
                except etree.XMLSyntaxError:
                    continue
                comments += sum(
                    1 for element in root.iter() if _local_name(element) in COMMENT_MARKERS
                )
                revisions += sum(
                    1
                    for element in root.iter()
                    if _local_name(element) in REVISION_CONTAINERS | REMOVED_REVISIONS | {"trackRevisions"}
                )
                revision_sessions += sum(
                    1
                    for element in root.iter()
                    for attribute in element.attrib
                    if etree.QName(attribute).localname.lower().startswith("rsid")
                )
                if name == "docProps/core.xml":
                    core_properties = {
                        "creator": str(root.findtext(f"{{{DC_NS}}}creator") or ""),
                        "last_modified_by": str(root.findtext(f"{{{CP_NS}}}lastModifiedBy") or ""),
                        "created": str(root.findtext(f"{{{DCTERMS_NS}}}created") or ""),
                        "modified": str(root.findtext(f"{{{DCTERMS_NS}}}modified") or ""),
                    }
    comment_parts = [
        name for name in package_names if "comments" in name.lower() or "people" in name.lower()
    ]
    custom_parts = [
        name for name in package_names if name.lower().startswith("customxml/") or name.lower() == "docprops/custom.xml"
    ]
    valid = (
        not comments
        and not revisions
        and not revision_sessions
        and not prohibited
        and not comment_parts
        and not custom_parts
        and core_properties["creator"] in {"", "Trisha Lynch"}
        and core_properties["last_modified_by"] in {"", "Trisha Lynch"}
        and not core_properties["created"] and not core_properties["modified"]
    )
    return {
        "status": "PASS" if valid else "BLOCKED",
        "comments": comments,
        "revisions": revisions,
        "revision_session_attributes": revision_sessions,
        "core_properties": core_properties,
        "prohibited_generator_identifiers": sorted(prohibited),
        "comment_parts": comment_parts,
        "custom_parts": custom_parts,
        "structurally_valid": True,
    }


def sanitize_docx(path: str | Path) -> dict[str, Any]:
    """Sanitize the actual OOXML package and prove visible content preservation."""
    candidate = Path(path)
    before = extract_docx_structure(candidate)
    with tempfile.TemporaryDirectory(prefix="career-catalyst-docx-") as temporary:
        cleaned = Path(temporary) / candidate.name
        with zipfile.ZipFile(candidate) as source, zipfile.ZipFile(
            cleaned, "w", compression=zipfile.ZIP_DEFLATED
        ) as destination:
            for info in source.infolist():
                name = info.filename
                if _excluded_part(name):
                    continue
                payload = source.read(name)
                if name == "docProps/core.xml":
                    payload = _neutralize_properties(payload, core=True)
                elif name == "docProps/app.xml":
                    payload = _neutralize_properties(payload, core=False)
                elif name == "[Content_Types].xml":
                    payload = _clean_content_types(payload)
                elif name.endswith(".rels"):
                    payload = _clean_relationships(payload)
                elif name == "word/settings.xml":
                    payload = _clean_word_xml(payload, settings=True)
                elif name in _document_parts(source.namelist()):
                    payload = _clean_word_xml(payload)
                destination.writestr(info, payload)
        shutil.copy2(cleaned, candidate)

    try:
        Document(str(candidate))
    except Exception as error:
        raise DocxQualityError(f"Sanitized DOCX cannot be reopened: {error}") from error
    after = extract_docx_structure(candidate)
    if before["text"] != after["text"]:
        raise DocxQualityError("DOCX hygiene changed visible candidate-facing text.")
    report = inspect_docx_hygiene(candidate)
    report.update(
        {
            "visible_content_preserved": True,
            "hyperlinks_preserved": before["hyperlinks"] == after["hyperlinks"],
            "hyperlinks": after["hyperlinks"],
        }
    )
    if report["status"] != "PASS" or not report["hyperlinks_preserved"]:
        raise DocxQualityError("DOCX hygiene validation failed after sanitation.")
    return report


def _markdown_visible_lines(markdown: str) -> list[str]:
    lines: list[str] = []
    for raw in str(markdown or "").splitlines():
        if raw.strip().startswith("<!--"):
            continue
        text = re.sub(r"^\s{0,3}(?:#{1,6}|[-*+])\s+", "", raw).strip()
        text = re.sub(
            r"\[([^]]+)\]\(([^)]+)\)",
            lambda match: (
                match.group(1)
                if match.group(2) in {match.group(1), f"mailto:{match.group(1)}"}
                else f"{match.group(1)} {match.group(2)}"
            ),
            text,
        )
        text = re.sub(r"[*_`]", "", text)
        if text:
            lines.append(re.sub(r"\s+", " ", text))
    return lines


def _normal_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)?", str(text or "").lower())


def validate_ats_round_trip(path: str | Path, intended_markdown: str) -> dict[str, Any]:
    """Validate parseability of the actual ATS DOCX without simulating ATS ranking."""
    parsed = extract_docx_structure(path)
    intended_lines = _markdown_visible_lines(intended_markdown)
    parsed_normal = " ".join(_normal_tokens(parsed["text"]))
    missing: list[str] = []
    for line in intended_lines:
        tokens = _normal_tokens(line)
        if len(tokens) >= 2 and " ".join(tokens) not in parsed_normal:
            missing.append(line)
    headings = [
        line for line in intended_lines if line.lower() in {
            "profile", "core competencies", "platforms & technologies",
            "professional experience", "earlier career", "professional development",
            "relevant projects & impact", "selected products & independent work",
        }
    ]
    duplicate_sections = sorted(
        {heading for heading in headings if headings.count(heading) > 1}
    )
    unsupported_glyphs = sorted(set(re.findall(r"[\uE000-\uF8FF]", parsed["text"])))
    blocking = []
    if parsed["table_count"]:
        blocking.append("ATS resume depends on one or more tables.")
    if parsed["textbox_count"]:
        blocking.append("ATS resume contains text boxes or floating text containers.")
    if parsed["hidden_text_marker_count"]:
        blocking.append("ATS resume contains hidden-text markup.")
    if missing:
        blocking.append(f"ATS round trip lost {len(missing)} intended content line(s).")
    if duplicate_sections:
        blocking.append("ATS resume contains duplicate sections: " + ", ".join(duplicate_sections))
    if unsupported_glyphs:
        blocking.append("ATS resume contains unsupported private-use glyphs.")
    return {
        "status": "PASS" if not blocking else "BLOCKED",
        "parseability_only": True,
        "parsed_preview": parsed["text"],
        "paragraph_count": len(parsed["paragraphs"]),
        "table_count": parsed["table_count"],
        "textbox_count": parsed["textbox_count"],
        "hidden_text_marker_count": parsed["hidden_text_marker_count"],
        "missing_lines": missing,
        "duplicate_sections": duplicate_sections,
        "unsupported_glyphs": unsupported_glyphs,
        "hyperlinks": parsed["hyperlinks"],
        "blocking_reasons": blocking,
    }


def compare_docx_factual_parity(styled_path: str | Path, ats_path: str | Path) -> dict[str, Any]:
    """Prove styled and ATS exports contain the same visible facts and links."""
    styled = extract_docx_structure(styled_path)
    ats = extract_docx_structure(ats_path)
    styled_tokens = Counter(_normal_tokens(styled["text"]))
    ats_tokens = Counter(_normal_tokens(ats["text"]))
    token_delta = (styled_tokens - ats_tokens) + (ats_tokens - styled_tokens)
    links_match = set(styled["hyperlinks"]) == set(ats["hyperlinks"])
    return {
        "status": "PASS" if not token_delta and links_match else "BLOCKED",
        "visible_facts_match": not token_delta,
        "hyperlinks_match": links_match,
        "token_delta": dict(token_delta),
    }


def require_docx_quality(report: Mapping[str, Any], *, label: str) -> None:
    if str(report.get("status") or "") != "PASS":
        reasons = report.get("blocking_reasons") or ["quality validation failed"]
        raise DocxQualityError(f"{label}: " + "; ".join(str(item) for item in reasons))
