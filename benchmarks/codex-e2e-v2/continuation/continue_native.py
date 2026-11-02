"""Prepare or execute one reviewed, once-only continuation of the stopped study.

This separate observer never changes the original runner, plan or phase-A data.
A review record and consent flag are necessary gates, not human authority or a
replacement for the ordinary outer native approval control.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path('/Users/nazeeh/Documents/ChatGPT/Continue/work/reflexfoundry-build')
ORIGINAL = REPO / 'runs/native-v2-study'
OUTPUT = REPO / 'runs/native-v2-continuation-01'
AUTHORITY = REPO.parent / 'reflexfoundry/evidence/native-v2-authorization-2026-11-01.json'
PLAN_SHA = '0634b5648f675aa6cd08e47397397298f7b83e10b7eb1ab00e5afb86440752d1'
FAILED_SHA = '7a4ef5d4ce2659216244619ef1c99870e77212c9044bfb01a10fbee8cd4eb975'
PHASE = 'reviewed-continuation-01'
AUTHORITY_TEXT_SHA256 = 'a39030316faa1a33666dc6e2cdc581610f0ed8eeda96cbe2387ef516f22576ef'


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path: Path, limit: int = 2 * 1024 * 1024) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'expected a regular metadata file: {path.name}')
    with path.open('rb') as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError('metadata exceeds its byte bound')
    return json.loads(data)


def inventory(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    total = 0
    for path in sorted(root.rglob('*')):
        if any(part in {'__pycache__', '.pytest_cache'} for part in path.relative_to(root).parts):
            continue
        if path.is_symlink():
            raise ValueError('phase-A evidence must not contain links')
        if path.is_file():
            total += path.stat().st_size
            if total > 32 * 1024 * 1024 or len(result) >= 4096:
                raise ValueError('phase-A evidence exceeds its bound')
            result[str(path.relative_to(root))] = sha(path)
    return result


def verify_manifest(root: Path, expected: dict[str, str]) -> None:
    if inventory(root) != expected:
        raise ValueError('original phase files changed')


def check_attempt_gate(index: int, original_count: int,
                       reserved: dict[int, dict[str, Any] | None]) -> None:
    if type(index) is not int or index not in (19, 20):
        raise ValueError('only original indices 19 and 20 are permitted')
    if original_count + len(reserved) >= 20:
        raise ValueError('shared twenty-reservation cap reached')
    if original_count != 18:
        raise ValueError('original reservation count must remain eighteen')
    if set(reserved) != set(range(19, index)):
        raise ValueError('once-only order changed, an attempt exists, or a prior attempt is missing')
    for result in reserved.values():
        if (not isinstance(result, dict) or result.get('protocol_failure') is not False
                or result.get('native_process_started') is not True):
            raise ValueError('prior continuation is incomplete or failed protocol; stop again')


def load_study() -> Any:
    sys.path.insert(0, str(REPO / 'scripts'))
    study = importlib.import_module('native_study_v2')
    if Path(study.__file__).resolve() != REPO / 'scripts/native_study_v2.py':
        raise ValueError('unexpected frozen study module')
    return study


def observer_sources() -> dict[str, str]:
    paths = [*sorted((REPO / 'src/reflexfoundry').glob('*.py')),
             *(REPO / 'scripts' / name for name in
               ('native_study_v2.py', 'native_retrieve_v2.py', 'native_study_tasks.py'))]
    return {str(path.relative_to(REPO)): sha(path) for path in paths}


def phase_a(study: Any, plan: dict[str, Any]) -> int:
    if sha(ORIGINAL / 'plan.json') != PLAN_SHA or sha(ORIGINAL / 'attempts/18/result.json') != FAILED_SHA:
        raise ValueError('original plan or failed result changed')
    folders = sorted((ORIGINAL / 'attempts').iterdir())
    if [p.name for p in folders] != [f'{i:02}' for i in range(1, 19)]:
        raise ValueError('original attempt inventory differs from exactly 1 through 18')
    for i in range(1, 19):
        folder = ORIGINAL / 'attempts' / f'{i:02}'
        result, started = read(folder / 'result.json'), read(folder / 'started.json')
        item = plan['order'][i - 1]
        if (started.get('native_process_started') is not True or result.get('native_process_started') is not True
                or any(result.get(key) != item[key] for key in ('index', 'task', 'repeat', 'arm'))):
            raise ValueError('original process or result identity changed')
        if sha(folder / 'candidate.py') != result.get('candidate_sha256'):
            raise ValueError('original candidate bytes changed')
        if i < 18 and (result.get('protocol_failure') is not False or result.get('task_success') is not True):
            raise ValueError('one of the seventeen valid original results changed')
        if i == 18:
            if (result.get('protocol_failure') is not True or result.get('timed_out') is not True
                    or result.get('immutable_files_preserved') is not True
                    or result.get('telemetry', {}).get('completed_turns') != 0
                    or result.get('telemetry', {}).get('token_usage') is not None
                    or result.get('retrieval_receipts') != [] or result.get('inference_observed') is not False
                    or result.get('changed_public_files') != [] or result.get('extra_files') != []
                    or result['candidate_sha256'] != item['mutated_source_sha256']):
                raise ValueError('original timeout no longer matches reviewed terminal evidence')
    study.validate_plan(plan, ORIGINAL)
    return 18


def prepare(output: Path) -> dict[str, Any]:
    if output.resolve() != OUTPUT or output.exists():
        raise ValueError('preparation requires the fresh designated continuation output')
    study = load_study()
    plan = read(ORIGINAL / 'plan.json')
    phase_a(study, plan)
    authority = read(AUTHORITY)
    authority_text = authority.get('authorization')
    if (not isinstance(authority_text, str)
            or hashlib.sha256(authority_text.encode()).hexdigest() != AUTHORITY_TEXT_SHA256):
        raise ValueError('direct user authority record differs from the reviewed scope')
    original_files = inventory(ORIGINAL)
    cases = []
    for item in plan['order'][-2:]:
        case = Path(item['case'])
        if (study.inventory(case, max_bytes=32 * 1024**2) != item['initial_files']
                or not study.case_runtime_matches(case, plan, item)
                or sha(ORIGINAL / 'prompts' / f"{item['index']:02}.txt") != item['prompt_sha256']):
            raise ValueError('original unattempted case or prompt changed')
        cases.append({key: item[key] for key in ('index', 'task', 'repeat', 'arm', 'case', 'prompt_sha256')})
    value = {'format': 1, 'phase': PHASE, 'status': 'prepared-not-run',
             'created_utc': datetime.now(timezone.utc).isoformat(),
             'original_plan_sha256': PLAN_SHA, 'original_failed_result_sha256': FAILED_SHA,
             'original_phase_files': original_files, 'observer_sources': observer_sources(),
             'observer_checkout': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
             'driver_sha256': sha(Path(__file__)), 'authority_record_sha256': sha(AUTHORITY),
             'direct_user_scope': {'total_calls': 20, 'seconds_per_call': 180,
                                   'context': 'public source and generated ReflexFoundry runtime, policy and report files',
                                   'subscription_only_confirmed': True, 'paid_api': False},
             'cases': cases, 'cli_version': plan['codex_version'], 'interpreter': sys.executable,
             'runtime_versions': study.runtime_versions(), 'independent_review_required': True,
             'ordinary_outer_review_required': True,
             'limits': ['No retry or resampling of trial18. Original files and stop record remain immutable.',
                        'Only19 then20 once, with20 blocked if19 fails protocol. Shared reservation cap20.',
                        'Timeout cause unknown; this is a declared observer amendment after a publication/time gap.',
                        'Combined estimates are post-amendment. Even success leaves trial18 invalid; at most15valid pairs.']}
    verify_manifest(ORIGINAL, original_files)
    output.mkdir(parents=True, exist_ok=False)
    study.save(output / 'amendment.json', value)
    return value


def validated(output: Path, review: Path) -> tuple[Any, dict[str, Any], dict[str, Any], str, str]:
    if output.resolve() != OUTPUT:
        raise ValueError('unexpected continuation output')
    study = load_study()
    amendment = read(output / 'amendment.json')
    if (amendment.get('format') != 1 or amendment.get('phase') != PHASE
            or amendment.get('original_plan_sha256') != PLAN_SHA
            or amendment.get('original_failed_result_sha256') != FAILED_SHA
            or amendment.get('driver_sha256') != sha(Path(__file__))
            or amendment.get('observer_sources') != observer_sources()
            or amendment.get('authority_record_sha256') != sha(AUTHORITY)
            or amendment.get('interpreter') != sys.executable):
        raise ValueError('amendment, source, authority or interpreter identity changed')
    plan = read(ORIGINAL / 'plan.json')
    phase_a(study, plan)
    verify_manifest(ORIGINAL, amendment['original_phase_files'])
    if amendment.get('runtime_versions') != study.runtime_versions() or amendment.get('cli_version') != plan['codex_version']:
        raise ValueError('runtime or CLI identity changed')
    tail = [{key: item[key] for key in ('index', 'task', 'repeat', 'arm', 'case', 'prompt_sha256')}
            for item in plan['order'][-2:]]
    if amendment.get('cases') != tail:
        raise ValueError('continuation cases differ from frozen original tail')
    amendment_sha = sha(output / 'amendment.json')
    record = read(review, 64 * 1024)
    if (record.get('amendment_sha256') != amendment_sha or record.get('driver_sha256') != sha(Path(__file__))
            or record.get('independent_review_complete') is not True
            or record.get('scope_indices') != [19, 20] or record.get('unresolved_blockers') != []
            or record.get('ordinary_outer_review_required') is not True
            or not isinstance(record.get('reviewer'), str) or not record['reviewer'].strip()
            or not isinstance(record.get('summary'), str) or not record['summary'].strip()):
        raise ValueError('a matching completed independent review record is required; a flag is not authority')
    return study, plan, amendment, amendment_sha, sha(review)


def reserved_results(output: Path) -> dict[int, dict[str, Any] | None]:
    root = output / 'attempts'
    result = {}
    for folder in sorted(root.iterdir()) if root.exists() else []:
        if folder.name not in {'19', '20'} or folder.is_symlink() or not folder.is_dir():
            raise ValueError('unexpected continuation reservation')
        read(folder / 'started.json')
        value = read(folder / 'result.json') if (folder / 'result.json').exists() else None
        if value is not None and value.get('index') != int(folder.name):
            raise ValueError('continuation result differs from its reserved index')
        result[int(folder.name)] = value
    return result


def run_one(index: int, output: Path, review: Path, *, consent_egress: bool) -> dict[str, Any]:
    if not consent_egress:
        raise ValueError('scoped human authority, independent review, outer approval and explicit consent are required')
    if type(index) is not int or index not in (19, 20):
        raise ValueError('only original indices 19 and 20 are permitted')
    started = time.perf_counter()
    study, plan, amendment, amendment_sha, review_sha = validated(output, review)
    previous = reserved_results(output)
    check_attempt_gate(index, 18, previous)
    for result in previous.values():
        if result is None or result.get('amendment_sha256') != amendment_sha or result.get('phase') != PHASE:
            raise ValueError('prior continuation result is not bound to this amendment')
    item = plan['order'][index - 1]
    case = Path(item['case'])
    task = next(task for task in study.TASKS if task.name == item['task'])
    if study.inventory(case, max_bytes=32 * 1024**2) != item['initial_files'] or not study.case_runtime_matches(case, plan, item):
        raise ValueError('once-only prepared case changed')
    prompt = ORIGINAL / 'prompts' / f'{index:02}.txt'
    if sha(prompt) != item['prompt_sha256']:
        raise ValueError('frozen prompt changed')
    folder = output / 'attempts' / f'{index:02}'
    folder.mkdir(parents=True, exist_ok=False)
    identity = {'index': index, 'phase': PHASE, 'amendment_sha256': amendment_sha,
                'review_sha256': review_sha, 'original_plan_sha256': PLAN_SHA}
    study.save(folder / 'started.json', {**identity, 'time_unix': time.time(), 'native_process_started': False})
    shutil.copy2(review, folder / 'review.json')
    if sha(folder / 'review.json') != review_sha:
        raise ValueError('review record changed during reservation; no native launch')
    final = folder / 'final-answer.txt'
    cmd = ['codex', 'exec', '--ephemeral', '--sandbox', 'workspace-write', '--skip-git-repo-check',
           '--json', '--color', 'never', '-C', str(case), '-o', str(final.resolve()), '-']
    study.save(folder / 'invocation.json', {'argv': cmd, 'prompt_sha256': item['prompt_sha256'],
                                          'external_authority_required': True, **identity})
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1')
    launch_started = time.perf_counter()
    try:
        proc = subprocess.Popen(cmd, cwd=case, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True)
    except OSError:
        result = {**identity, 'task': task.name, 'repeat': item['repeat'], 'arm': item['arm'],
                  'native_process_started': False, 'protocol_failure': True, 'task_success': False,
                  'pipeline_wall_ms': None, 'readiness_ms': (launch_started - started) * 1000,
                  'attempt_all_in_ms': (time.perf_counter() - started) * 1000,
                  'failure': 'native process could not start; stop again, no retry'}
        study.save(folder / 'result.json', result)
        return result
    study.save(folder / 'started.json', {**identity, 'time_unix': time.time(), 'native_process_started': True})
    try:
        assert proc.stdin is not None
        with contextlib.suppress(BrokenPipeError):
            proc.stdin.write(prompt.read_bytes())
            proc.stdin.close()
        result = study.observe_process(proc, plan['executable'], started=launch_started)
    finally:
        # An observer/input-delivery exception leaves a reserved incomplete
        # attempt, so the next index stays blocked; never leave its child live.
        study.stop(proc)
    verification = {'focused': study.run_check(task, case, task.focused_args),
                    'full': study.run_check(task, case, task.full_args)}
    grader = folder / 'independent-grader.py'
    grader.write_text(task.grader)
    verification['public_contract'] = study.run_check(task, case, (str(grader.resolve()),))
    verification_finished = time.perf_counter()
    try:
        current = study.inventory(case, max_bytes=32 * 1024**2)
    except (OSError, ValueError):
        current = {}
    allowed_new = {'context-result.json', 'advisory.json', '.reflex/requests.json'}
    extra = set(current) - set(item['initial_files']) - allowed_new
    changed = {name for name, value in item['initial_files'].items() if current.get(name) != value}
    unchanged = not extra and changed <= {task.source_file} and study.case_runtime_matches(case, plan, item)
    context = {}
    context_file = case / 'context-result.json'
    if context_file.is_file() and not context_file.is_symlink() and context_file.stat().st_size <= 128 * 1024:
        try:
            value = json.loads(context_file.read_text())
            if isinstance(value, dict):
                context = value
        except (ValueError, UnicodeDecodeError):
            pass
    retrieval = study.assess_retrieval(item, plan, context, result)
    try:
        _, _, _, checked_amendment, checked_review = validated(output, review)
        frozen = checked_amendment == amendment_sha and checked_review == review_sha
    except (OSError, ValueError):
        frozen = False
    receipt_valid = retrieval['observed_receipt_valid'] and unchanged and frozen
    inference = retrieval['inference_observed'] and unchanged and frozen
    usage = result['telemetry']['token_usage']
    protocol_ok = (result['telemetry']['completed_turns'] == 1 and usage is not None
                   and not result['invalid_events'] and not result['event_errors'] and not result['timed_out']
                   and not result['stream_limit_exceeded'] and result['cli_exit_code'] == 0 and unchanged and frozen
                   and retrieval['retrieval_protocol_valid'] and inference)
    result.update(**identity, task=task.name, repeat=item['repeat'], arm=item['arm'],
                  native_process_started=True, protocol_failure=not protocol_ok,
                  retrieval_protocol_valid=retrieval['retrieval_protocol_valid'] and unchanged and frozen,
                  inference_observed=inference, observed_receipt_valid=receipt_valid,
                  immutable_files_preserved=unchanged and frozen, independent=verification,
                  task_success=all(check['passed'] for check in verification.values()), context=context,
                  changed_public_files=sorted(changed), extra_files=sorted(extra),
                  pipeline_wall_ms=(verification_finished - launch_started) * 1000,
                  readiness_ms=(launch_started - started) * 1000, candidate_sha256=current.get(task.source_file))
    target = case / task.source_file
    if target.is_file() and not target.is_symlink() and target.stat().st_size <= 2 * 1024**2:
        shutil.copy2(target, folder / 'candidate.py')
    if final.exists():
        with final.open() as handle:
            answer = handle.read(12000)
        final.write_text(study.privacy_filter({'summary': answer})['summary'])
    assembled = time.perf_counter()
    result['postcondition_audit_ms'] = (assembled - verification_finished) * 1000
    result['attempt_all_in_ms'] = (assembled - started) * 1000
    study.save(folder / 'result.json', result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare-only', action='store_true')
    mode.add_argument('--run-index', type=int, choices=(19, 20))
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--review-record', type=Path)
    parser.add_argument('--consent-egress', action='store_true')
    args = parser.parse_args()
    if args.prepare_only:
        if args.consent_egress or args.review_record is not None:
            parser.error('preparation must not assert execution consent or completed review')
        value = prepare(args.output.resolve())
        print(json.dumps({'phase': value['phase'], 'status': value['status'], 'calls_started': 0}))
    else:
        if args.review_record is None:
            parser.error('run requires a matching independent review record')
        value = run_one(args.run_index, args.output.resolve(), args.review_record.resolve(), consent_egress=args.consent_egress)
        print(json.dumps({key: value[key] for key in ('index', 'phase', 'task_success', 'protocol_failure')}))


if __name__ == '__main__':
    main()
