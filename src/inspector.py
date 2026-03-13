"""
inspector.py
제공된 알고리즘을 연결하여 복수 이미지에 대한 검사를 배치 실행합니다.

실제 데이터 폴더 구조:
    data/
    └── {대오더}/              예: 3029C003AA/
        └── {시리얼넘버}/      예: 2EQ16144/
            ├── step_0.jpg
            ├── step_1.jpg
            └── ...
"""

import cv2
import os
import time
import numpy as np
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(__file__))
from provided_algorithm import template_matching

from excel_parser import (
    parse_orders, parse_inspection_points,
    get_steps_for_order, parse_step_numbers, OrderInfo
)
from database import init_db, save_original_image, save_inspection_log
from logger import log_inspection, log_error

# ── 설정 ────────────────────────────────────────────────────────
SCORE_THRESHOLD = 0.70   # 이 값 이상이면 OK
SAVE_BLOB       = False  # True: 원본 이미지를 DB에 바이너리로 저장 (용량 주의)


class Inspector:
    def __init__(self, xlsx_path: str, data_dir: str, output_dir: str):
        """
        xlsx_path  : 층별일람표.xlsx 경로
        data_dir   : 대오더 폴더들이 있는 루트 (예: data/)
        output_dir : 결과 시각화 이미지 저장 폴더
        """
        self.xlsx_path  = xlsx_path
        self.data_dir   = data_dir
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        # 엑셀 파싱
        self.orders = parse_orders(xlsx_path)
        self.order_cols, self.points = parse_inspection_points(xlsx_path)

        # 마스터 이미지 자동 추출 (엑셀 바코드 이미지 → data/{대오더}/master.png)
        from excel_parser import extract_master_images
        extract_master_images(xlsx_path, data_dir)

        # DB 초기화
        init_db()

    # ── 이미지 로드 ─────────────────────────────────────────────

    def _load_image(self, path: str):
        """경로에서 이미지 로드, 없으면 None 반환"""
        for ext in ['', '.jpg', '.jpeg', '.png', '.bmp']:
            full = path if os.path.splitext(path)[1] else path + ext
            if os.path.exists(full):
                img = cv2.imread(full)
                if img is not None:
                    return img, full
        return None, path

    def _load_step(self, serial_dir: str, step_no: int):
        """serial_dir/step_{N}.jpg 로드"""
        base = os.path.join(serial_dir, f"step_{step_no}")
        return self._load_image(base)

    def _list_serials(self, order_info: str) -> list:
        """대오더 폴더 안의 시리얼 넘버 폴더 목록 반환"""
        order_dir = os.path.join(self.data_dir, order_info)
        if not os.path.isdir(order_dir):
            return []
        return sorted([
            d for d in os.listdir(order_dir)
            if os.path.isdir(os.path.join(order_dir, d))
        ])

    # ── 마스터 이미지 결정 ──────────────────────────────────────

    def _get_master(self, order_info: str, serial_dir: str):
        """
        마스터(기준) 이미지 결정 전략:
        1순위: data/{order_info}/master.jpg  (직접 준비한 마스터)
        2순위: 같은 대오더의 첫 번째 시리얼 폴더의 step_0
        3순위: 현재 시리얼의 step_0
        """
        # 1순위: 전용 마스터 파일
        img, path = self._load_image(os.path.join(self.data_dir, order_info, "master.jpg"))
        if img is not None:
            return img, path

        # 2순위: 같은 대오더 첫 시리얼의 step_0
        serials = self._list_serials(order_info)
        if serials:
            first_dir = os.path.join(self.data_dir, order_info, serials[0])
            img, path = self._load_step(first_dir, 0)
            if img is not None:
                return img, path

        # 3순위: 현재 시리얼의 step_0
        return self._load_step(serial_dir, 0)

    # ── 단일 시리얼(제품) 검사 ──────────────────────────────────

    def inspect_serial(self, order: OrderInfo, serial_no: str) -> list:
        """
        한 제품(시리얼)에 대해 해당 step 이미지들을 모두 검사
        Returns: 검사 결과 레코드 목록
        """
        results    = []
        serial_dir = os.path.join(self.data_dir, order.order_info, serial_no)
        steps_map  = get_steps_for_order(order.order_info, self.points)

        if not steps_map:
            log_error("NO_STEPS",
                      f"검사 포인트 없음: {order.order_info}",
                      order_info=order.order_info, serial_no=serial_no)
            return results

        # 마스터 이미지 로드
        master_img, master_path = self._get_master(order.order_info, serial_dir)
        if master_img is None:
            log_error("MASTER_NOT_FOUND",
                      f"마스터 이미지 없음: {order.order_info}",
                      order_info=order.order_info, serial_no=serial_no)
            return results

        # step_0 원본 DB 저장
        save_original_image(order.order_info, serial_no, 0, master_path, SAVE_BLOB)

        # 각 부품별 검사
        for part_no, step_str in steps_map.items():
            step_numbers = parse_step_numbers(step_str)

            for step_no in step_numbers:
                input_img, input_path = self._load_step(serial_dir, step_no)
                if input_img is None:
                    log_error("IMAGE_NOT_FOUND",
                              f"step_{step_no}.jpg 없음: {serial_dir}",
                              order_info=order.order_info,
                              serial_no=serial_no,
                              step_no=step_no)
                    continue

                # 원본 이미지 DB 저장
                save_original_image(order.order_info, serial_no,
                                    step_no, input_path, SAVE_BLOB)

                # ── 알고리즘 실행 ──────────────────────────────
                try:
                    t0 = time.time()

                    # 출력 폴더: output/{대오더}/{시리얼}/step{N}_{부품번호}/
                    vis_dir = os.path.join(
                        self.output_dir,
                        order.order_info, serial_no,
                        f"step{step_no}_{part_no}"
                    )
                    os.makedirs(vis_dir, exist_ok=True)

                    # template_matching 호출
                    # input_img: 검사 대상 이미지
                    # master_img: 기준(마스터) 이미지
                    # templates: [input_img] — 이미지 자체를 템플릿으로
                    # top_left_points: padding=20 기준 좌상단 좌표
                    cropped_rois, matching_scores, vis_img = template_matching(
                        input_img      = input_img,
                        template_all   = master_img,
                        templates      = [input_img],
                        save_path      = vis_dir,
                        top_left_points= [(20, 20)],
                    )

                    elapsed_ms = (time.time() - t0) * 1000
                    score  = float(matching_scores[0]) if matching_scores else 0.0
                    result = "OK" if score >= SCORE_THRESHOLD else "NG"

                    # 부품명 조회
                    part_name = next(
                        (p.part_name for p in self.points if p.part_no == part_no), ""
                    )
                    vis_path = os.path.join(vis_dir, "visualized_input_with_boxes.jpeg")

                    # 로그 & DB 저장
                    record = log_inspection(
                        order_info    = order.order_info,
                        serial_no     = serial_no,
                        barcode_text  = order.barcode_text,
                        step_no       = step_no,
                        part_no       = part_no,
                        part_name     = part_name,
                        matching_score= score,
                        result        = result,
                        result_detail = step_str,
                        elapsed_ms    = elapsed_ms,
                    )
                    save_inspection_log(
                        order_info     = order.order_info,
                        serial_no      = serial_no,
                        barcode_text   = order.barcode_text,
                        step_no        = step_no,
                        part_no        = part_no,
                        part_name      = part_name,
                        matching_score = score,
                        result         = result,
                        result_detail  = step_str,
                        visualized_path= vis_path,
                    )
                    results.append(record)

                except Exception as e:
                    log_error(
                        error_type = type(e).__name__,
                        error_msg  = str(e),
                        order_info = order.order_info,
                        serial_no  = serial_no,
                        step_no    = step_no,
                        exc        = e,
                    )

        return results

    # ── 단일 대오더 전체 시리얼 검사 ────────────────────────────

    def inspect_order(self, order: OrderInfo) -> list:
        """한 대오더 안의 모든 시리얼(제품)을 검사"""
        serials = self._list_serials(order.order_info)
        if not serials:
            print(f"  ⚠ 시리얼 폴더 없음: {order.order_info}")
            log_error("NO_SERIAL_FOLDER",
                      f"시리얼 폴더 없음: {order.order_info}",
                      order_info=order.order_info)
            return []

        all_results = []
        for i, serial_no in enumerate(serials, 1):
            print(f"    [{i}/{len(serials)}] 시리얼: {serial_no}")
            results = self.inspect_serial(order, serial_no)
            all_results.extend(results)

        ok = sum(1 for r in all_results if r['result'] == 'OK')
        ng = sum(1 for r in all_results if r['result'] == 'NG')
        print(f"    → 완료: {len(all_results)}건 (OK:{ok} NG:{ng})")
        return all_results

    # ── 전체 배치 실행 ────────────────────────────────────────

    def run_all(self) -> dict:
        """전체 대오더 x 전체 시리얼 배치 검사"""
        print(f"\n{'='*55}")
        print(f"  검사 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  대오더 수: {len(self.orders)}")
        print(f"{'='*55}\n")

        all_results = []
        for order in self.orders:
            serials = self._list_serials(order.order_info)
            print(f"▶ {order.order_info}  ({len(serials)}개 시리얼)")
            results = self.inspect_order(order)
            all_results.extend(results)

        ok_cnt = sum(1 for r in all_results if r['result'] == 'OK')
        ng_cnt = sum(1 for r in all_results if r['result'] == 'NG')

        summary = {
            "total"      : len(all_results),
            "ok"         : ok_cnt,
            "ng"         : ng_cnt,
            "finished_at": datetime.now().isoformat(),
        }
        print(f"\n{'='*55}")
        print(f"  검사 완료 | 전체:{summary['total']}  OK:{ok_cnt}  NG:{ng_cnt}")
        print(f"{'='*55}\n")
        return summary


if __name__ == "__main__":
    xlsx = sys.argv[1] if len(sys.argv) > 1 else "층별일람표.xlsx"
    data = sys.argv[2] if len(sys.argv) > 2 else "data"
    out  = sys.argv[3] if len(sys.argv) > 3 else "data/output"

    inspector = Inspector(xlsx_path=xlsx, data_dir=data, output_dir=out)
    inspector.run_all()
