"""
viewer.py
저장된 로그와 DB를 조회하는 CLI/텍스트 기반 뷰어
Jupyter Notebook에서도 사용 가능
"""

import json
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from database import query_logs, query_errors, query_summary, get_connection
from logger import _load_json_log, export_csv


def print_summary():
    """전체 검사 요약 출력"""
    s = query_summary()
    print("\n" + "="*40)
    print("  검사 결과 요약")
    print("="*40)
    print(f"  전체 검사 건수 : {s['total']:>6}")
    print(f"  OK             : {s['ok']:>6}")
    print(f"  NG             : {s['ng']:>6}")
    print(f"  예외 발생 건수 : {s['errors']:>6}")
    print("="*40 + "\n")


def print_logs(order_info: str = None, result: str = None, limit: int = 20):
    """검사 이력 테이블 출력"""
    rows = query_logs(order_info=order_info, result=result, limit=limit)
    if not rows:
        print("조회 결과 없음")
        return

    header = f"{'시각':<20} {'대오더':<14} {'시리얼':<12} {'STEP':>4} {'부품번호':<8} {'점수':>6} {'결과':<4}"
    print("\n" + "-"*80)
    print(header)
    print("-"*80)
    for r in rows:
        t = r['inspected_at'][:19]
        score_pct = f"{r['matching_score']*100:.1f}%" if r['matching_score'] else "-"
        res_mark = "✅ OK" if r['result'] == 'OK' else "❌ NG"
        print(f"{t:<20} {r['order_info']:<14} {r['serial_no']:<12} "
              f"{r['step_no']:>4} {r['part_no']:<8} {score_pct:>6} {res_mark}")
    print("-"*80 + "\n")


def print_result_lines(order_info: str = None):
    """
    엑셀 명세 형식으로 출력: "구분번호:일치율:결과"
    예: C550:90:OK, 1515:88:OK, 3102:70:NG
    """
    records = _load_json_log()
    if order_info:
        records = [r for r in records if r.get('order_info') == order_info]

    if not records:
        print("로그 없음")
        return

    lines = [r.get('result_line', '') for r in records if r.get('result_line')]
    print("\n결과 라인 (엑셀 명세 형식):")
    print(", ".join(lines))
    print()


def print_errors(limit: int = 20):
    """예외 로그 출력"""
    rows = query_errors(limit=limit)
    if not rows:
        print("예외 로그 없음")
        return

    print("\n" + "="*60)
    print("  예외 로그")
    print("="*60)
    for r in rows:
        print(f"[{r['occurred_at'][:19]}] {r['error_type']}")
        print(f"  대오더: {r['order_info']} | step: {r['step_no']}")
        print(f"  내용: {r['error_msg']}")
        if r.get('stack_trace'):
            print(f"  스택: {r['stack_trace'][:200]}...")
        print()


def interactive_menu():
    """간단한 CLI 메뉴"""
    while True:
        print("\n" + "="*30)
        print("  로그/데이터 조회 메뉴")
        print("="*30)
        print("  1. 전체 요약 보기")
        print("  2. 검사 이력 전체 보기")
        print("  3. 대오더별 이력 보기")
        print("  4. NG 항목만 보기")
        print("  5. 결과 라인 출력 (엑셀 형식)")
        print("  6. 예외 로그 보기")
        print("  7. CSV 내보내기")
        print("  0. 종료")
        print("="*30)

        choice = input("선택: ").strip()

        if choice == '1':
            print_summary()
        elif choice == '2':
            print_logs(limit=50)
        elif choice == '3':
            order = input("대오더 정보 입력 (예: 3029C003AA): ").strip()
            print_logs(order_info=order)
            print_result_lines(order_info=order)
        elif choice == '4':
            print_logs(result='NG')
        elif choice == '5':
            order = input("대오더 입력 (전체는 엔터): ").strip() or None
            print_result_lines(order_info=order)
        elif choice == '6':
            print_errors()
        elif choice == '7':
            path = export_csv()
            print(f"저장 완료: {path}")
        elif choice == '0':
            break
        else:
            print("잘못된 입력")


# Jupyter Notebook용 함수
def show_dataframe(order_info: str = None, result: str = None):
    """pandas DataFrame으로 반환 (Jupyter용)"""
    try:
        import pandas as pd
        rows = query_logs(order_info=order_info, result=result, limit=1000)
        return pd.DataFrame(rows)
    except ImportError:
        print("pandas가 없습니다: pip install pandas")
        return None


if __name__ == "__main__":
    interactive_menu()
