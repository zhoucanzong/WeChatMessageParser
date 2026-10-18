#!/usr/bin/env python3
"""Build an allowlisted source-only skill ZIP; never package a workspace tree."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

FILES = {
    'SKILL.md','agents/openai.yaml',
    'references/macos.md','references/formats.md','references/commands.md','references/sources.md',
    'scripts/archive.py','scripts/audit_html.py','scripts/bootstrap_keys.py','scripts/capture_keys.py',
    'scripts/disk_inventory.py','scripts/media_pipeline.py','scripts/message_formats.py',
    'scripts/render_html.py','scripts/sqlcipher_probe.py','scripts/package_skill.py',
    'scripts/test_archive.py','scripts/requirements.txt',
}


def validate(root, forbidden=()):
    root=Path(root).resolve();found=set();issues=[]
    for path in root.rglob('*'):
        rel=path.relative_to(root).as_posix()
        if path.is_symlink():issues.append({'file':rel,'reason':'symlink'});continue
        if path.is_dir():continue
        found.add(rel)
        if rel not in FILES:
            issues.append({'file':rel,'reason':'not_allowlisted'});continue
        try:text=path.read_text('utf8')
        except (UnicodeDecodeError,OSError):issues.append({'file':rel,'reason':'not_utf8_source'});continue
        checks=[r'/Users/[A-Za-z0-9_.-]+/',r'/home/[A-Za-z0-9_.-]+/',
                r'wxid_[a-zA-Z0-9]{8,}',r'["\x27](?:enc_key|aeskey)["\x27]\s*:\s*["\x27][0-9a-fA-F]{32,64}["\x27]']
        if any(re.search(pattern,text) for pattern in checks):issues.append({'file':rel,'reason':'identity_or_secret_literal'})
        if any(marker and marker in text for marker in forbidden):issues.append({'file':rel,'reason':'private_marker'})
        if re.search(r'\b(?:TODO|FIXME)\b',text) and rel!='scripts/package_skill.py':issues.append({'file':rel,'reason':'unfinished_scaffold'})
    for missing in sorted(FILES-found):issues.append({'file':missing,'reason':'missing_required_file'})
    return issues


def package(root,output,forbidden=()):
    root=Path(root).resolve();output=Path(output).resolve()
    if output.is_relative_to(root):raise ValueError('package output must be outside the skill')
    issues=validate(root,forbidden)
    if issues:raise ValueError(json.dumps({'package_rejected':issues}))
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(FILES):
            info=zipfile.ZipInfo(root.name+'/'+rel,date_time=(2024,1,1,0,0,0))
            info.external_attr=0o100644<<16;info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,(root/rel).read_bytes())
    return {'files':len(FILES),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'privacy_scan':'passed_for_configured_patterns_and_markers'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('skill',type=Path);p.add_argument('--output',type=Path);p.add_argument('--forbid-file',type=Path);a=p.parse_args()
    markers=a.forbid_file.read_text().splitlines() if a.forbid_file else []
    if a.output:print(json.dumps(package(a.skill,a.output,markers)))
    else:
        result=validate(a.skill,markers);print(json.dumps({'issues':result}));raise SystemExit(bool(result))
