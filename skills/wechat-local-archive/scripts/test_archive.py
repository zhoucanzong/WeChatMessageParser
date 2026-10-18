"""Synthetic-only tests. No user database, process, network, or keychain access."""
import argparse
import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import wave
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from archive import export, resolve, snapshot, verify, write_new
from render_html import render
from audit_html import audit
from message_formats import parse_detail
from package_skill import validate


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def document(self):
        Image.new('RGB',(2,3),'green').save(self.root/'test.png')
        with wave.open(str(self.root/'test.wav'),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*1600)
        doc={'title':'Demo <script>alert(1)</script>','coverage':{'exported_rows':1},'messages':[
            {'time':'2024-01-01T00:00:00Z','sender':'演示联系人','text':'<img src="https://example.invalid/">',
             'status':'parsed','assets':[{'kind':'image','path':'test.png'},{'kind':'audio','path':'test.wav'}]}]}
        (self.root/'archive.json').write_text(json.dumps(doc));return self.root/'archive.json'
    def test_embedded_media_and_escaping(self):
        source=self.document();out=self.root/'chat.html';render(source,self.root,out)
        result=audit(out,1);self.assertTrue(result['ok']);self.assertEqual((result['images'],result['audio']),(1,1))
        self.assertIn('&lt;script&gt;',out.read_text());self.assertNotIn('<script>',out.read_text())
        self.assertFalse(audit(out,2)['ok'])
    def test_path_escape_and_symlink_rejected(self):
        source=self.document();doc=json.loads(source.read_text())
        with tempfile.TemporaryDirectory() as outside:
            p=Path(outside)/'photo.png';Image.new('RGB',(1,1)).save(p)
            (self.root/'link.png').symlink_to(p)
            for value in [str(p),'link.png']:
                doc['messages'][0]['assets']=[{'kind':'image','path':value}];source.write_text(json.dumps(doc))
                with self.assertRaises(ValueError):render(source,self.root,self.root/'bad.html')
                self.assertFalse((self.root/'bad.html').exists())
    def test_cap_and_existing_output_rejected(self):
        source=self.document()
        with self.assertRaises(ValueError):render(source,self.root,self.root/'cap.html',0)
        out=self.root/'already.html';out.write_text('keep')
        with self.assertRaises(ValueError):render(source,self.root,out)
        self.assertEqual(out.read_text(),'keep')
    def test_truncated_wav_payload_rejected_by_renderer_and_auditor(self):
        source=self.document();wav=self.root/'test.wav';wav.write_bytes(wav.read_bytes()[:44])
        with self.assertRaises(ValueError):render(source,self.root,self.root/'bad.html')
        doc='<article><audio src="data:audio/wav;base64,'+base64.b64encode(wav.read_bytes()).decode()+'"></audio></article>'
        p=self.root/'bad-audio.html';p.write_text(doc)
        self.assertFalse(audit(p,1)['ok'])
    def test_call_fragments_and_display_duration(self):
        r=parse_detail(50,'<voipmsg><VoIPBubbleMsg><room_type>0</room_type><msg>通话时长 01:02</msg><duration>0</duration></VoIPBubbleMsg></voipmsg><extra/>')
        self.assertEqual(r['duration_seconds'],62)
        r=parse_detail(50,'<voiplocalinfo><diaplay_content>已拒绝</diaplay_content></voiplocalinfo>')
        self.assertEqual(r['display'],'[通话] 已拒绝')
    def test_card_omits_secrets(self):
        r=parse_detail((33<<32)|49,'<msg><appmsg><type>33</type><title>演示</title><aeskey>do-not-export</aeskey></appmsg></msg>')
        self.assertNotIn('do-not-export',str(r))
    def test_audit_rejects_active_or_external_resources(self):
        for text in ['<script>alert(1)</script>','<style>@import "https://example.invalid";</style>','<img src="https://example.invalid/">','<audio onplay="alert(1)">']:
            p=self.root/'bad.html';p.write_text(text);self.assertFalse(audit(p)['ok'])
    def test_snapshot_disjoint_and_no_overwrite(self):
        source=self.root/'db';source.mkdir();(source/'toy.db').write_bytes(b'synthetic')
        target=self.root/'copy';snapshot(source,target);self.assertEqual((target/'toy.db').read_bytes(),b'synthetic')
        with self.assertRaises(FileExistsError):snapshot(source,target)
        with self.assertRaises(ValueError):snapshot(source,source/'child')
    def test_package_scan_forbids_runtime_files(self):
        root=self.root/'skill';root.mkdir();(root/'capture.db').write_bytes(b'not-real')
        self.assertTrue(any(x['reason']=='not_allowlisted' for x in validate(root)))

    def test_stored_transcript_does_not_skip_audio(self):
        import media_pipeline as media
        dbroot=self.root/'db';(dbroot/'message').mkdir(parents=True)
        (dbroot/'message/media_0.db').touch();calls=[]
        text=b'synthetic stored transcript';inner=b'\x12'+bytes([len(text)])+text
        packed=b'\x2a'+bytes([len(inner)])+inner
        row={'local_id':'1','server_id':'101','create_time':'1704067200','local_type':'34','content':'','packed':packed.hex()}
        class FakeDB:
            def __init__(self,rel):self.rel=rel
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def query(self,sql):
                calls.append(self.rel)
                return [{'body':b'synthetic silk placeholder'.hex()}] if 'media_0.db' in self.rel else [row]
        def fake_decode(silk,pcm,pcm_rate):Path(pcm).write_bytes(b'\0\0'*2400)
        cfg={'db_root':str(dbroot),'chat_id':'demo_peer','cache_dir':str(self.root/'cache')}
        with patch.object(media,'open_db',lambda cfg,rel:FakeDB(rel)),patch.dict(sys.modules,{'pilk':SimpleNamespace(decode=fake_decode)}):
            result=media.prepare(cfg,'message_0.db',1)
        self.assertEqual(result['wechat_stored_transcript'],text.decode())
        self.assertIn('message/media_0.db',calls)
        self.assertEqual(result['status'],'ready')
        with wave.open(result['audio']) as w:self.assertEqual(w.getnframes(),2400)
        receipt=Path(result['audio']).parent/'result.json'
        receipt.write_text(json.dumps({'status':'ready','source':'wechat_stored_transcript','text':'synthetic old cache'}))
        calls.clear()
        with patch.object(media,'open_db',lambda cfg,rel:FakeDB(rel)),patch.dict(sys.modules,{'pilk':SimpleNamespace(decode=fake_decode)}):
            retried=media.prepare(cfg,'message_0.db',1)
        self.assertIn('message/media_0.db',calls)
        self.assertTrue(Path(retried['audio']).is_file())
        Path(retried['audio']).write_bytes(b'corrupt synthetic WAV')
        calls.clear()
        with patch.object(media,'open_db',lambda cfg,rel:FakeDB(rel)),patch.dict(sys.modules,{'pilk':SimpleNamespace(decode=fake_decode)}):
            repaired=media.prepare(cfg,'message_0.db',1)
        self.assertIn('message/media_0.db',calls)
        with wave.open(repaired['audio']) as w:self.assertEqual(w.getnframes(),2400)
        audio=Path(repaired['audio']);audio.write_bytes(audio.read_bytes()[:44]);calls.clear()
        with patch.object(media,'open_db',lambda cfg,rel:FakeDB(rel)),patch.dict(sys.modules,{'pilk':SimpleNamespace(decode=fake_decode)}):
            repaired=media.prepare(cfg,'message_0.db',1)
        self.assertIn('message/media_0.db',calls)
        with wave.open(repaired['audio']) as w:self.assertEqual(len(w.readframes(w.getnframes())),4800)

    def test_preparation_failure_restores_original_with_hash_and_signature_checks(self):
        import bootstrap_keys as bootstrap
        for failure in ('copy','sign','verify-copy'):
            with self.subTest(stage=failure),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve();app=root/'WeChat.app';exe=app/'Contents/MacOS/WeChat';exe.parent.mkdir(parents=True);exe.write_bytes(b'synthetic executable')
                db=root/'db';db.mkdir();(db/'fixture.db').write_bytes(b'synthetic')
                state=root/'state';shadow=state/'WeChat-trial.app';commands=[]
                def command(args):
                    commands.append(args)
                    if args[0]=='codesign' and '-dvv' in args:return 'synthetic signature'
                    if args[0]=='/usr/bin/lldb':return 'synthetic-python-path'
                    if args[0]=='/usr/bin/ditto':
                        shadow.mkdir()
                        if failure=='copy':raise RuntimeError('synthetic copy failure')
                    if args[0]=='codesign' and '--force' in args and failure=='sign':raise RuntimeError('synthetic signing failure')
                    if args[0]=='codesign' and '--verify' in args and str(shadow) in args and failure=='verify-copy':raise RuntimeError('synthetic verify failure')
                    return ''
                fake_process=SimpleNamespace(pid=42,poll=lambda:None)
                with patch.object(bootstrap,'run',command),patch.object(bootstrap.sp,'run',return_value=subprocess.CompletedProcess([],1,stdout='')),patch.object(bootstrap.sp,'Popen',return_value=fake_process) as launched,patch.object(bootstrap.platform,'system',return_value='Darwin'),patch.object(bootstrap.platform,'machine',return_value='arm64'),patch.object(bootstrap.os,'geteuid',return_value=501),patch.object(bootstrap.time,'sleep'),patch.object(bootstrap,'emit'),patch.object(sys,'argv',['bootstrap_keys.py','--app',str(app),'--db-root',str(db),'--state-dir',str(state),'--acknowledge-debug-copy']):
                    with self.assertRaises(RuntimeError):bootstrap.main()
                self.assertEqual(launched.call_args.args[0],[str(exe)])
                self.assertEqual(exe.read_bytes(),b'synthetic executable')
                self.assertTrue((state/'WeChat-trial.disabled').exists())
                self.assertEqual(sum(a[0]=='codesign' and '--verify' in a and str(app) in a for a in commands),2)


class SQLCipherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sqlcipher_probe import library
        try:library()
        except (RuntimeError,OSError) as e:raise unittest.SkipTest('SQLCipher not installed; database tests not run') from e
    def test_encrypted_export_and_ambiguous_contacts(self):
        import hashlib
        from sqlcipher_probe import DB
        from capture_keys import verified
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);dbroot=root/'db';(dbroot/'contact').mkdir(parents=True);(dbroot/'message').mkdir()
            key=os.urandom(32);keyfile=root/'keys.json'
            write_new(keyfile,{'keys':{p:{'enc_key':key.hex()} for p in ['contact/contact.db','message/message_0.db']}})
            with DB(dbroot/'contact/contact.db',key.hex(),fixture_write=True) as db:
                db.query('CREATE TABLE contact(username TEXT,nick_name TEXT,remark TEXT)')
                db.query("INSERT INTO contact VALUES('demo_peer','演示同名',''),('demo_other','演示同名',''),('demo_self','本人','')")
            table='Msg_'+hashlib.md5(b'demo_peer').hexdigest();p=dbroot/'message/message_0.db'
            with DB(p,key.hex(),fixture_write=True) as db:
                db.query('CREATE TABLE Name2Id(user_name TEXT);')
                db.query("INSERT INTO Name2Id(rowid,user_name) VALUES(1,'demo_peer'),(2,'demo_self')")
                db.query(f'CREATE TABLE "{table}"(local_id INTEGER,server_id INTEGER,local_type INTEGER,create_time INTEGER,real_sender_id INTEGER,message_content BLOB)')
                body='合成文字，仅用于测试'.encode().hex()
                db.query(f'INSERT INTO "{table}" VALUES(1,101,1,1704067200,1,x\'{body}\')')
            self.assertTrue(verified(key,p.read_bytes()[:4096]))
            self.assertFalse(verified(os.urandom(32),p.read_bytes()[:4096]))
            self.assertEqual(len(resolve(dbroot,keyfile,'演示同名')),2)
            self.assertEqual(verify(dbroot,keyfile)['verified'],2)
            args=argparse.Namespace(db_root=dbroot,key_file=keyfile,chat_id='demo_peer',self_id='demo_self',timezone='UTC',start=None,end=None,max_messages=10,recover_media=False,account_dir=None,app_data=None,output=root/'archive.json')
            result=export(args);self.assertEqual(result['exported_rows'],1)
            doc=json.loads(args.output.read_text());self.assertEqual(doc['messages'][0]['text'],'合成文字，仅用于测试')
            self.assertNotIn(key.hex(),args.output.read_text())
            render(args.output,root,root/'chat.html');self.assertTrue(audit(root/'chat.html',1)['ok'])


if __name__=='__main__':unittest.main(verbosity=2)
