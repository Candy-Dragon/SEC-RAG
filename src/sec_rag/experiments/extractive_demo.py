"""Offline wiring demonstration only; not a medical baseline or SEC-RAG result."""


def run(question, *, top_k, disease, retrieval):
    return {"question": question, "answer": retrieval[0]["text"] + "[证据1]",
            "retrieval": retrieval, "model": {"name": "none"},
            "purpose": "offline interface demonstration, not experimental evidence"}
