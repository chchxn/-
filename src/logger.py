"""
logger.py
처리 로그를 파일(JSON/CSV)과 Python logging으로 이중 기록합니다.
"""

import logging
import json
import csv
import os
import traceback
from datetime import datetime
from pathlib import Path

LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
INSPECTION_LOG_FILE = os.path.join(LOG_DIR, 'inspection.json')
ERROR_LOG_FILE      = os.path.join(LOG_DIR, 'error.log')

# ── Python logging 설정 ──────────────────────────────────────

def setup_logger() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger('inspection')
    if logger.handlers:
        return logger  # 중복 방지

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter('[%(asctime)s] %(levelname)s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

    # 콘솔 출력
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # 에러 파일
    fh = logging.FileHandler(ERROR_LOG_FILE, encoding='utf-8')
    fh.setLevel(logging.ERROR)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


logger = setup_logger()


# ── JSON 로그 기록 ────────────────────────────────────────────

def _load_json_log() -> list:
    if not os.path.exists(INSPECTION_LOG_FILE):
        return []
    with open(INSPECTION_LOG_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _save_json_log(records: list):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(INSPECTION_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def log_inspection(order_info: str, serial_no: str, barcode_text: str,
                   step_no: int, part_no: str, part_name: str,
                   matching_score: float, result: str,
                   result_detail: str = "", elapsed_ms: float = 0.0,
                   error: bool = False):
    """
    검사 결과 기록 (엑셀 명세: "구분번호:일치율:결과" 형태)
    """
    record = {
        "inspected_at": datetime.now().isoformat(),
        "order_info":   order_info,
        "serial_no":    serial_no,
        "barcode_text": barcode_text,
        "step_no":      step_no,
        "part_no":      part_no,
        "part_name":    part_name,
        "matching_score": round(matching_score * 100, 1),  # % 단위
        "result":       result,          # OK / NG
        "result_detail": result_detail,  # 원형 번호 예: "①"
        # 엑셀 명세 형식: "C550:90:OK"
        "result_line":  f"{part_no}:{round(matching_score * 100, 1):.0f}:{result}",
        "elapsed_ms":   round(elapsed_ms, 1),
        "error_flag":   error,
    }

    # JSON 파일에 추가
    records = _load_json_log()
    records.append(record)
    _save_json_log(records)

    # Python logger
    level = logging.WARNING if result == 'NG' else logging.INFO
    logger.log(level,
        f"[{order_info}] step{step_no} {part_no}({part_name}) "
        f"→ score={record['matching_score']}% {result} ({elapsed_ms:.0f}ms)")

    return record


def log_error(error_type: str, error_msg: str,
              order_info: str = "", serial_no: str = "", step_no: int = -1,
              exc: Exception = None):
    """예외 상황 기록"""
    stack = traceback.format_exc() if exc else ""
    logger.error(
        f"[ERROR] {error_type} | order={order_info} serial={serial_no} step={step_no} | "
        f"{error_msg}\n{stack}"
    )
    # DB에도 저장 (database 모듈 임포트)
    try:
        from database import save_error_log
        save_error_log(error_type, error_msg, stack, order_info, serial_no, step_no)
    except Exception as e:
        logger.error(f"DB 오류 저장 실패: {e}")


def export_csv(output_path: str = None):
    """JSON 로그를 CSV로 내보내기"""
    records = _load_json_log()
    if not records:
        print("로그가 없습니다.")
        return

    if output_path is None:
        output_path = os.path.join(LOG_DIR, f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

    fieldnames = list(records[0].keys())
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"CSV 내보내기 완료: {output_path}")
    return output_path


if __name__ == "__main__":
    # 테스트
    log_inspection(
        order_info="3029C003AA", serial_no="2EQ02001",
        barcode_text="913029C00392AA212EQ02001",
        step_no=1, part_no="C551", part_name="토너 지역 라벨(유럽)",
        matching_score=0.91, result="OK", result_detail="①", elapsed_ms=123.4
    )
    log_inspection(
        order_info="3029C003AA", serial_no="2EQ02001",
        barcode_text="913029C00392AA212EQ02001",
        step_no=4, part_no="3102", part_name="현상 가압 조작 라벨",
        matching_score=0.55, result="NG", result_detail="④", elapsed_ms=98.7
    )
    print("테스트 로그 기록 완료")
    print("로그 내용:", json.dumps(_load_json_log(), ensure_ascii=False, indent=2)[:500])
