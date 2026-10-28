"""The Genie benchmark SQL must reproduce the reference answers (so the benchmark itself is correct)."""
import csv
import os
import re

import emulator
import reference

BENCHMARK = os.path.join(emulator.REPO_ROOT, "genie", "benchmark.csv")


def _numbers(text):
    return [(float(m), len(m.split(".")[1]) if "." in m else 0) for m in re.findall(r"-?\d+(?:\.\d+)?", text)]


def _matches(answer: str, row: tuple) -> bool:
    row_numbers = [float(v) for v in row if isinstance(v, (int, float)) or hasattr(v, "__float__")
                   and not isinstance(v, str)]
    row_text = " ".join(str(v) for v in row if isinstance(v, str))
    words = re.sub(r"\(.*", "", answer).strip()
    text_ok = (not re.search(r"[A-Za-z]", words)) or words in row_text
    # numbers inside the answer that are not part of a name (names carry a #nnn suffix)
    numbers_ok = True
    for value, decimals in _numbers(re.sub(r"#\d+", "", answer)):
        tolerance = 0.5 * 10 ** -decimals if decimals else 0.5
        if not any(abs(v - value) <= tolerance for v in row_numbers):
            numbers_ok = False
    return text_ok and numbers_ok


def test_every_benchmark_sql_matches_the_reference_answer(run, landing_dir):
    answers = {qid: (q, a) for qid, q, a in reference.genie_reference(landing_dir)}
    with open(BENCHMARK, newline="", encoding="utf-8") as fh:
        benchmark = list(csv.DictReader(fh))
    assert {b["question_id"] for b in benchmark} == set(answers)
    for b in benchmark:
        question, answer = answers[b["question_id"]]
        assert b["question"] == question
        rows = emulator.run_sql(run.con, b["expected_sql"])
        assert rows, b["question_id"]
        assert _matches(answer, rows[0]), f"{b['question_id']}: reference '{answer}' vs SQL result {rows[0]}"
