"""Load role-specific evidence phrasing afresh for each generation."""
from pathlib import Path
import yaml

def infer_framing_lens(job_title: str, job_text: str = "") -> str:
    """Choose evidence phrasing from the title, then strong job-text signals."""
    title = (job_title or "").lower()
    if any(term in title for term in (
        "program manager", "programme manager", "technical program manager", "tpm",
    )):
        return "program_manager"
    if any(term in title for term in (
        "operations manager", "director of operations", "operations director",
        "vp, operations", "vp operations", "business operations",
    )):
        return "operations_manager"
    text = (job_text or "")[:4000].lower()
    program_count = sum(text.count(term) for term in (
        "program management", "cross-functional program", "program delivery", "milestones",
    ))
    operations_count = sum(text.count(term) for term in (
        "day-to-day operations", "operational efficiency", "process improvement", "resourcing",
    ))
    if program_count >= 2 and program_count > operations_count:
        return "program_manager"
    if operations_count >= 2 and operations_count > program_count:
        return "operations_manager"
    return ""


def load_framed_evidence(project_root, parsed_job):
    lens = infer_framing_lens(parsed_job.get("job_title") or "", parsed_job.get("raw_text") or parsed_job.get("job_description") or "")
    path = Path(project_root) / "data" / "evidence_profile.yml"
    if not lens or not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        item["id"]: item["framing"][lens]
        for item in data.get("evidence", [])
        if (item.get("framing") or {}).get(lens)
    }
