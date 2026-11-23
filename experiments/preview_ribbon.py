#!/usr/bin/env python3
"""Render the Bobrov tab before and after a CUIX change as standalone HTML.

Usage: python3 experiments/preview_ribbon.py old.cuix new.cuix > preview.html
"""

import argparse
import base64
from html import escape
import xml.etree.ElementTree as ET
from zipfile import ZipFile


def ribbon(path):
    with ZipFile(path) as archive:
        group = ET.fromstring(archive.read("MenuGroup.cui"))
        macros = {node.get("UID"): node.find("Macro") for node in group.iter("MenuMacro")}
        root = ET.fromstring(archive.read("RibbonRoot.cui"))
        panels = {node.get("UID"): node for node in root.iter("RibbonPanelSource")}
        tab = next(root.iter("RibbonTabSource"))
        panel_html = []
        for ref in tab.findall("RibbonPanelSourceReference"):
            panel = panels[ref.get("PanelId")]
            buttons = []
            for button in panel.iter("RibbonCommandButton"):
                macro = macros[button.get("MenuMacroID")]
                image = macro.find("LargeImage").get("Name")
                icon = base64.b64encode(archive.read(image)).decode("ascii")
                label = escape(button.get("Text"))
                buttons.append(f'<div class="button"><img src="data:image/png;base64,{icon}" alt="">{label}</div>')
            title = escape(panel.get("Text"))
            panel_html.append(f'<div class="panel"><div class="buttons">{"".join(buttons)}</div><footer>{title}</footer></div>')
        return f'<div class="tab">{escape(tab.get("Text"))}</div><div class="panels">{"".join(panel_html)}</div>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before")
    parser.add_argument("after")
    args = parser.parse_args()
    print(f"""<!doctype html>
<html lang="ru">
<meta charset="utf-8">
<title>Вкладка Bobrov из CUIX</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font: 14px system-ui, sans-serif; background: #f0f2f5; color: #1e293b; }}
  main {{ width: max-content; padding: 20px; }}
  section + section {{ margin-top: 16px; }}
  h1 {{ margin: 0 0 14px; font-size: 20px; }}
  h2 {{ margin: 0 0 6px; font-size: 14px; font-weight: 500; }}
  .tab {{ width: fit-content; padding: 6px 14px; background: #37465a; color: white; border-radius: 5px 5px 0 0; }}
  .panels {{ display: flex; padding: 8px; gap: 6px; background: #37465a; border-radius: 0 6px 6px 6px; }}
  .panel {{ overflow: hidden; border: 1px solid #53657e; border-radius: 4px; background: #2a3648; color: #fff; }}
  .buttons {{ display: flex; min-height: 76px; justify-content: center; padding: 6px; }}
  .button {{ display: flex; flex-direction: column; align-items: center; gap: 3px; width: 86px; text-align: center; font-size: 12px; }}
  img {{ width: 32px; height: 32px; image-rendering: pixelated; }}
  footer {{ padding: 3px 8px; text-align: center; background: #243041; color: #dee6f1; font-size: 11px; }}
</style>
<main>
  <h1>Вкладка Bobrov из CUIX</h1>
  <section><h2>До изменения</h2>{ribbon(args.before)}</section>
  <section><h2>После изменения</h2>{ribbon(args.after)}</section>
</main>
</html>""")


if __name__ == "__main__":
    main()
