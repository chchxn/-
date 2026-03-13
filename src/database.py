"""
database.py
SQLite 기반 원본 데이터 DB 및 검사 이력 저장소
"""

import sqlite3
import os
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'db', 'inspection.db')


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """테이블 초기화 (최초 1회)"""
    conn = get_connection()
    cur = conn.cursor()

    # 원본 이미지 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS original_images (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            order_info  TEXT NOT NULL,         -- 예: 3029C003AA
            serial_no   TEXT NOT NULL,         -- 예: 2EQ02001
            step_no     INTEGER NOT NULL,      -- 0, 1, 2, ...
            file_path   TEXT NOT NULL,         -- 원본 파일 경로
            file_name   TEXT NOT NULL,
            image_blob  BLOB,                  -- 원본 이진 데이터 (선택)
            created_at  TEXT NOT NULL
        )
    """)

    # 검사 이력 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS inspection_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            order_info      TEXT NOT NULL,
            serial_no       TEXT NOT NULL,
            barcode_text    TEXT,
            step_no         INTEGER NOT NULL,
            part_no         TEXT NOT NULL,     -- 구분 번호 (예: C550)
            part_name       TEXT,
            matching_score  REAL,              -- 0.0 ~ 1.0
            result          TEXT NOT NULL,     -- OK / NG
            result_detail   TEXT,              -- 원형 표기 예: "①"
            visualized_path TEXT,              -- 결과 시각화 이미지 경로
            error_flag      INTEGER DEFAULT 0, -- 0=정상, 1=오류
            inspected_at    TEXT NOT NULL
        )
    """)

    # 예외 로그 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS error_logs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            order_info   TEXT,
            serial_no    TEXT,
            step_no      INTEGER,
            error_type   TEXT NOT NULL,
            error_msg    TEXT NOT NULL,
            stack_trace  TEXT,
            occurred_at  TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    print(f"[DB] 초기화 완료: {os.path.abspath(DB_PATH)}")


def save_original_image(order_info: str, serial_no: str, step_no: int,
                        file_path: str, save_blob: bool = False):
    """원본 이미지 정보를 DB에 저장"""
    conn = get_connection()
    blob = None
    if save_blob and os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            blob = f.read()

    conn.execute("""
        INSERT INTO original_images
            (order_info, serial_no, step_no, file_path, file_name, image_blob, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        order_info, serial_no, step_no,
        os.path.abspath(file_path),
        os.path.basename(file_path),
        blob,
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()


def save_inspection_log(order_info: str, serial_no: str, barcode_text: str,
                        step_no: int, part_no: str, part_name: str,
                        matching_score: float, result: str,
                        result_detail: str = "", visualized_path: str = ""):
    """검사 결과를 DB에 저장"""
    conn = get_connection()
    conn.execute("""
        INSERT INTO inspection_logs
            (order_info, serial_no, barcode_text, step_no, part_no, part_name,
             matching_score, result, result_detail, visualized_path, error_flag, inspected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
    """, (
        order_info, serial_no, barcode_text,
        step_no, part_no, part_name,
        round(matching_score, 4), result,
        result_detail, visualized_path,
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()


def save_error_log(error_type: str, error_msg: str, stack_trace: str = "",
                   order_info: str = "", serial_no: str = "", step_no: int = -1):
    """예외 로그를 DB에 저장"""
    conn = get_connection()
    conn.execute("""
        INSERT INTO error_logs
            (order_info, serial_no, step_no, error_type, error_msg, stack_trace, occurred_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        order_info, serial_no, step_no,
        error_type, error_msg, stack_trace,
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()


# ── 조회 함수들 ────────────────────────────────────────────────

def query_logs(order_info: str = None, result: str = None,
               limit: int = 100) -> list[dict]:
    """검사 이력 조회 (필터링 가능)"""
    conn = get_connection()
    sql = "SELECT * FROM inspection_logs WHERE 1=1"
    params = []
    if order_info:
        sql += " AND order_info = ?"
        params.append(order_info)
    if result:
        sql += " AND result = ?"
        params.append(result)
    sql += " ORDER BY inspected_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def query_errors(limit: int = 50) -> list[dict]:
    """예외 로그 조회"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM error_logs ORDER BY occurred_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def query_summary() -> dict:
    """전체 검사 요약 통계"""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM inspection_logs").fetchone()[0]
    ok    = conn.execute("SELECT COUNT(*) FROM inspection_logs WHERE result='OK'").fetchone()[0]
    ng    = conn.execute("SELECT COUNT(*) FROM inspection_logs WHERE result='NG'").fetchone()[0]
    errs  = conn.execute("SELECT COUNT(*) FROM error_logs").fetchone()[0]
    conn.close()
    return {"total": total, "ok": ok, "ng": ng, "errors": errs}


if __name__ == "__main__":
    init_db()
    print("DB 요약:", query_summary())
