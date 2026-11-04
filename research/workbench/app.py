"""Loopback-only UI; reuses the existing synthetic replay and read-only preflight."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import html
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import threading
from urllib.parse import parse_qs, urlsplit
import uuid
import webbrowser

from leek import replay
from research import cli
from research.workbench import history, history_view

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'examples/fixtures'
ASSETS = Path(__file__).resolve().parent
_UNSET = object()

def validate_config(config):
    if type(config) is not dict:
        raise ValueError('local configuration must be a JSON object')
    if set(config) - {'ca1_private_root', 'h002_data_dir', 'h003_data_dir'}:
        raise ValueError('unknown local configuration key')
    if any(type(v) is not str or not v for v in config.values()):
        raise ValueError('invalid local configuration path')
    return dict(config)

def esc(value):
    return html.escape(str(value), quote=True)

def read_json(path):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out: raise ValueError('duplicate key')
            out[k] = v
        return out
    if path.is_symlink() or path.stat().st_size > 2_000_000: raise ValueError('invalid file')
    return json.loads(path.read_text(), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))

def save_new(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)

def private_dir(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = path.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise ValueError('workbench directory must be owned and private; choose a new directory')

class Workbench:
    def __init__(self, state, config=_UNSET):
        self.config = validate_config({} if config is _UNSET else config)
        self.state = Path(state)
        private_dir(self.state)
        private_dir(self.state / 'runs')
        self.token = secrets.token_urlsafe(32)
        self.instance = secrets.token_hex(16)
        self.busy = threading.Lock()

    def preflights(self):
        rows = []
        for name, title in [('h002', '通道突破研究'), ('h003', '均值回归研究'), ('ca1', '多资产归档研究')]:
            implemented = all((cli.ROOT / p).is_file() for p in cli.EXPERIMENTS[name])
            try:
                report = cli.preflight(name, data_dir=self.config.get(name + '_data_dir'), private_root=self.config.get('ca1_private_root') if name == 'ca1' else None)
                ready = report['status'].startswith('READY_')
                missing, mismatch = report.get('missing', []), report.get('mismatched', [])
                if ready:
                    message = '归档资料已核对，可供另行研究；此工作台不运行历史收益。'
                elif mismatch:
                    message = f'{len(mismatch)} 项资料与登记不一致。请恢复原始版本，不要补造或跳过。'
                elif missing:
                    message = f'此入口尚缺 {len(missing)} 项资料。已有归档可通过本机配置接入，再重新检查。'
                else:
                    message = '当前校验未通过。请查看登记与输入版本；示例体验不受影响。'
                details = dict(status=report['status'], missing=missing, mismatched=mismatch)
            except Exception:
                ready, message, details = False, '资料无法读取或校验。原件未改动；修复本机配置后刷新即可。', {'status': 'INPUT_CHECK_FAILED'}
            rows.append(dict(title=title, implemented=implemented, ready=ready, message=message, details=details))
        return rows

    def run_demo(self):
        if not self.busy.acquire(blocking=False): raise ValueError('demo already running')
        try:
            ident = uuid.uuid4().hex
            dest = self.state / 'runs' / ident
            dest.mkdir(mode=0o700)
            save_new(dest / 'started.json', {'id': ident, 'synthetic': True, 'created_at': datetime.now(timezone.utc).isoformat()})
            try:
                replay.run(FIXTURES / 'replay-config.json', FIXTURES / 'replay-bars.json', dest / 'output')
                os.chmod(dest / 'output', 0o700)
                save_new(dest / 'outcome.json', {'status': 'COMPLETED', 'synthetic': True})
            except Exception:
                # Preserve partial files. Never copy exception messages, paths or secrets to UI.
                save_new(dest / 'outcome.json', {'status': 'FAILED', 'synthetic': True, 'reason': 'SYNTHETIC_REPLAY_FAILED'})
            return ident
        finally:
            self.busy.release()

    def demo(self, ident):
        if len(ident) != 32 or any(c not in '0123456789abcdef' for c in ident): raise ValueError('invalid run ID')
        dest = self.state / 'runs' / ident
        if dest.is_symlink(): raise ValueError('invalid run directory')
        try:
            start = read_json(dest / 'started.json')
            outcome = read_json(dest / 'outcome.json')
            if start.get('id') != ident or start.get('synthetic') is not True or outcome.get('synthetic') is not True: raise ValueError('identity')
            if outcome['status'] != 'COMPLETED': return {'id': ident, 'status': 'FAILED'}
            output = dest / 'output'
            if output.is_symlink(): raise ValueError('invalid output directory')
            report, checkpoint = read_json(output / 'report.json'), read_json(output / 'checkpoint.json')
            if checkpoint['report'] != report or checkpoint['report_sha256'] != replay.digest(replay.canonical(report)): raise ValueError('report integrity')
            binding = report['binding']
            if binding['input_sha256'] != replay.load(FIXTURES / 'replay-bars.json')[1] or binding['config_sha256'] != replay.load(FIXTURES / 'replay-config.json')[1] or binding['source_sha256'] != replay.source_hash(): raise ValueError('version changed')
            if report['currency'] != 'SIM' or report['complete'] is not True or not report['daily']: raise ValueError('not completed synthetic')
            # Validate rendering fields; hashes above are integrity checks, not provenance proof.
            for r in report['daily']:
                for k in ('nav', 'cash', 'total_pnl'): replay.dec(r[k])
            timestamp = datetime.fromisoformat(start['created_at'])
            if timestamp.tzinfo is None: raise ValueError('timestamp timezone')
            return dict(id=ident, status='COMPLETED', created_at=start['created_at'], display_time=timestamp.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'), report=report)
        except Exception:
            return dict(id=ident, status='UNREADABLE')

    def recent(self):
        try:
            data = read_json(ASSETS / 'recent.json')
            if type(data) is not list: raise ValueError('catalog')
            for row in data:
                if set(row) != {'date','title','summary','kind','url'} or any(type(v) is not str for v in row.values()): raise ValueError('catalog')
                if not row['url'].startswith('https://github.com/EndlessJour9527/leek/pull/'): raise ValueError('catalog URL')
            return data
        except Exception:
            return None

    def form(self, route, label, secondary=False):
        return f'<form method="post" action="{route}"><input type="hidden" name="token" value="{self.token}"><button class="{"secondary" if secondary else "primary"}" type="submit">{esc(label)}</button></form>'

    def page(self, ident=None, experiment=None):
        cards = ''
        for r in self.preflights():
            cards += f'<article class="data-card"><h3>{esc(r["title"])}</h3><span class="badge {"good" if r["ready"] else "wait"}">{"资料已接入" if r["ready"] else "等待资料核对"}</span><p>{esc(r["message"])}</p><p class="muted">{"代码已具备" if r["implemented"] else "代码文件缺失，请恢复完整版本"} · 本工作台尚未执行历史收益</p><details><summary>查看具体缺项与校验状态</summary><pre>{esc(json.dumps(r["details"],ensure_ascii=False,indent=2))}</pre></details></article>'
        recent = self.recent()
        research = '<p class="notice">研究摘要暂时无法读取。请恢复随源码提供的摘要文件后刷新；不影响示例体验。</p>' if recent is None else ''.join(f'<article class="research"><div class="eyebrow">{esc(r["date"])} · {esc(r["kind"])}</div><h3>{esc(r["title"])}</h3><p>{esc(r["summary"])}</p><a href="{esc(r["url"])}" target="_blank" rel="noreferrer noopener">查看公开研究 ↗</a></article>' for r in recent)
        demo = ''
        if ident:
            r = self.demo(ident)
            if r['status'] == 'COMPLETED':
                report=r['report']; last=report['daily'][-1]
                table=''.join(f'<tr><td>{esc(d["date"])}</td><td>{esc(d["nav"])}</td><td>{esc(d["cash"])}</td><td>{esc(d["total_pnl"])}</td></tr>' for d in report['daily'])
                demo=f'<section id="result" class="panel result"><div class="eyebrow">合成数据 · 已完成 · {esc(r["display_time"])}</div><h2>你已完成一次模拟研究</h2><p>使用仓库内置的虚构行情，收盘产生信号，下一列明交易日按开盘模型执行。未读取真实资产。</p><div class="metrics"><div><small>期末模拟资产</small><strong>{esc(last["nav"])} <em>SIM</em></strong></div><div><small>合成交易日</small><strong>{report["processed_sessions"]}</strong></div><div><small>模型执行尝试</small><strong>{len(report["orders"])}</strong></div></div><p class="notice">数字只用于理解流程，不能代表历史收益或未来盈利。示例不支持公司行动、真实流动性或交易所限价。</p><details><summary>展开每日结果与验证信息</summary><div class="scroll"><table><thead><tr><th>合成日期</th><th>模拟资产</th><th>现金</th><th>模拟损益</th></tr></thead><tbody>{table}</tbody></table></div><pre>{esc(json.dumps(report["binding"],indent=2))}</pre></details><p><a href="/export?id={esc(ident)}">导出本次合成示例结果（JSON）</a></p></section>'
            else:
                demo='<section id="result" class="panel"><h2>这次示例未能完整读取</h2><p>可能运行中断、输出损坏或源码版本已变化。原记录保留，不会自动补数。可以重新运行一个独立示例。</p>'+self.form('/demo','重新体验合成示例')+'</section>'
        history=[]
        for p in (self.state/'runs').iterdir():
            if p.is_dir() and not p.is_symlink() and len(p.name)==32 and all(c in '0123456789abcdef' for c in p.name): history.append(p)
        history.sort(key=lambda p:p.stat().st_mtime, reverse=True)
        links=''.join(f'<li><a href="/run?id={p.name}#result">合成体验 {len(history)-i} · {esc(self.demo(p.name)["status"].replace("COMPLETED","已完成").replace("UNREADABLE","需检查").replace("FAILED","未完成"))}</a></li>' for i,p in enumerate(history[:10])) or '<li>还没有体验记录。点击上方按钮即可开始。</li>'
        template=(ASSETS/'index.html').read_text()
        archived = history_view.render(experiment) if experiment else ''
        return template.replace('@@EXPERIMENTS@@',history_view.catalog()).replace('@@EXPERIMENT@@',archived).replace('@@DEMO_BUTTON@@',self.form('/demo','运行合成示例 →')).replace('@@RESULT@@',demo).replace('@@RESEARCH@@',research).replace('@@DATA@@',cards).replace('@@HISTORY@@',links).replace('@@STOP@@',self.form('/stop','退出工作台',True))

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self, app, port=0):
        self.app=app
        super().__init__(('127.0.0.1', port), Handler)
        self.origin='http://127.0.0.1:'+str(self.server_port)

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)
    def log_message(self, *args): pass
    def send(self, status, body, content_type='text/html; charset=utf-8', location=None, attachment=None):
        data=body.encode()
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.send_header('Referrer-Policy','same-origin')
        if location:self.send_header('Location',location)
        if attachment:self.send_header('Content-Disposition','attachment; filename="'+attachment+'"')
        self.end_headers();self.wfile.write(data)
    def trusted_host(self):
        return self.headers.get('Host') == self.server.origin.removeprefix('http://')
    def do_GET(self):
        if not self.trusted_host():self.send(403,'只接受本机入口');return
        parsed=urlsplit(self.path)
        try:
            if parsed.path=='/health':self.send(200,json.dumps({'instance':self.server.app.instance}), 'application/json');return
            if parsed.path=='/export':
                ident=parse_qs(parsed.query).get('id',[''])[0]
                result=self.server.app.demo(ident)
                if result['status']!='COMPLETED':raise ValueError('export unavailable')
                self.send(200,json.dumps(dict(synthetic=True,label='合成示例；不是历史收益或真实账户',created_at=result['created_at'],report=result['report']),ensure_ascii=False,indent=2),'application/json; charset=utf-8',attachment='leek-synthetic-example.json');return
            if parsed.path in ('/experiment', '/experiment-export'):
                query=parse_qs(parsed.query, keep_blank_values=True)
                if query!={'id':['ca1']}:raise ValueError('unknown experiment')
                if parsed.path=='/experiment-export':
                    result=history.load_experiment('ca1')
                    self.send(200,json.dumps(result,ensure_ascii=False,indent=2),'application/json; charset=utf-8',attachment='leek-ca1-public-archive.json');return
                self.send(200,self.server.app.page(experiment='ca1'));return
            if parsed.path=='/style.css':self.send(200,(ASSETS/'style.css').read_text(),'text/css');return
            if parsed.path not in ('/','/run'):self.send(404,'未找到页面。<a href="/">返回工作台</a>');return
            ident=parse_qs(parsed.query).get('id',[None])[0] if parsed.path=='/run' else None
            if parsed.path=='/run' and ident is None:raise ValueError('missing run')
            self.send(200,self.server.app.page(ident))
        except Exception:
            self.send(400,'页面资料无法读取，原记录未改动。<a href="/">返回工作台重新尝试</a>')
    def do_POST(self):
        if not self.trusted_host() or self.headers.get('Origin') not in (None,self.server.origin):self.send(403,'请求来源不匹配');return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=4096 or self.headers.get('Content-Type','').split(';')[0]!='application/x-www-form-urlencoded':raise ValueError('body')
            form=parse_qs(self.rfile.read(size).decode(),strict_parsing=True)
            if set(form)!={'token'} or form['token']!=[self.server.app.token]:self.send(403,'请刷新工作台后重试');return
            if self.path=='/demo':
                ident=self.server.app.run_demo();self.send(303,'',location='/run?id='+ident+'#result')
            elif self.path=='/stop':
                self.send(200,'<meta charset="utf-8"><h1>工作台已退出</h1><p>研究记录已保留。下次双击启动文件即可重新打开。</p>')
                threading.Thread(target=self.server.shutdown,daemon=True).start()
            else:self.send(404,'没有此操作')
        except Exception:
            self.send(400,'本次操作未能完成，已有记录保留。<a href="/">返回后重新体验</a>')

def existing_url(state):
    info=read_json(state/'instance.json')
    port=info['port']
    if type(port) is not int or not 1<=port<=65535:raise ValueError('port')
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
    try:
        conn.request('GET','/health');response=conn.getresponse();data=json.loads(response.read(4096))
        if response.status!=200 or data!={'instance':info['instance']}:raise ValueError('instance mismatch')
    finally:conn.close()
    return 'http://127.0.0.1:'+str(port)+'/'

def open_browser(url):
    # A GUI dispatch acknowledgement is not proof that a window became visible.
    try:
        requested = webbrowser.open(url)
    except Exception:
        requested = False
    label = '已请求浏览器打开；若未出现页面，请打开：' if requested else '浏览器未自动打开；请打开：'
    print(label + url, flush=True)

def main(argv=None):
    parser=argparse.ArgumentParser(description='Leek 本机研究工作台：只读研究 + 合成示例')
    parser.add_argument('--state-dir',type=Path,default=ROOT/'.workbench')
    parser.add_argument('--config',type=Path)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args(argv)
    # Explicit null/false/list is invalid, not an omitted configuration.
    config=validate_config(read_json(args.config) if args.config else {})
    private_dir(args.state_dir)
    lockpath=args.state_dir/'instance.lock'
    fd=os.open(lockpath,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'r+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            try:url=existing_url(args.state_dir)
            except Exception:
                print('已有实例尚未就绪或状态异常。请稍后重新打开，或关闭原工作台终端。未启动第二实例。');return 2
            print('复用已打开的工作台：'+url)
            if not args.no_browser:open_browser(url)
            return 0
        app=Workbench(args.state_dir,config)
        with Server(app) as server:
            info=args.state_dir/'instance.json'
            # Lock ownership allows replacing only this disposable instance pointer.
            if info.exists() or info.is_symlink():info.unlink()
            save_new(info,{'port':server.server_port,'instance':app.instance})
            url=server.origin+'/'
            print('Leek 已启动：'+url+'  仅本机访问；关闭此终端或点击网页退出即可停止。',flush=True)
            if not args.no_browser:open_browser(url)
            try:server.serve_forever(poll_interval=.2)
            except KeyboardInterrupt:pass
            finally:
                info.unlink(missing_ok=True)
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        print('工作台未能启动。请检查本机配置与目录权限；已有研究记录未覆盖。',file=sys.stderr)
        raise SystemExit(1)
