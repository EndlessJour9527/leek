import unittest,tempfile,json,subprocess,sys,copy
from pathlib import Path
from decimal import Decimal as D
from research.affordability_511010.analyze import parse,cash,number,analyze,EXPECTED_PINS,validate_sources
CASE={'commission_rate':'0.0002','minimum_commission':'5','slippage_bps':'5'}
class Tests(unittest.TestCase):
 def test_minimum_cash(self):self.assertEqual(cash(D('124.395'),CASE),(D('124.458'),D('5.00'),D('12450.800')))
 def test_ceiling_tick(self):self.assertEqual(cash(D('100.001'),CASE)[0],D('100.052'))
 def test_bad_numbers(self):
  for v in (True,'NaN','Infinity','0','-1',' 1','1_0'):
   with self.subTest(v=v),self.assertRaises(ValueError):number(v)
 def test_duplicate(self):
  row=['2021-10-18','2','3','1','2']
  with self.assertRaises(ValueError):parse([row,row],(1,2,3,4))
 def test_2026_excluded(self):
  a=parse([['2025-12-31','2','3','1','2'],['2026-01-05','1','1','1','1']],(1,2,3,4));self.assertEqual(list(a),['2025-12-31'])
 def test_no_rows_rejected(self):
  with self.assertRaises(ValueError):parse([],(1,2,3,4))
 def test_tamper_before_parse(self):
  import json
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'INPUT_PINS.json').write_text(json.dumps({'raw.bin':'0'*64}));(p/'raw.bin').write_text('{}')
   with self.assertRaises(ValueError):analyze(p,p)

 def test_pin_set_cannot_be_changed(self):
  variants=[{},dict(list(EXPECTED_PINS.items())[:-1]),{**EXPECTED_PINS,'extra':'0'*64},{**EXPECTED_PINS,'raw/511010_sohu.bin':'0'*64},{**EXPECTED_PINS,'raw/511010_sohu.bin':True}]
  for pins in variants:
   with self.subTest(pins=pins),tempfile.TemporaryDirectory() as d:
    p=Path(d);(p/'INPUT_PINS.json').write_text(json.dumps(pins))
    with self.assertRaises(ValueError):analyze(p,p)
 def test_bound_body_hash_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'INPUT_PINS.json').write_text(json.dumps(EXPECTED_PINS));(p/'raw').mkdir();(p/'raw/511010_sohu.bin').write_text('{}')
   with self.assertRaises(ValueError):analyze(p,p)
 def test_boolean_source_status_rejected(self):
  s=[{'code':'cn_511010','status':0}];t={'code':0,'data':{'sh511010':{}}};validate_sources(s,t)
  for value in (False,True,'0',None):
   with self.subTest(value=value):
    a=copy.deepcopy(s);a[0]['status']=value
    with self.assertRaises(ValueError):validate_sources(a,t)
    b=copy.deepcopy(t);b['code']=value
    with self.assertRaises(ValueError):validate_sources(s,b)
 def test_wrong_security(self):
  with self.assertRaises(ValueError):validate_sources([{'code':'cn_999999','status':0}],{'code':0,'data':{'sh511010':{}}})
 def test_nonfinite_cash_input(self):
  for value in (D('NaN'),D('Infinity'),True):
   with self.assertRaises(ValueError):cash(value,CASE)
 def test_optimized_rejected(self):
  command="from research.affordability_511010.analyze import analyze; from pathlib import Path; analyze(Path('absent'),Path('absent'))"
  r=subprocess.run([sys.executable,'-O','-c',command],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
  self.assertNotEqual(r.returncode,0);self.assertIn('INVALID_FROZEN_AFFORDABILITY_INPUT',r.stderr)
