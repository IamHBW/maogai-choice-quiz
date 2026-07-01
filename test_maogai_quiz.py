import random
import tempfile
import tkinter as tk
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from maogai_quiz import (
    QuizApp,
    build_summary_markdown,
    create_default_progress,
    displayed_correct_answer,
    next_question_index,
    record_check_result,
    toggle_manual_mark,
    write_summary_file,
)
from questions_data import questions


class MaogaiQuestionDataTests(unittest.TestCase):
    def assert_question_answer(self, snippet, expected_answer):
        matches = [item for item in questions if snippet in item["question"]]
        self.assertEqual(len(matches), 1, snippet)
        self.assertEqual(matches[0]["answer"], expected_answer)

    def test_expected_maogai_questions_are_present(self):
        expected_answers = {
            "毛泽东思想是“马克思主义中国化”的理论成果": "C",
            "科学发展观的根本方法": "C",
            "毛泽东思想活的灵魂包括": "ABC",
            "社会主义核心价值体系的基本内容包括": "ABCDE",
            "1935年召开的哪次会议": "B",
        }
        for snippet, expected_answer in expected_answers.items():
            with self.subTest(snippet=snippet):
                self.assert_question_answer(snippet, expected_answer)

    def test_removed_mechanical_question_stays_removed(self):
        self.assertFalse(
            any(
                "机械" in item["question"]
                or any("机械" in option for option in item.get("options", []))
                for item in questions
            ),
            "Unrelated mechanical-engineering content should not be in the bank.",
        )

    def test_25_26_autumn_winter_questions_are_inserted_before_meeting_document_items(self):
        autumn_winter_questions = [
            item
            for item in questions
            if "25-26秋冬回忆卷_答案.md" in item["explanation"]
        ]
        self.assertEqual(len(autumn_winter_questions), 24)
        self.assertTrue(
            all("选项为按教材和题库风格补全" in item["explanation"] for item in autumn_winter_questions)
        )

        first_autumn_winter_index = questions.index(autumn_winter_questions[0])
        first_meeting_document_index = next(
            index
            for index, item in enumerate(questions)
            if "重要会议和文献.md" in item["explanation"]
        )

        self.assertLess(first_autumn_winter_index, first_meeting_document_index)

    def test_24_25_autumn_winter_questions_are_inserted_before_25_26_items(self):
        autumn_winter_questions = [
            item
            for item in questions
            if "24-25秋冬回忆卷.md" in item["explanation"]
        ]
        self.assertEqual(len(autumn_winter_questions), 16)
        self.assertTrue(
            all("选项为按教材和题库风格补全" in item["explanation"] for item in autumn_winter_questions)
        )

        first_24_25_index = questions.index(autumn_winter_questions[0])
        first_25_26_index = next(
            index
            for index, item in enumerate(questions)
            if "25-26秋冬回忆卷_答案.md" in item["explanation"]
        )

        self.assertLess(first_24_25_index, first_25_26_index)

    def test_eighteenth_congress_question_uses_same_domain_options(self):
        matches = [item for item in questions if "2012年党的十八大将科学发展观" in item["question"]]
        self.assertEqual(len(matches), 1)
        self.assertEqual(
            matches[0]["options"],
            [
                "A. 党必须长期坚持的指导思想",
                "B. 新时期党的基本路线",
                "C. 马克思主义中国化时代化的第一次历史性飞跃",
                "D. 中国特色社会主义理论体系的开篇之作",
            ],
        )
        self.assertEqual(matches[0]["answer"], "A")

    def test_question_bank_schema_is_valid_and_uses_only_verified_items(self):
        self.assertGreaterEqual(len(questions), 60)
        uncertain_markers = ("不确定", "疑似", "具体忘了", "不知道是不是", "猜测", "xxx", "干扰项")
        valid_letters = tuple("ABCDE")

        for index, question in enumerate(questions, start=1):
            with self.subTest(index=index):
                self.assertIn(question.get("type"), ("single", "multiple"))
                self.assertTrue(question.get("question", "").strip())
                self.assertTrue(question.get("explanation", "").strip())
                self.assertNotIn("机械", question["question"])
                for marker in uncertain_markers:
                    self.assertNotIn(marker, question["question"])
                    self.assertNotIn(marker, question["explanation"])

                options = question.get("options", [])
                self.assertTrue(2 <= len(options) <= 5)
                expected_labels = valid_letters[: len(options)]
                for label, option in zip(expected_labels, options):
                    self.assertTrue(option.startswith(f"{label}. "), option)
                    for marker in uncertain_markers:
                        self.assertNotIn(marker, option)

                answer = question.get("answer", "")
                self.assertEqual(answer, "".join(sorted(answer)))
                self.assertTrue(set(answer).issubset(set(expected_labels)))
                if question["type"] == "single":
                    self.assertEqual(len(answer), 1)
                else:
                    self.assertGreater(len(answer), 1)


class QuizProgressTests(unittest.TestCase):
    def make_root(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is not available: {exc}")
        root.withdraw()
        return root

    def test_default_progress_has_one_status_per_question_and_saved_random_order(self):
        progress = create_default_progress(4, rng=random.Random(7))

        self.assertEqual(progress["current_index"], 0)
        self.assertEqual(progress["mode"], "sequential")
        self.assertTrue(progress["auto_save"])
        self.assertCountEqual(progress["random_order"], [0, 1, 2, 3])
        self.assertEqual(len(progress["question_status"]), 4)
        self.assertEqual(
            progress["question_status"][0],
            {
                "selected": None,
                "checked": False,
                "is_correct": None,
                "auto_wrong": False,
                "manual_marked": False,
            },
        )

    def test_next_question_uses_sequential_or_saved_random_order(self):
        progress = create_default_progress(5, rng=random.Random(1))

        self.assertEqual(next_question_index(progress, 5), 1)

        progress["mode"] = "random"
        progress["random_order"] = [3, 1, 4, 0, 2]
        progress["current_index"] = 1

        self.assertEqual(next_question_index(progress, 5), 4)

    def test_all_review_scope_keeps_sequential_navigation_unchanged(self):
        progress = create_default_progress(5, rng=random.Random(1))
        progress["current_index"] = 2
        progress["question_status"][1]["auto_wrong"] = True
        progress["question_status"][4]["manual_marked"] = True

        self.assertEqual(next_question_index(progress, 5), 3)
        self.assertEqual(next_question_index(progress, 5, direction=-1), 1)

    def test_all_review_scope_keeps_random_navigation_unchanged(self):
        progress = create_default_progress(5, rng=random.Random(1))
        progress["mode"] = "random"
        progress["random_order"] = [4, 1, 3, 0, 2]
        progress["current_index"] = 1
        progress["question_status"][0]["auto_wrong"] = True
        progress["question_status"][4]["manual_marked"] = True

        self.assertEqual(next_question_index(progress, 5), 3)
        self.assertEqual(next_question_index(progress, 5, direction=-1), 4)

    def test_wrong_marked_scope_navigates_only_live_wrong_or_marked_questions(self):
        progress = create_default_progress(5, rng=random.Random(1))
        progress["review_scope"] = "wrong_marked"
        progress["current_index"] = 1
        progress["question_status"][1]["auto_wrong"] = True
        progress["question_status"][3]["manual_marked"] = True

        self.assertEqual(next_question_index(progress, 5), 3)
        progress["current_index"] = 3
        self.assertEqual(next_question_index(progress, 5, direction=-1), 1)

    def test_wrong_marked_scope_random_navigation_uses_filtered_saved_order(self):
        progress = create_default_progress(5, rng=random.Random(1))
        progress["mode"] = "random"
        progress["review_scope"] = "wrong_marked"
        progress["random_order"] = [2, 4, 0, 3, 1]
        progress["current_index"] = 4
        progress["question_status"][1]["auto_wrong"] = True
        progress["question_status"][4]["manual_marked"] = True

        self.assertEqual(next_question_index(progress, 5), 1)
        progress["current_index"] = 1
        self.assertEqual(next_question_index(progress, 5, direction=-1), 4)

    def test_last_wrong_marked_scope_navigates_saved_previous_round_indices(self):
        progress = create_default_progress(5, rng=random.Random(1))
        progress["review_scope"] = "last_wrong_marked"
        progress["last_wrong_marked_indices"] = [1, 4]
        progress["current_index"] = 1

        self.assertEqual(next_question_index(progress, 5), 4)
        progress["current_index"] = 4
        self.assertEqual(next_question_index(progress, 5, direction=-1), 1)

    def test_random_next_question_follows_saved_order_even_when_checked(self):
        progress = create_default_progress(5, rng=random.Random(1))
        progress["mode"] = "random"
        progress["random_order"] = [0, 2, 4, 1, 3]
        progress["current_index"] = 0
        progress["question_status"][2]["checked"] = True
        progress["question_status"][4]["checked"] = True

        self.assertEqual(next_question_index(progress, 5), 2)

    def test_random_previous_question_follows_saved_order_even_when_checked(self):
        progress = create_default_progress(5, rng=random.Random(1))
        progress["mode"] = "random"
        progress["random_order"] = [0, 2, 4, 1, 3]
        progress["current_index"] = 3
        progress["question_status"][1]["checked"] = True
        progress["question_status"][4]["checked"] = True

        self.assertEqual(next_question_index(progress, 5, direction=-1), 1)

    def test_random_navigation_allows_checked_question_when_no_unchecked_remains(self):
        progress = create_default_progress(3, rng=random.Random(1))
        progress["mode"] = "random"
        progress["random_order"] = [0, 1, 2]
        progress["current_index"] = 0
        for status in progress["question_status"]:
            status["checked"] = True

        self.assertEqual(next_question_index(progress, 3), 1)

    def test_random_next_stops_at_saved_order_end(self):
        progress = create_default_progress(4, rng=random.Random(1))
        progress["mode"] = "random"
        progress["random_order"] = [0, 1, 2, 3]
        progress["current_index"] = 3
        progress["question_status"][0]["checked"] = True
        progress["question_status"][1]["checked"] = False
        progress["question_status"][2]["checked"] = True

        self.assertEqual(next_question_index(progress, 4), 3)

    def test_wrong_answer_sets_auto_wrong_without_requiring_manual_mark(self):
        progress = create_default_progress(2, rng=random.Random(2))

        record_check_result(progress, 0, "A", "B")

        self.assertEqual(progress["question_status"][0]["selected"], "A")
        self.assertTrue(progress["question_status"][0]["checked"])
        self.assertFalse(progress["question_status"][0]["is_correct"])
        self.assertTrue(progress["question_status"][0]["auto_wrong"])
        self.assertFalse(progress["question_status"][0]["manual_marked"])

    def test_manual_mark_toggle_does_not_clear_auto_wrong(self):
        progress = create_default_progress(1, rng=random.Random(3))
        record_check_result(progress, 0, "A", "B")

        toggle_manual_mark(progress, 0)
        toggle_manual_mark(progress, 0)

        self.assertTrue(progress["question_status"][0]["auto_wrong"])
        self.assertFalse(progress["question_status"][0]["manual_marked"])

    def test_tk_app_can_initialize_with_minimal_question_bank(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                progress_path = Path(temp_dir) / "quiz_progress.json"
                app = QuizApp(
                    root,
                    question_bank=[
                        {
                            "question": "Question",
                            "options": ["A. one", "B. two"],
                            "answer": "A",
                        }
                    ],
                    progress_path=progress_path,
                )
                root.update_idletasks()
                self.assertEqual(root.title(), "毛概选择题刷题器")
                self.assertEqual(app.question_label.cget("text"), "【单选】 Question")
                self.assertTrue(progress_path.exists())
        finally:
            root.destroy()

    def test_multiple_choice_question_label_shows_question_type(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {
                            "type": "multiple",
                            "question": "Q1",
                            "options": ["A. one", "B. two", "C. three"],
                            "answer": "AC",
                        }
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                )

                self.assertEqual(app.question_label.cget("text"), "【多选】 Q1")
        finally:
            root.destroy()

    def test_keyboard_selection_check_and_arrow_navigation(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {"question": "Q1", "options": ["A. one", "B. two"], "answer": "B"},
                        {"question": "Q2", "options": ["A. one", "B. two"], "answer": "A"},
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                )

                app.handle_key_press(SimpleNamespace(keysym="a", char="a"))

                status = app.progress["question_status"][0]
                self.assertEqual(status["selected"], "A")
                self.assertFalse(status["checked"])

                app.handle_key_press(SimpleNamespace(keysym="Return", char=""))

                self.assertTrue(status["checked"])
                self.assertTrue(status["auto_wrong"])

                app.handle_key_press(SimpleNamespace(keysym="Return", char=""))
                self.assertEqual(app.progress["current_index"], 1)

                app.handle_key_press(SimpleNamespace(keysym="Left", char=""))
                self.assertEqual(app.progress["current_index"], 0)

                app.handle_key_press(SimpleNamespace(keysym="Right", char=""))
                self.assertEqual(app.progress["current_index"], 1)
        finally:
            root.destroy()

    def test_unchecked_selection_does_not_reveal_correct_answer_color(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {"question": "Q1", "options": ["A. one", "B. two"], "answer": "B"}
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                )

                app.select_answer("A")

                self.assertEqual(app.option_buttons[0].cget("bg"), "#dbeafe")
                self.assertEqual(app.option_buttons[0].cget("selectcolor"), "#dbeafe")
                self.assertEqual(app.option_buttons[1].cget("bg"), "#ffffff")
                self.assertEqual(app.option_buttons[1].cget("selectcolor"), "#ffffff")
        finally:
            root.destroy()

    def test_wrong_answer_marks_selected_option_red_and_correct_option_green(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {"question": "Q1", "options": ["A. one", "B. two"], "answer": "B"}
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                )

                app.select_answer("A")
                app.check_answer()

                self.assertEqual(app.option_buttons[0].cget("bg"), "#fee2e2")
                self.assertEqual(app.option_buttons[0].cget("selectcolor"), "#fee2e2")
                self.assertEqual(app.option_buttons[1].cget("bg"), "#dcfce7")
                self.assertEqual(app.option_buttons[1].cget("selectcolor"), "#dcfce7")
        finally:
            root.destroy()

    def test_correct_answer_marks_only_selected_correct_option_green(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {"question": "Q1", "options": ["A. one", "B. two"], "answer": "B"}
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                )

                app.select_answer("B")
                app.check_answer()

                self.assertEqual(app.option_buttons[0].cget("bg"), "#ffffff")
                self.assertEqual(app.option_buttons[0].cget("selectcolor"), "#ffffff")
                self.assertEqual(app.option_buttons[1].cget("bg"), "#dcfce7")
                self.assertEqual(app.option_buttons[1].cget("selectcolor"), "#dcfce7")
        finally:
            root.destroy()

    def test_option_order_remaps_displayed_options_and_correct_answer(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {
                            "question": "Q1",
                            "options": ["A. make", "B. move", "C. analyze"],
                            "answer": "B",
                        }
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                )
                app.progress["option_orders"] = [[2, 0, 1]]

                app.show_question()
                app.select_answer("C")
                app.check_answer()

                self.assertEqual(app.option_buttons[0].cget("text"), "A. analyze")
                self.assertEqual(app.option_buttons[1].cget("text"), "B. make")
                self.assertEqual(app.option_buttons[2].cget("text"), "C. move")
                self.assertTrue(app.progress["question_status"][0]["is_correct"])
                self.assertIn("正确答案：C", app.feedback_var.get())
        finally:
            root.destroy()

    def test_option_order_remaps_multiple_choice_correct_answer(self):
        question = {
            "type": "multiple",
            "question": "Q1",
            "options": [
                "A. first",
                "B. second",
                "C. third",
                "D. fourth",
                "E. fifth",
            ],
            "answer": "ACE",
        }
        progress = create_default_progress(1, rng=random.Random(1))
        progress["option_orders"] = [[4, 0, 2, 1, 3]]

        self.assertEqual(
            displayed_correct_answer(progress, 0, question),
            "ABC",
        )

    def test_multiple_choice_record_check_uses_answer_sets(self):
        progress = create_default_progress(1, rng=random.Random(1))

        self.assertTrue(record_check_result(progress, 0, "CA", "AC"))
        self.assertEqual(progress["question_status"][0]["selected"], "AC")
        self.assertTrue(progress["question_status"][0]["is_correct"])

    def test_multiple_choice_selection_toggles_until_checked(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {
                            "type": "multiple",
                            "question": "Q1",
                            "options": ["A. one", "B. two", "C. three"],
                            "answer": "AC",
                        }
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                )

                app.select_answer("A")
                app.select_answer("C")
                app.select_answer("A")
                self.assertEqual(app.progress["question_status"][0]["selected"], "C")

                app.select_answer("A")
                app.check_answer()
                self.assertTrue(app.progress["question_status"][0]["is_correct"])
                self.assertIn("正确答案：AC", app.feedback_var.get())
        finally:
            root.destroy()

    def test_reset_generates_shuffled_option_orders(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {
                            "question": "Q1",
                            "options": ["A. make", "B. move", "C. analyze"],
                            "answer": "B",
                        },
                        {
                            "question": "Q2",
                            "options": ["A. √", "B. ×"],
                            "answer": "A",
                        },
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                    summary_dir=Path(temp_dir) / "summary",
                )

                with patch("maogai_quiz.messagebox.askyesno", return_value=True), patch(
                    "maogai_quiz.messagebox.showinfo"
                ), patch(
                    "maogai_quiz.random.shuffle",
                    side_effect=lambda values: values.reverse(),
                ):
                    app.reset_progress()

                self.assertEqual(app.progress["option_orders"], [[2, 1, 0], [0, 1]])
                self.assertEqual(app.option_buttons[0].cget("text"), "A. analyze")
                self.assertEqual(app.option_buttons[1].cget("text"), "B. move")
                self.assertEqual(app.option_buttons[2].cget("text"), "C. make")
        finally:
            root.destroy()

    def test_reset_changes_option_order_when_shuffle_leaves_identity_order(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {
                            "question": "Q1",
                            "options": ["A. make", "B. move", "C. analyze"],
                            "answer": "B",
                        },
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                    summary_dir=Path(temp_dir) / "summary",
                )

                with patch("maogai_quiz.messagebox.askyesno", return_value=True), patch(
                    "maogai_quiz.messagebox.showinfo"
                ), patch("maogai_quiz.random.shuffle", side_effect=lambda _values: None):
                    app.reset_progress()

                self.assertEqual(app.progress["option_orders"], [[1, 2, 0]])
                self.assertEqual(app.option_buttons[0].cget("text"), "A. move")
        finally:
            root.destroy()

    def test_random_mode_next_uses_queue_but_jump_uses_original_index(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {"question": "Q1", "options": ["A. one"], "answer": "A"},
                        {"question": "Q2", "options": ["A. one"], "answer": "A"},
                        {"question": "Q3", "options": ["A. one"], "answer": "A"},
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                )
                app.progress["mode"] = "random"
                app.progress["random_order"] = [2, 0, 1]
                app.progress["current_index"] = 0

                app.next_question()
                self.assertEqual(app.progress["current_index"], 1)

                app.go_to_question(2)
                self.assertEqual(app.progress["current_index"], 2)
        finally:
            root.destroy()

    def test_random_left_arrow_returns_to_previous_checked_question_in_order(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {"question": "Q1", "options": ["A. one"], "answer": "A"},
                        {"question": "Q2", "options": ["A. one"], "answer": "A"},
                        {"question": "Q3", "options": ["A. one"], "answer": "A"},
                        {"question": "Q4", "options": ["A. one"], "answer": "A"},
                        {"question": "Q5", "options": ["A. one"], "answer": "A"},
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                )
                app.progress["mode"] = "random"
                app.progress["random_order"] = [0, 3, 4, 1, 2]
                app.progress["current_index"] = 3
                app.progress["question_status"][0]["checked"] = True

                app.handle_key_press(SimpleNamespace(keysym="Left", char=""))

                self.assertEqual(app.progress["current_index"], 0)
        finally:
            root.destroy()

    def test_switching_to_random_from_checked_question_moves_to_first_unchecked_question(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {"question": "Q1", "options": ["A. one"], "answer": "A"},
                        {"question": "Q2", "options": ["A. one"], "answer": "A"},
                        {"question": "Q3", "options": ["A. one"], "answer": "A"},
                        {"question": "Q4", "options": ["A. one"], "answer": "A"},
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                )
                app.progress["current_index"] = 0
                app.progress["random_order"] = [3, 1, 0, 2]
                app.progress["question_status"][0]["checked"] = True
                app.progress["question_status"][1]["checked"] = True
                app.mode_var.set("random")

                with patch("maogai_quiz.random.shuffle", side_effect=lambda values: values.reverse()):
                    app.change_mode()

                self.assertEqual(app.progress["random_order"], [0, 1, 3, 2])
                self.assertEqual(app.progress["current_index"], 3)
        finally:
            root.destroy()

    def test_switching_to_random_keeps_unchecked_current_question_at_unchecked_front(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {"question": "Q1", "options": ["A. one"], "answer": "A"},
                        {"question": "Q2", "options": ["A. one"], "answer": "A"},
                        {"question": "Q3", "options": ["A. one"], "answer": "A"},
                        {"question": "Q4", "options": ["A. one"], "answer": "A"},
                        {"question": "Q5", "options": ["A. one"], "answer": "A"},
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                )
                app.progress["current_index"] = 2
                app.progress["random_order"] = [4, 3, 2, 1, 0]
                app.progress["question_status"][0]["checked"] = True
                app.progress["question_status"][1]["checked"] = True
                app.mode_var.set("random")

                with patch("maogai_quiz.random.shuffle", side_effect=lambda values: values.reverse()):
                    app.change_mode()

                self.assertEqual(app.progress["random_order"], [0, 1, 2, 4, 3])
                self.assertEqual(app.progress["current_index"], 2)
        finally:
            root.destroy()

    def test_empty_wrong_marked_scope_is_rejected(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {"question": "Q1", "options": ["A. one"], "answer": "A"},
                        {"question": "Q2", "options": ["A. one"], "answer": "A"},
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                )

                app.review_scope_var.set("wrong_marked")
                app.change_review_scope()

                self.assertEqual(app.progress["review_scope"], "all")
                self.assertEqual(app.review_scope_var.get(), "all")
                self.assertIn("暂无错题或标记题", app.feedback_var.get())
        finally:
            root.destroy()

    def test_filtered_review_scope_meta_shows_original_question_position_and_scoped_checked_count(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {"question": "Q1", "options": ["A. one"], "answer": "A"},
                        {"question": "Q2", "options": ["A. one"], "answer": "A"},
                        {"question": "Q3", "options": ["A. one"], "answer": "A"},
                        {"question": "Q4", "options": ["A. one"], "answer": "A"},
                        {"question": "Q5", "options": ["A. one"], "answer": "A"},
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                )
                app.progress["review_scope"] = "last_wrong_marked"
                app.progress["last_wrong_marked_indices"] = [1, 3]
                app.progress["current_index"] = 3
                app.progress["question_status"][0]["checked"] = True
                app.progress["question_status"][1]["checked"] = True

                app.show_question()

                self.assertIn("上一轮错题/标记 | 第 4/5 题", app.meta_var.get())
                self.assertIn("已检查 1/2", app.meta_var.get())
        finally:
            root.destroy()

    def test_reset_keeps_previous_round_wrong_marked_indices_for_review(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {"question": "Q1", "options": ["A. one", "B. two"], "answer": "B"},
                        {"question": "Q2", "options": ["A. one"], "answer": "A"},
                        {"question": "Q3", "options": ["A. one"], "answer": "A"},
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                    summary_dir=Path(temp_dir) / "summary",
                )
                record_check_result(app.progress, 0, "A", "B")
                app.progress["question_status"][2]["manual_marked"] = True

                with patch("maogai_quiz.messagebox.askyesno", return_value=True), patch(
                    "maogai_quiz.messagebox.showinfo"
                ):
                    app.reset_progress()

                self.assertEqual(app.progress["last_wrong_marked_indices"], [0, 2])
                self.assertFalse(app.progress["question_status"][0]["auto_wrong"])
                self.assertFalse(app.progress["question_status"][2]["manual_marked"])
        finally:
            root.destroy()

    def test_summary_includes_auto_wrong_and_manual_marked_questions_once(self):
        question_bank = [
            {
                "type": "multiple",
                "question": "Q1 text",
                "options": ["A. one", "B. two"],
                "answer": "AB",
                "explanation": "Q1 explanation",
            },
            {"question": "Q2 text", "options": ["A. yes"], "answer": "A"},
            {"question": "Q3 text", "options": ["A. yes", "B. no"], "answer": "A"},
        ]
        progress = create_default_progress(3, rng=random.Random(4))
        record_check_result(progress, 0, "A", "AB")
        progress["question_status"][1]["manual_marked"] = True
        record_check_result(progress, 2, "B", "A")
        progress["question_status"][2]["manual_marked"] = True

        markdown = build_summary_markdown(
            question_bank,
            progress,
            generated_at=datetime(2026, 5, 27, 17, 30, 5),
        )

        self.assertIn("# 毛概错题 Summary", markdown)
        self.assertIn("生成时间：2026-05-27 17:30:05", markdown)
        self.assertIn("总题数：3", markdown)
        self.assertIn("已检查题数：2", markdown)
        self.assertIn("导出题数：3", markdown)
        self.assertIn("## 1. 第 1 题", markdown)
        self.assertIn("来源：自动错题", markdown)
        self.assertIn("用户选择：A", markdown)
        self.assertIn("正确答案：AB", markdown)
        self.assertIn("最近结果：错误", markdown)
        self.assertIn("题型：多选", markdown)
        self.assertIn("解析：Q1 explanation", markdown)
        self.assertIn("## 2. 第 2 题", markdown)
        self.assertIn("来源：手动标记", markdown)
        self.assertIn("最近结果：未检查", markdown)
        self.assertIn("## 3. 第 3 题", markdown)
        self.assertIn("来源：自动错题、手动标记", markdown)
        self.assertEqual(markdown.count("Q3 text"), 1)

    def test_summary_records_empty_state_before_reset(self):
        progress = create_default_progress(1, rng=random.Random(5))

        markdown = build_summary_markdown(
            [{"question": "Q1", "options": ["A. one"], "answer": "A"}],
            progress,
            generated_at=datetime(2026, 5, 27, 17, 31),
        )

        self.assertIn("导出题数：0", markdown)
        self.assertIn("本次重置前没有错题或标记题。", markdown)

    def test_write_summary_file_creates_summary_directory_and_timestamped_file(self):
        progress = create_default_progress(1, rng=random.Random(6))
        progress["question_status"][0]["manual_marked"] = True

        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_summary_file(
                Path(temp_dir) / "summary",
                [{"question": "Q1", "options": ["A. one"], "answer": "A"}],
                progress,
                generated_at=datetime(2026, 5, 27, 17, 32, 9),
            )

            self.assertEqual(path.name, "summary-20260527-173209.md")
            self.assertTrue(path.exists())
            self.assertIn("Q1", path.read_text(encoding="utf-8"))

    def test_reset_writes_summary_before_clearing_progress(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {"question": "Q1", "options": ["A. one", "B. two"], "answer": "B"}
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                    summary_dir=Path(temp_dir) / "summary",
                )
                record_check_result(app.progress, 0, "A", "B")

                with patch("maogai_quiz.messagebox.askyesno", return_value=True), patch(
                    "maogai_quiz.messagebox.showinfo"
                ):
                    app.reset_progress()

                summary_files = list((Path(temp_dir) / "summary").glob("summary-*.md"))
                self.assertEqual(len(summary_files), 1)
                self.assertIn("Q1", summary_files[0].read_text(encoding="utf-8"))
                self.assertFalse(app.progress["question_status"][0]["checked"])
                self.assertFalse(app.progress["question_status"][0]["auto_wrong"])
        finally:
            root.destroy()

    def test_reset_does_not_clear_progress_when_summary_write_fails(self):
        root = self.make_root()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app = QuizApp(
                    root,
                    question_bank=[
                        {"question": "Q1", "options": ["A. one", "B. two"], "answer": "B"}
                    ],
                    progress_path=Path(temp_dir) / "quiz_progress.json",
                    summary_dir=Path(temp_dir) / "summary",
                )
                record_check_result(app.progress, 0, "A", "B")

                with patch("maogai_quiz.messagebox.askyesno", return_value=True), patch(
                    "maogai_quiz.write_summary_file",
                    side_effect=OSError("disk full"),
                ), patch("maogai_quiz.messagebox.showerror") as showerror:
                    app.reset_progress()

                self.assertTrue(app.progress["question_status"][0]["checked"])
                self.assertTrue(app.progress["question_status"][0]["auto_wrong"])
                showerror.assert_called_once()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
