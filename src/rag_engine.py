import re
import numpy as np
from typing import List, Dict, Tuple, Any, Optional
from . import embedding
from langsmith import traceable

# Utilities & Tokenizer
THAI_STOP = set([
    "คือ","เป็น","ไหม","มั้ย","หรือ","และ","กับ","ที่","ใน","ของ","ให้","ได้","ต้อง","ขอ","หน่อย",
    "ทำ","ยังไง","อย่างไร","อะไร","กี่","เท่าไหร่","ไป","มา","แล้ว","ค่ะ","ครับ","นะ","หน่อยนะ",
    "จาก","นั้น","นี้","นั้น","โดย","การ","ความ","ระบบ","ทาง","ท่าน","จะ"
])

def _safe_lower(s: str) -> str:
    return (s or "").lower().strip()

def _tokenize_th_simple(text: str) -> List[str]:
    text = _safe_lower(text)
    # เก็บ ก-ฮ, a-z, 0-9 และช่องว่าง
    text = re.sub(r"[^a-z0-9\u0E00-\u0E7F\s]", " ", text)
    # ตัดด้วยช่องว่าง และกรองคำฟุ่มเฟือย
    toks = [t for t in text.split() if t and t not in THAI_STOP and len(t) > 1]
    return toks

def _lexical_overlap_score(query: str, doc: str) -> float:
    q_toks = _tokenize_th_simple(query)
    if not q_toks:
        return 0.0
    
    doc_lower = _safe_lower(doc)
    hit_count = 0
    for q in q_toks:
        if q in doc_lower:
            hit_count += 1
            
    return hit_count / len(q_toks)

def _get_item_id(item: Dict[str, Any], fallback_idx: int) -> str:
    if isinstance(item, dict):
        if "id" in item and item["id"]:
            return str(item["id"])
    return f"idx:{fallback_idx}"

def _get_type(item: Dict[str, Any]) -> str:
    return str(item.get("type", "info") or "info").strip().lower()

def _get_content(item: Dict[str, Any]) -> str:
    return str(item.get("content", "") or "")


# Intent Analysis (Fast Block)

BLOCK_PATTERNS = [
    r"\b(การเมือง|เลือกตั้ง|พรรค|นายก|ฝ่ายค้าน|รัฐบาล)\b",
    r"\b(ทำอาหาร|สูตร|คุกกี้|ทำกับข้าว)\b",
    r"\b(หนัง|ซีรีส์|อนิเมะ|เกม|หวย|เลขเด็ด)\b",
    r"\b(ด่า|เหี้ย|สัส|ควย|ไอ้)\b",
]

def analyze_intent(user_query: str) -> str:
    q = _safe_lower(user_query)
    for pat in BLOCK_PATTERNS:
        if re.search(pat, q):
            return "BLOCK"
    return "QUERY"

@traceable(run_type="llm", name="Rewrite Query")
def rewrite_query(user_query: str, chat_history, client=None, model_name: str = "") -> str:
    uq = (user_query or "").strip()
    if not uq: return uq
    if not client or not model_name: return uq

    last_context = ""
    if chat_history:
        # วนลูปย้อนหลังจากข้อความใหม่สุด ไปเก่าสุด
        for msg in reversed(chat_history):
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "assistant":
                if "ขออภัยค่ะ" not in content and "ไม่พบข้อมูล" not in content:
                    last_context = content[:300] 
                    break
                
    system_prompt = f"""You are a Query Rewriter for a RAG chatbot.
Task: Rewrite the user input to be a PRECISE SEARCH QUERY for a vector database.

Current Conversation Context:
Last Bot Message: "{last_context}"

Rules:
1. **Refine:** Fix typos and expand specific abbreviations (FF -> Fundamental Fund, SF, RPA) to full names.
2. **Context Dependency Check (CRITICAL):**
   - **IF** the input contains pronouns (it, this, that, "อันนี้", "มัน") OR is incomplete (e.g., "Still not working", "How about the other one?"), **COMBINE** it with the [Last Bot Message].
   - **IF** the input is a **COMPLETE, STANDALONE** question (e.g., "Why file upload failed?", "How to change password?"), **IGNORE** the [Last Bot Message] and treat it as a NEW TOPIC.
3. Output ONLY the rewritten Thai string."""

    try:
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"User Input: {uq}"} 
            ],
            temperature=0.1, 
            max_tokens=1000,
        )
        new_query = resp.choices[0].message.content.strip().replace('"', "")
        
        print(f"   [Rewriter] '{uq}' -> '{new_query}'") 
        return new_query

    except Exception as e:
        print(f"Rewrite Error: {e}")
        return uq
    
# Retrieval Stage 
@traceable(run_type="retriever", name="Supabase Search")
def retrieval_stage(
    query: str,
    target_data: List[Dict[str, Any]],
    target_vectors: np.ndarray,
    top_k: int = 15,
    mmr: bool = True,
    mmr_lambda: float = 0.70 
) -> List[Dict[str, Any]]:
    
    if not target_data or target_vectors is None or len(target_data) == 0:
        return []
    
    qvec = embedding.get_embedding_remote(query)
    if np.all(qvec == 0): return []
    
    # Cosine Similarity
    sims = np.dot(target_vectors, qvec)

    # Pre-filter top pool
    pool_k = min(len(target_data), max(top_k * 2, 50))
    top_idx = np.argsort(sims)[::-1][:pool_k]
    
    cand = []
    for idx in top_idx:
        item = target_data[idx]
        cand.append({
            "idx": int(idx),
            "id": _get_item_id(item, idx),
            "data": item,
            "vector_score": float(sims[idx]),
        })
        
    # Dedup by ID
    dedup = {}
    for c in cand:
        cid = c["id"]
        if cid not in dedup or c["vector_score"] > dedup[cid]["vector_score"]:
            dedup[cid] = c
    cand = list(dedup.values())

    cand.sort(key=lambda x: x["vector_score"], reverse=True)

    if not mmr or len(cand) <= top_k:
        return cand[:top_k]

    # MMR Logic
    selected = []
    selected_idx = []
    
    selected.append(cand[0])
    selected_idx.append(0)
    
    pool_vecs = target_vectors[[c["idx"] for c in cand]]

    while len(selected) < min(top_k, len(cand)):
        best_mmr = -1e9
        best_idx = -1
        
        for i in range(len(cand)):
            if i in selected_idx: continue
            
            sim_q = cand[i]["vector_score"]
            
            sel_vecs = pool_vecs[selected_idx]
            curr_vec = pool_vecs[i]            
            sim_sel = np.max(np.dot(sel_vecs, curr_vec)) if len(sel_vecs) > 0 else 0
            
            mmr_score = (mmr_lambda * sim_q) - ((1 - mmr_lambda) * sim_sel)
            
            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_idx = i
        
        if best_idx != -1:
            selected.append(cand[best_idx])
            selected_idx.append(best_idx)
        else:
            break

    return selected

# Reranking Stage
TYPE_WEIGHTS = {
    "fact": 1.10, "definition": 1.05,
    "guide": 1.25, "troubleshoot": 1.15, "info": 1.00,
}

def reranking_stage(
    query: str, candidates: List[Dict[str, Any]], top_k: int = 6, 
    intent: str = "QUERY" 
) -> List[Tuple[Dict[str, Any], float]]:
    
    if not candidates: return []
    q_norm = _safe_lower(query)
    reranked = []

    for c in candidates:
        item = c["data"]
        content = _get_content(item)
        dtype = _get_type(item)
        meta = item.get("metadata", {}) or {}
        
        # Base Score (Vector)
        score = float(c.get("vector_score", 0.0)) * 100.0

        # Lexical Overlap
        score += _lexical_overlap_score(query, content) * 40.0
        
        # Type Weight
        score *= TYPE_WEIGHTS.get(dtype, 1.0)
        
        # Metadata Boosts
        topic = str(meta.get("topic") or meta.get("name") or "").lower()
        if topic and len(topic) > 2 and ((topic in q_norm) or (q_norm in topic and len(q_norm) > 3)):
            score += 80.0 

        # Step Match
        m = re.search(r"(ขั้นตอน|step)\s*(ที่)?\s*(\d+)", q_norm)
        if m:
            want_step = int(m.group(3))
            step_no = meta.get("step_number")
            if step_no and int(step_no) == want_step: score += 100.0
            elif step_no: score -= 20.0

        # Fund Abbr
        fund_abbr = str(meta.get("fund_abbr") or "").lower()
        if fund_abbr and fund_abbr in q_norm.split(): score += 50.0

        reranked.append((item, score))

    reranked.sort(key=lambda x: x[1], reverse=True)
    return reranked[:top_k]

# Build Context

def build_context(
    query: str,
    ranked_items: List[Tuple[Dict[str, Any], float]],
    max_items: int = 3,             
    max_chars_per_item: int = 600, 
    min_coverage: float = 0.05      
) -> Tuple[str, bool]:

    if not ranked_items:
        return "ไม่พบข้อมูลที่เกี่ยวข้องในระบบ", False

    blocks = []
    cover_scores = []

    for item, score in ranked_items[:max_items]:
        dtype = _get_type(item)
        content = _get_content(item).strip()
        if not content: continue

        # Cleaning
        content = content.replace("คู่มือการใช้งาน:", "").replace("รายละเอียด:", "").strip()
        content = content.replace("วิธีทำ (ภาพรวม):", "").replace("คำศัพท์:", "").strip()

        # Truncate
        if len(content) > max_chars_per_item:
            content = content[:max_chars_per_item] + "...(ตัดทอน)"

        # Coverage Check
        cover = _lexical_overlap_score(query, content)
        cover_scores.append(cover)

        blocks.append(f"[{dtype.upper()}]: {content}")

    if not blocks:
        return "ไม่พบข้อมูลที่เกี่ยวข้องในระบบ", False

    avg_cover = sum(cover_scores) / max(1, len(cover_scores))
    top_score = ranked_items[0][1] / 100.0 
    
    is_relevant = (avg_cover >= min_coverage) or (top_score > 0.45)

    return "\n".join(blocks).strip(), is_relevant