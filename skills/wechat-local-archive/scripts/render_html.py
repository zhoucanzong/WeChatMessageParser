#!/usr/bin/env python3
"""Render normalized chat JSON into an offline single-file HTML archive."""
import argparse
import base64
import html
import io
import json
import os
from pathlib import Path
import wave


def asset_uri(asset, json_dir, media_root):
    path=Path(asset['path'])
    path=(json_dir/path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(media_root):raise ValueError('asset escapes media root')
    data=path.read_bytes();kind=asset['kind']
    if kind=='image':
        from PIL import Image
        im=Image.open(io.BytesIO(data));im.verify()
        mime={'JPEG':'image/jpeg','PNG':'image/png','GIF':'image/gif','WEBP':'image/webp'}.get(im.format)
        if mime is None:raise ValueError('unsupported image format')
    elif kind=='audio':
        with wave.open(io.BytesIO(data)) as w:
            if w.getnframes()<=0 or w.getframerate()<=0:raise ValueError('empty WAV')
            expected=w.getnframes()*w.getnchannels()*w.getsampwidth()
            if len(w.readframes(w.getnframes()))!=expected:raise ValueError('truncated WAV payload')
        mime='audio/wav'
    elif kind=='video':
        if len(data)<12 or data[4:8]!=b'ftyp':raise ValueError('expected MP4 container; validate playback separately')
        mime='video/mp4'
    else:raise ValueError('unsupported asset kind')
    return 'data:'+mime+';base64,'+base64.b64encode(data).decode(),len(data)


def render(source, media_root, output, max_media_mib=256):
    source=Path(source).resolve();media_root=Path(media_root).resolve();output=Path(output)
    if output.exists():raise ValueError('output already exists')
    doc=json.loads(source.read_text());messages=doc['messages'];parts=[];total_bytes=0;asset_count=0
    expected=doc.get('coverage',{}).get('exported_rows',len(messages))
    if expected!=len(messages):raise ValueError('archive message count does not match coverage')
    for m in messages:
        body=html.escape(str(m.get('text','')))
        for asset in m.get('assets',[]):
            p=Path(asset['path']);p=(source.parent/p).resolve() if not p.is_absolute() else p.resolve()
            if not p.is_relative_to(media_root):raise ValueError('asset escapes media root')
            if total_bytes+p.stat().st_size>max_media_mib*1024*1024:raise ValueError('media exceeds configured cap; no attachments silently omitted')
            uri,size=asset_uri(asset,source.parent,media_root);total_bytes+=size;asset_count+=1
            if asset['kind']=='image':body+=f'<br><img loading="lazy" alt="聊天图片" src="{uri}">'
            elif asset['kind']=='audio':body+=f'<br><audio controls preload="none" src="{uri}"></audio>'
            else:body+=f'<br><video controls preload="none" src="{uri}"></video>'
            if asset.get('note'):body+='<details><summary>附件说明</summary>'+html.escape(str(asset['note']))+'</details>'
        state=html.escape(str(m.get('status','unknown')))
        parts.append(f'<article data-status="{state}"><div class="meta">{html.escape(str(m.get("time","")))} · {html.escape(str(m.get("sender","未知发送者")))}</div><div class="content">{body}</div></article>')
    title=html.escape(str(doc.get('title','聊天记录')))
    unresolved=sum(m.get('status') in ('metadata_only','unsupported','parse_error','media_unavailable') for m in messages)
    start='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; media-src data:; style-src 'unsafe-inline'">
<style>body{font-family:system-ui,sans-serif;max-width:850px;margin:32px auto;padding:0 18px;background:#f2f5f3;color:#17251d}article{background:#fff;border:1px solid #dfe6e1;border-radius:12px;padding:18px;margin:12px 0}.meta{font-size:12px;color:#657469;margin-bottom:8px}.content{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.65}img,video{max-width:100%;max-height:560px;margin-top:12px}audio{width:100%;margin-top:12px}summary{cursor:pointer}details{font-size:13px;color:#526156}</style>'''
    output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    text=start+f'<title>{title}</title></head><body><h1>{title}</h1><p>{len(messages)} 条记录 · {asset_count} 个内嵌媒体 · {unresolved} 条仍有未解析内容</p><p>此文件可离线查看。通话详情不包含通话录音；机器转写须以音频为准。</p>'+''.join(parts)+'</body></html>'
    with os.fdopen(os.open(output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'w') as f:f.write(text)
    return {'messages':len(messages),'assets':asset_count,'embedded_bytes':total_bytes,'unresolved_messages':unresolved}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('archive',type=Path);ap.add_argument('--media-root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--max-media-mib',type=float,default=256);a=ap.parse_args()
    print(json.dumps(render(a.archive,a.media_root,a.output,a.max_media_mib),ensure_ascii=False))
