"""Bounded public-feed availability/schema probe; no trading or dataset publication."""
import hashlib
import json
from urllib.request import Request, urlopen


def main():
    urls = {
        'tencent_raw_2020': 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh510300,day,2020-01-01,2020-12-31,640,',
        'eastmoney_raw': 'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.510300&klt=101&fqt=0&beg=20190101&end=20251231&lmt=10000&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
        'eastmoney_dividends': 'https://fundf10.eastmoney.com/fhsp_510300.html',
    }
    for name, url in urls.items():
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'})
            with urlopen(req, timeout=20) as response:
                raw = response.read(5000001)
            if len(raw) > 5000000:
                raise ValueError('response too large')
            result = dict(feed=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            if name.startswith('tencent'):
                item = json.loads(raw)['data']['sh510300']
                bars = item.get('day', [])
                result.update(keys=list(item), rows=len(bars), first_date=bars[0][0] if bars else None,
                              last_date=bars[-1][0] if bars else None, row_width=len(bars[0]) if bars else 0)
            elif name == 'eastmoney_raw':
                item = json.loads(raw).get('data') or {}
                bars = item.get('klines', [])
                result.update(keys=list(item), rows=len(bars), first_date=bars[0].split(',')[0] if bars else None,
                              last_date=bars[-1].split(',')[0] if bars else None)
            else:
                from html.parser import HTMLParser
                class Table(HTMLParser):
                    def __init__(self):
                        super().__init__(); self.capture=False; self.rows=[]; self.row=[]; self.cell=''
                    def handle_starttag(self, tag, attrs):
                        if tag=='tr': self.row=[]
                        if tag in ('td','th'): self.capture=True; self.cell=''
                    def handle_data(self, data):
                        if self.capture: self.cell+=data.strip()
                    def handle_endtag(self, tag):
                        if tag in ('td','th'): self.row.append(self.cell); self.capture=False
                        if tag=='tr' and self.row: self.rows.append(self.row)
                parser=Table(); parser.feed(raw.decode('utf-8', errors='replace'))
                result['distribution_rows']=[r for r in parser.rows if any('2025' in v or '2024' in v or '2023' in v or '2022' in v or '2021' in v or '2020' in v or '2019' in v for v in r) and len(r)<12]
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        except Exception as exc:
            print(json.dumps({'feed': name, 'status': 'UNAVAILABLE', 'reason': type(exc).__name__+': '+str(exc)}))

if __name__ == '__main__':
    main()
