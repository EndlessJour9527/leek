import json,tempfile,unittest,subprocess,sys
from pathlib import Path
from research.margin_20261030.analyze import analyze
class Checks(unittest.TestCase):
 def fixture(self,p):
  days=['2025-10-29','2025-10-30','2025-10-31','2025-11-03'];values=[100,110,90,90]
  rows=[dict(DIM_DATE=d,XOB_MARKET_0001=m,RZYE=v) for d,v in zip(days,values) for m in ('融资融券_沪证','融资融券_深证')]
  rows += [dict(DIM_DATE=d,XOB_MARKET_0001='融资融券_北证',RZYE=999999) for d in days]
  for name,data in [('margin.raw',rows),('margin_page2.raw',[])]: (p/name).write_text(json.dumps({'success':True,'result':{'data':data}}))
  for name,code in [('SSEC','000001'),('CSI300','000300'),('CHINEXT','399006')]: (p/(name+'.raw')).write_text(json.dumps({'data':{'code':code,'klines':[d+',0,'+str(v) for d,v in zip(days,values)]}}))
 def test_formula_groups_lags_and_privacy(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);self.fixture(p);r=analyze(p)
   self.assertEqual(r['n'],3);self.assertAlmostEqual(r['results']['SSEC']['same']['pearson'],1);self.assertEqual(r['results']['SSEC']['next']['n'],2)
   self.assertEqual([g['n'] for g in r['results']['SSEC']['same']['groups'].values()],[1,1,1]);self.assertFalse(r['publication_timestamps_verified']);self.assertNotIn('today_latest_financing',r);self.assertFalse((p/'aligned.json').exists())
 def test_conflicting_duplicate_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);self.fixture(p);row=json.loads((p/'margin.raw').read_text())['result']['data'][0];row['RZYE']=1;(p/'margin_page2.raw').write_text(json.dumps({'success':True,'result':{'data':[row]}}))
   with self.assertRaises(ValueError):analyze(p)
 def test_missing_market_not_zero(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);self.fixture(p);f=p/'margin.raw';a=json.loads(f.read_text());a['result']['data']=[r for r in a['result']['data'] if not(r['DIM_DATE']=='2025-10-30' and r['XOB_MARKET_0001']=='融资融券_深证')];f.write_text(json.dumps(a));r=analyze(p)
   self.assertEqual(r['missing_financing_dates'],['2025-10-30','2025-10-31']);self.assertEqual(r['n'],1)
 def test_wrong_index(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);self.fixture(p);f=p/'SSEC.raw';a=json.loads(f.read_text());a['data']['code']='bad';f.write_text(json.dumps(a))
   with self.assertRaises(ValueError):analyze(p)

 def test_invalid_balances(self):
  for value in ('NaN','Infinity',-1,0,True,None,{},[]):
   with self.subTest(value=value),tempfile.TemporaryDirectory() as d:
    p=Path(d);self.fixture(p);f=p/'margin.raw';a=json.loads(f.read_text());a['result']['data'][0]['RZYE']=value;f.write_text(json.dumps(a))
    with self.assertRaises(ValueError):analyze(p)
 def test_invalid_index_prices(self):
  for value in ('NaN','Infinity','-1','0'):
   with self.subTest(value=value),tempfile.TemporaryDirectory() as d:
    p=Path(d);self.fixture(p);f=p/'SSEC.raw';a=json.loads(f.read_text());a['data']['klines'][0]='2025-10-29,0,'+value;f.write_text(json.dumps(a))
    with self.assertRaises(ValueError):analyze(p)
 def test_empty_samples(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);self.fixture(p)
   for name in ('margin.raw','margin_page2.raw'):(p/name).write_text(json.dumps({'success':True,'result':{'data':[]}}))
   r=analyze(p);self.assertEqual(r['n'],0);self.assertIsNone(r['start']);self.assertIsNone(r['results']['SSEC']['same']['pearson']);self.assertEqual(r['status'],'NO_PAIRED_SAMPLES_NOT_TRADABLE')
 def test_optimized_rejected(self):
  r=subprocess.run([sys.executable,'-O','-c',"from research.margin_20261030.analyze import analyze; analyze('absent')"],capture_output=True,text=True)
  self.assertNotEqual(r.returncode,0);self.assertIn('INVALID_MARGIN_INPUT',r.stderr)
