"""比較 embedding 模型在條款文件上的檢索效果（P2 實驗）。

做法：
1. 把 samples/ 的範例文件依「條」切塊（每條一個 chunk）。
2. 用每個模型把條文與測試問題轉成向量。
3. 對每個問題，依餘弦相似度排序所有條文，看正確條文排第幾名。
4. 計算 Hit@1、Hit@3、MRR，並依題組（A～E）分開統計。

只用 Python 標準函式庫，不需安裝任何套件。
"""

import json
import math
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434")
SAMPLES_DIR = Path(os.environ.get("SAMPLES_DIR", "/samples"))
HERE = Path(__file__).parent

# 文件代號：檔名 → chunk 代號前綴
DOCS = {
    "曬圖島-使用條款.md": "T",
    "曬圖島-隱私權政策.md": "PZ",
    "ShaituIsland-Privacy-Policy.md": "PE",
}

# 各模型官方建議的前綴（prompt）。query 與文件用不同前綴，能讓模型知道哪個是「問題」、哪個是「被搜尋的內容」。
MODELS = {
    "bge-m3": {
        "query": "{q}",
        "doc": "{t}",
    },
    "qwen3-embedding:0.6b": {
        "query": "Instruct: Given a question about terms of service or a privacy policy, "
        "retrieve the clause that answers it\nQuery: {q}",
        "doc": "{t}",
    },
    "embeddinggemma": {
        "query": "task: search result | query: {q}",
        "doc": "title: none | text: {t}",
    },
}

ARTICLE_RE = re.compile(r"^###\s*(?:第\s*(\d+)\s*條|Article\s+(\d+))")


def load_chunks():
    """依 `### 第 N 條` / `### Article N` 標題把文件切成一條一塊。"""
    chunks = []
    for filename, prefix in DOCS.items():
        current_id, lines = None, []
        for line in (SAMPLES_DIR / filename).read_text(encoding="utf-8").splitlines():
            m = ARTICLE_RE.match(line)
            # 遇到新條文或新章節（## 開頭），就把上一條收起來
            if m or line.startswith("## "):
                if current_id:
                    chunks.append({"id": current_id, "text": "\n".join(lines).strip()})
                current_id, lines = None, []
            if m:
                current_id = f"{prefix}{m.group(1) or m.group(2)}"
                lines = [line.lstrip("# ").strip()]
            elif current_id:
                lines.append(line)
        if current_id:
            chunks.append({"id": current_id, "text": "\n".join(lines).strip()})
    return chunks


def embed(model, texts):
    """呼叫 Ollama 的 /api/embed，一次送一批文字，回傳正規化後的向量。"""
    body = json.dumps({"model": model, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embed", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        vectors = json.loads(resp.read())["embeddings"]
    return [normalize(v) for v in vectors]


def normalize(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cosine(a, b):
    # 兩個向量都已正規化，內積就等於餘弦相似度
    return sum(x * y for x, y in zip(a, b))


def evaluate(model, prompts, chunks, queries):
    t0 = time.perf_counter()
    doc_vecs = embed(model, [prompts["doc"].format(t=c["text"]) for c in chunks])
    t_docs = time.perf_counter() - t0

    t0 = time.perf_counter()
    q_vecs = embed(model, [prompts["query"].format(q=q["q"]) for q in queries])
    t_queries = time.perf_counter() - t0

    details = []
    for q, qv in zip(queries, q_vecs):
        ranked = sorted(
            ((cosine(qv, dv), c["id"]) for c, dv in zip(chunks, doc_vecs)), reverse=True
        )
        ids = [cid for _, cid in ranked]
        # 正確答案中排名最前面的那個（名次從 1 起算）
        rank = min(ids.index(g) + 1 for g in q["gold"] if g in ids)
        details.append({"id": q["id"], "group": q["group"], "rank": rank, "top3": ids[:3]})

    return {
        "dim": len(doc_vecs[0]),
        "seconds_docs": round(t_docs, 2),
        "seconds_queries": round(t_queries, 2),
        "details": details,
    }


def summarize(details):
    n = len(details)
    return {
        "n": n,
        "hit1": sum(d["rank"] == 1 for d in details) / n,
        "hit3": sum(d["rank"] <= 3 for d in details) / n,
        "mrr": sum(1 / d["rank"] for d in details) / n,
    }


def main():
    chunks = load_chunks()
    data = json.loads((HERE / "queries.json").read_text(encoding="utf-8"))
    queries = data["queries"]
    print(f"條文數：{len(chunks)}，問題數：{len(queries)}", file=sys.stderr)

    results = {}
    for model, prompts in MODELS.items():
        for mode in ("建議前綴", "無前綴"):
            p = prompts if mode == "建議前綴" else {"query": "{q}", "doc": "{t}"}
            if mode == "無前綴" and p == prompts:
                continue  # bge-m3 本來就不用前綴，不重複跑
            print(f"跑 {model}（{mode}）…", file=sys.stderr)
            r = evaluate(model, p, chunks, queries)
            groups = sorted({d["group"] for d in r["details"]})
            r["overall"] = summarize(r["details"])
            r["by_group"] = {g: summarize([d for d in r["details"] if d["group"] == g]) for g in groups}
            results[f"{model}｜{mode}"] = r

    (HERE / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 印出總表
    print("| 模型 | 維度 | Hit@1 | Hit@3 | MRR | " + " | ".join(f"{g} Hit@1" for g in "ABCDE") + " |")
    print("|---|---|---|---|---|" + "---|" * 5)
    for name, r in results.items():
        o = r["overall"]
        g = " | ".join(f"{r['by_group'][x]['hit1']:.0%}" for x in "ABCDE")
        print(f"| {name} | {r['dim']} | {o['hit1']:.0%} | {o['hit3']:.0%} | {o['mrr']:.3f} | {g} |")


if __name__ == "__main__":
    main()
