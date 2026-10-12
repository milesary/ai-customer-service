"""Small, hand-authored retrieval check; results are not end-to-end LLM accuracy."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.seed import DOCS
from app.knowledge_base.retriever import rank


def jaccard(query, docs):
    def tokens(s):
        return set(re.findall(r"[a-z]+", s.lower()) + re.findall(r"[\u4e00-\u9fff]", s))

    q = tokens(query)
    scored = []
    for d in docs:
        dt = tokens(d["title"] + " " + d["content"])
        score = len(q & dt) / len(q | dt) if q | dt else 0
        scored.append({**d, "score": score})
    return sorted(scored, key=lambda d: -d["score"])[:3]


def evaluate():
    cases = json.loads(
        Path(__file__).with_name("cases.json").read_text(encoding="utf-8")
    )
    docs = [{"id": i, "title": t, "content": c} for i, t, c in DOCS]
    report = {
        "dataset": f"{len(cases)} hand-authored queries / {len(docs)} seeded documents",
        "scope": "Retrieval only; same corpus for both methods; no real LLM or production traffic.",
        "methods": {},
    }
    for name, method in [("legacy_jaccard", jaccard), ("bm25_multigrain", rank)]:
        answered = 0
        hit1 = 0
        hit3 = 0
        rr = 0
        unknown = 0
        rejected = 0
        details = []
        for case in cases:
            results = method(case["query"], docs)
            ids = [r["id"] for r in results]
            expected = case["expected"]
            if expected:
                answered += 1
                hit1 += bool(ids and ids[0] in expected)
                hit3 += any(i in expected for i in ids)
                rr += next(
                    (1 / (index + 1) for index, i in enumerate(ids) if i in expected), 0
                )
            else:
                unknown += 1
                rejected += not ids
            details.append(
                {
                    "query": case["query"],
                    "expected": expected,
                    "retrieved": ids,
                    "scores": [r["score"] for r in results],
                }
            )
        report["methods"][name] = {
            "hit_at_1": round(hit1 / answered, 4),
            "hit_at_3": round(hit3 / answered, 4),
            "mrr_at_3": round(rr / answered, 4),
            "unknown_empty_rate": round(rejected / unknown, 4),
            "details": details,
        }
    destination = Path(__file__).with_name("report.json")
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: {m: v for m, v in value.items() if m != "details"}
                for k, value in report["methods"].items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    evaluate()
