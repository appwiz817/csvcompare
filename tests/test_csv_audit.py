import csv
import tempfile
import unittest
from pathlib import Path

from csv_audit.compare import compare
from csv_audit.config import resolve_path
from csv_audit.csvio import read_csv


class CsvAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def make_csv(self, name, text, delimiter=","):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return read_csv(path, delimiter)

    def test_keyed_differences_missing_empty_and_decimal(self):
        a = self.make_csv("a.csv", "id,value\n1,1.0\n2,\n")
        b = self.make_csv("b.csv", "id,value\n1,1.00\n3,x\n")
        result = compare(a, b, True, ("id",))
        self.assertGreater(result.categories["different_value"], 0)
        self.assertEqual(result.categories["decimal_places_difference"], 1)
        self.assertEqual(result.categories["missing_from_target"], 1)
        self.assertEqual(result.categories["missing_from_source"], 1)
        self.assertIn("empty_value", result.categories)

    def test_duplicate_keys(self):
        a = self.make_csv("a.csv", "id,v\n1,a\n1,b\n")
        b = self.make_csv("b.csv", "id,v\n1,a\n")
        result = compare(a, b, True, ("id",))
        self.assertEqual(result.categories["duplicate_key"], 1)

    def test_no_key_exact_multiset(self):
        a = self.make_csv("a.csv", "v\nx\nx\ny\n")
        b = self.make_csv("b.csv", "v\nx\ny\n")
        result = compare(a, b, False, ())
        self.assertEqual(result.categories["missing_from_target"], 1)

    def test_pipe_and_tab_delimiters(self):
        self.assertEqual(self.make_csv("p.csv", "id|v\n1|x\n", "|").rows[0]["v"], "x")
        self.assertEqual(self.make_csv("t.csv", "id\tv\n1\tx\n", "\t").rows[0]["v"], "x")

    def test_limit_after_matching(self):
        a = self.make_csv("a.csv", "id,v\n1,a\n2,b\n")
        b = self.make_csv("b.csv", "id,v\n1,x\n2,y\n")
        result = compare(a, b, True, ("id",), limit=1)
        self.assertEqual(result.units_considered, 1)
        self.assertEqual(result.categories["different_value"], 1)

    def test_path_resolution(self):
        self.assertEqual(resolve_path("file.csv", self.root), (self.root / "file.csv").resolve())
        absolute = (self.root / "absolute.csv").resolve()
        self.assertEqual(resolve_path(str(absolute), self.root), absolute)


if __name__ == "__main__":
    unittest.main()
