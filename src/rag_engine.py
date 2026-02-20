import re
import numpy as np
from typing import List, Dict, Tuple, Any, Optional
from . import embedding
from langsmith import traceable


# Utilities 

def _safe_lower(s: str) -> str:
    return (s or "").lower().strip()

def _get_item_id(item: Dict[str, Any], fallback_idx: int) -> str:
    if isinstance(item, dict):
        if "id" in item and item["id"]:
            return str(item["id"])
    return f"idx:{fallback_idx}"

def _get_type(item: Dict[str, Any]) -> str:
    return str(item.get("type", "info") or "info").strip().lower()

def _get_content(item: Dict[str, Any]) -> str:
    return str(item.get("content", "") or "")


# Intent & Rewrite 
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

def rewrite_query(user_query: str, chat_history, client=None, model_name: str = "") -> str:
    uq = (user_query or "").strip()
    if not uq: return uq
    if not client or not model_name: return uq

    is_long_query = len(uq) > 50 or len(uq.split()) > 10
    last_context = ""
    if chat_history and not is_long_query:
        for msg in reversed(chat_history):
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "assistant":
                if "ขออภัยค่ะ" not in content and "ไม่พบข้อมูล" not in content:
                    last_context = content[:100] 
                    break
    else:
        if is_long_query:
            print(f"   [Rewriter] Long query detected ({len(uq)} chars). Ignore History.")

    
    system_prompt = f"""
You are an expert Query Rewriter for a Retrieval-Augmented Generation (RAG) chatbot.

Your ONLY task is to rewrite the user input into a clear, precise Thai search query for a vector database.

You MUST NOT answer the question.
You MUST NOT add explanations.
You MUST NOT invent information.

Current Conversation Context:
Last Bot Message: "{last_context}"

--------------------------------
PROCESS

Step 1: Analyze Input
Determine whether the input is:
- A complete question
- A follow-up referring to previous context

--------------------------------
Step 2: Detect Topic Shift (CRITICAL)

IF the input introduces a NEW topic:
→ Ignore the Last Bot Message completely.

IF the input uses pronouns or depends on context:
→ Merge ONLY relevant information from Last Bot Message.

IF Last Bot Message is empty:
→ Use ONLY current input.

--------------------------------
Step 3: Apply Domain Terminology (CRITICAL FIX)

1. "ทุน" (Fund) Context:
   - "ทุน" ALWAYS means "Research Grant/Fund" (ทุนวิจัย).
   - NEVER rewrite "ทุน" as "Scholarship" (ทุนการศึกษา) unless user explicitly mentions "student" or "study".
   
2. Abbreviations:
   - FF -> Fundamental Fund
   - PM -> Project Manager / หัวหน้าโครงการ

--------------------------------
OUTPUT RULES (MANDATORY)

- Output ONLY ONE single-line Thai search query
- No quotes
- No bullets
- No explanations
- No English (except technical terms)
- No emojis

Format:
[Intent] + [System/Feature] + [Problem/Condition]

Examples:
Input: "ขอทุนยากไหม"
Output: ขั้นตอนและเกณฑ์การขอรับทุนวิจัย (Research Fund)

Input: "FF คือไร"
Output: รายละเอียดกองทุน Fundamental Fund

Input: "เข้าไม่ได้" (Context: Login)
Output: วิธีแก้ไขปัญหาการเข้าสู่ระบบ RPA ไม่สำเร็จ

Input: "ขอคู่มือการขอเบิกเงินทดรองจ่าย"
Output: อธิบายขั้นตอนการเบิกเงินทดรองจ่ายทั้งหมด
"""

    try:
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"User Input: {uq}"} 
            ],
            temperature=0.2, 
            max_tokens=1500,
        )
        new_query = resp.choices[0].message.content.strip().replace('"', "")
        
        print(f"   [Rewriter] '{uq}' -> '{new_query}'") 
        return new_query

    except Exception as e:
        print(f"Rewrite Error: {e}")
        return uq

# Retrieval Stage 
def retrieval_stage(
    query: str, target_data: List[Dict[str, Any]], target_vectors: np.ndarray,
    top_k: int = 20, mmr: bool = True, mmr_lambda: float = 0.90  
) -> List[Dict[str, Any]]:
    
    if not target_data or target_vectors is None or len(target_data) == 0:
        return []

    # ส่ง vector ไปหา
    qvec = embedding.get_embedding_remote(query)
    if np.all(qvec == 0): return []
    
    # วัดความเหมือน
    sims = np.dot(target_vectors, qvec)
    
    # ดึงทั้งหมด
    pool_k = min(len(target_data), max(top_k * 2, 70))
    top_idx = np.argsort(sims)[::-1][:pool_k]
    
    # เก็บข้อมูลคู่กับคะแนน
    cand = []
    for idx in top_idx:
        if idx >= len(target_data):
            print(f"   [Warning] Index {idx} is out of range. DB has {len(target_data)} items.")
            continue 
            
        cand.append({
            "idx": int(idx),
            "id": _get_item_id(target_data[idx], idx),
            "data": target_data[idx],
            "vector_score": float(sims[idx]),
        })
        
    dedup = {}
    # กัน id ซ้ำกัน    
    for c in cand:
        cid = c["id"]
        if cid not in dedup or c["vector_score"] > dedup[cid]["vector_score"]:
            dedup[cid] = c
    cand = list(dedup.values())
    cand.sort(key=lambda x: x["vector_score"], reverse=True)

    if not mmr or len(cand) <= top_k:
        return cand[:top_k]
        
    # MMR Logic
    selected = [cand[0]]
    selected_idx = [0]
    pool_vecs = target_vectors[[c["idx"] for c in cand]]

    while len(selected) < min(top_k, len(cand)):
        best_mmr = -1e9
        best_idx = -1
        for i in range(len(cand)):
            if i in selected_idx: continue
            
            # คะแนนความเหมือนกับคำถาม (Relevance)
            sim_q = cand[i]["vector_score"]
            
            # คะแนนความเหมือนกับสิ่งที่เลือกไปแล้ว (Redundancy)
            sel_vecs = pool_vecs[selected_idx]
            curr_vec = pool_vecs[i]            
            sim_sel = np.max(np.dot(sel_vecs, curr_vec)) if len(sel_vecs) > 0 else 0
            
            # สูตร MMR: ถ้า Lambda สูง (0.9) จะสนใจ sim_q มากกว่า (ยอมให้ซ้ำได้บ้าง)
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
    "definition": 1.05,"guide": 1.25, "troubleshoot": 1.15, "info": 1.00,"contact" : 1.20,"warning": 1.15,
}

@traceable(run_type="chain", name="Reranking Calculation")
def reranking_stage(
    query: str, candidates: List[Dict[str, Any]], top_k: int = 8, intent: str = "QUERY" 
) -> List[Tuple[Dict[str, Any], float]]:
    
    if not candidates: return []
    
    # Normalizing Query
    q_norm = _safe_lower(query).replace(" ", "") 
    reranked = []
    
    for c in candidates:
        item = c["data"]
        dtype = (item.get("type") or "info").lower() 
        meta = item.get("metadata", {}) or {}
        
        # Base Score จาก Vector
        score = float(c.get("vector_score", 0.0)) * 100.0
        
        #  Type Boost
        score *= TYPE_WEIGHTS.get(dtype, 1.0)  
        
        #  Topic/Name Match 
        topic_val = str(meta.get("topic") or meta.get("name") or "")
        topic = _safe_lower(topic_val).replace(" ", "")
        
        if len(topic) > 2 and (topic in q_norm or q_norm in topic):
            score += 30.0  
            
        # 3. Step Match
        m = re.search(r"(ขั้นตอน|step)\s*(ที่)?\s*(\d+)", query)
        if m:
            want_step = int(m.group(3))
            step_no = meta.get("step_number")
            if step_no and int(step_no) == want_step: 
                score += 60.0 
            elif step_no: 
                score -= 20.0 # ถ้าถามขั้นตอน 1 แต่เจอขั้นตอน 5 ให้ลดคะแนน
                
        # Fund Match 
        fund_abbr = _safe_lower(str(meta.get("fund_abbr") or " "))
        if fund_abbr.strip() and fund_abbr in q_norm: 
            score += 30.0 
            
        # Status Match
        if dtype == "fact":  
            status_val = str(meta.get("status", "")).strip().lower()
            
            active_keywords = [
                'y', 'yes', 'enable', 'active', 'true', '1', 'on', 
                'open', 'working', 'ปกติ', 'เปิด', 'ทำงาน', 'อนุมัติ'
            ]
            
            if any(k in status_val for k in active_keywords):
                score += 30.0
            
        item["metadata"]["final_rerank_score"] = score
        reranked.append((item, score))

    # เรียงลำดับตามคะแนนใหม่จากมากไปน้อย
    reranked.sort(key=lambda x: x[1], reverse=True)
    return reranked[:top_k]