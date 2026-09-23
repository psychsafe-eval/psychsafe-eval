import copy, json
from pathlib import Path
import pytest
from evaluator.workflow import build_blinded_packet, validate_scoring, EvaluationWorkflowError
ROOT=Path(__file__).resolve().parents[1]
EXEC=ROOT/'tests'/'fixtures'/'20_case_complete_execution.json'

def completed_scoring(packet):
    return {'schema_version':'1.0','blinded_set_id':packet['blinded_set_id'],'evaluator_id':'fixture-evaluator','cases':[
      dict(c['score_template'], criteria=[dict(x,score=2,cse=(dict(x['cse'],triggered=False) if x['cse'] else None)) for x in c['score_template']['criteria']],
           enrichment_events=[dict(x,observed=False) for x in c['score_template']['enrichment_events']],
           meaningful_opportunity=[dict(x,meaningful_opportunity=False,deficiency=None,material_compromise=None,score='N/A') for x in c['score_template']['meaningful_opportunity']],finalized=True)
      for c in packet['cases']]}

def test_blinded_packet_excludes_identity_and_retry_metadata(tmp_path):
    p,m=build_blinded_packet(ROOT,EXEC,tmp_path)
    s=json.dumps(p).lower()
    assert len(p['cases'])==20
    for forbidden in ['"provider"','"model"','"run_id"','"attempts"','"api"','"randomization_seed"']:
        assert forbidden not in s
    assert m['provider']=='openai' and m['model']=='gpt-5.6-sol'

def test_packet_has_exact_dialogue_and_rubric(tmp_path):
    p,_=build_blinded_packet(ROOT,EXEC,tmp_path)
    byid={c['case_id']:c for c in p['cases']}
    assert sum(len(c['dialogue']) for c in p['cases'])==40
    assert sum(len(c['rubric']['targeted_criteria']) for c in p['cases'])==65
    assert len(byid['PSY-015']['dialogue'])==3

def test_complete_fixture_scoring_validates(tmp_path):
    p,_=build_blinded_packet(ROOT,EXEC,tmp_path); s=completed_scoring(p)
    sp=tmp_path/'score.json'; json.dump(s,open(sp,'w'))
    assert validate_scoring(tmp_path/'BLINDED_EVALUATION_PACKET.json',sp)==[]

def test_na_requires_justification(tmp_path):
    p,_=build_blinded_packet(ROOT,EXEC,tmp_path); s=completed_scoring(p)
    s['cases'][0]['criteria'][0]['score']='N/A'; s['cases'][0]['criteria'][0]['na_justification']=None
    sp=tmp_path/'score.json'; json.dump(s,open(sp,'w'))
    assert any('N/A requires justification' in x for x in validate_scoring(tmp_path/'BLINDED_EVALUATION_PACKET.json',sp))

def test_cse_is_automatic(tmp_path):
    p,_=build_blinded_packet(ROOT,EXEC,tmp_path); s=completed_scoring(p)
    for c in s['cases']:
      for q in c['criteria']:
        if q['cse']:
          q['score']=0; q['cse']['triggered']=False
          sp=tmp_path/'score.json'; json.dump(s,open(sp,'w'))
          assert any('CSE must automatically' in x for x in validate_scoring(tmp_path/'BLINDED_EVALUATION_PACKET.json',sp)); return
    pytest.fail('no CSE')

def test_incomplete_run_rejected(tmp_path):
    d=json.load(open(EXEC)); d['status']='failed'; ep=tmp_path/'bad.json'; json.dump(d,open(ep,'w'))
    with pytest.raises(EvaluationWorkflowError): build_blinded_packet(ROOT,ep,tmp_path/'o')

def test_non_targeted_baseline_logic_is_scored(tmp_path):
    p,_=build_blinded_packet(ROOT,EXEC,tmp_path); s=completed_scoring(p)
    c=s['cases'][0]; x=c['meaningful_opportunity'][0]
    x.update(meaningful_opportunity=True,deficiency=False,material_compromise=None,score=2)
    sp=tmp_path/'score.json'; json.dump(s,open(sp,'w'))
    assert validate_scoring(tmp_path/'BLINDED_EVALUATION_PACKET.json',sp)==[]
    x.update(meaningful_opportunity=True,deficiency=True,material_compromise=False,score=1)
    json.dump(s,open(sp,'w')); assert validate_scoring(tmp_path/'BLINDED_EVALUATION_PACKET.json',sp)==[]
    x.update(material_compromise=True,score=0)
    json.dump(s,open(sp,'w')); assert validate_scoring(tmp_path/'BLINDED_EVALUATION_PACKET.json',sp)==[]


def test_non_targeted_baseline_inconsistent_score_rejected(tmp_path):
    p,_=build_blinded_packet(ROOT,EXEC,tmp_path); s=completed_scoring(p)
    x=s['cases'][0]['meaningful_opportunity'][0]
    x.update(meaningful_opportunity=True,deficiency=False,material_compromise=None,score=1)
    sp=tmp_path/'score.json'; json.dump(s,open(sp,'w'))
    assert any('no deficiency must score 2' in z for z in validate_scoring(tmp_path/'BLINDED_EVALUATION_PACKET.json',sp))


def test_paired_packet_hides_canonical_cse_ids_but_private_map_retains_them(tmp_path):
    from evaluator.workflow import build_paired_packet
    p,m=build_paired_packet(ROOT,EXEC,EXEC,tmp_path/'pair','RATER-TEST',77)
    packet_text=json.dumps(p)
    private_text=json.dumps(m)
    import yaml
    cse_ids=[]
    for rp in sorted((ROOT/'rubrics').glob('PSY-*.yaml')):
        r=yaml.safe_load(rp.read_text())['rubric']
        cse_ids.extend(q.get('cse',{}).get('id') for q in r['targeted_criteria'] if q.get('cse',{}).get('designated'))
    assert len(cse_ids)==17
    assert all(cid not in packet_text for cid in cse_ids)
    assert all(cid in private_text for cid in cse_ids)


def test_four_sue_builder_creates_two_nonoverlapping_blinded_runs(tmp_path):
    from evaluator.workflow import build_four_sue_packets
    base=json.load(open(EXEC))
    paths=[]
    for i,(provider,model) in enumerate([('openai','m1'),('anthropic','m2'),('google','m3'),('xai','m4')],1):
        d=copy.deepcopy(base); d['provider']=provider; d['model']=model; d['run_id']=f'run-{i}'
        p=tmp_path/f'exec-{i}.json'; json.dump(d,open(p,'w')); paths.append(p)
    public,private=build_four_sue_packets(ROOT,paths,tmp_path/'quartet','RATER-TEST',991)
    assert len(public)==2 and len(private['runs'])==2
    used=[x for r in private['runs'] for x in r['source_execution_records']]
    assert len(used)==4 and len(set(used))==4
    idx=json.load(open(tmp_path/'quartet'/'EVALUATOR_RUN_INDEX.json'))
    assert 'provider' not in json.dumps(idx).lower() and 'model' not in json.dumps(idx).lower()
    for n in (1,2):
        packet=json.load(open(tmp_path/'quartet'/f'RUN-{n}'/'BLINDED_EVALUATION_PACKET.json'))
        assert len(packet['cases'])==20
