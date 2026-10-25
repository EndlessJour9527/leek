"""Synthetic, offline contract tests, not strategy or profitability evidence."""
import copy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import subprocess
import sys
import unittest

from research import evidence_boundary as boundary

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'examples/fixtures/research-evidence'


def fixture(name='historical-accepted'):
    return boundary.load_document((FIXTURES / (name + '.json')).read_text())


def seal(doc):
    """Rebind altered synthetic examples so non-hash checks are actually tested."""
    packet, candidate, challenge = doc['packet'], doc['candidate'], doc['challenge']
    packet['snapshot_sha256'] = boundary.canonical_sha256({k: v for k, v in packet.items() if k != 'snapshot_sha256'})
    candidate['packet_sha256'] = challenge['packet_sha256'] = packet['snapshot_sha256']
    candidate['candidate_sha256'] = boundary.canonical_sha256({k: v for k, v in candidate.items() if k != 'candidate_sha256'})
    challenge['candidate_sha256'] = candidate['candidate_sha256']
    return doc


def negative_search(doc):
    candidate = doc['candidate']
    candidate['counter_evidence_ids'] = []
    candidate['counter_search'] = {
        'scope': 'PACKET_ONLY', 'query': 'Synthetic bounded search for facts contradicting the neutral thesis.',
        'searched_at': '2026-01-06T09:02:00Z', 'as_of': doc['packet']['as_of'],
        'searched_evidence_ids': [item['evidence_id'] for item in doc['packet']['evidence']],
        'limitations': 'Only this synthetic packet; no external sources or actual model search.',
        'conclusion': 'NONE_FOUND_IN_BOUNDED_SCOPE',
    }
    return seal(doc)


class EvidenceBoundaryTests(unittest.TestCase):
    def assert_invalid(self, doc, code=None):
        result = boundary.evaluate(doc)
        self.assertEqual(result['status'], 'INVALID', result)
        self.assertEqual(result['research_stance'], 'ABSTAIN')
        self.assertFalse(result['execution_authorized'])
        self.assertFalse(result['profit_evidence'])
        if code:
            self.assertEqual(result['errors'][0]['code'], code, result)
        return result

    def test_historical_retrospective_capture_is_never_holdout(self):
        result = boundary.evaluate(fixture())
        self.assertEqual(result['status'], 'RESEARCH_PACKET_ACCEPTED')
        self.assertEqual(result['data_label'], 'ALL_SEEN_OR_RECONSTRUCTED')
        for flag in ('execution_authorized', 'profit_evidence', 'clean_holdout', 'truth_verified',
                     'provenance_authenticated', 'independent_authorship_verified', 'statistical_independence_verified'):
            self.assertFalse(result[flag])
        self.assertGreater(result['decision_available_at'], result['evidence_cutoff'])

    def test_forward_capture_cutoff_does_not_backdate_later_analysis(self):
        doc = fixture('forward-accepted')
        result = boundary.evaluate(doc)
        self.assertEqual(result['status'], 'RESEARCH_PACKET_ACCEPTED')
        self.assertEqual(result['data_label'], 'FORWARD_SHADOW_UNVERIFIED')
        self.assertFalse(result['clean_holdout'])
        self.assertEqual(result['decision_available_at'], doc['challenge']['created_at'])
        self.assertGreater(result['candidate_created_at'], result['evidence_cutoff'])

    def test_explicit_counterevidence_and_bounded_negative_search_both_supported(self):
        self.assertEqual(boundary.evaluate(fixture())['status'], 'RESEARCH_PACKET_ACCEPTED')
        self.assertEqual(boundary.evaluate(negative_search(fixture()))['status'], 'RESEARCH_PACKET_ACCEPTED')

    def test_missing_or_contradictory_counter_search_rejected(self):
        doc = fixture(); doc['candidate']['counter_evidence_ids'] = []
        self.assert_invalid(seal(doc), 'MISSING_COUNTEREVIDENCE')
        doc = negative_search(fixture())
        doc['candidate']['counter_evidence_ids'] = ['synthetic-counter-001']
        self.assert_invalid(seal(doc), 'CONTRADICTORY_SEARCH')

    def test_negative_search_is_bounded_and_cannot_be_empty(self):
        for field, value, code in (
            ('scope', 'WORLD', 'INVALID_ENUM'), ('query', ' ', 'INVALID_STRING'),
            ('limitations', '', 'INVALID_STRING'), ('searched_evidence_ids', [], 'INVALID_REFERENCES'),
            ('conclusion', 'NO_COUNTEREVIDENCE_EXISTS', 'INVALID_ENUM'),
            ('as_of', '2026-01-05T16:01:00Z', 'CUTOFF_MISMATCH'),
            ('searched_at', '2026-01-06T08:59:00Z', 'TIMESTAMP_ORDER'),
            ('searched_at', '2026-01-06T09:06:00Z', 'TIMESTAMP_ORDER')):
            with self.subTest(field=field, value=value):
                doc = negative_search(fixture()); doc['candidate']['counter_search'][field] = value
                self.assert_invalid(seal(doc), code)

    def test_material_disagreement_is_review_and_abstain_not_a_vote(self):
        doc = fixture('contradiction-review')
        result = boundary.evaluate(doc)
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertEqual(result['research_stance'], 'ABSTAIN')
        self.assertFalse(result['execution_authorized'])
        doc['candidate']['stance'] = 'ABSTAIN'
        self.assertEqual(boundary.evaluate(seal(doc))['status'], 'REVIEW_REQUIRED')

    def test_candidate_and_challenger_can_each_abstain(self):
        self.assertEqual(boundary.evaluate(fixture('explicit-abstain'))['status'], 'ABSTAIN')
        doc = fixture(); doc['challenge']['disposition'] = 'ABSTAIN'
        result = boundary.evaluate(doc)
        self.assertEqual(result['status'], 'ABSTAIN')
        self.assertEqual(result['research_stance'], 'ABSTAIN')

    def test_contradiction_disposition_must_agree_with_list(self):
        doc = fixture('contradiction-review')
        for disposition in ('NO_MATERIAL_CONTRADICTION_FOUND', 'ABSTAIN'):
            doc['challenge']['disposition'] = disposition
            self.assert_invalid(doc, 'CONTRADICTORY_DISPOSITION')
        doc = fixture(); doc['challenge']['disposition'] = 'MATERIAL_CONTRADICTIONS'
        self.assert_invalid(doc, 'CONTRADICTORY_DISPOSITION')

    def test_publication_and_availability_after_cutoff_rejected_even_rehashed(self):
        for mode in ('historical_development', 'forward_shadow'):
            for field in ('published_at', 'available_at'):
                with self.subTest(mode=mode, field=field):
                    doc = fixture(); doc['packet']['mode'] = mode
                    row = doc['packet']['evidence'][0]
                    row[field] = '2026-01-05T16:00:01Z'
                    if field == 'published_at':
                        row['available_at'] = row[field]
                    self.assert_invalid(seal(doc), 'FUTURE_EVIDENCE')

    def test_forward_future_capture_rejected(self):
        doc = fixture(); doc['packet']['mode'] = 'forward_shadow'
        self.assert_invalid(seal(doc), 'FUTURE_CAPTURE')

    def test_source_timestamp_order(self):
        for field, value in (('available_at', '2026-01-05T09:59:00Z'),
                             ('captured_at', '2026-01-05T10:04:00Z')):
            doc = fixture(); doc['packet']['evidence'][0][field] = value
            self.assert_invalid(seal(doc), 'TIMESTAMP_ORDER')

    def test_packet_candidate_challenge_creation_order(self):
        for obj, value in (('packet', '2026-01-06T08:59:00Z'),
                           ('candidate', '2026-01-06T09:00:00Z'),
                           ('challenge', '2026-01-06T09:04:00Z')):
            doc = fixture(); doc[obj]['created_at'] = value
            self.assert_invalid(seal(doc), 'TIMESTAMP_ORDER')

    def test_as_of_is_same_instant_not_same_spelling(self):
        doc = fixture()
        doc['candidate']['as_of'] = '2026-01-06T00:00:00+08:00'
        doc['challenge']['as_of'] = '2026-01-05T11:00:00-05:00'
        self.assertEqual(boundary.evaluate(seal(doc))['status'], 'RESEARCH_PACKET_ACCEPTED')
        doc['challenge']['as_of'] = '2026-01-05T11:00:01-05:00'
        self.assert_invalid(seal(doc), 'CUTOFF_MISMATCH')

    def test_timestamp_offsets_compare_absolute_instants(self):
        doc = fixture()
        doc['packet']['evidence'][0]['available_at'] = '2026-01-06T00:00:01+08:00'
        self.assert_invalid(seal(doc), 'FUTURE_EVIDENCE')

    def test_timestamp_invalid_aware_calendar_and_offset_rejected(self):
        for value in (None, '', '2026-01-05', '2026-01-05T16:00:00', '2026-02-30T16:00:00Z',
                      '2026-01-05T16:00:00-00:00', '2026-01-05T16:00:00+00:60',
                      '2026-01-05T16:00:00+08:99', '2026-01-05T16:00:00+24:00',
                      '2026-01-05T24:00:00Z', '2026-01-05T16:00:60Z'):
            with self.subTest(value=value):
                doc = fixture(); doc['packet']['as_of'] = value
                self.assert_invalid(seal(doc), 'INVALID_TIMESTAMP')

    def test_missing_timestamp_never_defaulted(self):
        for obj in ('packet', 'candidate', 'challenge'):
            for field in ('as_of', 'created_at'):
                doc = fixture(); del doc[obj][field]
                self.assert_invalid(seal(doc), 'MISSING_FIELDS')
        for field in ('published_at', 'available_at', 'captured_at'):
            doc = fixture(); del doc['packet']['evidence'][0][field]
            self.assert_invalid(seal(doc), 'MISSING_FIELDS')

    def test_content_tampering_and_packet_metadata_tampering(self):
        doc = fixture(); doc['packet']['evidence'][0]['content'] += ' altered'
        self.assert_invalid(seal(doc), 'HASH_MISMATCH')
        doc = fixture(); doc['packet']['evidence'][0]['source_uri'] += '/altered'
        self.assert_invalid(doc, 'HASH_MISMATCH')
        doc = fixture(); doc['packet']['packet_id'] += '-altered'
        self.assert_invalid(doc, 'HASH_MISMATCH')

    def test_candidate_mutation_breaks_its_hash(self):
        for field, value in (('stance', 'BULLISH'), ('thesis', 'A changed synthetic thesis.'),
                             ('producer_id', 'another-analyst')):
            doc = fixture(); doc['candidate'][field] = value
            self.assert_invalid(doc, 'HASH_MISMATCH')

    def test_reusing_challenge_after_candidate_resealed_is_rejected(self):
        doc = fixture(); old_challenge = copy.deepcopy(doc['challenge'])
        doc['candidate']['stance'] = 'BULLISH'; seal(doc)
        doc['challenge'] = old_challenge
        self.assert_invalid(doc, 'CANDIDATE_MISMATCH')

    def test_reusing_candidate_with_different_packet_is_rejected(self):
        doc = fixture(); old_candidate = copy.deepcopy(doc['candidate'])
        doc['packet']['packet_id'] = 'another-packet'; seal(doc)
        doc['candidate'] = old_candidate
        self.assert_invalid(doc, 'PACKET_MISMATCH')

    def test_reusing_challenge_with_different_packet_is_rejected(self):
        doc = fixture(); old_challenge = copy.deepcopy(doc['challenge'])
        doc['packet']['packet_id'] = 'another-packet'; seal(doc)
        doc['challenge'] = old_challenge
        self.assert_invalid(doc, 'PACKET_MISMATCH')

    def test_cross_run_objects_are_rejected(self):
        for obj in ('candidate', 'challenge'):
            doc = fixture(); doc[obj]['run_id'] = 'other-run'
            self.assert_invalid(seal(doc), 'RUN_MISMATCH')
        doc = fixture(); doc['packet']['run_id'] = 'other-run'
        self.assert_invalid(seal(doc), 'RUN_MISMATCH')

    def test_self_review_and_identity_aliases(self):
        doc = fixture(); doc['challenge']['producer_id'] = doc['candidate']['producer_id']
        self.assert_invalid(doc, 'SELF_REVIEW')
        for value in ('synthetic-analyst ', ' synthetic-analyst', 'SYNTHETIC-ANALYST', 'synthetic-analyst\n'):
            doc = fixture(); doc['challenge']['producer_id'] = value
            self.assert_invalid(doc, 'INVALID_ID')

    def test_duplicate_ids_and_references(self):
        doc = fixture(); doc['packet']['evidence'].append(copy.deepcopy(doc['packet']['evidence'][0]))
        self.assert_invalid(seal(doc), 'DUPLICATE_ID')
        doc = fixture(); doc['candidate']['supporting_evidence_ids'] *= 2
        self.assert_invalid(seal(doc), 'DUPLICATE_ID')
        doc = fixture(); doc['challenge']['challenge_id'] = doc['candidate']['candidate_id']
        self.assert_invalid(doc, 'DUPLICATE_ID')

    def test_unknown_evidence_and_incomplete_review(self):
        doc = fixture(); doc['candidate']['supporting_evidence_ids'] = ['invented-evidence']
        self.assert_invalid(seal(doc), 'UNKNOWN_REFERENCE')
        doc = fixture(); doc['challenge']['reviewed_evidence_ids'] = ['synthetic-support-001']
        self.assert_invalid(doc, 'INCOMPLETE_REVIEW')
        doc = fixture('contradiction-review')
        doc['challenge']['contradictions'][0]['evidence_ids'] = ['invented-evidence']
        self.assert_invalid(doc, 'UNKNOWN_REFERENCE')

    def test_review_must_cover_packet_evidence_even_when_candidate_did_not_cite_it(self):
        doc = fixture()
        extra = copy.deepcopy(doc['packet']['evidence'][0])
        extra['evidence_id'] = 'synthetic-uncited-001'
        doc['packet']['evidence'].append(extra)
        self.assert_invalid(seal(doc), 'INCOMPLETE_REVIEW')
        doc['challenge']['reviewed_evidence_ids'].append(extra['evidence_id'])
        self.assertEqual(boundary.evaluate(doc)['status'], 'RESEARCH_PACKET_ACCEPTED')

    def test_counter_search_cannot_precede_packet_creation(self):
        doc = negative_search(fixture())
        doc['candidate']['counter_search']['searched_at'] = '2026-01-06T09:00:30Z'
        self.assert_invalid(seal(doc), 'TIMESTAMP_ORDER')

    def test_observed_sources_require_http_hostname_without_credentials(self):
        for uri in ('synthetic://example.invalid/test', 'file:///tmp/evidence', 'https:///missing-host',
                    'https://user:password@example.invalid/data', 'https://user@example.invalid/data',
                    'https://bad_host.invalid/data', 'https://-bad.invalid/data',
                    'https://bad-.invalid/data', 'https://host..invalid/data', 'https://example.invalid../data',
                    'https://example.invalid:99999/data', 'https://example.invalid:bad/data',
                    'https://example.invalid /data', ' https://example.invalid/data',
                    'https://example.invalid/line\nfeed', 'https://example%40invalid/data',
                    'not a URI'):
            with self.subTest(uri=uri):
                doc = fixture(); doc['packet']['data_classification'] = 'OBSERVED'
                for row in doc['packet']['evidence']:
                    row['source_uri'] = uri
                self.assert_invalid(seal(doc), 'INVALID_SOURCE_URI')

    def test_source_syntax_does_not_imply_network_access_or_authenticity(self):
        for classification, uri in (('OBSERVED', 'https://example.invalid/evidence#section'),
                                    ('OBSERVED', 'http://127.0.0.1:8080/evidence'),
                                    ('OBSERVED', 'https://[2001:db8::1]/evidence'),
                                    ('SYNTHETIC', 'synthetic://example.invalid/fixture')):
            with self.subTest(classification=classification, uri=uri):
                doc = fixture(); doc['packet']['data_classification'] = classification
                for row in doc['packet']['evidence']:
                    row['source_uri'] = uri
                report = boundary.evaluate(seal(doc))
                self.assertEqual(report['status'], 'RESEARCH_PACKET_ACCEPTED')
                self.assertFalse(report['provenance_authenticated'])
                self.assertFalse(report['truth_verified'])

    def test_unknown_fields_rejected_at_every_object_level(self):
        for location in ('envelope', 'packet', 'evidence', 'candidate', 'challenge', 'counter_search', 'search_summary', 'contradiction'):
            with self.subTest(location=location):
                doc = negative_search(fixture('contradiction-review'))
                target = {'envelope': doc, 'packet': doc['packet'], 'evidence': doc['packet']['evidence'][0],
                          'candidate': doc['candidate'], 'challenge': doc['challenge'],
                          'counter_search': doc['candidate']['counter_search'],
                          'search_summary': doc['challenge']['search_summary'],
                          'contradiction': doc['challenge']['contradictions'][0]}[location]
                target['quantity'] = 100
                self.assert_invalid(seal(doc), 'UNKNOWN_FIELDS')

    def test_order_actions_and_free_text_never_become_stances(self):
        for stance in ('BUY', 'SELL', 'LONG', 'SHORT', 'buy 100', '', None, ['BULLISH']):
            doc = fixture(); doc['candidate']['stance'] = stance
            self.assert_invalid(seal(doc), 'INVALID_ENUM')
        for text in ('BUY 100', '```json\n{}\n```', 'prefix {}', '{"stance":"BUY"} trailing'):
            result = boundary.evaluate_json(text)
            self.assertEqual(result['status'], 'INVALID')
            self.assertEqual(result['research_stance'], 'ABSTAIN')

    def test_missing_support_thesis_and_invalidation_rejected(self):
        for field, value, code in (('supporting_evidence_ids', [], 'INVALID_REFERENCES'),
                                    ('thesis', '', 'INVALID_STRING'),
                                    ('invalidation_condition', ' ', 'INVALID_STRING')):
            doc = fixture(); doc['candidate'][field] = value
            self.assert_invalid(seal(doc), code)

    def test_strict_json_duplicate_keys_nonfinite_and_version(self):
        for text in ('{"schema_version":1,"schema_version":1}', '{"a":{"x":1,"x":2}}',
                     '{"value":NaN}', '{"value":Infinity}', '{"value":-Infinity}', '{"value":1e999}'):
            self.assertEqual(boundary.evaluate_json(text)['status'], 'INVALID')
        for version in (True, 1.0, '1', None, 2):
            doc = fixture(); doc['schema_version'] = version
            self.assert_invalid(doc, 'INVALID_VERSION')
        for value in (float('inf'), float('nan'), float('-inf')):
            doc = fixture(); doc['candidate']['thesis'] = value
            self.assert_invalid(doc, 'NONFINITE_NUMBER')

    def test_lone_surrogates_and_non_json_python_types_are_safe(self):
        result = boundary.evaluate_json('{"bad":"\\ud800"}')
        self.assertEqual(result['status'], 'INVALID')
        self.assertEqual(result['errors'][0]['code'], 'INVALID_UNICODE')
        for value in (set(), object(), b'content', ('tuple',)):
            doc = fixture(); doc['candidate']['thesis'] = value
            self.assert_invalid(doc, 'INVALID_JSON_TYPE')
        self.assert_invalid({1: 'not a JSON key'}, 'INVALID_JSON_TYPE')

    def test_frozen_packet_is_immutable_and_input_is_not_mutated(self):
        doc = fixture(); original = copy.deepcopy(doc)
        result = boundary.evaluate(doc)
        self.assertEqual(doc, original)
        self.assertEqual(boundary.evaluate(doc), result)
        packet = boundary._packet(doc['packet'])
        with self.assertRaises(FrozenInstanceError):
            packet.run_id = 'other-run'
        with self.assertRaises(FrozenInstanceError):
            packet.evidence[0].content = 'changed'
        doc['packet']['evidence'][0]['content'] = 'changed outside immutable value'
        self.assertNotEqual(packet.evidence[0].content, doc['packet']['evidence'][0]['content'])

    def test_canonical_hash_stable_for_key_order_not_content_or_array_order(self):
        self.assertEqual(boundary.canonical_sha256({'b': 2, 'a': 1}), boundary.canonical_sha256({'a': 1, 'b': 2}))
        self.assertNotEqual(boundary.canonical_sha256([1, 2]), boundary.canonical_sha256([2, 1]))
        self.assertNotEqual(boundary.content_sha256('a'), boundary.content_sha256('a '))

    def test_all_cli_fixtures_are_byte_reproducible_including_optimized_runtime(self):
        statuses = {'historical-accepted': 0, 'forward-accepted': 0, 'contradiction-review': 2,
                    'explicit-abstain': 2, 'future-rejected': 1}
        for optimize in ([], ['-O'], ['-OO']):
            for name, code in statuses.items():
                with self.subTest(name=name, optimize=optimize):
                    result = subprocess.run([sys.executable, *optimize, '-m', 'research.evidence_boundary',
                                             str(FIXTURES / (name + '.json'))], cwd=ROOT, capture_output=True)
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertEqual(result.stderr, b'')
                    self.assertEqual(result.stdout, (FIXTURES / (name + '.expected.json')).read_bytes())

    def test_cli_invalid_input_stdin_and_missing_file_fail_closed(self):
        for args, text in ((['-'], 'BUY'), (['-'], '{"a": NaN}'), ([str(FIXTURES / 'absent.json')], None)):
            result = subprocess.run([sys.executable, '-m', 'research.evidence_boundary', *args],
                                    cwd=ROOT, input=text, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['status'], 'INVALID')
            self.assertFalse(report['execution_authorized'])
            self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
