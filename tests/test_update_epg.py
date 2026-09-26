import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location("updater", Path(__file__).resolve().parents[1] / "scripts/update_epg.py")
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


def programme(start, stop, title="Test", channel="x"):
    p = ET.Element("programme", channel=channel, start=start, stop=stop)
    ET.SubElement(p, "title").text = title
    return p


class EPGTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
        self.p = programme("20260926130000 +0000", "20260926140000 +0000")
        self.channel = {"id": "x", "name": "X"}

    def test_timezone_represents_same_instant(self):
        self.assertEqual(u.stamp("20260926140000 +0200"), self.now)

    def test_invalid_and_overlapping_programmes_are_removed(self):
        bad = programme("20260926150000 +0000", "20260926140000 +0000")
        overlap = programme("20260926133000 +0000", "20260926143000 +0000")
        result = u.canonical_programmes([self.p, self.p, bad, overlap], self.now)
        self.assertEqual(len(result), 1)

    def test_failed_channel_uses_only_still_valid_previous_guide(self):
        _, rows = u.assemble([self.channel], {}, {"x": [self.p]}, self.now)
        self.assertEqual(rows[0]["status"], "previous")

    def test_expired_guide_is_not_counted_as_covered(self):
        expired = programme("20260925120000 +0000", "20260925130000 +0000")
        root, rows = u.assemble([self.channel], {}, {"x": [expired]}, self.now)
        self.assertEqual(rows[0]["status"], "missing")
        self.assertEqual(root.findall("programme"), [])

    def test_only_requested_ids_are_imported_from_gzip(self):
        root = ET.Element("tv")
        root.extend([self.p, programme("20260926130000 +0000", "20260926140000 +0000", channel="other")])
        result = u.parse_xmltv(gzip.compress(ET.tostring(root)), {"x"})
        self.assertEqual(set(result), {"x"})
        self.assertEqual(result["x"][0].findtext("title"), "Test")

    def test_zappr_invalid_control_chars_and_timezone(self):
        c = {"id": "x", "provider": "rai", "source_id": "one"}
        payload = {"rai": {"one": [{"name": "A\u0001B", "startTime": {"iso": "2026-09-26T14:00:00+02:00"}, "endTime": {"iso": "2026-09-26T15:00:00+02:00"}}]}}
        p = u.parse_zappr(json.dumps(payload).encode(), [c])["x"][0]
        self.assertEqual(p.findtext("title"), "AB")
        self.assertEqual(u.stamp(p.get("start")), self.now)

    def test_total_source_failure_preserves_published_file(self):
        with u.scratch_directory() as folder:
            root = Path(folder)
            (root / "epg").mkdir()
            (root / "playlist.m3u").write_text('#EXTM3U\n#EXTINF:-1 tvg-id="x",X\nhttps://example.org/live\n')
            c = {**self.channel, "format": "xmltv", "source_id": "x", "source_url": "https://example.org/epg"}
            (root / "epg/channels.json").write_text(json.dumps({"channels": [c]}))
            initial = gzip.compress(b'<tv><channel id="x"><display-name>X</display-name></channel></tv>')
            output = root / "JackTV_EPG.xml.gz"
            output.write_bytes(initial)
            with patch.object(u, "fetch_source", side_effect=OSError("unavailable")):
                with self.assertRaises(RuntimeError):
                    u.main(["--root", str(root)])
            self.assertEqual(output.read_bytes(), initial)
            self.assertFalse((root / "epg/status.json").exists())

    def test_dtd_is_rejected(self):
        with self.assertRaises(ValueError):
            u.parse_xmltv(b'<!DOCTYPE tv [<!ENTITY x "bad">]><tv/>', {"x"})


if __name__ == "__main__":
    unittest.main()
