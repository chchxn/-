"""
ui.py - 화상 검사 시스템 UI
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from database import query_logs, query_summary


class InspectionApp(tk.Tk):
    def __init__(self, xlsx_path, data_dir, output_dir):
        super().__init__()
        self.xlsx_path  = xlsx_path
        self.data_dir   = data_dir
        self.output_dir = output_dir

        self.title("화상 검사 시스템")
        self.geometry("1200x750")
        self.configure(bg="#f0f2f5")
        self.resizable(True, True)

        from excel_parser import parse_orders, parse_inspection_points
        self.orders = parse_orders(xlsx_path)
        self.order_cols, self.points = parse_inspection_points(xlsx_path)

        self._build_ui()
        self._refresh_table()

    # ── UI 구성 ──────────────────────────────────────────────

    def _build_ui(self):
        # 헤더
        header = tk.Frame(self, bg="#1a73e8", height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="🔍  화상 검사 시스템",
                 bg="#1a73e8", fg="white",
                 font=("맑은 고딕", 15, "bold")).pack(side="left", padx=20)
        self.status_lbl = tk.Label(header, text="● 대기 중",
                                   bg="#1a73e8", fg="#a8d8ff",
                                   font=("맑은 고딕", 10))
        self.status_lbl.pack(side="right", padx=20)

        # 메인 레이아웃
        body = tk.Frame(self, bg="#f0f2f5")
        body.pack(fill="both", expand=True, padx=16, pady=12)

        # 왼쪽 사이드바
        self._build_sidebar(body)

        # 오른쪽 콘텐츠
        self._build_content(body)

    def _build_sidebar(self, parent):
        side = tk.Frame(parent, bg="white", width=240,
                        relief="flat", bd=0)
        side.pack(side="left", fill="y", padx=(0, 12))
        side.pack_propagate(False)

        def section(text):
            tk.Label(side, text=text, bg="white", fg="#5f6368",
                     font=("맑은 고딕", 9, "bold")).pack(anchor="w", padx=16, pady=(16,4))

        # ── 검사 대상 선택 ──
        section("검사 대상 선택")

        tk.Label(side, text="모델 (대오더)", bg="white", fg="#202124",
                 font=("맑은 고딕", 9)).pack(anchor="w", padx=16)

        self.order_var = tk.StringVar()
        order_values = ["전체 실행"] + [o.order_info for o in self.orders]
        self.order_cb = ttk.Combobox(side, textvariable=self.order_var,
                                     values=order_values, width=26, state="readonly",
                                     font=("맑은 고딕", 9))
        self.order_cb.pack(padx=16, pady=(2,8), fill="x")
        self.order_cb.set("전체 실행")
        self.order_cb.bind("<<ComboboxSelected>>", self._on_order_change)

        tk.Label(side, text="제품 번호 (시리얼)", bg="white", fg="#202124",
                 font=("맑은 고딕", 9)).pack(anchor="w", padx=16)

        self.serial_var = tk.StringVar()
        self.serial_cb = ttk.Combobox(side, textvariable=self.serial_var,
                                      width=26, state="readonly",
                                      font=("맑은 고딕", 9))
        self.serial_cb.pack(padx=16, pady=(2,8), fill="x")
        self.serial_cb.set("모델 선택 후 자동 표시")

        # 안내 문구
        tk.Label(side,
                 text="※ '전체 실행' 선택 시\n   모든 제품을 자동 검사합니다",
                 bg="white", fg="#9aa0a6",
                 font=("맑은 고딕", 8), justify="left").pack(anchor="w", padx=16, pady=(0,8))

        # 실행 버튼
        self.btn_run = tk.Button(side, text="▶  검사 시작",
                                 bg="#1a73e8", fg="white",
                                 font=("맑은 고딕", 11, "bold"),
                                 relief="flat", pady=10, cursor="hand2",
                                 activebackground="#1557b0", activeforeground="white",
                                 command=self._run_inspection)
        self.btn_run.pack(fill="x", padx=16, pady=(4, 4))

        self.btn_refresh = tk.Button(side, text="🔄  결과 새로고침",
                                     bg="#e8f0fe", fg="#1a73e8",
                                     font=("맑은 고딕", 9),
                                     relief="flat", pady=6, cursor="hand2",
                                     command=self._refresh_table)
        self.btn_refresh.pack(fill="x", padx=16, pady=(0, 16))

        # 구분선
        tk.Frame(side, bg="#e0e0e0", height=1).pack(fill="x", padx=16)

        # ── 요약 통계 ──
        section("검사 요약")
        self.stat_frame = tk.Frame(side, bg="white")
        self.stat_frame.pack(fill="x", padx=16, pady=(0,16))

        self.stat_total = self._stat_row(self.stat_frame, "전체",  "#5f6368")
        self.stat_ok    = self._stat_row(self.stat_frame, "OK",    "#1e8e3e")
        self.stat_ng    = self._stat_row(self.stat_frame, "NG",    "#d93025")
        self.stat_err   = self._stat_row(self.stat_frame, "오류",  "#f29900")

        # 구분선
        tk.Frame(side, bg="#e0e0e0", height=1).pack(fill="x", padx=16)

        # ── 이미지 미리보기 ──
        section("결과 이미지")
        self.img_frame = tk.Frame(side, bg="#f8f9fa", height=200)
        self.img_frame.pack(fill="x", padx=16, pady=(0,8))
        self.img_frame.pack_propagate(False)

        self.img_label = tk.Label(self.img_frame, bg="#f8f9fa",
                                  text="결과 행을 클릭하면\n이미지가 표시됩니다",
                                  fg="#9aa0a6", font=("맑은 고딕", 9))
        self.img_label.pack(expand=True)

        self.img_info = tk.Label(side, bg="white", fg="#5f6368",
                                 font=("맑은 고딕", 8), wraplength=210, justify="center")
        self.img_info.pack(padx=16)

    def _stat_row(self, parent, label, color):
        f = tk.Frame(parent, bg="white")
        f.pack(fill="x", pady=2)
        tk.Label(f, text=label, bg="white", fg=color,
                 font=("맑은 고딕", 9, "bold"), width=6, anchor="w").pack(side="left")
        var = tk.StringVar(value="0")
        tk.Label(f, textvariable=var, bg="white", fg=color,
                 font=("맑은 고딕", 11, "bold")).pack(side="right")
        return var

    def _build_content(self, parent):
        content = tk.Frame(parent, bg="#f0f2f5")
        content.pack(side="left", fill="both", expand=True)

        # 탭
        tab_bar = tk.Frame(content, bg="#f0f2f5")
        tab_bar.pack(fill="x", pady=(0,8))

        tk.Label(tab_bar, text="검사 이력", bg="#f0f2f5", fg="#202124",
                 font=("맑은 고딕", 11, "bold")).pack(side="left")

        # 필터 버튼
        self.filter_var = tk.StringVar(value="전체")
        for label, color in [("전체","#5f6368"), ("OK","#1e8e3e"), ("NG","#d93025")]:
            tk.Button(tab_bar, text=label, bg="white", fg=color,
                      font=("맑은 고딕", 9, "bold"),
                      relief="flat", padx=12, pady=2, cursor="hand2",
                      command=lambda l=label: self._filter(l)).pack(side="right", padx=2)

        # 테이블 카드
        card = tk.Frame(content, bg="white", relief="flat")
        card.pack(fill="both", expand=True)

        cols = ("검사 시각", "모델(대오더)", "제품번호(시리얼)", "STEP", "부품번호", "부품명", "일치율", "결과")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", height=30)

        widths = [140, 115, 115, 50, 80, 170, 65, 60]
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=col,
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=w, anchor="center")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
                        background="white", foreground="#202124",
                        fieldbackground="white", rowheight=26,
                        font=("맑은 고딕", 9))
        style.configure("Treeview.Heading",
                        background="#f8f9fa", foreground="#5f6368",
                        font=("맑은 고딕", 9, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", "#e8f0fe")],
                  foreground=[("selected", "#1a73e8")])

        self.tree.tag_configure("OK", foreground="#1e8e3e")
        self.tree.tag_configure("NG", foreground="#d93025")
        self.tree.tag_configure("odd", background="#fafafa")
        self.tree.tag_configure("even", background="white")

        sb_y = ttk.Scrollbar(card, orient="vertical",   command=self.tree.yview)
        sb_x = ttk.Scrollbar(card, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)

        self.tree.pack(side="left", fill="both", expand=True)
        sb_y.pack(side="right", fill="y")
        sb_x.pack(side="bottom", fill="x")

        self.tree.bind("<<TreeviewSelect>>", self._on_row_select)

    # ── 이벤트 ───────────────────────────────────────────────

    def _on_order_change(self, event=None):
        order_info = self.order_var.get()
        if order_info == "전체 실행":
            self.serial_cb.set("전체 자동 실행")
            self.serial_cb["values"] = []
            return
        order_dir = os.path.join(self.data_dir, order_info)
        if os.path.isdir(order_dir):
            serials = sorted([
                d for d in os.listdir(order_dir)
                if os.path.isdir(os.path.join(order_dir, d))
            ])
            self.serial_cb["values"] = ["전체"] + serials
            self.serial_cb.set("전체")
        else:
            self.serial_cb["values"] = []
            self.serial_cb.set("폴더 없음")

    def _on_row_select(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return
        vals = self.tree.item(selected[0])["values"]
        if len(vals) < 5:
            return
        order_info = vals[1]
        serial_no  = vals[2]
        step_no    = vals[3]
        part_no    = vals[4]

        vis_dir  = os.path.join(self.output_dir, order_info, serial_no,
                                f"step{step_no}_{part_no}")
        img_path = os.path.join(vis_dir, "visualized_input_with_boxes.jpeg")

        if os.path.exists(img_path):
            self._show_image(img_path)
            self.img_info.config(
                text=f"{order_info}  /  {serial_no}\nSTEP {step_no}  |  부품 {part_no}"
            )
        else:
            self.img_label.config(image="", text="이미지 없음", fg="#9aa0a6")
            self.img_label.image = None
            self.img_info.config(text="")

    def _show_image(self, path):
        try:
            from PIL import Image, ImageTk
            img = Image.open(path)
            img.thumbnail((210, 190))
            photo = ImageTk.PhotoImage(img)
            self.img_label.config(image=photo, text="")
            self.img_label.image = photo
        except Exception:
            self.img_label.config(image="",
                                  text="Pillow 설치 필요\npip install Pillow",
                                  fg="#d93025")
            self.img_label.image = None

    def _filter(self, result: str):
        self.filter_var.set(result)
        self._refresh_table()

    def _sort_by(self, col):
        pass  # 필요 시 구현

    # ── 테이블 갱신 ──────────────────────────────────────────

    def _refresh_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        result_filter = self.filter_var.get()
        rows = query_logs(
            result=None if result_filter == "전체" else result_filter,
            limit=1000
        )

        for i, r in enumerate(rows):
            t     = r["inspected_at"][:19]
            score = f"{r['matching_score']*100:.1f}%" if r["matching_score"] else "-"
            res   = r["result"]
            tags  = (res, "odd" if i % 2 else "even")
            self.tree.insert("", "end", tags=tags, values=(
                t, r["order_info"], r["serial_no"],
                r["step_no"], r["part_no"], r["part_name"],
                score, res
            ))

        s = query_summary()
        self.stat_total.set(str(s["total"]))
        self.stat_ok.set(str(s["ok"]))
        self.stat_ng.set(str(s["ng"]))
        self.stat_err.set(str(s["errors"]))

    # ── 검사 실행 ─────────────────────────────────────────────

    def _set_ui(self, running: bool):
        state = "disabled" if running else "normal"
        self.btn_run.config(state=state)
        self.btn_refresh.config(state=state)
        self.order_cb.config(state="disabled" if running else "readonly")
        self.serial_cb.config(state="disabled" if running else "readonly")

    def _run_inspection(self):
        order_info = self.order_var.get()
        serial_no  = self.serial_var.get()

        self._set_ui(True)

        if order_info == "전체 실행":
            self.status_lbl.config(text="● 전체 검사 중...", fg="#fdd663")
            threading.Thread(target=self._task_all, daemon=True).start()
        elif serial_no in ("", "전체", "전체 자동 실행", "모델 선택 후 자동 표시"):
            self.status_lbl.config(text=f"● {order_info} 검사 중...", fg="#fdd663")
            threading.Thread(target=self._task_order,
                             args=(order_info,), daemon=True).start()
        else:
            self.status_lbl.config(
                text=f"● {order_info} / {serial_no} 검사 중...", fg="#fdd663")
            threading.Thread(target=self._task_serial,
                             args=(order_info, serial_no), daemon=True).start()

    def _task_all(self):
        try:
            from inspector import Inspector
            Inspector(self.xlsx_path, self.data_dir, self.output_dir).run_all()
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("오류", str(e)))
        finally:
            self.after(0, self._on_done)

    def _task_order(self, order_info):
        try:
            from inspector import Inspector
            insp  = Inspector(self.xlsx_path, self.data_dir, self.output_dir)
            order = next((o for o in insp.orders if o.order_info == order_info), None)
            if order:
                insp.inspect_order(order)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("오류", str(e)))
        finally:
            self.after(0, self._on_done)

    def _task_serial(self, order_info, serial_no):
        try:
            from inspector import Inspector
            insp  = Inspector(self.xlsx_path, self.data_dir, self.output_dir)
            order = next((o for o in insp.orders if o.order_info == order_info), None)
            if order:
                insp.inspect_serial(order, serial_no)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("오류", str(e)))
        finally:
            self.after(0, self._on_done)

    def _on_done(self):
        self._set_ui(False)
        self.status_lbl.config(text="● 완료", fg="#a8d8ff")
        self._refresh_table()


def run_app(xlsx_path, data_dir, output_dir):
    app = InspectionApp(xlsx_path, data_dir, output_dir)
    app.mainloop()


if __name__ == "__main__":
    BASE = os.path.dirname(os.path.dirname(__file__))
    run_app(
        xlsx_path  = os.path.join(BASE, "층별일람표.xlsx"),
        data_dir   = os.path.join(BASE, "data"),
        output_dir = os.path.join(BASE, "data", "output"),
    )
