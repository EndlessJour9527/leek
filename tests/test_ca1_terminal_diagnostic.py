import unittest,copy,tempfile
from decimal import Decimal as D
from pathlib import Path
from research.ca1_diagnostics.terminal_stress import mark,analyze
class Checks(unittest.TestCase):
 def row(self):return dict(cash='40',receivable='10',nav='100',positions={s:dict(quantity=1,close=v,value=v) for s,v in [('510300','20'),('511010','10'),('518880','20')]})
 def test_zero(self):self.assertEqual(D(mark(self.row(),{})['stressed_nav']),100)
 def test_linear(self):
  a=D(mark(self.row(),{'518880':D('-.1')})['loss_cny']);b=D(mark(self.row(),{'518880':D('-.2')})['loss_cny']);self.assertEqual(2*a,b)
 def test_joint_conserves_cash_and_receivable(self):self.assertEqual(D(mark(self.row(),{s:D('-1') for s in self.row()['positions']})['stressed_nav']),50)
 def test_wrong_units_reject(self):
  row=self.row();row['positions']['511010']['quantity']=10
  with self.assertRaises(ValueError):mark(row,{})
 def test_nan_reject(self):
  row=self.row();row['cash']='NaN'
  with self.assertRaises(ValueError):mark(row,{})
 def test_tampered_bytes_before_parsing(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'x').write_text('{}')
   with self.assertRaises(ValueError):analyze(p,{'x':'0'*64})
if __name__=='__main__':unittest.main()
