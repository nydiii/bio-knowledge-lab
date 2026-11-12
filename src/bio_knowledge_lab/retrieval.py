"""Small CPU evidence retriever inspired by CER; no truth labels are inferred."""
from collections import Counter
import math
import re


def _tokens(text):
    return re.findall(r"[\w-]+", text.casefold())


def retrieve_evidence(documents, query, exclude_doc_id=None, top_k=5):
    """Return BM25-ranked source spans, each explicitly marked candidate."""
    if top_k < 1:
        raise ValueError("top_k必须大于0")
    passages = []
    for document in documents:
        if document["doc_id"] == exclude_doc_id:
            continue
        for match in re.finditer(r"[^.!?\n]+(?:[.!?]+|$)", document["text"]):
            raw = match.group()
            start = match.start() + len(raw) - len(raw.lstrip())
            end = match.end() - len(raw) + len(raw.rstrip())
            text = document["text"][start:end]
            if text:
                passages.append({"doc_id": document["doc_id"], "start": start, "end": end, "text": text})
    if not passages:
        return []
    counts = [Counter(_tokens(item["text"])) for item in passages]
    lengths = [sum(count.values()) for count in counts]
    average = sum(lengths) / len(lengths) or 1
    terms = set(_tokens(query))
    frequencies = {term: sum(term in count for count in counts) for term in terms}
    scored = []
    for passage, count, length in zip(passages, counts, lengths):
        score = 0.0
        for term in terms:
            frequency = count[term]
            if frequency:
                idf = math.log(1 + (len(passages) - frequencies[term] + .5) / (frequencies[term] + .5))
                score += idf * frequency * 2.5 / (frequency + 1.5 * (.25 + .75 * length / average))
        if score:
            scored.append({**passage, "score": round(score, 6), "method": "bm25", "status": "retrieved_candidate"})
    return sorted(scored, key=lambda x: (-x["score"], x["doc_id"], x["start"]))[:top_k]
