import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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
        self.assertEqual(result.categories["decimal_diff"], 1)

    def test_equal_decimal_with_different_precision_is_only_decimal_difference(self):
        left = self.make_csv("left.csv", "id,value\n1,3.40\n")
        right = self.make_csv("right.csv", "id,value\n1,3.4000\n")

        result = compare(left, right, True, ("id",))

        self.assertNotIn("different_value", result.categories)
        self.assertEqual(result.categories["decimal_diff"], 1)
        self.assertEqual(
            [item["category"] for item in result.differences],
            ["decimal_diff", "decimal_diff"],
        )

    def test_equal_numeric_values_with_same_precision_are_not_differences(self):
        left = self.make_csv("left.csv", "id,value\n1,+03.40\n")
        right = self.make_csv("right.csv", "id,value\n1,3.40\n")

        result = compare(left, right, True, ("id",))

        self.assertNotIn("different_value", result.categories)
        self.assertNotIn("decimal_diff", result.categories)
        self.assertEqual(result.differences, [])

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
        self.assertEqual(
            list(rows[0]),
            [
                "data_source", "category", "k_id", "diff_column", "diff_value",
                "id", "value", "old", "new",
            ],
        )
        self.assertEqual(rows[0]["k_id"], "1")
        self.assertEqual(rows[0]["diff_column"], "value")
        self.assertEqual(rows[0]["diff_value"], "a")
        self.assertEqual(rows[0]["value"], "a")
        self.assertEqual(rows[0]["old"], "x")

    def test_source_category_header_does_not_overwrite_difference_category(self):
        left = self.make_csv(
            "left.csv", "id,category,value\n1,source-one,old\n"
        )
        right = self.make_csv(
            "right.csv", "id,category,value\n1,source-two,new\n"
        )
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

        with (report_dir / "differences.csv").open(
            newline="", encoding="utf-8"
        ) as file:
            rows = list(csv.DictReader(file))
        value_differences = [
            row for row in rows if row["diff_column"] == "value"
        ]

        self.assertEqual(
            {row["category"] for row in value_differences},
            {"different_value"},
        )
        self.assertEqual(
            {row["source_category"] for row in value_differences},
            {"source-one", "source-two"},
        )

    def test_report_folder_uses_short_local_timestamp_and_collision_suffix(self):
        left = self.make_csv("left.csv", "id,value\n1,a\n")
        right = self.make_csv("right.csv", "id,value\n1,b\n")
        config = Config(
            data_dir=self.root,
            file1=left.path,
            file2=right.path,
            reports=self.root / "reports",
            key=("id",),
            delimiter=",",
        )
        result = compare(left, right, True, ("id",))
        fixed_now = Mock()
        fixed_now.astimezone.return_value.strftime.return_value = "20261122-230712"

        with patch("csv_audit.reporting.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = fixed_now
            first = write_reports(config, left, right, result, True, None)
            second = write_reports(config, left, right, result, True, None)

        self.assertRegex(first.name, r"^\d{8}-\d{6}$")
        self.assertEqual(second.name, f"{first.name}-2")

    def test_examples_report_has_one_paired_example_per_category(self):
        left = self.make_csv("left.csv", "id,name,amount\n1,Alice,3.40\n")
        right = self.make_csv("right.csv", "id,name,amount\n1,Bob,3.4000\n")
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

        with (report_dir / "examples.csv").open(newline="", encoding="utf-8") as file:
            examples = list(csv.DictReader(file))
        by_category = {}
        for row in examples:
            by_category.setdefault(row["category"], []).append(row)

        self.assertEqual(
            set(by_category),
            {"different_value", "decimal_diff"},
        )
        self.assertEqual(len(by_category["different_value"]), 2)
        self.assertEqual(len(by_category["decimal_diff"]), 2)
        for rows in by_category.values():
            self.assertEqual(
                {row["data_source"] for row in rows},
                {"file1", "file2"},
            )

    def test_examples_pair_decimal_precision_rows_when_headers_differ(self):
        left = self.make_csv("left.csv", "id,amount\n1,3.40\n")
        right = self.make_csv("right.csv", "id,total\n1,3.4000\n")
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

        with (report_dir / "examples.csv").open(newline="", encoding="utf-8") as file:
            examples = list(csv.DictReader(file))
        decimal_examples = [
            row for row in examples
            if row["category"] == "decimal_diff"
        ]

        self.assertEqual(len(decimal_examples), 2)
        self.assertEqual(
            {row["data_source"] for row in decimal_examples},
            {"file1", "file2"},
        )
        self.assertEqual(
            {row["diff_column"] for row in decimal_examples},
            {"amount", "total"},
        )


if __name__ == "__main__":
    unittest.main()
