import streamlit as st
import time
from openai import OpenAI
import config
from src import data_loader, embedding, rag_engine

# Config & Setup
st.set_page_config(
    page_title="น้องทุน AI (Main Logic)",
    page_icon="🤖",
    layout="wide"
)

RETRIEVE_TOPK = 12
RERANK_TOPK = 8
TYPE_THRESH = {"fact": 0.38, "definition": 0.36, "troubleshoot": 0.34, "info": 0.35}

def get_threshold(item_type: str) -> float:
    return TYPE_THRESH.get((item_type or "info").strip().lower(), 0.35)

@st.cache_resource(show_spinner="กำลังโหลดฐานข้อมูล... กรุณารอสักครู่")
def setup_system():
    client = OpenAI(api_key=config.CURRENT_KEY, base_url=config.CURRENT_URL)
    all_data = data_loader.load_supabase_knowledge()
    all_vecs = embedding.build_vector_store(all_data, config.CACHE_JSON)
    return client, all_data, all_vecs

try:
    client, all_data, all_vecs = setup_system()
except Exception as e:
    st.error(f"System Load Error: {e}"); st.stop()

# CSS steamlit
st.markdown("""
<style>
    /* แต่งปุ่มแนะนำ */
    div.stButton > button {
        width: 300px ; 
        height: 70px ; 
        border-radius: 20px;
        padding: 0px 15px;        
        
        /* จัดข้อความกึ่งกลางเสมอ */
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        
        line-height: 1.4;
        font-size: 18px;          
        font-weight: 500;
        
        /* สีพื้นหลัง */
        background: linear-gradient(145deg, #1e293b, #0f172a);
        color: #f8fafc;
        border: 1px solid #334155;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        transition: transform 0.2s, box-shadow 0.2s;
    }

    div.stButton > button:hover {
        background: linear-gradient(145deg, #3b82f6, #2563eb);
        border-color: #60a5fa;
        transform: translateY(-4px);
        box-shadow: 0 10px 20px rgba(59, 130, 246, 0.3);
        color: white;
    }
    
    /* แต่งปุ่ม ปุ่มเมนูเล็ก */
    [data-testid="stPopover"] > button {
        height: 50px !important;
        min-height: 50px !important;
        width: auto !important;
        border-radius: 25px !important;
        padding: 0 25px !important;
        background: #ffffff !important;
        border: 2px solid #e2e8f0 !important;
        color: #475569 !important;
        font-weight: 600 !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05) !important;
        
        /* Reset ค่า display ของปุ่มเล็ก */
        display: inline-flex; 
        justify-content: center;
    }
    [data-testid="stPopover"] > button:hover {
        border-color: #3b82f6 !important;
        color: #3b82f6 !important;
        background: #f8fafc !important;
    }

    /* ช่อง Chat Input */
    [data-testid="stChatInput"] {
        border-radius: 24px !important;
        border: 2px solid #3b82f6 !important;
        background-color: #ffffff !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
        padding: 5px !important;
    }
    [data-testid="stChatInput"] textarea {
        color: #0f172a !important; 
        font-size: 16px !important;
    }
    
    [data-testid="column"] { padding: 0 8px; }
    
</style>
""", unsafe_allow_html=True)

# Chat Logic & UI
if "messages" not in st.session_state: st.session_state.messages = []
if "prompt_trigger" not in st.session_state: st.session_state.prompt_trigger = None

# แสดงประวัติเก่า
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ส่วนแสดงปุ่ม
if len(st.session_state.messages) == 0:
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<h4 style='text-align: center;'>💡 คำถามแนะนำ:</h4>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    suggestions = [
        "ขอดูคู่มือการ\nขอเบิกเงิน",       
        "ขอดูคู่มือการ\nอัปโหลดใบเสร็จ", 
        "เข้าสู่ระบบ\nไม่ได้", 
        "รหัสใบเสร็จ\nRPA คืออะไร"
    ]
    
    # ใช้ Spacer Columns บีบปุ่มให้อยู่ตรงกลางสวยๆ
    c_left, c1, c2, c3, c4, c_right = st.columns([1, 3, 3, 3, 3, 1]) 
    
    with c1:
        if st.button(suggestions[0], key="sug_full_1"):
            st.session_state.prompt_trigger = suggestions[0].replace("\n", " ")
            st.rerun()
    with c2:
        if st.button(suggestions[1], key="sug_full_2"):
            st.session_state.prompt_trigger = suggestions[1].replace("\n", " ")
            st.rerun()
    with c3:
        if st.button(suggestions[2], key="sug_full_3"):
            st.session_state.prompt_trigger = suggestions[2].replace("\n", " ")
            st.rerun()
    with c4:
        if st.button(suggestions[3], key="sug_full_4"):
            st.session_state.prompt_trigger = suggestions[3].replace("\n", " ")
            st.rerun()

else:
    # ปุ่ม Popup ตอนเริ่มคุยแล้ว
    col_spacer, col_pop, col_rest = st.columns([0.2, 1.5, 8]) 
    with col_pop:
        with st.popover("✨ เมนูคำถาม", use_container_width=True):
            st.markdown("###### เลือกหัวข้อ:")
            suggestions = ["ขอดูคู่มือการ\nขอเบิกเงิน", "ขอดูคู่มือการ\nอัปโหลดใบเสร็จ", "เข้าสู่ระบบ\nไม่ได้", "รหัสใบเสร็จ\nRPA คืออะไร"]
            p_col1, p_col2 = st.columns(2)
            with p_col1:
                if st.button(suggestions[0], key="sug_pop_1"):
                    st.session_state.prompt_trigger = suggestions[0].replace("\n", " "); st.rerun()
                if st.button(suggestions[2], key="sug_pop_3"):
                    st.session_state.prompt_trigger = suggestions[2].replace("\n", " "); st.rerun()
            with p_col2:
                if st.button(suggestions[1], key="sug_pop_2"):
                    st.session_state.prompt_trigger = suggestions[1].replace("\n", " "); st.rerun()
                if st.button(suggestions[3], key="sug_pop_4"):
                    st.session_state.prompt_trigger = suggestions[3].replace("\n", " "); st.rerun()

# Main Chat

chat_val = st.chat_input("พิมพ์คำถามที่นี่...")

if st.session_state.prompt_trigger:
    user_input = st.session_state.prompt_trigger
    st.session_state.prompt_trigger = None 
else:
    user_input = chat_val

if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    rag_history = list(st.session_state.messages)[-5:]

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        intent = rag_engine.analyze_intent(user_input)
        
        if intent == "BLOCK":
            full_response = "ขออภัยค่ะ น้องทุนตอบเฉพาะเรื่องงานวิจัยและระบบเบิกจ่ายค่ะ"
            message_placeholder.markdown(full_response)
        
        else:
            with st.status("น้องทุนกำลังคิด...", expanded=True) as status:
                st.write("เรียบเรียงคำถาม...")
                query = rag_engine.rewrite_query(user_input, rag_history, client, config.CURRENT_MODEL)
                st.write("ค้นหาข้อมูล...")
                cands = rag_engine.retrieval_stage(query, all_data, all_vecs, top_k=RETRIEVE_TOPK)
                st.write("คัดกรองเนื้อหา...")
                results = rag_engine.reranking_stage(query, cands, top_k=RERANK_TOPK, intent=intent)

                context_lines = []
                pass_count = 0
                for item, score in results:
                    itype = (item.get("type") or "info").lower()
                    th = get_threshold(itype)
                    if (score / 100.0) >= th:
                        pass_count += 1
                        context_lines.append(f"<{itype}>{item.get('content','')}</{itype}>")
                
                context_str = "\n".join(context_lines).strip()
                has_context = (pass_count >= 1) and (len(context_str) > 0)
                status.update(label="ประมวลผลเสร็จสิ้น", state="complete", expanded=False)

            if not has_context:
                full_response = "ไม่พบข้อมูลในระบบที่เกี่ยวข้องค่ะ รบกวนระบุรายละเอียดเพิ่ม เช่น ชื่อเมนู หรือขั้นตอนที่ทำค้างอยู่ค่ะ"
                message_placeholder.markdown(full_response)
            else:
                msgs = [
                    {
                        "role": "system",
                        "content": f"{config.STATIC_SYS_PROMPT}\n\nContext from Database:\n{context_str}"
                    }
                ] + [{"role": "user", "content": query}]

                try:
                    stream = client.chat.completions.create(
                        model=config.CURRENT_MODEL,
                        messages=msgs, stream=True, temperature=0.3, max_tokens=4096,
                        extra_body={"repetition_penalty": 1.12, "top_p": 0.9}
                    )
                    for chunk in stream:
                        c = chunk.choices[0].delta.content
                        if c: full_response += c; message_placeholder.markdown(full_response + "▌")
                    message_placeholder.markdown(full_response)
                except Exception as e:
                    st.error(f"Gen Error: {e}")
                    full_response = "เกิดข้อผิดพลาดในการสร้างคำตอบค่ะ"

    st.session_state.messages.append({"role": "assistant", "content": full_response})
    st.rerun()