"""Candidate-facing metadata for every generated Career Catalyst DOCX."""

from __future__ import annotations

import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Union
from xml.etree import ElementTree as ET


PathInput = Union[str, Path]
AUTHOR = "Trisha Lynch"
CORE_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"

ET.register_namespace("cp", CORE_NAMESPACE)
ET.register_namespace("dc", DC_NAMESPACE)
ET.register_namespace("dcterms", "http://purl.org/dc/terms/")
ET.register_namespace("dcmitype", "http://purl.org/dc/dcmitype/")
ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
ET.register_namespace("vt", "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes")


class DocxMetadataError(Exception):
    """Raised when candidate-facing DOCX properties cannot be guaranteed."""


def _set_property(root: ET.Element, namespace: str, name: str, value: str) -> None:
    element = root.find(f"{{{namespace}}}{name}")
    if element is None:
        element = ET.SubElement(root, f"{{{namespace}}}{name}")
    element.text = value


def _contains_generator_reference(element: ET.Element) -> bool:
    return bool(
        re.search(
            r"python(?:-docx)?|generated\s+by\s+python",
            ET.tostring(element, encoding="unicode"),
            flags=re.I,
        )
    )


def _sanitize_property_xml(
    payload: bytes,
    package_name: str,
    *,
    title: str,
    subject: str,
    author: str,
) -> bytes:
    root = ET.fromstring(payload)
    if package_name == "docProps/core.xml":
        _set_property(root, DC_NAMESPACE, "creator", author)
        _set_property(root, CORE_NAMESPACE, "lastModifiedBy", author)
        _set_property(root, DC_NAMESPACE, "title", title)
        _set_property(root, DC_NAMESPACE, "subject", subject)
        _set_property(root, DC_NAMESPACE, "description", "")
        _set_property(root, CORE_NAMESPACE, "keywords", "")

    for child in list(root):
        if _contains_generator_reference(child):
            root.remove(child)
    for key, value in list(root.attrib.items()):
        if re.search(r"python", value, flags=re.I):
            root.attrib[key] = ""

    serialized = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    if re.search(br"python", serialized, flags=re.I):
        raise ValueError(f"Generator metadata remains in {package_name}")
    return serialized


def clean_docx_metadata(
    docx_path: PathInput,
    *,
    title: str,
    subject: str = "",
    author: str = AUTHOR,
) -> Path:
    """Rewrite only DOCX property XML with candidate-facing metadata."""
    path = Path(docx_path)
    temporary: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{path.stem}-metadata-",
            suffix=".docx",
            dir=str(path.parent),
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(
            temporary, "w"
        ) as destination:
            for info in source.infolist():
                payload = source.read(info.filename)
                if info.filename.startswith("docProps/") and info.filename.endswith(".xml"):
                    payload = _sanitize_property_xml(
                        payload,
                        info.filename,
                        title=title,
                        subject=subject,
                        author=author,
                    )
                destination.writestr(info, payload)
        os.replace(temporary, path)
        temporary = None
    except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError) as error:
        raise DocxMetadataError(
            f"Unable to apply candidate-facing DOCX metadata to {path}: {error}"
        ) from error
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return path
