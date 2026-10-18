#!/usr/bin/env python3
"""Check message count and embedded resources, without opening a browser."""
import argparse
import base64
from html.parser import HTMLParser
import io
import json
import re
from pathlib import Path
import wave


class Audit(HTMLParser):
    def __init__(self):
        super().__init__();self.messages=0;self.assets=[];self.errors=[];self.in_style=False
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='article':self.messages+=1
        if tag=='style':self.in_style=True
        if tag in ('script','iframe','object','embed','form','base'):self.errors.append('active_content:'+tag)
        if tag=='meta' and attrs.get('http-equiv','').lower()=='refresh':self.errors.append('refresh')
        for key,value in attrs.items():
            if key.startswith('on'):self.errors.append('event_handler')
            if key in ('srcset','poster'):self.errors.append('unsupported_resource_attribute:'+key)
            if key in ('href','src','action'):
                if value.startswith('data:') and tag in ('img','audio','video'):self.assets.append((tag,value))
                elif not value.startswith('#'):self.errors.append('non_embedded_resource')
            if key=='style' and re.search(r'url\s*\(|@import',value,re.I):self.errors.append('css_resource')
    def handle_endtag(self,tag):
        if tag=='style':self.in_style=False
    def handle_data(self,data):
        if self.in_style and re.search(r'url\s*\(|@import',data,re.I):self.errors.append('css_resource')


def audit(path,expected=None):
    a=Audit();a.feed(Path(path).read_text());images=audio=videos=0
    if expected is not None and a.messages!=expected:a.errors.append('message_count_mismatch')
    for tag,url in a.assets:
        try:
            header,encoded=url.split(',',1)
            if not header.endswith(';base64'):raise ValueError('base64 required')
            data=base64.b64decode(encoded,validate=True)
            if tag=='img':
                from PIL import Image
                im=Image.open(io.BytesIO(data));im.verify()
                formats={'JPEG':'image/jpeg','PNG':'image/png','GIF':'image/gif','WEBP':'image/webp'}
                if header!='data:'+formats.get(im.format,'unsupported')+';base64':raise ValueError('image MIME mismatch')
                images+=1
            elif tag=='audio':
                if header!='data:audio/wav;base64':raise ValueError('WAV required')
                with wave.open(io.BytesIO(data)) as w:
                    if not w.getnframes():raise ValueError('empty audio')
                    expected=w.getnframes()*w.getnchannels()*w.getsampwidth()
                    if len(w.readframes(w.getnframes()))!=expected:raise ValueError('truncated WAV')
                audio+=1
            else:
                if header!='data:video/mp4;base64' or data[4:8]!=b'ftyp':raise ValueError('MP4 required')
                videos+=1
        except (ValueError,OSError,KeyError,wave.Error):a.errors.append('invalid_embedded_media')
    return {'ok':not a.errors,'messages':a.messages,'images':images,'audio':audio,'videos':videos,
            'errors':a.errors,'browser_playback_verified':False}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('html',type=Path);ap.add_argument('--expected-messages',type=int);args=ap.parse_args()
    result=audit(args.html,args.expected_messages);print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
