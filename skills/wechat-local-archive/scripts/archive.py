#!/usr/bin/env python3
"""Deterministic, explicitly scoped local database operations; never starts WeChat."""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlcipher_probe import DB, load_key
from message_formats import parse_detail


def literal(value):
    return "CAST(x'" + value.encode().hex() + "' AS TEXT)"


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def open_db(root, keys, relative):
    path = root / relative
    return DB(path, load_key(keys, path))


def signatures(root):
    result = {}
    for p in sorted(root.rglob('*')):
        if p.is_file() and not p.is_symlink() and p.name.endswith(('.db', '.db-wal', '.db-shm')):
            s = p.stat()
            result[str(p.relative_to(root))] = (s.st_size, s.st_mtime_ns, s.st_ino)
    return result


def snapshot(root, output):
    output = output.resolve()
    if output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError('snapshot must be disjoint from source')
    before = signatures(root)
    if not before:
        raise ValueError('no database files')
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    for rel in before:
        dest = output / rel
        dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(root / rel, dest)
        dest.chmod(0o600)
    after = signatures(root)
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    report = {'files': len(before), 'changed_during_copy': changed,
              'cross_database_transaction_consistency_guaranteed': False,
              'requires_sqlcipher_integrity_check': True}
    write_new(output / 'snapshot-manifest.json', report)
    if changed:
        raise ValueError('source changed during snapshot; keep diagnostic and retry in a new directory')
    return report


def resolve(root, keys, name):
    with open_db(root, keys, 'contact/contact.db') as db:
        return db.query('SELECT username,nick_name,remark FROM contact WHERE '
                        f'username={literal(name)} OR nick_name={literal(name)} OR remark={literal(name)}')


def verify(root, keys):
    rows = []
    for p in sorted(root.rglob('*.db')):
        try:
            with DB(p, load_key(keys, p)) as db:
                check = db.query('PRAGMA quick_check;')
                tables = db.query("SELECT count(*) AS n FROM sqlite_master WHERE type='table'")
                rows.append({'database': str(p.relative_to(root)), 'ok': check == [{'quick_check':'ok'}],
                             'tables': int(tables[0]['n']), 'quick_check': check})
        except (RuntimeError, ValueError, OSError) as error:
            rows.append({'database': str(p.relative_to(root)), 'ok': False, 'error': str(error)})
    return {'databases': len(rows), 'verified': sum(r['ok'] for r in rows), 'results': rows}


def decode_text(value):
    data = bytes.fromhex(value or '')
    if data.startswith(b'\x28\xb5\x2f\xfd'):
        try:
            from compression import zstd
            data = zstd.decompress(data)
        except ImportError:
            import zstandard
            data = zstandard.ZstdDecompressor().decompress(data, max_output_size=16*1024*1024)
    return data.decode('utf8', 'strict')


def export(args):
    root, keys = args.db_root, args.key_file
    if args.output.exists():
        raise ValueError('output already exists')
    zone = ZoneInfo(args.timezone)
    terms = []
    if args.start:
        start = datetime.strptime(args.start, '%Y-%m-%d').replace(tzinfo=zone)
        terms.append(f'create_time >= {int(start.timestamp())}')
    if args.end:
        end = datetime.strptime(args.end, '%Y-%m-%d').replace(tzinfo=zone) + timedelta(days=1)
        terms.append(f'create_time < {int(end.timestamp())}')
    if args.start and args.end and start >= end:
        raise ValueError('invalid date range')
    where = (' WHERE ' + ' AND '.join(terms)) if terms else ''
    table = 'Msg_' + hashlib.md5(args.chat_id.encode()).hexdigest()
    paths = sorted(p for p in (root/'message').glob('message_*.db')
                   if re.fullmatch(r'message_\d+\.db', p.name))
    if not paths:
        raise ValueError('no regular message shards')
    shards, selected = [], 0
    for path in paths:
        with DB(path, load_key(keys, path)) as db:
            if db.query(f"SELECT 1 FROM sqlite_master WHERE name='{table}' AND type='table'"):
                n = int(db.query(f'SELECT count(*) AS n FROM "{table}"{where}')[0]['n'])
                shards.append((path, n)); selected += n
    if not shards:
        raise ValueError('no local table for selected conversation')
    if selected > args.max_messages:
        raise ValueError(f'selection has {selected} rows; narrow dates or explicitly increase --max-messages')
    contact_rows = resolve(root, keys, args.chat_id)
    title = next((r['remark'] or r['nick_name'] for r in contact_rows if r['username'] == args.chat_id), args.chat_id)
    messages, sender_names = [], {}
    for path, count in shards:
        with DB(path, load_key(keys, path)) as db:
            rows = db.query('SELECT local_id,server_id,local_type,create_time,real_sender_id,'
                            f'hex(message_content) AS body FROM "{table}"{where} ORDER BY create_time,local_id')
            if len(rows) != count:
                raise ValueError('row count changed; export from a stable snapshot')
            for row in rows:
                sender = db.query('SELECT user_name FROM Name2Id WHERE rowid=' + str(int(row['real_sender_id'])))
                sender_id = sender[0]['user_name'] if len(sender) == 1 else None
                if sender_id and sender_id not in sender_names:
                    found = resolve(root, keys, sender_id)
                    sender_names[sender_id] = next((r['remark'] or r['nick_name'] for r in found if r['username']==sender_id), sender_id)
                sender_label = '我' if args.self_id and sender_id == args.self_id else sender_names.get(sender_id, '未知发送者')
                kind = int(row['local_type'])
                try:
                    content = decode_text(row['body'])
                    if args.chat_id.endswith('@chatroom') and sender_id and content.startswith(sender_id+':\n'):
                        content = content[len(sender_id)+2:]
                    detail = {'category':'text', 'status':'parsed', 'display':content} if kind==1 else parse_detail(kind, content)
                except Exception as error:
                    detail = {'category':'unknown', 'status':'parse_error', 'display':f'[正文解析失败：{type(error).__name__}]'}
                message = {'id':f'{path.name}:{table}:{row["local_id"]}',
                           'time':datetime.fromtimestamp(int(row['create_time']),zone).isoformat(),
                           'sender':sender_label, 'kind':detail['category'], 'text':detail['display'],
                           'status':detail['status'], 'detail':detail, 'assets':[],
                           'source':{'database':path.name,'local_id':row['local_id'],'server_id':row['server_id'],'local_type':kind}}
                if args.recover_media and kind in (3,34):
                    from media_pipeline import prepare
                    cache=args.output.parent/(args.output.stem+'-media')
                    cfg={'db_root':str(root),'key_file':str(keys),'account_dir':str(args.account_dir),
                         'self_id':args.self_id,'chat_id':args.chat_id,'cache_dir':str(cache)}
                    if args.app_data:cfg['app_data']=str(args.app_data)
                    result=prepare(cfg,path.name,int(row['local_id']))
                    if result.get('wechat_stored_transcript'):
                        message['text']+='\n微信已存机器转写（未经人工确认）：'+result['wechat_stored_transcript']
                    notes=[]
                    if result.get('thumbnail_only'):notes.append('仅缩略图')
                    if result.get('wxgf_first_frame_only'):notes.append('仅第一帧')
                    if 'message_md5_match' in result:
                        notes.append({True:'消息 MD5 一致',False:'消息 MD5 未匹配；仅完成定位和图像解码',None:'消息 MD5 未核验'}[result['message_md5_match']])
                    for field,asset_kind in [('image','image'),('audio','audio')]:
                        if result.get(field):
                            asset_path=Path(result[field]).resolve()
                            if not asset_path.is_relative_to(cache.resolve()):raise ValueError('unexpected media output path')
                            message['assets'].append({'kind':asset_kind,'path':str(asset_path.relative_to(args.output.parent.resolve())), 'note':'；'.join(notes)})
                    if message['assets']:
                        message['status']='media_decoded'
                        message['text']+='\n已还原本地媒体；语音未转写。' if kind==34 else '\n已还原本地图片，需视觉检查。'
                    else:
                        message['status']='media_unavailable'
                        message['text']+='\n媒体未还原：'+result.get('reason','unavailable')
                messages.append(message)
    messages.sort(key=lambda m:(m['time'],m['id']))
    archive={'title':title,'selection':{'chat_id':args.chat_id,'start':args.start,'end':args.end,'timezone':args.timezone},
             'coverage':{'selected_rows':selected,'exported_rows':len(messages),'cross_shard_deduplication':False,
                         'assets_recovered':sum(len(m['assets']) for m in messages),
                         'unresolved_messages':sum(m['status'] in ('parse_error','metadata_only','unsupported','media_unavailable') for m in messages)},
             'messages':messages}
    write_new(args.output,archive)
    return archive['coverage']


def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    for name in ('inventory','snapshot','verify','resolve','export'):
        p=sub.add_parser(name);p.add_argument('--db-root',type=Path,required=True)
        if name not in ('inventory','snapshot'):p.add_argument('--key-file',type=Path,required=True)
        if name in ('snapshot','verify','export'):p.add_argument('--output',type=Path,required=True)
        if name=='resolve':p.add_argument('--name',required=True)
        if name=='export':
            p.add_argument('--chat-id',required=True);p.add_argument('--self-id');p.add_argument('--timezone',default='UTC')
            p.add_argument('--start');p.add_argument('--end');p.add_argument('--max-messages',type=int,default=100000)
            p.add_argument('--recover-media',action='store_true');p.add_argument('--account-dir',type=Path);p.add_argument('--app-data',type=Path)
    a=ap.parse_args();os.umask(0o077);a.db_root=a.db_root.resolve(strict=True)
    if hasattr(a,'output'):
        a.output=a.output.resolve()
        if a.output.is_relative_to(a.db_root):ap.error('output must be outside the database input directory')
    if a.command=='export' and a.recover_media and (not a.account_dir or not a.self_id):ap.error('media recovery requires --account-dir and --self-id')
    if a.command=='inventory':result={'databases':len(list(a.db_root.rglob('*.db'))),'files':signatures(a.db_root),'message_content_read':False}
    elif a.command=='snapshot':result=snapshot(a.db_root,a.output)
    elif a.command=='verify':result=verify(a.db_root,a.key_file);write_new(a.output,result)
    elif a.command=='resolve':
        rows=resolve(a.db_root,a.key_file,a.name);result={'matches':rows,'unique':len(rows)==1}
        print(json.dumps(result,ensure_ascii=False));return 0 if len(rows)==1 else 2
    else:result=export(a)
    print(json.dumps(result,ensure_ascii=False));return 0


if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,RuntimeError,OSError) as e:print(json.dumps({'error':str(e)},ensure_ascii=False));sys.exit(1)
