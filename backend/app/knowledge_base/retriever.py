"""BM25 over Chinese unigrams/bigrams and Latin words; no semantic-model claims."""

import math
import re
from collections import Counter
from app.db import connection


def tokenize(text):
    text = text.lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    for part in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.extend(part[i : i + 2] for i in range(len(part) - 1))
        tokens.extend(part)
    return tokens


def rank(query, docs, limit=3):
    if not docs:
        return []
    terms = set(tokenize(query))
    counters = [Counter(tokenize(d["title"] + " " + d["content"])) for d in docs]
    lengths = [sum(c.values()) for c in counters]
    avg = max(sum(lengths) / len(docs), 1)
    df = Counter(t for c in counters for t in c)
    results = []
    for doc, c, length in zip(docs, counters, lengths):
        score = 0.0
        for term in terms:
            freq = c[term]
            if freq:
                idf = math.log(1 + (len(docs) - df[term] + 0.5) / (df[term] + 0.5))
                weight = 0.2 if len(term) == 1 and "\u4e00" <= term <= "\u9fff" else 1
                score += (
                    weight
                    * idf
                    * freq
                    * 2.5
                    / (freq + 1.5 * (0.25 + 0.75 * length / avg))
                )
        if score > 0:
            results.append({**doc, "score": round(score, 4)})
    return sorted(results, key=lambda d: -d["score"])[:limit]


def retrieve(query, limit=3):
    with connection() as conn:
        docs = [dict(r) for r in conn.execute("SELECT * FROM knowledge")]
    return rank(query, docs, limit)
