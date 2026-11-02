import ast
import http.client
import io
from contextlib import redirect_stdout
import os
import re
import shutil
import subprocess
import sys
import time
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from research.workbench import app as w

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.app=w.Workbench(self.root/'state')
    def tearDown(self):self.tmp.cleanup()
    def test_empty_first_open(self):
        page=self.app.page()
        self.assertIn('运行合成示例',page);self.assertIn('还没有体验记录',page)
        self.assertIn('等待资料核对',page);self.assertIn('本工作台尚未执行历史收益',page)
        self.assertNotIn(str(w.ROOT),page)
    def test_demo_persistence_and_export_input(self):
        first=self.app.run_demo();before=(self.root/'state/runs'/first/'output/report.json').read_bytes()
        result=self.app.demo(first)
        self.assertEqual(result['status'],'COMPLETED');self.assertEqual(result['report']['currency'],'SIM')
        second=self.app.run_demo();self.assertNotEqual(first,second)
        self.assertEqual(before,(self.root/'state/runs'/first/'output/report.json').read_bytes())
        reopened=w.Workbench(self.root/'state');self.assertIn(first,reopened.page());self.assertIn('合成数据 · 已完成',reopened.page(first))
    def test_failure_preserved_retry_new(self):
        with patch.object(w.replay,'run',side_effect=ValueError('token=PRIVATE_SECRET')):first=self.app.run_demo()
        self.assertEqual(self.app.demo(first)['status'],'FAILED')
        self.assertNotIn('PRIVATE_SECRET',self.app.page(first))
        second=self.app.run_demo();self.assertEqual(self.app.demo(second)['status'],'COMPLETED')
        self.assertTrue((self.root/'state/runs'/first).exists())
    def test_corrupt_result_kept(self):
        ident=self.app.run_demo();p=self.root/'state/runs'/ident/'output/report.json';p.write_text('{bad')
        self.assertEqual(self.app.demo(ident)['status'],'UNREADABLE')
        self.assertIn('重新体验合成示例',self.app.page(ident));self.assertEqual(p.read_text(),'{bad')
    def test_tampered_report_not_completed(self):
        ident=self.app.run_demo();p=self.root/'state/runs'/ident/'output/report.json';r=json.loads(p.read_text());r['daily'][-1]['nav']='123456';p.write_text(json.dumps(r))
        self.assertEqual(self.app.demo(ident)['status'],'UNREADABLE')
    def test_incomplete_run(self):
        p=self.root/'state/runs'/('a'*32);p.mkdir();w.save_new(p/'started.json',{'id':'a'*32,'synthetic':True})
        self.assertEqual(self.app.demo('a'*32)['status'],'UNREADABLE')
    def test_bad_config_and_summary(self):
        with self.assertRaises(ValueError):w.Workbench(self.root/'state',{'broker':'none'})
        original=w.read_json
        def broken(path):
            if path.name=='recent.json':raise ValueError('private path')
            return original(path)
        with patch.object(w,'read_json',side_effect=broken):self.assertIn('摘要暂时无法读取',self.app.page())
    def test_no_implicit_history_run(self):
        with patch.object(w.cli,'run_experiment',side_effect=AssertionError('must not run')):
            self.app.page();self.app.run_demo()
    def test_symlink_and_path_rejected(self):
        with self.assertRaises(ValueError):self.app.demo('../secret')
        target=self.root/'outside';target.mkdir();(self.root/'state/runs'/('b'*32)).symlink_to(target)
        with self.assertRaises(ValueError):self.app.demo('b'*32)
    def test_ready_is_not_execution(self):
        with patch.object(w.cli,'preflight',return_value={'status':'READY_FOR_ARCHIVE_REPLAY'}):
            page=self.app.page();self.assertIn('资料已接入',page);self.assertIn('此工作台不运行历史收益',page)
    def test_preflight_exception_redacted(self):
        with patch.object(w.cli,'preflight',side_effect=OSError('/private/token=SECRET')):
            page=self.app.page();self.assertIn('资料无法读取',page);self.assertNotIn('SECRET',page)

class HTTPTests(unittest.TestCase):
    setUp = WorkbenchTests.setUp
    tearDown = WorkbenchTests.tearDown
    # Integration uses loopback only, no network fixtures or browser dependency.
    def test_http_actions_and_boundaries(self):
        with w.Server(self.app) as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(method,path,body=None,headers=None):
                c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                c.request(method,path,body,headers or {});r=c.getresponse();data=r.read().decode();out=(r.status,dict(r.getheaders()),data);c.close();return out
            try:
                self.assertEqual(server.server_address[0],'127.0.0.1')
                home=request('GET','/');self.assertEqual(home[0],200)
                self.assertEqual(home[1]['Referrer-Policy'],'same-origin')
                self.assertEqual(request('GET','/',headers={'Host':'evil.example'})[0],403)
                self.assertEqual(request('GET','/../../.workbench-config.json')[0],404)
                hdr={'Content-Type':'application/x-www-form-urlencoded','Origin':server.origin}
                self.assertEqual(request('POST','/demo','token=wrong',hdr)[0],403)
                bad=dict(hdr,Origin='https://evil.example')
                self.assertEqual(request('POST','/demo',urlencode({'token':self.app.token}),bad)[0],403)
                self.assertEqual(request('POST','/demo',urlencode({'token':self.app.token}),dict(hdr,Origin='null'))[0],403)
                status,headers,_=request('POST','/demo',urlencode({'token':self.app.token}),hdr)
                self.assertEqual(status,303);location=headers['Location'].split('#')[0]
                self.assertIn('合成数据 · 已完成',request('GET',location)[2])
                export=request('GET',location.replace('/run?','/export?'))
                self.assertEqual(export[0],200);self.assertIs(json.loads(export[2])['synthetic'],True)
                self.assertIn('leek-synthetic-example.json',export[1]['Content-Disposition'])
                self.assertEqual(request('POST','/run-real',urlencode({'token':self.app.token}),hdr)[0],404)
            finally:server.shutdown();thread.join()

class StartupTests(unittest.TestCase):
    def test_browser_dispatch_failure_does_not_abort(self):
        for failure in (False, OSError('secret=not-for-output')):
            out=io.StringIO()
            kwargs={'side_effect': failure} if isinstance(failure,Exception) else {'return_value':failure}
            with patch.object(w.webbrowser,'open',**kwargs),redirect_stdout(out):
                w.open_browser('http://127.0.0.1:12345/')
            self.assertIn('浏览器未自动打开',out.getvalue())
            self.assertIn('http://127.0.0.1:12345/',out.getvalue())
            self.assertNotIn('secret',out.getvalue())

    def test_declared_python_grammar(self):
        # This is syntax validation using the current interpreter, not 3.10/3.11 runtime execution.
        for version in ((3,10),(3,11),(3,12)):
            with self.subTest(grammar=version):
                ast.parse(Path(w.__file__).read_text(), feature_version=version)

    def test_explicit_invalid_config_api(self):
        with tempfile.TemporaryDirectory() as d:
            for config in ([], False, None, 0, 3, '', True):
                with self.subTest(config=repr(config)):
                    state=Path(d)/'should-not-exist'
                    with self.assertRaises(ValueError):w.Workbench(state,config)
                    self.assertFalse(state.exists())

    def test_invalid_config_cli(self):
        with tempfile.TemporaryDirectory() as d:
            for index,text in enumerate(('[]','false','null','0','42','""','true','{bad JSON')):
                with self.subTest(config=text):
                    config=Path(d)/('config'+str(index)+'.json');config.write_text(text)
                    state=Path(d)/('state'+str(index))
                    r=subprocess.run([sys.executable,'-m','research.workbench.app','--config',str(config),'--state-dir',str(state),'--no-browser'],cwd=w.ROOT,capture_output=True,text=True,timeout=8)
                    self.assertEqual(r.returncode,1)
                    self.assertIn('工作台未能启动',r.stderr)
                    self.assertFalse(state.exists())
                    self.assertNotIn(str(config),r.stderr)

    def launch_and_stop(self, command, cwd, state, env=None):
        process=subprocess.Popen(command,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            for _ in range(100):
                if process.poll() is not None:
                    out,err=process.communicate();self.fail('startup exited: '+out+err)
                try:
                    info=json.loads((state/'instance.json').read_text());break
                except (OSError,ValueError):time.sleep(.05)
            else:self.fail('no instance')
            c=http.client.HTTPConnection('127.0.0.1',info['port'],timeout=5)
            c.request('GET','/');r=c.getresponse();body=r.read().decode();self.assertEqual(r.status,200);c.close()
            self.assertIn('运行合成示例',body)
            token=re.search('name="token" value="([^"]+)"',body).group(1)
            c=http.client.HTTPConnection('127.0.0.1',info['port'],timeout=5)
            c.request('POST','/stop',urlencode({'token':token}),{'Content-Type':'application/x-www-form-urlencoded','Origin':'http://127.0.0.1:'+str(info['port'])})
            r=c.getresponse();r.read();self.assertEqual(r.status,200);c.close()
            self.assertEqual(process.wait(timeout=5),0)
            self.assertFalse((state/'instance.json').exists())
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=5)
            process.stdout.close();process.stderr.close()

    def test_empty_object_cli(self):
        with tempfile.TemporaryDirectory() as d:
            config=Path(d)/'empty.json';config.write_text('{}')
            self.launch_and_stop([sys.executable,'-m','research.workbench.app','--config',str(config),'--state-dir',str(Path(d)/'state'),'--no-browser'],w.ROOT,Path(d)/'state')

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS Bash launcher integration')
    def test_launcher_without_config_in_spaced_directory(self):
        with tempfile.TemporaryDirectory(prefix='leek launch space ') as d:
            # Test the exact script with macOS Bash3.2; Python imports unchanged repository via PYTHONPATH.
            target=Path(d)/'打开 Leek.command';shutil.copyfile(w.ROOT/'打开 Leek.command',target)
            state=Path(d)/'state'
            env=dict(os.environ,LEEK_PYTHON=sys.executable,PYTHONPATH=str(w.ROOT))
            self.launch_and_stop(['/bin/bash',str(target),'--state-dir',str(state),'--no-browser'],'/tmp',state,env)

if __name__=='__main__':unittest.main()
