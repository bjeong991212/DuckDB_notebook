"""Execute the actual notebook cells against small, independent Parquet fixtures."""
import ast
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

import duckdb
import nbformat


NOTEBOOK = Path(__file__).resolve().parents[1] / "parquet_query.ipynb"


class NotebookSession:
    def __init__(self, paths, root, **settings):
        self.cells = [c.source for c in nbformat.read(NOTEBOOK, as_version=4).cells
                      if c.cell_type == "code"]
        self.namespace = {}
        self.settings = {"PARQUET_PATHS": paths, "PROJECT_ROOT": str(root), **settings}
        try:
            for index in range(len(self.cells)):
                self.run_cell(index)
        except Exception:
            self.close()
            raise

    def run_cell(self, index, **settings):
        overrides = {**self.settings, **settings}
        tree = ast.parse(self.cells[index])
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id in overrides:
                    value = overrides[target.id]
                    expression = f"Path({value!r})" if target.id == "PROJECT_ROOT" else repr(value)
                    node.value = ast.parse(expression, mode="eval").body
        ast.fix_missing_locations(tree)
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(tree, f"notebook-cell-{index}", "exec"), self.namespace)
        self.namespace["display"] = lambda *args, **kwargs: None

    def query(self, **kwargs):
        sql, params = self.namespace["build_query"](**kwargs)
        return self.namespace["con"].execute(sql, params).fetchdf()

    def close(self):
        if "con" in self.namespace:
            self.namespace["con"].close()


class NotebookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="parquet-notebook-tests-")
        cls.root = Path(cls.temp.name)
        cls.fixture = cls.root / "data[1].parquet"
        con = duckdb.connect()
        con.execute("""
            CREATE TABLE fixture AS
            SELECT 1 AS id, 10.25::DECIMAL(12,2) AS amount, 'A' AS category,
                   '100% alpha' AS label, DATE '2026-01-01' AS event_date,
                   TIMESTAMPTZ '2026-01-01 00:00:00+00' AS event_time,
                   'literal dot' AS "a.b", 'quoted' AS "odd""name",
                   {'city': 'Seoul', 'score': 10} AS payload,
                   [{'k': 'x', 'v': 1}, {'k': 'y', 'v': 2}] AS items,
                   ['one', 'two'] AS tags, MAP(['a', 'b'], [1, 2]) AS mapping
            UNION ALL
            SELECT 2, 20.50, 'B', 'plain', DATE '2026-01-02',
                   TIMESTAMPTZ '2026-01-02 00:00:00+00', 'other', 'quoted',
                   {'city': 'Busan', 'score': 20}, [], [], MAP([], [])
            UNION ALL
            SELECT 3, NULL, NULL, NULL, DATE '2026-01-03',
                   TIMESTAMPTZ '2026-01-03 00:00:00+00', NULL, NULL,
                   NULL, NULL, NULL, NULL
        """)
        con.table("fixture").write_parquet(str(cls.fixture))
        cls.empty = cls.root / "empty.parquet"
        con.sql("SELECT * FROM fixture WHERE FALSE").write_parquet(str(cls.empty))
        cls.nonfinite = cls.root / "nonfinite.parquet"
        con.sql("""
            SELECT x FROM (VALUES (1.0::DOUBLE), (3.0::DOUBLE),
                ('NaN'::DOUBLE), ('Infinity'::DOUBLE), ('-Infinity'::DOUBLE), (NULL)) t(x)
        """).write_parquet(str(cls.nonfinite))
        cls.nested_only = cls.root / "nested_only.parquet"
        con.sql("SELECT {'items': [1,2]} AS payload").write_parquet(str(cls.nested_only))
        cls.parts = cls.root / "parts"
        cls.parts.mkdir()
        con.sql("SELECT 1 AS id, 'a' AS extra").write_parquet(str(cls.parts / "a.parquet"))
        con.sql("SELECT 2 AS id").write_parquet(str(cls.parts / "b.parquet"))
        con.close()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.session = NotebookSession(str(self.fixture), self.root)
        self.addCleanup(self.session.close)

    def test_default_profile_and_bounded_scope(self):
        n = self.session.namespace
        self.assertEqual(len(n["result"]), 3)
        profile = n["profile"].set_index("column")
        self.assertEqual(profile.loc["amount", "nulls"], 1)
        self.assertEqual(profile.loc["amount", "min"], "10.25")
        stats = n["numeric_summary"](["amount"])
        self.assertAlmostEqual(float(stats.iloc[0]["mean"]), 15.375)
        self.session.run_cell(3, PROFILE_ROWS=1)
        self.assertEqual(n["profile_count"], 1)
        self.assertEqual(len(self.session.query()), 3)
        self.session.run_cell(3, PROFILE_ROWS=None)
        self.assertEqual(n["profile_count"], 3)

    def test_numeric_dates_nulls_and_paging(self):
        query = self.session.query
        self.assertEqual(query(filters=[("amount", ">=", 10), ("amount", "<", 20)])["id"].tolist(), [1])
        self.assertEqual(query(filters=[("event_date", ">=", "2026-01-02"),
                                        ("event_date", "<", "2026-01-03")])["id"].tolist(), [2])
        self.assertEqual(query(filters=[("event_time", ">=", "2026-01-01T09:00:00+09:00"),
                                        ("event_time", "<", "2026-01-02T09:00:00+09:00")])["id"].tolist(), [1])
        self.assertEqual(query(filters=[("amount", "is null", None)])["id"].tolist(), [3])
        self.assertEqual(query(filters=[("category", "not in", ["B"])])["id"].tolist(), [1])
        self.assertTrue(query(filters=[("id", "in", [])]).empty)
        self.assertEqual(query(order_by=[("id", "desc")], limit=1, offset=1)["id"].tolist(), [2])

    def test_quoted_names_and_literal_filter_values(self):
        query = self.session.query
        result = query(selected_columns=["a.b", 'odd"name', ("payload", "city")],
                       filters=[(("payload", "city"), "=", "Seoul")])
        self.assertEqual(result.iloc[0].tolist(), ["literal dot", "quoted", "Seoul"])
        self.assertTrue(query(filters=[("category", "=", "A' OR TRUE --")]).empty)
        self.assertEqual(query(filters=[("label", "contains", "%")])["id"].tolist(), [1])
        for args in [dict(filters=[("id", "DROP TABLE", 1)]),
                     dict(selected_columns=["missing"]), dict(limit=0), dict(offset=-1),
                     dict(filters=[("id", "=", None)]),
                     dict(filters=[("id", "in", [None])])]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                query(**args)

    def test_nested_struct_lists_and_maps(self):
        inspect = self.session.namespace["inspect_nested"]
        self.assertEqual(inspect("payload", ["id"]).df()["value.city"].iloc[0], "Seoul")
        items = inspect("items", ["id"]).df()
        self.assertEqual(items["parent.id"].tolist(), [1, 1])
        self.assertEqual(items["value.v"].tolist(), [1, 2])
        self.assertEqual(inspect("tags").df()["value"].tolist(), ["one", "two"])
        self.assertEqual(inspect("mapping").df()["value.key"].tolist(), ["a", "b"])
        self.assertEqual(len(inspect("items", parent_rows=1, limit=1).df()), 1)

    def test_custom_sql_parameters_and_read_queries(self):
        run = self.session.namespace["run_sql"]
        result = run("WITH t AS (SELECT * FROM data WHERE id > ?) SELECT id FROM t ORDER BY id", [1], 1).df()
        self.assertEqual(result["id"].tolist(), [2])
        for sql in ["DROP VIEW data", "SELECT 1; SELECT 2"]:
            with self.assertRaises(ValueError):
                run(sql)
        self.session.run_cell(7, CUSTOM_SQL="SELECT count(*) AS n FROM data")
        self.assertEqual(self.session.namespace["sql_result"]["n"].tolist(), [3])

    def test_empty_nested_only_and_nonfinite_files(self):
        for path in [self.empty, self.nested_only, self.nonfinite]:
            with self.subTest(path=path.name):
                session = NotebookSession(str(path), self.root)
                try:
                    if path == self.empty:
                        self.assertTrue(session.namespace["result"].empty)
                        self.assertEqual(session.namespace["profile_count"], 0)
                    elif path == self.nested_only:
                        self.assertIsNone(session.namespace["frequency_column"])
                        self.assertEqual(session.namespace["inspect_nested"](("payload", "items")).df()["value"].tolist(), [1, 2])
                    else:
                        stats = session.namespace["numeric_summary"](["x"]).iloc[0]
                        self.assertEqual(stats["non_finite"], 3)
                        self.assertEqual(stats["mean"], 2)
                        self.assertEqual(stats["median"], 2)
                finally:
                    session.close()

    def test_file_discovery_and_schema_union(self):
        session = NotebookSession([str(self.parts), str(self.parts / "a.parquet")], self.root)
        self.addCleanup(session.close)
        self.assertEqual(len(session.namespace["files"]), 2)
        result = session.query(order_by=[("id", "asc")])
        self.assertEqual(result["id"].tolist(), [1, 2])
        self.assertEqual(result["extra"].isna().tolist(), [False, True])
        resolve = session.namespace["resolve_files"]
        self.assertEqual(len(resolve(str(self.parts / "*.parquet"))), 2)
        self.assertEqual(resolve(str(self.fixture)), [str(self.fixture)])
        with self.assertRaises(FileNotFoundError):
            resolve(str(self.root / "missing*.parquet"))

    def test_exports_preserve_types_and_existing_files(self):
        self.session.run_cell(5, FILTERS=[("id", "<", 3)], ORDER_BY=[("id", "asc")])
        self.session.run_cell(8, EXPORT_FORMAT="parquet", EXPORT_STEM="typed")
        con = self.session.namespace["con"]
        path = self.root / "exports" / "typed.parquet"
        restored = con.read_parquet(str(path))
        self.assertEqual(restored.types, con.table("data").types)
        self.assertEqual(restored.count("*").fetchone()[0], 2)
        original_bytes = path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.session.run_cell(8, EXPORT_FORMAT="parquet", EXPORT_STEM="typed")
        self.assertEqual(path.read_bytes(), original_bytes)
        self.session.run_cell(5, FILTERS=[("id", "<", 0)])
        self.session.run_cell(8, EXPORT_FORMAT="parquet", EXPORT_STEM="empty")
        empty = con.read_parquet(str(self.root / "exports" / "empty.parquet"))
        self.assertEqual(empty.types, con.table("data").types)
        self.assertEqual(empty.count("*").fetchone()[0], 0)
        self.session.run_cell(6, NESTED_FIELD="items", PARENT_COLUMNS=["id"])
        self.session.run_cell(8, EXPORT_FORMAT="parquet", EXPORT_RESULT="nested_result", EXPORT_STEM="nested")
        self.assertEqual(con.read_parquet(str(self.root / "exports" / "nested.parquet")).count("*").fetchone()[0], 2)
        self.session.run_cell(7, CUSTOM_SQL="SELECT id FROM data ORDER BY id LIMIT 1")
        self.session.run_cell(8, EXPORT_FORMAT="csv", EXPORT_RESULT="sql_result", EXPORT_STEM="query")
        self.assertEqual((self.root / "exports" / "query.csv").read_text(encoding="utf-8-sig"), "id\n1\n")


if __name__ == "__main__":
    unittest.main()
