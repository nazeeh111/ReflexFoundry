import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'continue_native.py'
spec = importlib.util.spec_from_file_location('continuation_under_test', SOURCE)
assert spec and spec.loader
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def test_driver_source_matches_reviewable_snapshot():
    manifest = json.loads((SOURCE.parent / 'SOURCE_SHA256SUMS.json').read_text())
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == manifest['continue_native.py']


@pytest.mark.parametrize('index', [0, 1, 18, 21, True, '19'])
def test_only_original_unused_indices_are_allowed(index):
    with pytest.raises(ValueError, match='only original indices'):
        driver.check_attempt_gate(index, 18, {})


def test_prior_file_change_is_rejected(tmp_path):
    source = tmp_path / 'result.json'
    source.write_text('{"protocol_failure": true}')
    manifest = driver.inventory(tmp_path)
    source.write_text('{"protocol_failure": false}')
    with pytest.raises(ValueError, match='original phase files changed'):
        driver.verify_manifest(tmp_path, manifest)


def test_original_and_continuation_share_one_call_cap():
    with pytest.raises(ValueError, match='twenty-reservation cap'):
        driver.check_attempt_gate(20, 18, {19: {}, 20: None})


@pytest.mark.parametrize('prior', [None, {'native_process_started': True, 'protocol_failure': True}])
def test_twenty_is_blocked_if_nineteen_is_incomplete_or_failed(prior):
    with pytest.raises(ValueError, match='stop again'):
        driver.check_attempt_gate(20, 18, {19: prior})


def test_nineteen_cannot_be_retried():
    with pytest.raises(ValueError, match='once-only order'):
        driver.check_attempt_gate(19, 18, {19: {'native_process_started': True, 'protocol_failure': False}})


def test_only_successful_protocol_nineteen_opens_twenty():
    driver.check_attempt_gate(19, 18, {})
    driver.check_attempt_gate(20, 18, {19: {'native_process_started': True, 'protocol_failure': False}})
