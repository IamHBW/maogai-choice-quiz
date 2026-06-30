import json
import random
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

try:
    from questions_data import questions
except Exception as exc:  # pragma: no cover - exercised by manual startup
    QUESTIONS_IMPORT_ERROR = exc
    questions = []
else:
    QUESTIONS_IMPORT_ERROR = None


PROGRESS_FILE = Path(__file__).with_name("quiz_progress.json")
SUMMARY_DIR = Path(__file__).with_name("summary")
PROGRESS_VERSION = 1
ANSWER_KEYS = ("A", "B", "C", "D", "E")
MODE_SEQUENTIAL = "sequential"
MODE_RANDOM = "random"
SCOPE_ALL = "all"
SCOPE_WRONG_MARKED = "wrong_marked"
SCOPE_LAST_WRONG_MARKED = "last_wrong_marked"


def empty_question_status():
    return {
        "selected": None,
        "checked": False,
        "is_correct": None,
        "auto_wrong": False,
        "manual_marked": False,
    }


def create_default_progress(total_questions, rng=None):
    rng = rng or random.Random()
    random_order = list(range(total_questions))
    rng.shuffle(random_order)
    return {
        "version": PROGRESS_VERSION,
        "current_index": 0,
        "mode": MODE_SEQUENTIAL,
        "review_scope": SCOPE_ALL,
        "random_order": random_order,
        "option_orders": [],
        "last_wrong_marked_indices": [],
        "auto_save": True,
        "question_status": [empty_question_status() for _ in range(total_questions)],
    }


def normalize_progress(raw_progress, total_questions, rng=None):
    progress = create_default_progress(total_questions, rng=rng)
    if not isinstance(raw_progress, dict):
        return progress

    current_index = raw_progress.get("current_index", 0)
    if isinstance(current_index, int) and 0 <= current_index < total_questions:
        progress["current_index"] = current_index

    mode = raw_progress.get("mode")
    if mode in (MODE_SEQUENTIAL, MODE_RANDOM):
        progress["mode"] = mode

    review_scope = raw_progress.get("review_scope")
    if review_scope in (SCOPE_ALL, SCOPE_WRONG_MARKED, SCOPE_LAST_WRONG_MARKED):
        progress["review_scope"] = review_scope

    random_order = raw_progress.get("random_order")
    if (
        isinstance(random_order, list)
        and len(random_order) == total_questions
        and sorted(random_order) == list(range(total_questions))
    ):
        progress["random_order"] = random_order

    option_orders = raw_progress.get("option_orders")
    if isinstance(option_orders, list) and len(option_orders) == total_questions:
        progress["option_orders"] = [
            order[:] if isinstance(order, list) else []
            for order in option_orders
        ]

    progress["auto_save"] = bool(raw_progress.get("auto_save", True))

    statuses = raw_progress.get("question_status")
    if isinstance(statuses, list):
        for index, saved_status in enumerate(statuses[:total_questions]):
            if not isinstance(saved_status, dict):
                continue
            status = progress["question_status"][index]
            selected = saved_status.get("selected")
            status["selected"] = normalize_answer(selected) or None
            status["checked"] = bool(saved_status.get("checked", False))
            is_correct = saved_status.get("is_correct")
            status["is_correct"] = is_correct if isinstance(is_correct, bool) else None
            status["auto_wrong"] = bool(saved_status.get("auto_wrong", False))
            status["manual_marked"] = bool(saved_status.get("manual_marked", False))

    last_indices = raw_progress.get("last_wrong_marked_indices")
    if isinstance(last_indices, list):
        seen = set()
        progress["last_wrong_marked_indices"] = []
        for index in last_indices:
            if type(index) is not int or not 0 <= index < total_questions or index in seen:
                continue
            progress["last_wrong_marked_indices"].append(index)
            seen.add(index)

    if progress["review_scope"] != SCOPE_ALL:
        active_indices = active_question_indices(progress, total_questions)
        if not active_indices:
            progress["review_scope"] = SCOPE_ALL
        elif progress["current_index"] not in active_indices:
            progress["current_index"] = active_indices[0]

    return progress


def strip_option_label(option):
    if (
        isinstance(option, str)
        and len(option) >= 3
        and option[0] in ANSWER_KEYS
        and option[1:3] == ". "
    ):
        return option[3:]
    return option


def normalize_answer(answer):
    if not isinstance(answer, str):
        return ""
    selected = []
    for value in answer.upper():
        if value in ANSWER_KEYS and value not in selected:
            selected.append(value)
    return "".join(sorted(selected, key=ANSWER_KEYS.index))


def is_multiple_choice_question(question):
    return question.get("type") == "multiple" or len(normalize_answer(question.get("answer", ""))) > 1


def question_type_label(question):
    return "多选" if is_multiple_choice_question(question) else "单选"


def display_question_text(question):
    return f"【{question_type_label(question)}】 {question.get('question', '')}"


def identity_option_order(option_count):
    return list(range(option_count))


def valid_option_order(option_order, option_count):
    return (
        isinstance(option_order, list)
        and len(option_order) == option_count
        and sorted(option_order) == list(range(option_count))
    )


def is_true_false_question(question):
    options = question.get("options", [])
    return [strip_option_label(option) for option in options] == ["√", "×"]


def option_order_for_question(progress, question_index, question):
    options = question.get("options", [])
    option_count = len(options)
    option_orders = progress.get("option_orders", [])
    if question_index < len(option_orders) and valid_option_order(
        option_orders[question_index],
        option_count,
    ):
        return option_orders[question_index]
    return identity_option_order(option_count)


def build_option_orders(question_bank, shuffle_options=False):
    option_orders = []
    for question in question_bank:
        order = identity_option_order(len(question.get("options", [])))
        if shuffle_options and len(order) > 1 and not is_true_false_question(question):
            random.shuffle(order)
            if order == identity_option_order(len(order)):
                order = order[1:] + order[:1]
        option_orders.append(order)
    return option_orders


def display_options_for_question(progress, question_index, question):
    options = question.get("options", [])
    order = option_order_for_question(progress, question_index, question)
    return [
        f"{ANSWER_KEYS[position]}. {strip_option_label(options[original_index])}"
        for position, original_index in enumerate(order)
    ]


def displayed_correct_answer(progress, question_index, question):
    answer = normalize_answer(question.get("answer", ""))
    if not answer:
        return question.get("answer")

    order = option_order_for_question(progress, question_index, question)
    displayed_letters = []
    for answer_key in answer:
        original_answer_index = ANSWER_KEYS.index(answer_key)
        if original_answer_index not in order:
            displayed_letters.append(answer_key)
            continue
        displayed_letters.append(ANSWER_KEYS[order.index(original_answer_index)])
    return normalize_answer("".join(displayed_letters))


def saved_random_order_is_valid(random_order, total_questions):
    return (
        isinstance(random_order, list)
        and len(random_order) == total_questions
        and sorted(random_order) == list(range(total_questions))
    )


def base_question_order(progress, total_questions):
    if total_questions <= 0:
        return []
    if progress.get("mode") == MODE_RANDOM:
        random_order = progress.get("random_order", [])
        if saved_random_order_is_valid(random_order, total_questions):
            return random_order[:]
    return list(range(total_questions))


def live_wrong_marked_indices(progress, total_questions):
    statuses = progress.get("question_status", [])
    indices = []
    for index in range(total_questions):
        if index >= len(statuses):
            continue
        status = statuses[index]
        if status.get("auto_wrong") or status.get("manual_marked"):
            indices.append(index)
    return indices


def question_in_review_scope(progress, question_index):
    review_scope = progress.get("review_scope", SCOPE_ALL)
    if review_scope == SCOPE_ALL:
        return True
    if review_scope == SCOPE_WRONG_MARKED:
        statuses = progress.get("question_status", [])
        if not 0 <= question_index < len(statuses):
            return False
        status = statuses[question_index]
        return bool(status.get("auto_wrong") or status.get("manual_marked"))
    if review_scope == SCOPE_LAST_WRONG_MARKED:
        return question_index in set(progress.get("last_wrong_marked_indices", []))
    return True


def active_question_indices(progress, total_questions):
    order = base_question_order(progress, total_questions)
    if progress.get("review_scope", SCOPE_ALL) == SCOPE_ALL:
        return order
    return [index for index in order if question_in_review_scope(progress, index)]


def next_question_index(progress, total_questions, direction=1):
    if total_questions <= 0:
        return 0

    current_index = progress.get("current_index", 0)
    base_order = base_question_order(progress, total_questions)
    active_order = active_question_indices(progress, total_questions)
    if not active_order:
        return current_index if isinstance(current_index, int) else 0

    if current_index in active_order:
        current_position = active_order.index(current_index)
        next_position = max(0, min(len(active_order) - 1, current_position + direction))
        return active_order[next_position]

    active_set = set(active_order)
    if current_index in base_order:
        current_position = base_order.index(current_index)
        if direction > 0:
            for index in base_order[current_position + 1 :]:
                if index in active_set:
                    return index
            return active_order[-1]
        if direction < 0:
            for index in reversed(base_order[:current_position]):
                if index in active_set:
                    return index
            return active_order[0]

    return active_order[0]


def rebuild_random_order_for_current_state(progress, total_questions):
    checked_indices = []
    unchecked_indices = []
    statuses = progress.get("question_status", [])

    for index in range(total_questions):
        if index < len(statuses) and statuses[index].get("checked"):
            checked_indices.append(index)
        else:
            unchecked_indices.append(index)

    current_index = progress.get("current_index", 0)
    if current_index in unchecked_indices:
        remaining_unchecked = [
            index for index in unchecked_indices if index != current_index
        ]
        random.shuffle(remaining_unchecked)
        unchecked_order = [current_index] + remaining_unchecked
    else:
        unchecked_order = unchecked_indices[:]
        random.shuffle(unchecked_order)
        if unchecked_order:
            progress["current_index"] = unchecked_order[0]
        elif total_questions > 0 and not 0 <= current_index < total_questions:
            progress["current_index"] = 0

    progress["random_order"] = checked_indices + unchecked_order


def record_check_result(progress, question_index, selected, correct_answer):
    status = progress["question_status"][question_index]
    selected = normalize_answer(selected)
    correct_answer = normalize_answer(correct_answer)
    is_correct = selected == correct_answer
    status["selected"] = selected
    status["checked"] = True
    status["is_correct"] = is_correct
    if not is_correct:
        status["auto_wrong"] = True
    return is_correct


def toggle_manual_mark(progress, question_index):
    status = progress["question_status"][question_index]
    status["manual_marked"] = not status["manual_marked"]
    return status["manual_marked"]


def load_progress_file(path, total_questions):
    if not path.exists():
        return create_default_progress(total_questions), None

    try:
        raw_progress = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return create_default_progress(total_questions), "进度不可用，已从头开始"

    return normalize_progress(raw_progress, total_questions), None


def save_progress_file(path, progress):
    path.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_summary_markdown(question_bank, progress, generated_at=None):
    generated_at = generated_at or datetime.now()
    statuses = progress.get("question_status", [])
    checked_count = sum(1 for status in statuses if status.get("checked"))
    records = []

    for index, question in enumerate(question_bank):
        if index >= len(statuses):
            continue
        status = statuses[index]
        if status.get("auto_wrong") or status.get("manual_marked"):
            records.append((index, question, status))

    lines = [
        "# 毛概错题 Summary",
        "",
        f"生成时间：{generated_at:%Y-%m-%d %H:%M:%S}",
        f"总题数：{len(question_bank)}",
        f"已检查题数：{checked_count}",
        f"导出题数：{len(records)}",
        "",
    ]

    if not records:
        lines.extend(["本次重置前没有错题或标记题。", ""])
        return "\n".join(lines)

    for export_index, (question_index, question, status) in enumerate(records, start=1):
        sources = []
        if status.get("auto_wrong"):
            sources.append("自动错题")
        if status.get("manual_marked"):
            sources.append("手动标记")

        if status.get("checked"):
            latest_result = "正确" if status.get("is_correct") else "错误"
        else:
            latest_result = "未检查"

        correct_answer = displayed_correct_answer(progress, question_index, question)
        lines.extend(
            [
                f"## {export_index}. 第 {question_index + 1} 题",
                "",
                f"来源：{'、'.join(sources)}",
                f"用户选择：{status.get('selected') or '未选择'}",
                f"正确答案：{correct_answer}",
                f"最近结果：{latest_result}",
                f"题型：{question_type_label(question)}",
                "",
                f"题干：{question.get('question', '')}",
                "",
                "选项：",
            ]
        )
        for option in display_options_for_question(progress, question_index, question):
            lines.append(f"- {option}")
        lines.extend(
            [
                "",
                f"解析：{question.get('explanation') or '暂无解析。'}",
                "",
            ]
        )

    return "\n".join(lines)


def write_summary_file(summary_dir, question_bank, progress, generated_at=None):
    generated_at = generated_at or datetime.now()
    summary_dir = Path(summary_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    path = summary_dir / f"summary-{generated_at:%Y%m%d-%H%M%S}.md"
    path.write_text(
        build_summary_markdown(question_bank, progress, generated_at=generated_at),
        encoding="utf-8",
    )
    return path


class QuizApp:
    def __init__(
        self,
        root,
        question_bank=None,
        progress_path=PROGRESS_FILE,
        summary_dir=SUMMARY_DIR,
    ):
        self.root = root
        self.questions = list(question_bank if question_bank is not None else questions)
        self.total_questions = len(self.questions)
        self.progress_path = Path(progress_path)
        self.summary_dir = Path(summary_dir)
        self.option_buttons = []
        self.option_vars = []
        self.number_buttons = []
        self.settings_visible = False

        self.selected_answer = tk.StringVar(value="")
        self.mode_var = tk.StringVar(value=MODE_SEQUENTIAL)
        self.review_scope_var = tk.StringVar(value=SCOPE_ALL)
        self.auto_save_var = tk.BooleanVar(value=True)
        self.meta_var = tk.StringVar(value="")
        self.feedback_var = tk.StringVar(value="")
        self.save_status_var = tk.StringVar(value="尚未保存")

        self.progress, startup_notice = load_progress_file(
            self.progress_path,
            self.total_questions,
        )
        self.mode_var.set(self.progress["mode"])
        self.review_scope_var.set(self.progress["review_scope"])
        self.auto_save_var.set(self.progress["auto_save"])

        self._configure_window()
        self._build_layout()
        self.root.bind("<Key>", self.handle_key_press)
        self.root.bind("<Control-s>", lambda _event: self.save_progress(show_dialog=True))

        if not self.progress_path.exists():
            self.save_progress(show_dialog=False)
        if startup_notice:
            messagebox.showwarning("进度提示", startup_notice)

        self.show_question()

    def _configure_window(self):
        self.root.title("毛概选择题刷题器")
        self.root.geometry("1120x720")
        self.root.minsize(980, 620)
        self.root.configure(bg="#eef2f7")

        self.font_title = ("Microsoft YaHei UI", 18, "bold")
        self.font_body = ("Microsoft YaHei UI", 11)
        self.font_body_bold = ("Microsoft YaHei UI", 11, "bold")
        self.font_small = ("Microsoft YaHei UI", 9)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

    def _build_layout(self):
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self._build_top_bar()

        self.body_frame = tk.Frame(self.root, bg="#eef2f7")
        self.body_frame.grid(row=1, column=0, sticky="nsew")
        self.body_frame.grid_rowconfigure(0, weight=1)
        self.body_frame.grid_columnconfigure(1, weight=1)

        self._build_number_panel()
        self._build_question_panel()
        self._build_settings_panel()

    def _build_top_bar(self):
        top = tk.Frame(self.root, bg="#172033", padx=18, pady=14)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(1, weight=1)

        title_block = tk.Frame(top, bg="#172033")
        title_block.grid(row=0, column=0, sticky="w")
        tk.Label(
            title_block,
            text="毛概选择题刷题器",
            bg="#172033",
            fg="#f8fafc",
            font=self.font_title,
        ).pack(anchor="w")
        tk.Label(
            title_block,
            text="仅供学习 请勿商用",
            bg="#172033",
            fg="#cbd5e1",
            font=self.font_small,
        ).pack(anchor="w", pady=(3, 0))

        action_bar = tk.Frame(top, bg="#172033")
        action_bar.grid(row=0, column=2, sticky="e")
        self.save_button = self._make_top_button(
            action_bar,
            "保存进度",
            lambda: self.save_progress(show_dialog=True),
        )
        self.save_button.pack(side="left", padx=(0, 8))
        self.settings_button = self._make_top_button(
            action_bar,
            "设置",
            self.toggle_settings,
        )
        self.settings_button.pack(side="left")

    def _make_top_button(self, parent, text, command):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg="#f8fafc",
            fg="#172033",
            activebackground="#dbeafe",
            activeforeground="#172033",
            relief="flat",
            padx=14,
            pady=8,
            font=self.font_body_bold,
            cursor="hand2",
        )

    def _build_number_panel(self):
        panel = tk.Frame(self.body_frame, bg="#f8fafc", padx=12, pady=14, width=220)
        panel.grid(row=0, column=0, sticky="nsw")
        panel.grid_propagate(False)
        panel.grid_rowconfigure(2, weight=1)

        tk.Label(
            panel,
            text="题号导航",
            bg="#f8fafc",
            fg="#111827",
            font=self.font_body_bold,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            panel,
            text="颜色表示答题状态",
            bg="#f8fafc",
            fg="#64748b",
            font=self.font_small,
        ).grid(row=1, column=0, sticky="w", pady=(2, 10))

        container = tk.Frame(panel, bg="#f8fafc")
        container.grid(row=2, column=0, sticky="nsew")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.number_canvas = tk.Canvas(
            container,
            bg="#f8fafc",
            bd=0,
            highlightthickness=0,
            width=188,
        )
        scrollbar = ttk.Scrollbar(
            container,
            orient="vertical",
            command=self.number_canvas.yview,
        )
        self.number_canvas.configure(yscrollcommand=scrollbar.set)
        self.number_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.number_grid = tk.Frame(self.number_canvas, bg="#f8fafc")
        self.number_canvas_window = self.number_canvas.create_window(
            (0, 0),
            window=self.number_grid,
            anchor="nw",
        )
        self.number_grid.bind("<Configure>", self._update_number_scroll_region)
        self.number_canvas.bind("<Configure>", self._resize_number_grid)
        self.number_canvas.bind_all("<MouseWheel>", self._scroll_number_panel)

        for index in range(self.total_questions):
            button = tk.Button(
                self.number_grid,
                text=str(index + 1),
                width=4,
                relief="flat",
                bd=1,
                font=self.font_small,
                cursor="hand2",
                command=lambda value=index: self.go_to_question(value),
            )
            button.grid(row=index // 5, column=index % 5, padx=3, pady=3)
            self.number_buttons.append(button)

    def _build_question_panel(self):
        panel = tk.Frame(self.body_frame, bg="#eef2f7", padx=18, pady=18)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        panel.bind("<Configure>", self._resize_text_wraps)

        meta = tk.Frame(panel, bg="#eef2f7")
        meta.grid(row=0, column=0, sticky="ew")
        meta.grid_columnconfigure(0, weight=1)
        tk.Label(
            meta,
            textvariable=self.meta_var,
            bg="#eef2f7",
            fg="#475569",
            font=self.font_small,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            meta,
            textvariable=self.save_status_var,
            bg="#eef2f7",
            fg="#64748b",
            font=self.font_small,
        ).grid(row=0, column=1, sticky="e")

        question_card = tk.Frame(
            panel,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#d8dee9",
            padx=20,
            pady=18,
        )
        question_card.grid(row=1, column=0, sticky="ew", pady=(10, 14))
        question_card.grid_columnconfigure(0, weight=1)
        self.question_label = tk.Label(
            question_card,
            text="",
            bg="#ffffff",
            fg="#111827",
            justify="left",
            anchor="w",
            wraplength=760,
            font=("Microsoft YaHei UI", 13, "bold"),
        )
        self.question_label.grid(row=0, column=0, sticky="ew")

        work_area = tk.Frame(panel, bg="#eef2f7")
        work_area.grid(row=2, column=0, sticky="nsew")
        work_area.grid_rowconfigure(0, weight=1)
        work_area.grid_columnconfigure(0, weight=1)

        self.options_frame = tk.Frame(work_area, bg="#eef2f7")
        self.options_frame.grid(row=0, column=0, sticky="new")
        self.options_frame.grid_columnconfigure(0, weight=1)

        for index, answer_key in enumerate(ANSWER_KEYS):
            option_var = tk.BooleanVar(value=False)
            button = tk.Checkbutton(
                self.options_frame,
                text="",
                variable=option_var,
                onvalue=True,
                offvalue=False,
                indicatoron=False,
                anchor="w",
                justify="left",
                wraplength=740,
                padx=16,
                pady=12,
                bg="#ffffff",
                fg="#111827",
                activebackground="#e0f2fe",
                selectcolor="#dbeafe",
                relief="flat",
                bd=1,
                font=self.font_body,
                cursor="hand2",
                command=lambda value=answer_key: self.select_answer(value),
            )
            button.grid(row=index, column=0, sticky="ew", pady=(0, 10))
            self.option_buttons.append(button)
            self.option_vars.append(option_var)

        action_row = tk.Frame(panel, bg="#eef2f7")
        action_row.grid(row=3, column=0, sticky="ew", pady=(10, 12))
        self.check_button = self._make_action_button(
            action_row,
            "检查",
            "#2563eb",
            self.check_answer,
        )
        self.check_button.pack(side="left")
        self.next_button = self._make_action_button(
            action_row,
            "下一题",
            "#334155",
            self.next_question,
        )
        self.next_button.pack(side="left", padx=(10, 0))
        self.mark_button = self._make_action_button(
            action_row,
            "标记错题",
            "#b45309",
            self.toggle_current_mark,
        )
        self.mark_button.pack(side="left", padx=(10, 0))

        tk.Label(
            panel,
            textvariable=self.feedback_var,
            bg="#eef2f7",
            fg="#334155",
            font=self.font_body_bold,
            anchor="w",
            justify="left",
        ).grid(row=4, column=0, sticky="ew")

        self.explanation_text = tk.Text(
            panel,
            height=6,
            wrap="word",
            bg="#fff7ed",
            fg="#431407",
            relief="flat",
            padx=14,
            pady=12,
            font=self.font_body,
        )
        self.explanation_text.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        self.explanation_text.configure(state="disabled")

    def _make_action_button(self, parent, text, bg, command):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg="#ffffff",
            activebackground=bg,
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=10,
            font=self.font_body_bold,
            cursor="hand2",
        )

    def _build_settings_panel(self):
        self.settings_panel = tk.Frame(
            self.body_frame,
            bg="#ffffff",
            padx=16,
            pady=18,
            width=260,
            highlightthickness=1,
            highlightbackground="#d8dee9",
        )
        self.settings_panel.grid(row=0, column=2, sticky="nse")
        self.settings_panel.grid_propagate(False)
        self.settings_panel.grid_remove()

        tk.Label(
            self.settings_panel,
            text="设置",
            bg="#ffffff",
            fg="#111827",
            font=("Microsoft YaHei UI", 15, "bold"),
        ).pack(anchor="w")

        tk.Label(
            self.settings_panel,
            text="出题模式",
            bg="#ffffff",
            fg="#475569",
            font=self.font_body_bold,
        ).pack(anchor="w", pady=(22, 8))
        for label, mode in (("顺序出题", MODE_SEQUENTIAL), ("随机出题", MODE_RANDOM)):
            tk.Radiobutton(
                self.settings_panel,
                text=label,
                value=mode,
                variable=self.mode_var,
                command=self.change_mode,
                bg="#ffffff",
                fg="#111827",
                activebackground="#ffffff",
                font=self.font_body,
            ).pack(anchor="w", pady=3)

        tk.Label(
            self.settings_panel,
            text="刷题范围",
            bg="#ffffff",
            fg="#475569",
            font=self.font_body_bold,
        ).pack(anchor="w", pady=(18, 8))
        for label, review_scope in (
            ("全部题", SCOPE_ALL),
            ("当前错题或标记题", SCOPE_WRONG_MARKED),
            ("上一轮错题或标记题", SCOPE_LAST_WRONG_MARKED),
        ):
            tk.Radiobutton(
                self.settings_panel,
                text=label,
                value=review_scope,
                variable=self.review_scope_var,
                command=self.change_review_scope,
                bg="#ffffff",
                fg="#111827",
                activebackground="#ffffff",
                font=self.font_body,
            ).pack(anchor="w", pady=3)

        tk.Checkbutton(
            self.settings_panel,
            text="自动保存",
            variable=self.auto_save_var,
            command=self.change_auto_save,
            bg="#ffffff",
            activebackground="#ffffff",
            fg="#111827",
            font=self.font_body,
        ).pack(anchor="w", pady=(18, 12))

        self._make_settings_button("保存当前进度", lambda: self.save_progress(show_dialog=True))
        self._make_settings_button("加载之前的进度", self.load_progress)
        self._make_settings_button("重置进度", self.reset_progress, bg="#dc2626")
        self._make_settings_button("确定/关闭", self.toggle_settings, bg="#334155")

    def _make_settings_button(self, text, command, bg="#2563eb"):
        tk.Button(
            self.settings_panel,
            text=text,
            command=command,
            bg=bg,
            fg="#ffffff",
            activebackground=bg,
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=9,
            font=self.font_body_bold,
            cursor="hand2",
        ).pack(fill="x", pady=5)

    def _update_number_scroll_region(self, _event):
        self.number_canvas.configure(scrollregion=self.number_canvas.bbox("all"))

    def _resize_number_grid(self, event):
        self.number_canvas.itemconfigure(self.number_canvas_window, width=event.width)

    def _scroll_number_panel(self, event):
        if self.number_canvas.winfo_containing(event.x_root, event.y_root):
            self.number_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _resize_text_wraps(self, event):
        wraplength = max(420, event.width - 80)
        self.question_label.configure(wraplength=wraplength)
        for button in self.option_buttons:
            button.configure(wraplength=wraplength - 20)

    def show_question(self):
        if self.total_questions == 0:
            self.meta_var.set("题库不可用")
            self.question_label.configure(text="没有可用题目。")
            self.feedback_var.set("请检查 questions_data.py。")
            self._set_explanation("")
            return

        current_index = self.progress["current_index"]
        question = self.questions[current_index]
        status = self._current_status()

        self.mode_var.set(self.progress["mode"])
        self.review_scope_var.set(self.progress["review_scope"])
        self.auto_save_var.set(self.progress["auto_save"])
        self.selected_answer.set(status["selected"] or "")
        self.question_label.configure(text=display_question_text(question))
        self._update_meta()
        self._update_options(question, status)
        self._update_feedback(question, status)
        self._update_number_buttons()
        self.root.focus_set()

    def _update_meta(self):
        active_indices = active_question_indices(self.progress, self.total_questions)
        if self.progress.get("review_scope") == SCOPE_ALL:
            checked_total = self.total_questions
            checked_count = sum(
                1 for item in self.progress["question_status"] if item["checked"]
            )
        else:
            checked_total = len(active_indices)
            checked_count = sum(
                1
                for index in active_indices
                if self.progress["question_status"][index]["checked"]
            )
        wrong_count = sum(
            1
            for item in self.progress["question_status"]
            if item["auto_wrong"] or item["manual_marked"]
        )
        mode_name = "随机模式" if self.progress["mode"] == MODE_RANDOM else "顺序模式"
        scope_names = {
            SCOPE_ALL: "全部题",
            SCOPE_WRONG_MARKED: "当前错题/标记",
            SCOPE_LAST_WRONG_MARKED: "上一轮错题/标记",
        }
        scope_name = scope_names.get(self.progress.get("review_scope"), "全部题")
        self.meta_var.set(
            f"{mode_name} | {scope_name} | 第 {self.progress['current_index'] + 1}/{self.total_questions} 题 "
            f"| 已检查 {checked_count}/{checked_total} | 错题/标记 {wrong_count}"
        )

    def _update_options(self, question, status):
        current_index = self.progress["current_index"]
        options = display_options_for_question(self.progress, current_index, question)
        correct_answer = displayed_correct_answer(self.progress, current_index, question)
        selected = normalize_answer(status.get("selected") or "")
        for index, button in enumerate(self.option_buttons):
            if index >= len(options):
                button.grid_remove()
                self.option_vars[index].set(False)
                continue
            answer_key = ANSWER_KEYS[index]
            self.option_vars[index].set(answer_key in selected)
            button.grid()
            button.configure(
                text=options[index],
                state="disabled" if status["checked"] else "normal",
            )
            self._style_option_button(button, answer_key, status, correct_answer)

        can_check = bool(status["selected"]) and not status["checked"]
        self.check_button.configure(state="normal" if can_check else "disabled")
        self.next_button.configure(state="normal")
        self.mark_button.configure(
            text="取消标记" if status["manual_marked"] else "标记错题"
        )

    def _style_option_button(self, button, answer_key, status, correct_answer):
        selected = normalize_answer(status.get("selected") or "")
        if answer_key in selected:
            button.configure(
                bg="#dbeafe",
                selectcolor="#dbeafe",
                fg="#0f172a",
                relief="solid",
            )
        else:
            button.configure(
                bg="#ffffff",
                selectcolor="#ffffff",
                fg="#111827",
                relief="flat",
            )

        if status["checked"]:
            if answer_key in normalize_answer(correct_answer):
                button.configure(bg="#dcfce7", selectcolor="#dcfce7", fg="#14532d")
            elif answer_key in selected:
                button.configure(bg="#fee2e2", selectcolor="#fee2e2", fg="#7f1d1d")

    def _update_feedback(self, question, status):
        if not status["checked"]:
            self.feedback_var.set("选择答案后点击“检查”，或按 Enter 判题。")
            self._set_explanation("检查后显示解析。")
            return

        correct_answer = displayed_correct_answer(
            self.progress,
            self.progress["current_index"],
            question,
        )
        explanation = question.get("explanation", "") or "暂无解析。"
        if status["is_correct"]:
            self.feedback_var.set(f"回答正确。正确答案：{correct_answer}")
        else:
            self.feedback_var.set(f"回答错误。正确答案：{correct_answer}")
        self._set_explanation(explanation)

    def _set_explanation(self, text):
        self.explanation_text.configure(state="normal")
        self.explanation_text.delete("1.0", "end")
        self.explanation_text.insert("1.0", text)
        self.explanation_text.configure(state="disabled")

    def _update_number_buttons(self):
        for index, button in enumerate(self.number_buttons):
            status = self.progress["question_status"][index]
            is_current = index == self.progress["current_index"]
            label = f"{index + 1}{'*' if status['manual_marked'] else ''}"

            if is_current:
                bg, fg, relief = "#2563eb", "#ffffff", "sunken"
            elif status["auto_wrong"] or (
                status["checked"] and status["is_correct"] is False
            ):
                bg, fg, relief = "#fee2e2", "#7f1d1d", "flat"
            elif status["checked"] and status["is_correct"]:
                bg, fg, relief = "#dcfce7", "#14532d", "flat"
            elif status["manual_marked"]:
                bg, fg, relief = "#fed7aa", "#7c2d12", "flat"
            else:
                bg, fg, relief = "#e5e7eb", "#334155", "flat"

            button.configure(text=label, bg=bg, fg=fg, relief=relief)

    def _current_status(self):
        return self.progress["question_status"][self.progress["current_index"]]

    def select_answer(self, answer_key):
        status = self._current_status()
        if status["checked"]:
            return

        question = self.questions[self.progress["current_index"]]
        option_count = len(question.get("options", []))
        if answer_key not in ANSWER_KEYS[:option_count]:
            return

        if is_multiple_choice_question(question):
            selected = set(normalize_answer(status.get("selected") or ""))
            if answer_key in selected:
                selected.remove(answer_key)
            else:
                selected.add(answer_key)
            status["selected"] = normalize_answer("".join(selected)) or None
        else:
            status["selected"] = answer_key
        self.selected_answer.set(status["selected"] or "")
        self.save_status_var.set("有未保存更改")
        self._autosave()
        self.show_question()

    def check_answer(self):
        status = self._current_status()
        if status["checked"]:
            return
        selected = normalize_answer(status["selected"] or self.selected_answer.get())
        if not selected:
            self.feedback_var.set("请先选择一个答案。")
            return

        question = self.questions[self.progress["current_index"]]
        record_check_result(
            self.progress,
            self.progress["current_index"],
            selected,
            displayed_correct_answer(
                self.progress,
                self.progress["current_index"],
                question,
            ),
        )
        self.save_status_var.set("有未保存更改")
        self._autosave()
        self.show_question()

    def next_question(self):
        self._move_question(direction=1)

    def previous_question(self):
        self._move_question(direction=-1)

    def _move_question(self, direction):
        next_index = next_question_index(self.progress, self.total_questions, direction)
        if next_index == self.progress["current_index"]:
            edge = "最后一题" if direction > 0 else "第一题"
            self.feedback_var.set(f"已经是当前模式下的{edge}。")
            return
        self.go_to_question(next_index)

    def go_to_question(self, question_index):
        if not 0 <= question_index < self.total_questions:
            return
        if not question_in_review_scope(self.progress, question_index):
            self.feedback_var.set("当前刷题范围只包含错题或标记题。")
            return
        self.progress["current_index"] = question_index
        self.save_status_var.set("有未保存更改")
        self._autosave()
        self.show_question()

    def toggle_current_mark(self):
        toggle_manual_mark(self.progress, self.progress["current_index"])
        self.save_status_var.set("有未保存更改")
        self._autosave()
        self.show_question()

    def change_review_scope(self):
        review_scope = self.review_scope_var.get()
        if review_scope not in (SCOPE_ALL, SCOPE_WRONG_MARKED, SCOPE_LAST_WRONG_MARKED):
            self.review_scope_var.set(self.progress.get("review_scope", SCOPE_ALL))
            return

        previous_scope = self.progress.get("review_scope", SCOPE_ALL)
        self.progress["review_scope"] = review_scope
        active_indices = active_question_indices(self.progress, self.total_questions)
        if review_scope != SCOPE_ALL and not active_indices:
            self.progress["review_scope"] = previous_scope
            self.review_scope_var.set(previous_scope)
            self.feedback_var.set("暂无错题或标记题，已保持当前刷题范围。")
            return

        if active_indices and self.progress["current_index"] not in active_indices:
            self.progress["current_index"] = active_indices[0]

        self.save_status_var.set("有未保存更改")
        self._autosave()
        self.show_question()

    def change_mode(self):
        mode = self.mode_var.get()
        if mode not in (MODE_SEQUENTIAL, MODE_RANDOM):
            return
        previous_mode = self.progress["mode"]
        random_order_invalid = sorted(self.progress["random_order"]) != list(
            range(self.total_questions)
        )
        self.progress["mode"] = mode
        if mode == MODE_RANDOM:
            if previous_mode != MODE_RANDOM or random_order_invalid:
                rebuild_random_order_for_current_state(
                    self.progress,
                    self.total_questions,
                )
        elif random_order_invalid:
            self.progress["random_order"] = list(range(self.total_questions))
            random.shuffle(self.progress["random_order"])
        self.save_status_var.set("有未保存更改")
        self._autosave()
        self.show_question()

    def change_auto_save(self):
        self.progress["auto_save"] = bool(self.auto_save_var.get())
        self.save_status_var.set("自动保存已开启" if self.progress["auto_save"] else "自动保存已关闭")
        if self.progress["auto_save"]:
            self.save_progress(show_dialog=False)

    def toggle_settings(self):
        if self.settings_visible:
            self.settings_panel.grid_remove()
            self.settings_button.configure(text="设置")
        else:
            self.settings_panel.grid()
            self.settings_button.configure(text="关闭设置")
        self.settings_visible = not self.settings_visible

    def save_progress(self, show_dialog=False):
        try:
            save_progress_file(self.progress_path, self.progress)
        except OSError as exc:
            self.save_status_var.set("保存失败")
            messagebox.showerror("保存失败", str(exc))
            return False

        self.save_status_var.set("进度已保存")
        if show_dialog:
            messagebox.showinfo("保存进度", "当前进度已保存。")
        return True

    def _autosave(self):
        if self.progress.get("auto_save", True):
            self.save_progress(show_dialog=False)

    def load_progress(self):
        progress, notice = load_progress_file(self.progress_path, self.total_questions)
        self.progress = progress
        self.mode_var.set(self.progress["mode"])
        self.review_scope_var.set(self.progress["review_scope"])
        self.auto_save_var.set(self.progress["auto_save"])
        if notice:
            messagebox.showwarning("进度提示", notice)
        else:
            messagebox.showinfo("加载进度", "已加载之前的进度。")
        self.show_question()

    def reset_progress(self):
        confirmed = messagebox.askyesno(
            "重置进度",
            "确定要清空答题状态、错题标记和当前题位置吗？",
        )
        if not confirmed:
            return
        try:
            summary_path = write_summary_file(
                self.summary_dir,
                self.questions,
                self.progress,
            )
        except OSError as exc:
            messagebox.showerror("生成错题 Summary 失败", f"未重置进度：{exc}")
            return
        last_wrong_marked_indices = live_wrong_marked_indices(
            self.progress,
            self.total_questions,
        )
        self.progress = create_default_progress(self.total_questions)
        self.progress["option_orders"] = build_option_orders(
            self.questions,
            shuffle_options=True,
        )
        self.progress["last_wrong_marked_indices"] = last_wrong_marked_indices
        self.review_scope_var.set(self.progress["review_scope"])
        self.save_progress(show_dialog=False)
        self.show_question()
        messagebox.showinfo(
            "重置进度",
            f"已生成错题记录：{summary_path}\n进度已重置。",
        )

    def handle_key_press(self, event):
        if event.keysym == "Return":
            if self._current_status()["checked"]:
                self.next_question()
            else:
                self.check_answer()
            return

        if event.keysym == "Left":
            self.previous_question()
            return
        if event.keysym == "Right":
            self.next_question()
            return

        answer_key = (event.char or "").upper()
        if answer_key in ANSWER_KEYS:
            self.select_answer(answer_key)


def main():
    root = tk.Tk()
    if QUESTIONS_IMPORT_ERROR is not None:
        root.withdraw()
        messagebox.showerror("题库不可用", f"题库导入失败：{QUESTIONS_IMPORT_ERROR}")
        root.destroy()
        return
    QuizApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
