"""
main.py
검사 시스템 진입점

사용법:
    python main.py                                      # UI 실행 (기본)
    python main.py --cli                                # CLI 전체 배치
    python main.py --cli --order 3029C003AA             # CLI 대오더 하나
    python main.py --cli --order 3029C003AA --serial 2EQ16144
    python main.py --view                               # 조회 메뉴
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

BASE       = os.path.dirname(__file__)
XLSX_PATH  = os.path.join(BASE, "층별일람표.xlsx")
DATA_DIR   = os.path.join(BASE, "data")
OUTPUT_DIR = os.path.join(BASE, "data", "output")


def main():
    parser = argparse.ArgumentParser(description='화상 검사 시스템')
    parser.add_argument('--cli',    action='store_true', help='CLI 모드 (UI 없이 실행)')
    parser.add_argument('--view',   action='store_true', help='조회 메뉴 실행')
    parser.add_argument('--order',  default=None,        help='특정 대오더 (예: 3029C003AA)')
    parser.add_argument('--serial', default=None,        help='특정 시리얼 (예: 2EQ16144)')
    args = parser.parse_args()

    if not os.path.exists(XLSX_PATH):
        print(f"[오류] 엑셀 파일 없음: {XLSX_PATH}")
        sys.exit(1)

    # ── 조회 메뉴 ──
    if args.view:
        from viewer import interactive_menu
        interactive_menu()
        return

    # ── CLI 모드 ──
    if args.cli:
        from inspector import Inspector
        insp = Inspector(xlsx_path=XLSX_PATH, data_dir=DATA_DIR, output_dir=OUTPUT_DIR)

        if args.order and args.serial:
            order = next((o for o in insp.orders if o.order_info == args.order), None)
            if not order:
                print(f"[오류] 대오더 없음: {args.order}")
                sys.exit(1)
            print(f"단일 제품 검사: {args.order} / {args.serial}")
            insp.inspect_serial(order, args.serial)

        elif args.order:
            order = next((o for o in insp.orders if o.order_info == args.order), None)
            if not order:
                print(f"[오류] 대오더 없음: {args.order}")
                sys.exit(1)
            insp.inspect_order(order)

        else:
            insp.run_all()

        from viewer import print_summary
        print_summary()
        return

    # ── UI 모드 (기본) ──
    from ui import run_app
    run_app(xlsx_path=XLSX_PATH, data_dir=DATA_DIR, output_dir=OUTPUT_DIR)


if __name__ == '__main__':
    main()