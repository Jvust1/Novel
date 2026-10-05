"""Original synthetic encodings through real reference/originality/UI entries."""
from __future__ import annotations

import codecs
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from novel_ai.reading import extract_reference, extract_reference_text
from novel_ai.reference_pack import build_reference_pack, build_reference_source
from novel_ai.text_decoding import (
    EncodingSelectionRequired,
    TextDecodingError,
    decode_reference_text,
)

ROOT = Path(__file__).resolve().parents[1]
TEXT = ('第三章 雨停之后\r\n周宁把铜钥匙放在桌上，没有解释门为什么开着。\r\n'
        '他用空出的右手扶住门框，等屋里的人先说话。\r\n' * 12)


@pytest.mark.parametrize('codec', ['utf-8', 'utf-8-sig', 'utf-16', 'utf-32'])
def test_deterministic_unicode_exact_text_and_provenance(codec):
    raw = TEXT.encode(codec)
    decoded = decode_reference_text(raw)
    assert decoded.text == TEXT
    report = decoded.report()
    assert report['source_sha256'] == hashlib.sha256(raw).hexdigest()
    assert report['decoded_utf8_sha256'] == hashlib.sha256(TEXT.encode()).hexdigest()
    assert report['source_bytes'] == len(raw)
    assert report['round_trip_verified'] is True
    assert TEXT not in json.dumps(report)


def test_gb18030_requires_choice_even_when_detector_ranks_it_first():
    raw = TEXT.encode('gb18030')
    with pytest.raises(EncodingSelectionRequired) as caught:
        extract_reference_text('synthetic.txt', raw)
    assert 'gb18030' in [row['encoding'] for row in caught.value.candidates]
    assert extract_reference_text('synthetic.txt', raw, encoding='gb18030') == TEXT


@pytest.mark.parametrize('codec', ['utf-8', 'utf-16-le', 'cp1252'])
def test_bom_conflict_never_tries_another_codec(codec):
    with pytest.raises(TextDecodingError, match='BOM'):
        decode_reference_text(codecs.BOM_UTF16_BE + TEXT.encode('utf-16-be'), encoding=codec)


def test_profile_uses_complete_text_before_analysis_or_hashing():
    original = build_reference_source('synthetic.txt', TEXT.encode())
    selected = build_reference_source('synthetic.txt', TEXT.encode('gb18030'), encoding='gb18030')
    assert original.style == selected.style
    assert original.signature_hashes == selected.signature_hashes
    assert original.char_count == selected.char_count
    assert original.source_id != selected.source_id
    assert selected.decoding['decision'] == 'explicit'
    assert selected.decoding['encoding'] == 'gb18030'
    assert TEXT not in selected.model_dump_json()


def test_mixed_pack_retains_legacy_three_tuple_and_per_file_codec():
    pack = build_reference_pack([('a.txt', TEXT.encode(), 1),
                                 ('b.txt', TEXT.encode('gb18030'), 2, 'gb18030')])
    assert pack.source_count == 2
    assert pack.sources[0].decoding['encoding'] == 'utf-8'
    assert pack.sources[1].decoding['encoding'] == 'gb18030'
    assert pack.sources[0].char_count == pack.sources[1].char_count


def cli(tmp_path, name, *args):
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    return subprocess.run([sys.executable, str(ROOT/'scripts'/name), *map(str, args)],
                          cwd=tmp_path, env=env, text=True, capture_output=True, check=False, timeout=30)


def test_reference_pack_cli_failure_preserves_old_output_then_explicit_choice_works(tmp_path):
    source = tmp_path/'original.txt'; source.write_bytes(TEXT.encode('gb18030'))
    output = tmp_path/'pack.json'; output.write_bytes(b'previous complete evidence')
    rejected = cli(tmp_path, 'build_reference_pack.py', source, '--out', output)
    assert rejected.returncode == 2
    assert output.read_bytes() == b'previous complete evidence'
    assert TEXT not in rejected.stderr
    accepted = cli(tmp_path, 'build_reference_pack.py', source, '--encoding', source, 'gb18030', '--out', output)
    assert accepted.returncode == 0, accepted.stderr
    pack = json.loads(output.read_text())
    assert pack['sources'][0]['decoding']['encoding'] == 'gb18030'
    assert pack['sources'][0]['char_count'] == build_reference_source('original.txt', TEXT.encode()).char_count
    assert source.read_bytes() == TEXT.encode('gb18030')


def test_originality_cli_finds_identical_prose_across_different_encodings(tmp_path):
    target = tmp_path/'target.txt';target.write_bytes(TEXT.encode())
    ref = tmp_path/'ref.txt';ref.write_bytes(TEXT.encode('gb18030'))
    output = tmp_path/'originality.json';output.write_bytes(b'previous evidence')
    rejected = cli(tmp_path,'check_originality.py','--target',target,'--reference',ref,'--output',output)
    assert rejected.returncode == 2
    assert output.read_bytes() == b'previous evidence'
    result = cli(tmp_path,'check_originality.py','--target',target,'--reference',ref,
                 '--reference-encoding','gb18030','--output',output)
    assert result.returncode == 2, result.stderr  # Identical reference must fail originality.
    report = json.loads(output.read_text())
    assert report['passed'] is False
    assert report['input_decoding']['target']['decoded_utf8_sha256'] == report['input_decoding']['references'][0]['decoded_utf8_sha256']
    assert TEXT not in output.read_text()


def test_encoding_selection_count_or_path_errors_do_not_write(tmp_path):
    a=tmp_path/'a.txt';a.write_bytes(TEXT.encode())
    out=tmp_path/'absent.json'
    r=cli(tmp_path,'check_originality.py','--target',a,'--reference',a,'--reference',a,
          '--reference-encoding','utf-8','--output',out)
    assert r.returncode == 2 and not out.exists()
    r=cli(tmp_path,'build_reference_pack.py',a,'--encoding',tmp_path/'other.txt','utf-8','--out',out)
    assert r.returncode == 2 and not out.exists()


def test_legacy_utf8_reader_contract_is_retained():
    result=extract_reference('original.md',TEXT.encode())
    assert result.backend=='utf8' and result.text==TEXT


def test_style_lab_rejects_ambiguous_bytes_before_model_or_save_then_accepts_choice(monkeypatch,tmp_path):
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    from novel_ai.provider import OpenAICompatibleProvider

    source_bytes=[TEXT.encode('gb18030')]
    class Upload:
        name='original-synthetic.txt'
        def getvalue(self):
            return source_bytes[0]

    old_uploader=st.file_uploader
    def uploader(label,*args,**kwargs):
        if label.startswith('上传参考文本'):
            return Upload()
        return old_uploader(label,*args,**kwargs)
    calls=[]
    def forbidden(*args,**kwargs):
        calls.append(True)
        raise AssertionError('must not contact model before successful decoding')
    monkeypatch.setattr(st,'file_uploader',uploader)
    monkeypatch.setattr(OpenAICompatibleProvider,'chat',forbidden)
    monkeypatch.chdir(tmp_path)
    at=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    assert not at.exception
    before={p:p.read_bytes() for p in (tmp_path/'data').rglob('*') if p.is_file()}
    next(b for b in at.button if b.label=='分析并加入风格库').click().run()
    assert not at.exception and at.error
    assert not calls and not at.session_state['style_profiles']
    assert all(p.read_bytes()==raw for p,raw in before.items())
    assert not list((tmp_path/'data').rglob('style_profiles.json'))
    at.selectbox(key='reference_text_encoding').set_value('GB18030')
    next(c for c in at.checkbox if c.label=='使用当前模型做语义文体分析').uncheck()
    next(b for b in at.button if b.label=='分析并加入风格库').click().run()
    assert not at.exception and not calls
    assert len(at.session_state['style_profiles'])==1
    expected=build_reference_source('original-synthetic.txt',TEXT.encode()).style
    actual=at.session_state['style_profiles'][0]['fingerprint']
    assert actual['avg_sentence_chars']==expected.avg_sentence_chars
    assert at.session_state['style_profiles'][0]['decoding']['encoding']=='gb18030'
    assert list((tmp_path/'data').rglob('style_profiles.json'))
    source_bytes[0]=TEXT.encode('utf-8')  # Same filename, a different actual source.
    at.run()
    assert at.selectbox(key='reference_text_encoding').value=='自动确认 UTF-8 或 BOM'
    next(b for b in at.button if b.label=='分析并加入风格库').click().run()
    assert not at.exception and not calls
    assert len(at.session_state['style_profiles'])==2
    assert at.session_state['style_profiles'][1]['decoding']['encoding']=='utf-8'
    previous={p:p.read_bytes() for p in (tmp_path/'data').rglob('*') if p.is_file()}
    source_bytes[0]=b'\x00\x01not plain text'
    at.run()
    next(b for b in at.button if b.label=='分析并加入风格库').click().run()
    assert at.error and not at.exception and not calls
    assert len(at.session_state['style_profiles'])==2
    assert all(p.read_bytes()==raw for p,raw in previous.items())


def test_originality_mixed_pdf_and_gb18030_references_use_explicit_auto_slot(tmp_path):
    from test_reading import make_pdf
    target=tmp_path/'target.txt';target.write_bytes(TEXT.encode())
    pdf=tmp_path/'other.pdf';pdf.write_bytes(make_pdf('A separate original fixture.'))
    ref=tmp_path/'legacy.txt';ref.write_bytes(TEXT.encode('gb18030'))
    out=tmp_path/'review.json'
    r=cli(tmp_path,'check_originality.py','--target',target,'--reference',pdf,'--reference',ref,
          '--reference-encoding','auto','--reference-encoding','gb18030','--output',out)
    assert r.returncode==2, r.stderr
    report=json.loads(out.read_text())
    assert report['input_decoding']['references'][0] is None
    assert report['input_decoding']['references'][1]['encoding']=='gb18030'
