"""Automated checks of the BobrovMenu module (issues #1 and #5).

They verify everything that can be verified without AutoCAD: the committed CUIX package
matches its sources, the package is a consistent OPC/CUIX file, the command, menu and
ribbon tab follow the spec, nothing forbidden by sections 2 and 7 is present, and the
bundle and the manual install archive have the expected layout.  The manual acceptance
of section 8 is in docs/acceptance-protocol.md.

    python3 -m unittest discover -s tests -v
"""

import hashlib
import re
import struct
import sys
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_cuix  # noqa: E402
import make_icons  # noqa: E402
import package  # noqa: E402

CUIX = ROOT / "installer" / "BobrovMenu.bundle" / "Contents" / "BobrovMenu.cuix"
PACKAGE_CONTENTS = ROOT / "installer" / "BobrovMenu.bundle" / "PackageContents.xml"
MANUAL = ROOT / "installer" / "manual"

MACRO = "$M=$(if,$(getvar,cmdactive),^C^C)_XDATAPALETTE "
TOOLTIP = "Показать или скрыть панель «Свойства XDATA» (XDATAPALETTE)"
BUTTON = "Палитра XDATA"
RIBBON_COMMANDS = {
    "Палитра XDATA": [("XDATAPALETTE", BUTTON)],
    "Умные выноски": [
        ("SL_CREATE", "Создать"),
        ("SL_CREATE_GROUP", "Создать групповую"),
        ("SL_UPDATE", "Обновить"),
        ("SL_RULES", "Правила"),
    ],
    "База данных": [("DB_EDIT", "Редактор БД")],
}
COMMANDS = {command for buttons in RIBBON_COMMANDS.values() for command, _ in buttons}
PLUGIN_GUIDS = {"dad36109-0e0e-411e-9681-4259d2b90a08", "9c948433-c934-4767-9470-ae1a38762682"}
OPC_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
EXPECTED_ROOTS = {
    "Header.cui": "CustSection",
    "MenuGroup.cui": "MenuGroup",
    "WorkspaceRoot.cui": "WorkspaceRoot",
    "PopMenuRoot.cui": "PopMenuRoot",
    "RibbonRoot.cui": "RibbonRoot",
    "ToolbarRoot.cui": "ToolbarRoot",
    "AcceleratorRoot.cui": "AcceleratorRoot",
    "QuickAccessToolbarRoot.cui": "QuickAccessToolbarRoot",
}


def cuix_entries():
    with zipfile.ZipFile(CUIX) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def xml(name):
    return ET.fromstring(cuix_entries()[name])


def png_size(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise AssertionError("not a PNG file")
    return struct.unpack(">II", data[16:24])


class SourcesTest(unittest.TestCase):
    def test_committed_cuix_matches_sources(self):
        self.assertEqual(build_cuix.read_entries(CUIX), build_cuix.source_entries())

    def test_icons_match_generator(self):
        for name, draw in make_icons.ICONS.items():
            with self.subTest(name=name):
                self.assertEqual((build_cuix.SOURCE / name).read_bytes(), make_icons.png_bytes(draw()))

    def test_build_is_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp, "a.cuix"), Path(tmp, "b.cuix")
            build_cuix.build(first, build_cuix.source_entries())
            build_cuix.build(second, build_cuix.source_entries())
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(build_cuix.read_entries(first), build_cuix.read_entries(CUIX))

    def test_unpack_round_trip(self):
        # A CUIX saved by the CUI editor is turned back into sources with --unpack.
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp, "src")
            source.mkdir()
            Path(source, "stale.cui").write_text("<old />")
            build_cuix.unpack(CUIX, source)
            self.assertFalse(Path(source, "stale.cui").exists())
            self.assertEqual(build_cuix.source_entries(source), build_cuix.read_entries(CUIX))


class PackageStructureTest(unittest.TestCase):
    def setUp(self):
        self.entries = cuix_entries()

    def test_zip_is_valid_and_dates_fixed(self):
        with zipfile.ZipFile(CUIX) as archive:
            self.assertIsNone(archive.testzip())
            for info in archive.infolist():
                self.assertEqual(info.date_time, build_cuix.ZIP_DATE, info.filename)

    def test_all_xml_parts_are_well_formed(self):
        for name, data in self.entries.items():
            if name.endswith((".cui", ".xml", ".rels")):
                with self.subTest(name=name):
                    ET.fromstring(data)

    def test_root_elements(self):
        for name, root in EXPECTED_ROOTS.items():
            with self.subTest(name=name):
                self.assertEqual(xml(name).tag, root)

    def test_content_types_cover_every_entry(self):
        types = xml("[Content_Types].xml")
        ns = "{http://schemas.openxmlformats.org/package/2006/content-types}"
        defaults = {d.get("Extension").lower() for d in types.iter(ns + "Default")}
        overrides = {o.get("PartName").lstrip("/") for o in types.iter(ns + "Override")}
        for name in self.entries:
            if name == "[Content_Types].xml":
                continue
            with self.subTest(name=name):
                self.assertTrue(name in overrides or name.rsplit(".", 1)[-1].lower() in defaults)

    def test_relationships(self):
        rels = list(xml("_rels/.rels").iter("{%s}Relationship" % OPC_RELS))
        ids = [r.get("Id") for r in rels]
        self.assertEqual(len(ids), len(set(ids)), "relationship Ids must be unique")
        targets = {r.get("Target").lstrip("/"): r.get("Type") for r in rels}
        for target, kind in targets.items():
            with self.subTest(target=target):
                self.assertIn(target, self.entries)
                self.assertEqual(kind, "Image" if target.endswith(".png") else "CUI")
        parts = {n for n in self.entries if n.endswith((".cui", ".png"))}
        self.assertEqual(parts, set(targets), "every part must be related and vice versa")

    def test_menu_package_info_lists_every_part(self):
        info = self.entries["Menu_Package_Info.xml"].decode("utf-8")
        listed = set(re.findall(r'PartData_Name="/?([^"]+)"', info))
        parts = {n for n in self.entries if n.endswith((".cui", ".png"))}
        self.assertTrue(parts <= listed, "missing in Menu_Package_Info.xml: %s" % sorted(parts - listed))

    def test_icons_are_16_and_32(self):
        for tag, size in (("SmallImage", 16), ("LargeImage", 32)):
            referenced = []
            for macro in xml("MenuGroup.cui").iter("Macro"):
                command = macro.findtext("CLICommand")
                with self.subTest(command=command, size=size):
                    name = macro.find(tag).get("Name")
                    self.assertEqual(name, f"BOBROV_{command}_{size}.png")
                    data = self.entries[name]
                    self.assertEqual(png_size(data), (size, size))
                    referenced.append(data)
            self.assertEqual(len(set(referenced)), len(COMMANDS), "each command has its own icon")

    def test_saved_by_autocad_2020_format(self):
        # Spec 4.1: a file of the oldest target version (R23.1 = AutoCAD 2020) opens in newer ones.
        for name, data in self.entries.items():
            if not name.endswith(".cui"):
                continue
            for rev in ET.fromstring(data).iter():
                if rev.tag in ("ModifiedRev", "Revision"):
                    with self.subTest(name=name):
                        version = (int(rev.get("MajorVersion")), int(rev.get("MinorVersion")))
                        self.assertLessEqual(version, (23, 1))

    def test_uids_are_unique(self):
        uids = []
        for name, data in self.entries.items():
            if name.endswith(".cui"):
                uids += [e.get("UID") for e in ET.fromstring(data).iter() if e.get("UID")]
        duplicates = sorted({u for u in uids if uids.count(u) > 1})
        self.assertEqual(duplicates, [])


class CommandTest(unittest.TestCase):
    def setUp(self):
        group = xml("MenuGroup.cui")
        self.group = group
        self.macro = group.find(".//MenuMacro[@UID='ID_BOBROV_XDATAPALETTE']")

    def test_menu_group(self):
        self.assertEqual(self.group.get("Name"), "BOBROVMENU")

    def test_macro_is_the_recommended_toggle(self):
        macro = self.macro.find("Macro")
        self.assertEqual(macro.findtext("Name"), BUTTON)
        self.assertEqual(macro.findtext("Command"), MACRO)
        self.assertTrue(macro.findtext("Command").endswith("_XDATAPALETTE "), "trailing space ends the input")
        self.assertEqual(macro.findtext("HelpString"), TOOLTIP)

    def test_label_is_neutral(self):
        # Spec 6: no on/off state and no «Включить»/«Выключить» in labels.
        text = " ".join(t for d in cuix_entries().values() for t in [d.decode("utf-8", "ignore")])
        for word in ("Включить", "Выключить", "Скрыть палитру", "Показать палитру"):
            self.assertNotIn(word, text)

    def test_no_forbidden_content(self):
        # Keep startup and workspace settings out of the partial menu.
        bobrov = b"".join(cuix_entries().values()) + PACKAGE_CONTENTS.read_bytes()
        text = re.sub(r"<!--.*?-->", "", bobrov.decode("utf-8", "ignore"), flags=re.S).upper()
        for word in ("XDATAPALETTE_ON", "XDATAPALETTE_OFF", "NETLOAD", ".DLL", ".LSP", ".FAS", ".VLX",
                     "MENUBAR", "WSCURRENT", "(COMMAND", "(LOAD", "STARTUPCOMMAND", "LOADONAUTOCADSTARTUP",
                     "ACADPALETTESETXDATA"):
            with self.subTest(word=word):
                self.assertNotIn(word, text)

    def test_only_expected_commands_and_matching_global_macros(self):
        macros = list(self.group.iter("Macro"))
        self.assertCountEqual([m.findtext("CLICommand") for m in macros], COMMANDS)
        for macro in macros:
            command = macro.findtext("CLICommand")
            if command != "XDATAPALETTE":
                with self.subTest(command=command):
                    self.assertEqual(
                        macro.findtext("Command"),
                        f"$M=$(if,$(getvar,cmdactive),^C^C)_{command};",
                    )

    def test_no_workspaces_are_defined(self):
        root = xml("WorkspaceRoot.cui")
        self.assertEqual(root.findall(".//Workspace"), [])


class MenuAndRibbonTest(unittest.TestCase):
    def setUp(self):
        self.macro_id = "ID_BOBROV_XDATAPALETTE"

    def test_pull_down_menu(self):
        menus = xml("PopMenuRoot.cui").findall("PopMenu")
        self.assertEqual(len(menus), 1)
        menu = menus[0]
        self.assertEqual(menu.findtext("Name"), "Bobrov")
        self.assertIn("POP1", [a.text for a in menu.findall("Alias")])
        items = menu.findall("PopMenuItem")
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.get("IsSeparator"), "false")
        # AutoCAD's PopMenuItem reader uses NameRef for the menu item's label.
        self.assertEqual(item.findtext("NameRef"), BUTTON)
        self.assertEqual(item.find("MenuItem/MacroRef").get("MenuMacroID"), self.macro_id)

    def test_ribbon_tab_panel_and_large_button(self):
        ribbon = xml("RibbonRoot.cui")
        panels = {p.get("UID"): p for p in ribbon.iter("RibbonPanelSource")}
        tabs = list(ribbon.iter("RibbonTabSource"))
        self.assertEqual(len(tabs), 1)
        tab = tabs[0]
        self.assertEqual(tab.findtext("Name"), "Bobrov")
        self.assertEqual(tab.get("Text"), "Bobrov")
        # Shown in every workspace without changing the workspaces of the user.
        self.assertEqual(tab.get("DefaultDisplay"), "AddToWorkspace")
        refs = tab.findall("RibbonPanelSourceReference")
        self.assertCountEqual([ref.get("PanelId") for ref in refs], panels)
        self.assertEqual([panels[ref.get("PanelId")].get("Text") for ref in refs], list(RIBBON_COMMANDS))
        macros = {m.get("UID"): m.find("Macro") for m in xml("MenuGroup.cui").iter("MenuMacro")}
        for panel in panels.values():
            title = panel.get("Text")
            with self.subTest(panel=title):
                self.assertEqual(panel.findtext("Name"), title)
                buttons = list(panel.iter("RibbonCommandButton"))
                self.assertEqual(
                    [(macros[b.get("MenuMacroID")].findtext("CLICommand"), b.get("Text")) for b in buttons],
                    RIBBON_COMMANDS[title],
                )
                for button in buttons:
                    self.assertEqual(button.get("ButtonStyle"), "LargeWithText")
                    self.assertEqual(button.findtext("TooltipTitle"), button.get("Text"))
                    self.assertEqual(macros[button.get("MenuMacroID")].findtext("Name"), button.get("Text"))


class BundleTest(unittest.TestCase):
    def setUp(self):
        self.root = ET.parse(PACKAGE_CONTENTS).getroot()

    def test_bundle_files(self):
        bundle = PACKAGE_CONTENTS.parent
        files = sorted(p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file())
        self.assertEqual(files, ["Contents/BobrovMenu.cuix", "PackageContents.xml"])

    def test_component_and_runtime_requirements(self):
        entries = self.root.findall("Components/ComponentEntry")
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.get("AppName"), "BobrovMenu")
        self.assertEqual(entry.get("ModuleName"), "./Contents/BobrovMenu.cuix")
        self.assertTrue((PACKAGE_CONTENTS.parent / entry.get("ModuleName")).is_file())
        requirements = entry.find("RuntimeRequirements")
        self.assertEqual(
            dict(requirements.attrib),
            {"OS": "Win64", "Platform": "AutoCAD*", "SeriesMin": "R23.1"},
        )
        for attribute in ("LoadOnAutoCADStartup", "LoadOnCommandInvocation", "LoadReasons"):
            self.assertIsNone(entry.get(attribute))
        self.assertIsNone(entry.find("Commands"))

    def test_new_guids(self):
        codes = [self.root.get("ProductCode"), self.root.get("UpgradeCode")]
        parsed = [str(uuid.UUID(code.strip("{}"))) for code in codes]
        self.assertEqual(len(set(parsed)), 2)
        self.assertFalse(set(parsed) & PLUGIN_GUIDS, "GUIDs must differ from acadPaletteSetXDATA")
        self.assertEqual(self.root.get("AutodeskProduct"), "AutoCAD")
        self.assertEqual(self.root.get("Name"), "BobrovMenu")


class ManualInstallTest(unittest.TestCase):
    def test_scripts_target_only_the_bundle(self):
        target = r"%APPDATA%\Autodesk\ApplicationPlugins\BobrovMenu.bundle"
        for name in ("install.cmd", "uninstall.cmd"):
            text = (MANUAL / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn('set "TARGET=%s"' % target, text)
                self.assertNotIn("acadPaletteSetXDATA.bundle\"", text)
                for word in ("MENUBAR", "WSCURRENT", "acad.exe", "reg add"):
                    self.assertNotIn(word, text)
        self.assertIn("rmdir /s /q \"%TARGET%\"", (MANUAL / "uninstall.cmd").read_text(encoding="utf-8"))

    def test_archive_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            package.main(["--version", "v0.2.42", "--commit", "0123abc", "--output-dir", tmp])
            path = Path(tmp, "BobrovMenu-manual-install-v0.2.42.zip")
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                prefix = package.BUNDLE_PREFIX
                self.assertEqual(sorted(names), sorted([
                    prefix + "PackageContents.xml", prefix + "Contents/BobrovMenu.cuix",
                    "install.cmd", "uninstall.cmd", "INSTALL.md", "release-manifest.txt",
                ]))
                self.assertEqual(archive.read(prefix + "Contents/BobrovMenu.cuix"), CUIX.read_bytes())
                contents = archive.read(prefix + "PackageContents.xml").decode("utf-8")
                self.assertIn('AppVersion="0.2.42"', contents)
                for name in ("install.cmd", "uninstall.cmd"):
                    data = archive.read(name)
                    self.assertEqual(data.count(b"\n"), data.count(b"\r\n"), name + " must use CRLF")
                manifest = archive.read("release-manifest.txt").decode("utf-8")
                self.assertIn("v0.2.42", manifest)
                self.assertIn("0123abc", manifest)
                for name in names:
                    if name != "release-manifest.txt":
                        digest = hashlib.sha256(archive.read(name)).hexdigest()
                        self.assertIn(f"{digest}  {name}", manifest.splitlines())
                entries = ET.fromstring(contents).findall("Components/ComponentEntry")
                self.assertCountEqual(
                    [prefix + entry.get("ModuleName")[2:] for entry in entries],
                    [prefix + "Contents/BobrovMenu.cuix"],
                )

    def test_version_is_validated(self):
        self.assertEqual(package.app_version("v1.2.3"), "1.2.3")
        with self.assertRaises(SystemExit):
            package.app_version("latest")


if __name__ == "__main__":
    unittest.main()
