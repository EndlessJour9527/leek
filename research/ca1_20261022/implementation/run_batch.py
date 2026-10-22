"""Strict release-bound, immutable output runner. Never runs on import."""
from ca1 import *
import argparse
ROOT=Path(__file__).resolve().parent

def run(output,release):
 manifest=ROOT/'IMPLEMENTATION_MANIFEST.json'; certificate=json.loads(Path(release).read_text())
 if certificate.get('status')!='RUN_RELEASE' or certificate.get('manifest_sha256')!=sha(manifest): raise ValueError('NO_MATCHING_INDEPENDENT_RUN_RELEASE')
 for rel,expected in json.loads(manifest.read_text()).items():
  if sha(ROOT/rel)!=expected: raise ValueError('IMPLEMENTATION_INPUT_HASH_CHANGED:'+rel)
 data=json.loads((ROOT/'INPUTS.json').read_text()); output=Path(output); output.mkdir(exist_ok=False)
 summaries={}
 for account in ('CA1','SCASH','BH300','CASH'):
  for multiple in (1,2):
   key=account+('_BASE' if multiple==1 else '_DOUBLE'); report=replay(data,account,multiple)
   dump(output/(key+'.json'),report); summaries[key]=summarize(report)
   dump(output/(key+'_research_cost.json'),subscription(report['daily']))
   if multiple==1: dump(output/(key+'_fixed_fill_double.json'),fixed_fill_double(report))
 dump(output/'SUMMARY.json',summaries); dump(output/'DECISION.json',economics(summaries))
 dump(output/'REPRODUCIBILITY.json',dict(manifest_sha256=sha(manifest),release_sha256=sha(release),command='python run_batch.py --release RUN_RELEASE.json --output RESULTS',data_use='ALL_SEEN_DEVELOPMENT',real_execution='NOT_CERTIFIED'))
 dump(output/'RESULT_HASHES.json',{p.name:sha(p) for p in sorted(output.glob('*.json'))})
 print(json.dumps(economics(summaries),indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--release',required=True);p.add_argument('--output',required=True);a=p.parse_args();run(a.output,a.release)
