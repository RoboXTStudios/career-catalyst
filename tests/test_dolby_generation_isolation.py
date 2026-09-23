from pathlib import Path
import shutil

from scripts.candidate_output import domain_adjacency
from scripts.generate_cover_letter import generate_cover_letter, load_generation_context
from scripts.parse_job import parse_job_description
from scripts.tailor_resume import tailor_resume

ROOT = Path(__file__).resolve().parents[1]


def test_customer_journeys_do_not_classify_content_operations_as_cx():
    assert not domain_adjacency({'job_title': 'Content Operations Manager', 'raw_text': 'Enable connected customer journeys across content channels.'})['customer_experience']
    assert domain_adjacency({'job_title': 'Director, Customer Experience Strategy'})['customer_experience']


def test_gitlab_then_dolby_then_gitlab_builds_fresh_context(tmp_path):
    for directory in ('data', 'config'):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    shutil.copy2(ROOT / 'tests/fixtures/dolby_evidence_framing.yml', tmp_path / 'data/evidence_profile.yml')
    jobs = tmp_path / 'jobs'
    jobs.mkdir()
    for name in ('gitlab_director_customer_experience_strategy', 'dolby_content_operations_manager'):
        shutil.copy2(ROOT / 'tests/fixtures/jobs' / f'{name}.md', jobs / f'{name}.md')
    texts = []
    for name in ('gitlab_director_customer_experience_strategy', 'dolby_content_operations_manager', 'gitlab_director_customer_experience_strategy'):
        result = generate_cover_letter(jobs / f'{name}.md', tmp_path)
        texts.append(Path(result['output_path']).read_text())
    assert 'transferable to Customer Experience' in texts[0]
    assert texts[0] == texts[2]
    assert 'Dear Dolby Hiring Team,' in texts[1]
    assert 'Customer Experience' not in texts[1]
    assert 'GitLab' not in texts[1]
    assert 'spreadsheet-based tracking to a shared Airtable system' in texts[1]
    assert 'Disney+ campaign on an ongoing basis' in texts[1]
    job = jobs / 'dolby_content_operations_manager.md'
    context = load_generation_context(job, tmp_path)
    resume = tailor_resume('executive_operations', job, tmp_path, role_intent=context['role_intent'])
    content = Path(resume['output_path']).read_text()
    assert 'spreadsheet-based tracking to a shared Airtable system' in content
    assert 'Disney+ campaign on an ongoing basis' in content
