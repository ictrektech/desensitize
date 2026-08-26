# -*- coding: utf-8 -*-
"""Patch footers: PAGE -> PAGE \\* ROMAN / \\* arabic per section; strip empty pgNumType."""
import re
import shutil
import sys
import zipfile

path = sys.argv[1]
tmp = path + ".tmp"

with zipfile.ZipFile(path) as zin:
    items = {n: zin.read(n) for n in zin.namelist()}

doc = items["word/document.xml"].decode("utf-8")
rels = items["word/_rels/document.xml.rels"].decode("utf-8")

# 1) strip empty pgNumType (cover section)
doc = doc.replace("<w:pgNumType/>", "")

# 2) map sectPr pgNumType fmt -> footer rId
rid_to_target = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
fmt_of_footer = {}
for sect in re.findall(r"<w:sectPr[^>]*>.*?</w:sectPr>", doc, re.S):
    m_fmt = re.search(r'<w:pgNumType[^>]*w:fmt="([^"]+)"', sect)
    if not m_fmt:
        continue
    fmt = m_fmt.group(1)
    for rid in re.findall(r'<w:footerReference[^>]*r:id="([^"]+)"', sect):
        target = rid_to_target.get(rid, "")
        if "footer" in target:
            fmt_of_footer["word/" + target.lstrip("/")] = fmt

patched = []
for name, fmt in fmt_of_footer.items():
    if name not in items:
        continue
    switch = "ROMAN" if "oman" in fmt or "ROMAN" in fmt else "arabic"
    xml = items[name].decode("utf-8")
    new_xml, n = re.subn(
        r"(<w:instrText[^>]*>)\s*PAGE\s*(</w:instrText>)",
        r"\1 PAGE \\* " + switch + r" \\* MERGEFORMAT \2",
        xml,
    )
    if n:
        items[name] = new_xml.encode("utf-8")
        patched.append((name, fmt, switch, n))

items["word/document.xml"] = doc.encode("utf-8")

with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
    for name, data in items.items():
        zout.writestr(name, data)
shutil.move(tmp, path)
print("patched footers:", patched)
