import csv
import tempfile
import unittest
from pathlib import Path

from csv_audit.compare import compare
from csv_audit.config import Config, resolve_path
from csv_audit.csvio import read_csv
from csv_audit.reporting import write_reports


class CsvAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_csv(self, name, text, delimiter=","):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return read_csv(path, delimiter)

    def test_keyed_difference_and_decimal_places(self):
        left = self.make_csv("left.csv", "id,value\n1,3.0\n")
        right = self.make_csv("right.csv", "id,value\n1,5.00\n")
        result = compare(left, right, True, ("id",))
        self.assertEqual(result.categories["different_value"], 1)
        self.assertEqual(result.categories["decimal_places_difference"], 1)

    # def test_default_ignores_case_whitespace_and_blank_null_pairs(self):
    #     left = self.make_csv("left.csv", "id,name,empty\n1, Alice ,\n")
    #     right = self.make_csv("right.csv", "id,name,empty\n1,alice,NULL\n")
    #     result = compare(left, right, True, ("id",))
    #     self.assertNotIn("different_value", result.categories)

    def test_blank_and_null_marker_are_reported(self):
        left = self.make_csv("left.csv", "id,value\n1,\n")
        right = self.make_csv("right.csv", "id,value\n1,NULL\n")
        result = compare(left, right, True, ("id",))
        self.assertEqual(result.categories["different_value"], 1)

    def test_both_whitespace_only_values_are_ignored(self):
        left = self.make_csv("left.csv", "id,value\n1,   \n")
        right = self.make_csv("right.csv", "id,value\n1,\t\n")
        result = compare(left, right, True, ("id",))
        self.assertNotIn("different_value", result.categories)


    def test_flags_can_make_case_and_whitespace_significant(self):
        left = self.make_csv("left.csv", "id,name\n1, Alice\n")
        right = self.make_csv("right.csv", "id,name\n1,alice\n")
        result = compare(
            left, right, True, ("id",),
            case_sensitive=True, trim_whitespace=False,
        )
        self.assertEqual(result.categories["different_value"], 1)

    def test_duplicate_keys_and_missing_records(self):
        left = self.make_csv("left.csv", "id,value\n1,a\n1,b\n2,c\n")
        right = self.make_csv("right.csv", "id,value\n1,a\n3,d\n")
        result = compare(left, right, True, ("id",))
        self.assertEqual(result.categories["duplicate_key"], 1)
        self.assertEqual(result.categories["missing_from_target"], 2)
        self.assertEqual(result.categories["missing_from_source"], 1)

    def test_no_key_exact_multiset(self):
        left = self.make_csv("left.csv", "value\nx\nx\ny\n")
        right = self.make_csv("right.csv", "value\nx\ny\n")
        result = compare(left, right, False, ())
        self.assertEqual(result.categories["missing_from_target"], 1)

    def test_tab_and_pipe_delimiters(self):
        pipe = self.make_csv("pipe.csv", "id|value\n1|x\n", "|")
        tab = self.make_csv("tab.csv", "id\tvalue\n1\tx\n", "\t")
        self.assertEqual(pipe.rows[0]["value"], "x")
        self.assertEqual(tab.rows[0]["value"], "x")

    def test_limit_is_applied_after_matching(self):
        left = self.make_csv("left.csv", "id,value\n1,a\n2,b\n")
        right = self.make_csv("right.csv", "id,value\n1,x\n2,y\n")
        result = compare(left, right, True, ("id",), limit=1)
        self.assertEqual(result.units_considered, 1)
        self.assertEqual(result.categories["different_value"], 1)

    def test_path_resolution(self):
        self.assertEqual(
            resolve_path("file.csv", self.root),
            (self.root / "file.csv").resolve(),
        )
        absolute = (self.root / "absolute.csv").resolve()
        self.assertEqual(resolve_path(str(absolute), self.root), absolute)

    def test_reports_include_headers_and_examples(self):
        left = self.make_csv("left.csv", "id,value,old\n1,a,x\n")
        right = self.make_csv("right.csv", "id,value,new\n1,b,y\n")
        config = Config(
            data_dir=self.root,
            file1=left.path,
            file2=right.path,
            reports=self.root / "reports",
            key=("id",),
            delimiter=",",
        )
        result = compare(left, right, True, ("id",))
        report_dir = write_reports(config, left, right, result, True, None)

        self.assertTrue((report_dir / "summary.csv").exists())
        self.assertTrue((report_dir / "differences.csv").exists())
        self.assertTrue((report_dir / "examples.csv").exists())

        with (report_dir / "summary.csv").open(newline="", encoding="utf-8") as f:
            summary = list(csv.reader(f))
        self.assertIn(
            ["headers_only_in_file1", "['old']"],
            summary,
        )
        self.assertIn(
            ["headers_only_in_file2", "['new']"],
            summary,
        )

        with (report_dir / "differences.csv").open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["key__id"], "1")
        self.assertEqual(rows[0]["record__value"], "a")
        self.assertEqual(rows[0]["issue_column_value"], "a")


if __name__ == "__main__":
    unittest.main()
