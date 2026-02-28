import csv
import io
import sqlite3
from dataclasses import dataclass, field
from datetime import date as DateType
from datetime import datetime
from pathlib import Path


@dataclass
class CallRecord:
    model: str
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    total_tokens: int
    cost_usd: float
    timestamp: str = field(default="")

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().astimezone().isoformat()


_CSV_FIELDS = [
    "id",
    "timestamp",
    "model",
    "input_tokens",
    "output_tokens",
    "thinking_tokens",
    "total_tokens",
    "cost_usd",
]

_CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS call_history (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp       TEXT    NOT NULL,
        model           TEXT    NOT NULL,
        input_tokens    INTEGER NOT NULL DEFAULT 0,
        output_tokens   INTEGER NOT NULL DEFAULT 0,
        thinking_tokens INTEGER NOT NULL DEFAULT 0,
        total_tokens    INTEGER NOT NULL DEFAULT 0,
        cost_usd        REAL    NOT NULL DEFAULT 0.0
    )
"""

_INSERT_SQL = """
    INSERT INTO call_history
        (timestamp, model, input_tokens, output_tokens,
         thinking_tokens, total_tokens, cost_usd)
    VALUES (?, ?, ?, ?, ?, ?, ?)
"""


def _fmt_ts(ts: str) -> str:
    """ISO 8601 UTC タイムスタンプを "YYYY-MM-DD HH:MM:SS" に変換する（CSV 表示用）。"""
    return ts[:19].replace("T", " ")


def _prepare_rows(rows: list[dict]) -> list[dict]:
    """CSV 書き込み用にタイムスタンプをフォーマット変換したコピーを返す。"""
    return [{**r, "timestamp": _fmt_ts(r["timestamp"])} for r in rows]


def _to_date_str(d: str | DateType) -> str:
    """引数を "YYYY-MM-DD" 文字列に正規化する。"""
    return str(d)[:10]


class HistoryDB:
    """
    SQLite を使った呼び出し履歴管理。DB ファイルは初回アクセス時に自動作成される。
    ":memory:" を指定するとインメモリ DB として動作する（テスト用途）。

    日付フィルタリング:
        日付は "YYYY-MM-DD" 文字列または datetime.date オブジェクトで指定する。
        タイムスタンプは実行環境のローカルタイムゾーンで保存されるため、
        日付比較もローカルタイムゾーン基準となる。
    """

    def __init__(self, db_path: str | Path = "history.db"):
        self._db_path_str = str(db_path)
        # :memory: の場合は単一接続を保持して再利用する
        if self._db_path_str == ":memory:":
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            self._conn = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        return sqlite3.connect(self._db_path_str)

    def _init_db(self) -> None:
        conn = self._connect()
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()
        if self._conn is None:
            conn.close()

    def save(self, record: CallRecord) -> None:
        """レコードを DB に保存する。"""
        with self._connect() as conn:
            conn.execute(_INSERT_SQL, (
                record.timestamp,
                record.model,
                record.input_tokens,
                record.output_tokens,
                record.thinking_tokens,
                record.total_tokens,
                record.cost_usd,
            ))

    # ------------------------------------------------------------------
    # 内部共通クエリ
    # ------------------------------------------------------------------

    def _query(self, where: str = "", params: tuple = ()) -> list[dict]:
        """WHERE 句を受け取って call_history を昇順で返す内部ヘルパー。"""
        sql = "SELECT * FROM call_history"
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY id ASC"
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def _write_csv(self, output_path: Path, rows: list[dict]) -> None:
        """rows を CSV ファイルに出力する内部ヘルパー。"""
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(_prepare_rows(rows))

    # ------------------------------------------------------------------
    # 全件取得
    # ------------------------------------------------------------------

    def get_all(self) -> list[dict]:
        """全履歴を古い順（id ASC）で返す。"""
        return self._query()

    def get_total_cost(self) -> float:
        """全履歴のコスト合計（USD）を返す。"""
        with self._connect() as conn:
            result = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) FROM call_history"
            ).fetchone()
        return result[0]

    def to_csv_string(self) -> str:
        """全履歴を CSV 文字列として返す（BOM なし UTF-8）。"""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(_prepare_rows(self.get_all()))
        return buf.getvalue().replace("\r\n", "\n")

    def to_csv(self, output_path: str | Path) -> None:
        """全履歴を CSV ファイルに出力する。"""
        self._write_csv(Path(output_path), self.get_all())

    # ------------------------------------------------------------------
    # 指定日付
    # ------------------------------------------------------------------

    def get_by_date(self, date: str | DateType) -> list[dict]:
        """指定日付（UTC）の履歴を返す。"""
        d = _to_date_str(date)
        return self._query("DATE(timestamp) = ?", (d,))

    def get_cost_by_date(self, date: str | DateType) -> float:
        """指定日付（UTC）のコスト合計（USD）を返す。"""
        return sum(r["cost_usd"] for r in self.get_by_date(date))

    def to_csv_by_date(self, output_path: str | Path, date: str | DateType) -> None:
        """指定日付（UTC）の履歴を CSV ファイルに出力する。"""
        self._write_csv(Path(output_path), self.get_by_date(date))

    # ------------------------------------------------------------------
    # 指定日付範囲
    # ------------------------------------------------------------------

    def get_by_date_range(
        self, start: str | DateType, end: str | DateType
    ) -> list[dict]:
        """指定日付範囲（UTC, 両端含む）の履歴を返す。"""
        return self._query(
            "DATE(timestamp) >= ? AND DATE(timestamp) <= ?",
            (_to_date_str(start), _to_date_str(end)),
        )

    def get_cost_by_date_range(
        self, start: str | DateType, end: str | DateType
    ) -> float:
        """指定日付範囲（UTC, 両端含む）のコスト合計（USD）を返す。"""
        return sum(r["cost_usd"] for r in self.get_by_date_range(start, end))

    def to_csv_by_date_range(
        self, output_path: str | Path, start: str | DateType, end: str | DateType
    ) -> None:
        """指定日付範囲（UTC, 両端含む）の履歴を CSV ファイルに出力する。"""
        self._write_csv(Path(output_path), self.get_by_date_range(start, end))
