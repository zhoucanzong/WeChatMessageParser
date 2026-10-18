"""Structured message parsing; unknown fields and credentials are not exported."""
import re
import xml.etree.ElementTree as ET

def xml_fragments(value: str) -> ET.Element:
    if "<!DOCTYPE" in value.upper() or "<!ENTITY" in value.upper():
        raise ValueError("DTD/entity declarations are unsupported")
    value = re.sub(r"<\?xml[^>]*\?>", "", value).replace("\x00", "")
    return ET.fromstring("<root>" + value + "</root>")

def tag_text(root: ET.Element, path: str) -> str:
    node = root.find(path)
    return "".join(node.itertext()).strip() if node is not None else ""

def parse_detail(kind: int, content: str) -> dict:
    if kind == 10000:
        try:
            text = "".join(xml_fragments(content).itertext()).strip()
        except ET.ParseError:
            text = content
        return {"category": "system", "status": "parsed", "display": text}
    root = xml_fragments(content)
    if kind == 50:
        # Later local wording can describe completion; retain the original words
        # instead of inventing who rejected/canceled a call.
        wording = (tag_text(root, ".//voiplocalinfo/diaplay_content")
                   or tag_text(root, ".//voiplocalinfo/display_content")
                   or tag_text(root, ".//VoIPBubbleMsg/msg"))
        room = tag_text(root, ".//room_type")
        call_kind = {"0": "视频通话", "1": "语音通话"}.get(room, "通话")
        duration = re.search(r"通话时长\s*(\d{1,3}:\d{2}(?::\d{2})?)", wording)
        result = {"category": "call", "status": "parsed" if wording else "metadata_only",
                  "call_kind": call_kind, "wording": wording,
                  "display": f"[{call_kind}] {wording or '状态未记录'}"}
        if duration:
            parts = [int(x) for x in duration.group(1).split(":")]
            seconds = sum(n * 60 ** i for i, n in enumerate(reversed(parts)))
            result.update(duration_display=duration.group(1), duration_seconds=seconds,
                          duration_source="message_display_text")
        # Numeric duration can be zero even when the display has a real duration.
        if tag_text(root, ".//duration"):
            result["raw_duration_field"] = tag_text(root, ".//duration")
        return result
    if kind & 0xffffffff == 49:
        title = tag_text(root, ".//appmsg/title")
        subtype = tag_text(root, ".//appmsg/type")
        source = tag_text(root, ".//sourcedisplayname")
        name = "小程序分享" if subtype == "33" else "分享卡片"
        return {"category": "card", "status": "parsed", "title": title,
                "description": tag_text(root, ".//appmsg/des"), "source_name": source,
                "subtype": subtype, "display": f"[{name}] {title}" + (f"（{source}）" if source else ""),
                "linked_content_opened": False}
    if kind in (3, 34, 47):
        name, tag = {3: ("图片", "img"), 34: ("语音", "voicemsg"), 47: ("表情", "emoji")}[kind]
        element = root.find(".//" + tag)
        if element is None:
            raise ValueError("expected media metadata not found")
        result = {"category": {3: "image", 34: "voice", 47: "emoji"}[kind],
                  "status": "metadata_only", "display": f"[{name}]"}
        # Explicit allowlist excludes keys, signed URLs, and authentication fields.
        allowed = {3: ("md5", "length", "hdlength"),
                   34: ("voiceformat", "voicelength", "length"),
                   47: ("md5", "width", "height", "attachedtext")}[kind]
        result["metadata"] = {k: element.get(k) for k in allowed if element.get(k)}
        return result
    return {"category": "unknown", "status": "unsupported", "display": f"[未支持的类型 {kind}]"}
