from pathlib import Path
import json
from evaluator.workflow import build_paired_packet
from evaluator.interface import render_interface
ROOT=Path(__file__).resolve().parents[1]
EXEC=ROOT/'tests'/'fixtures'/'20_case_complete_execution.json'
def test_paired_interface_renders(tmp_path):
    p,m=build_paired_packet(ROOT,EXEC,EXEC,tmp_path,'RATER-TEST',1203)
    assert p['schema_version']=='2.0' and len(p['cases'])==20
    assert all(len(c['responses'])==2 for c in p['cases'])
    assert all('case_id' not in c and 'title' not in c for c in p['cases'])
    out=render_interface(tmp_path/'BLINDED_EVALUATION_PACKET.json',tmp_path/'EVALUATOR_INTERFACE.html')
    text=out.read_text(encoding='utf-8')
    for phrase in ['Model A','Model B','Saved locally','Next case','Review & Complete','N/A is an exceptional override','Meaningful Opportunity','Drag to resize panes']:
        assert phrase in text
    assert 'Export scoring JSON' not in text and 'Evaluator ID <input' not in text and 'BLINDING_MAP' not in text

def test_pairing_seed_is_reproducible(tmp_path):
    p1,m1=build_paired_packet(ROOT,EXEC,EXEC,tmp_path/'a','RATER-TEST',77)
    p2,m2=build_paired_packet(ROOT,EXEC,EXEC,tmp_path/'b','RATER-TEST',77)
    assert [x['case_id'] for x in m1['case_mapping']]==[x['case_id'] for x in m2['case_mapping']]
    assert [[r['source_run_id'] for r in x['responses']] for x in m1['case_mapping']]==[[r['source_run_id'] for r in x['responses']] for x in m2['case_mapping']]

def test_private_map_contains_identity_but_packet_does_not(tmp_path):
    p,m=build_paired_packet(ROOT,EXEC,EXEC,tmp_path,'RATER-TEST',77)
    assert any(x['case_id'].startswith('PSY-') for x in m['case_mapping'])
    assert 'PSY-013' not in json.dumps(p)

def test_renderer_uses_nested_canonical_anchor_fields(tmp_path):
    build_paired_packet(ROOT,EXEC,EXEC,tmp_path,'RATER-TEST',1203)
    out=render_interface(tmp_path/'BLINDED_EVALUATION_PACKET.json',tmp_path/'EVALUATOR_INTERFACE.html')
    text=out.read_text(encoding='utf-8')
    assert 'anchors.concise||{}' in text
    assert 'anchors.full||{}' in text
    assert 'More detail' in text
    assert "anchors[String(val)]||anchors[val]||{}" not in text
    assert 'JSON.stringify(a)' not in text


def test_renderer_uses_human_facing_enrichment_event_description(tmp_path):
    build_paired_packet(ROOT,EXEC,EXEC,tmp_path,'RATER-TEST',1203)
    out=render_interface(tmp_path/'BLINDED_EVALUATION_PACKET.json',tmp_path/'EVALUATOR_INTERFACE.html')
    text=out.read_text(encoding='utf-8')
    assert 'e.trigger_description||e.canonical_wording||e.event||e.description||e.criterion' in text
    assert 'JSON.stringify(e)' not in text


def test_renderer_preserves_ordered_list_across_blank_markdown_lines(tmp_path):
    build_paired_packet(ROOT,EXEC,EXEC,tmp_path,'RATER-TEST',1203)
    out=render_interface(tmp_path/'BLINDED_EVALUATION_PACKET.json',tmp_path/'EVALUATOR_INTERFACE.html')
    text=out.read_text(encoding='utf-8')
    assert "if(!l.trim()){if(list)pendingBlank=true;continue}" in text
    assert "out.push('<ol>');list='ol'" in text

def test_model_switch_is_compact_and_sticky(tmp_path):
    build_paired_packet(ROOT,EXEC,EXEC,tmp_path,'RATER-TEST',1203)
    out=render_interface(tmp_path/'BLINDED_EVALUATION_PACKET.json',tmp_path/'EVALUATOR_INTERFACE.html')
    text=out.read_text(encoding='utf-8')
    assert '.model-switch{display:flex;align-items:center;justify-content:center;gap:6px;margin:0 0 14px;padding:5px 0 7px;position:sticky' in text
    assert '.model-switch button{padding:5px 9px;line-height:1.2}' in text

def test_targeted_criteria_render_in_canonical_rubric_order(tmp_path):
    build_paired_packet(ROOT,EXEC,EXEC,tmp_path,'RATER-TEST',1203)
    out=render_interface(tmp_path/'BLINDED_EVALUATION_PACKET.json',tmp_path/'EVALUATOR_INTERFACE.html')
    text=out.read_text(encoding='utf-8')
    assert "let qs=c.rubric.targeted_criteria;for(let i=0;i<qs.length;i++)" in text
    assert "for(const d of DIMS){let qs=c.rubric.targeted_criteria.filter" not in text


def test_scoring_horizon_instruction_preserves_full_trajectory_context(tmp_path):
    build_paired_packet(ROOT,EXEC,EXEC,tmp_path,'RATER-TEST',1203)
    out=render_interface(tmp_path/'BLINDED_EVALUATION_PACKET.json',tmp_path/'EVALUATOR_INTERFACE.html')
    text=out.read_text(encoding='utf-8')
    assert 'Scoring horizon: through' in text
    assert 'Later turns remain visible for longitudinal context and must not be treated as information the model should have known at this point.' in text
