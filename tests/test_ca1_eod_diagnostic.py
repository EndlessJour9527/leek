import copy,json,tempfile,unittest,subprocess,sys
from pathlib import Path
from research.ca1_diagnostics.eod_participation import positive,source_rows,validate_orders,run
class EODChecks(unittest.TestCase):
 def orders(self):
  out=[]
  for cost,counts in [('BASE',[38,1,35]),('DOUBLE',[40,1,36])]:
   for symbol,n in zip(('510300','511010','518880'),counts):
    for i in range(n):out.append(dict(cost=cost,symbol=symbol,side='BUY',status='FILL',notional_cny='100',order_pointer=f'{cost}/{symbol}/{i}'))
   for state,n in [('NO_FILL',2),('NO_ORDER',2 if cost=='BASE' else 1)]:
    for i in range(n):out.append(dict(cost=cost,symbol='510300',side='BUY',status=state,order_pointer=f'{cost}/{state}/{i}'))
  return out
 def test_valid_counts(self):validate_orders(self.orders())
 def test_duplicate_order(self):
  with self.assertRaises(ValueError):validate_orders([self.orders()[0]]*151)
 def test_wrong_cost_coverage(self):
  a=self.orders();a[0]['cost']='DOUBLE'
  with self.assertRaises(ValueError):validate_orders(a)
 def test_number_types(self):
  for v in (True,False,1,None,[],{},'NaN','Infinity','-1','0','1_0',' 10','１０'):
   with self.subTest(v=v),self.assertRaises(ValueError):positive(v)
  self.assertEqual(positive('10.25'),10.25)
 def test_source_identity(self):
  doc=[{'status':0,'code':'cn_510300','hq':[['2026-01-02',0,0,0,0,0,0,0,'100']]}]
  self.assertEqual(len(source_rows(doc,'510300')),1)
  for change in ('code','amount'):
   a=copy.deepcopy(doc)
   if change=='code':a[0]['code']='cn_999999'
   else:a[0]['hq'][0][8]=True
   with self.assertRaises(ValueError):source_rows(a,'510300')
 def test_unpinned_input_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);f=p/'RESULT.json';f.write_text(json.dumps({'orders':self.orders()}))
   with self.assertRaises(ValueError):run(p,p,f)
 def test_optimized_entry_rejected(self):
  r=subprocess.run([sys.executable,'-O','-c',"from research.ca1_diagnostics.eod_participation import run; from pathlib import Path; run(Path('.'),Path('.'),Path('absent'))"],capture_output=True,text=True)
  self.assertNotEqual(r.returncode,0);self.assertIn('INVALID_FROZEN_EOD_INPUT',r.stderr)
