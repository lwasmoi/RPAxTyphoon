import re
import httpx
from openai import OpenAI
from langsmith.wrappers import wrap_openai
from langsmith import traceable
from collections import deque
import config
from src import data_loader, embedding, rag_engine

client = OpenAI(
    api_key=config.CURRENT_KEY,
    base_url=config.CURRENT_URL
)
raw_client = OpenAI(
    api_key=config.CURRENT_KEY,
    base_url=config.CURRENT_URL
)

client = wrap_openai(raw_client)
print(f"Bot started! Model: {config.CURRENT_MODEL}")

print(f"[INFO] Bot started with LangSmith Tracing! Model: {config.CURRENT_MODEL}")

# Load Knowledge
print("\n--- Loading Knowledge Base (All-in-One DB) ---")
all_data = data_loader.load_supabase_knowledge()
# ปกติ
all_vecs = embedding.build_vector_store(all_data, config.CACHE_JSON)
# all_vecs = embedding.build_vector_store(all_data, config.CACHE_JSON, force_refresh=True)

# ค่า Config การค้นหา
RETRIEVE_TOPK = 12
RERANK_TOPK = 8     

TYPE_THRESH = {
    "fact": 0.38,
    "definition": 0.36,
    "troubleshoot": 0.34,
    "info": 0.35,
}

def get_threshold(item_type: str) -> float:
    return TYPE_THRESH.get((item_type or "info").strip().lower(), 0.35)

# Chat Loop 
@traceable(run_type="chain", name="RPA Bot Pipeline")
def run_chat():
    history = deque(maxlen=5)
    print("\nน้องทุน  พร้อมบริการค่ะ (พิมพ์ 'exit' เพื่อออก)")

    while True:
        try:
            u_in = input("\nคุณ: ").strip()
            if not u_in: continue
            if u_in.lower() in ["exit", "quit"]: break

            print("Thinking...", end="\r")

            # Intent Analysis
            intent = rag_engine.analyze_intent(u_in)
            if intent == "BLOCK":
                msg = "ขออภัยค่ะ น้องทุนตอบเฉพาะเรื่องงานวิจัยและระบบเบิกจ่ายค่ะ"
                print(f"\nBot: {msg}")
                continue

            # Rewrite Query
            query = rag_engine.rewrite_query(u_in, history, client, config.CURRENT_MODEL)

            # Retrieval & Rerank
            cands = rag_engine.retrieval_stage(query, all_data, all_vecs, top_k=RETRIEVE_TOPK)
            
            results = rag_engine.reranking_stage(query, cands, top_k=RERANK_TOPK, intent=intent)

            # Context Construction
            context_lines = []
            pass_count = 0

            for item, score in results:
                itype = (item.get("type") or "info").lower()
                th = get_threshold(itype)
                score01 = score / 100.0

                if score01 >= th:
                    pass_count += 1
                    context_lines.append(f"<{itype}>{item.get('content','')}</{itype}>")

            context_str = "\n".join(context_lines).strip()
            has_context = (pass_count >= 1) and (len(context_str) > 0)

            if not has_context:
                msg = "ไม่พบข้อมูลในระบบที่เกี่ยวข้องค่ะ รบกวนระบุรายละเอียดเพิ่ม เช่น ชื่อเมนู หรือขั้นตอนที่ทำค้างอยู่ค่ะ"
                print(f"\nBot: {msg}")
                # history.append({"role":"user","content": u_in})
                continue

            # Generation Payload
            msgs = [
                {
                    "role": "system",
                    "content": f"{config.STATIC_SYS_PROMPT}\n\nContext from Database:\n{context_str}"
                }
            # ] + list(history) + [{"role": "user", "content": query}]
            ] + [{"role": "user", "content": query}]

            print("Bot: ", end="", flush=True)
            stream = client.chat.completions.create(
                model=config.CURRENT_MODEL,
                messages=msgs,
                stream=True,
                temperature=0.3,
                max_tokens=4096,
                extra_body={
                    "repetition_penalty": 1.12, 
                    "top_p": 0.9,
                }
            )

            full_res = ""
            for chunk in stream:
                c = chunk.choices[0].delta.content
                if c:
                    print(c, end="", flush=True)
                    full_res += c
            print()

            history.append({"role": "user", "content": u_in})
            history.append({"role": "assistant", "content": full_res})
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == "__main__":
    run_chat()