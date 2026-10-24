"""Turn pytest JUnit failures into GitHub annotations (readable via the API)."""

import sys
import xml.etree.ElementTree as ET


def escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")


root = ET.parse(sys.argv[1]).getroot()
for case in root.iter("testcase"):
    for kind in ("failure", "error"):
        node = case.find(kind)
        if node is None:
            continue
        name = f"{case.get('classname')}.{case.get('name')}"
        detail = (node.get("message") or "") + "\n" + (node.text or "")
        print(f"::error title={kind}: {name}::{escape(detail[-3500:])}")
