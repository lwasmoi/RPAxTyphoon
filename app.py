import streamlit as st
import time
import re 
import uuid  
from openai import OpenAI
import config
from src import data_loader, embedding, rag_engine
import datetime
from langsmith.wrappers import wrap_openai
from langsmith import traceable
from apscheduler.schedulers.background import BackgroundScheduler
import requests
from src import db_actions 


# SETUP PAGE & SESSION 

st.set_page_config(
    page_title="น้องทุน AI",
    layout="centered", 
    initial_sidebar_state="collapsed", 
)
hide_streamlit_style = """
<style>
    /* ซ่อนส่วนเกิน */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}

    /* STYLE สำหรับปุ่ม ?  */
    .restart-tooltip-container {
        position: fixed;
        top: 35px;          /* ปรับให้ตรงกับแนวปุ่ม */
        right: 180px;       /* ปรับให้ห่างจากปุ่มเริ่มใหม่ (อยู่ทางซ้ายของปุ่ม) */
        z-index: 999999;    /* ให้อยู่บนสุด */
    }
    
    .tooltip-icon {
        background: #f8fafc;
        color: #94a3b8;
        width: 24px; 
        height: 24px;
        border-radius: 50%;
        text-align: center;
        line-height: 24px;
        font-weight: bold;
        font-size: 14px;
        border: 1px solid #cbd5e1;
        cursor: help;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        transition: all 0.2s;
    }
    
    .tooltip-icon:hover {
        background: #ffffff;
        color: #ef4444; /* เปลี่ยนเป็นสีแดงตอนชี้ */
        border-color: #fca5a5;
    }

    /* กล่องข้อความที่จะเด้งขึ้นมา */
    .tooltip-text {
        visibility: hidden;
        width: 160px;
        background-color: #334155;
        color: #fff;
        text-align: center;
        border-radius: 8px;
        padding: 8px 12px;
        position: absolute;
        z-index: 1;
        top: 130%; /* ให้เด้งอยู่ข้างล่างไอคอน */
        left: 50%;
        margin-left: -80px; /* จัดกึ่งกลาง */
        
        /* Effect */
        opacity: 0;
        transition: opacity 0.3s;
        font-size: 12px;
        font-weight: normal;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    /* ลูกศรชี้ขึ้นของกล่องข้อความ */
    .tooltip-text::after {
        content: "";
        position: absolute;
        bottom: 100%;
        left: 50%;
        margin-left: -5px;
        border-width: 5px;
        border-style: solid;
        border-color: transparent transparent #334155 transparent;
    }

    /* โชว์เมื่อเอาเมาส์ชี้ */
    .restart-tooltip-container:hover .tooltip-text {
        visibility: visible;
        opacity: 1;
    }
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)


st.markdown("""
    <div class="restart-tooltip-container">
        <div class="tooltip-icon">?</div>
        <span class="tooltip-text">กดปุ่มนี้เมื่อต้องการ<br>เริ่มหัวข้อใหม่</span>
    </div>
""", unsafe_allow_html=True)




def get_db_metadata_time():
    try:
        db_time = data_loader.get_sync_metadata() 
        return db_time
    except Exception as e:
        print(f"Metadata Fetch Error: {e}")
        return datetime.datetime.now().strftime("%Y-%m-%d")

@st.cache_resource(show_spinner=False) 
def setup_system(day_key, force_refresh=False): 
    client = wrap_openai(OpenAI(api_key=config.CURRENT_KEY, base_url=config.CURRENT_URL))
    all_data = data_loader.load_knowledge(day_key) 
    all_vecs = embedding.build_vector_store(all_data, config.CACHE_JSON, force_refresh=force_refresh)
    return client, all_data, all_vecs


def daily_sync_job():
    print("--- [APScheduler] Starting Daily Sync ---")
    try:
        success = db_actions.confirm_sync_metadata()
        if success:
            # เคลียร์ cache เฉพาะระบบ RAG 
            setup_system.clear() 
            print("[INFO] setup_system Cache cleared.")
            
            # โหลด Data ใหม่
            new_ver = str(get_db_metadata_time())
            print(f"Metadata updated. Background Loading: {new_ver}")
            _ = setup_system(new_ver, force_refresh=True) 
            
            # ยิงเข้าเว็บตัวเองภายใน Docker เพื่อปลุก UI
            # target_url = "http://localhost:8501/"
            target_url = "http://rpaxai.urmo.psu.ac.th/alpha/"

            try:
                requests.get(target_url, timeout=5)
                print(f"Warm-up signal sent to {target_url}")
            except Exception as e:
                print(f"[WARN] Warm-up signal failed: {e}")
                
            print("--- [SUCCESS] Sync & Pre-load Complete ---")
    except Exception as e:
        print(f"Sync error: {e}")
        
@st.cache_resource
def init_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Bangkok")
    scheduler.add_job(daily_sync_job, 'interval', minutes=2)
    scheduler.start()
    return scheduler

_ = init_scheduler()        
        

@st.dialog("ข้อตกลงการใช้งาน")
def show_disclaimer():
    st.markdown("""
        <style>
            /* ซ่อนปุ่ม  X ใน  */
            button[aria-label="Close"] {
                display: none !important;
            }
            /* ป้องกันการคลิกพื้นที่สีดำรอบนอกเพื่อปิด (Overlay) */
            div[data-testid="stModal"] {
                pointer-events: none;
            }
            /* คืนค่าให้เนื้อหาข้างในคลิกได้ปกติ */
            div[data-testid="stModal"] > div {
                pointer-events: auto;
            }
        </style>
        """, unsafe_allow_html=True)
    st.write("ระบบนี้เป็น AI สำหรับช่วยตอบคำถามการเบิกเงินและใบเสร็จ")
    st.warning("กรุณากดปุ่ม  'เริ่มใหม่'  หากต้องการเริ่มคุยหัวข้อใหม่")
    
    button_placeholder = st.empty()

    if "disclaimer_timer_done" not in st.session_state:
        for i in range(5, 0, -1):
            button_placeholder.button(f"กรุณาอ่านเงื่อนไข... ({i})", disabled=True, key=f"wait_{i}")
            time.sleep(1)
        
        st.session_state.disclaimer_timer_done = True
        st.rerun()
        
    else:
        if button_placeholder.button("ยอมรับเงื่อนไข", type="primary", key="accept_btn"):
            st.session_state.accepted_terms = True
            st.rerun()

if "accepted_terms" not in st.session_state:
    show_disclaimer()
    

# เช็คว่ามี session_id  ถ้ายังไม่มีค่อยสร้าง
if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex[:4]

RETRIEVE_TOPK = 20
RERANK_TOPK = 8
TYPE_THRESH = {
    "fact": 0.38,           # ความจริง/ตัวเลข 
    "definition": 0.36,     # นิยามศัพท์
    "troubleshoot": 0.34,   # การแก้ปัญหา 
    "info": 0.35,           # ข้อมูลทั่วไป
    "guide": 0.35,          # ขั้นตอน/คู่มือ 
    "warning": 0.36,        # คำเตือน
    "contact": 0.37         # ข้อมูลติดต่อ
}

def get_threshold(item_type: str) -> float:
    return TYPE_THRESH.get((item_type or "info").strip().lower(), 0.35)

def set_ask(txt):
    st.session_state.prompt_trigger = txt.replace("\n", " ")


try:
    current_db_ver = str(get_db_metadata_time()) 
    client, all_data, all_vecs = setup_system(current_db_ver, force_refresh=False)
except Exception as e:
    st.error(f"System Load Error: {e}")
    st.stop()


@traceable(run_type="chain", name="Decision Logic")
def decide_log_sources(collected_data):
    final_sources = []
    
    debug_info = {
        "s1": 0, "s2": 0, "s3": 0,
        "gap_12": 0, "gap_23": 0,
        "decision": "No Data"
    }

    if collected_data:
        if len(collected_data) == 1:
            final_sources.append(collected_data[0][0])
            debug_info["s1"] = collected_data[0][1]
            debug_info["decision"] = "Single Item Found"
            
        else:
            s1 = collected_data[0][1] 
            s2 = collected_data[1][1] 
            gap_12 = s1 - s2
            debug_info["s1"] = s1
            debug_info["s2"] = s2
            debug_info["gap_12"] = gap_12

            if s1 >= 87.0 or gap_12 >= 8.0:
                final_sources.append(collected_data[0][0]) 
                debug_info["decision"] = "Dominant Win (Keep 1)"
            else:
    
                if len(collected_data) >= 3:
                    s3 = collected_data[2][1]
                    gap_23 = s2 - s3
                    
                    debug_info["s3"] = s3
                    debug_info["gap_23"] = gap_23
                    if gap_23 >= 5.0: 
                        final_sources = [d[0] for d in collected_data[:2]]
                        debug_info["decision"] = "Top 2 Separate (Keep 2)"
                    else:
                        final_sources = [d[0] for d in collected_data[:3]]
                        debug_info["decision"] = "Ambiguous (Keep 3)"
                
                else:
                    final_sources = [d[0] for d in collected_data[:2]]
                    debug_info["decision"] = "Only 2 Items (Keep 2)"
    
    log_string = ", ".join(final_sources) if final_sources else None
    return log_string, debug_info

# HEADER & RESET BUTTON

col_header, col_reset = st.columns([8, 2])

with col_reset:
    if st.button("เริ่มใหม่", type="primary", use_container_width=True):
        # หน่วงเวลาแสดงสถานะ 
        with st.spinner("กำลังล้างความจำ..."): 
            time.sleep(1.0) 
            
        st.session_state.messages = []            
        st.session_state.session_id = uuid.uuid4().hex[:4] 
        st.rerun()                            

st.divider()



# CSS STYLING
st.markdown("""
<style>
    /* 1 จัดโครงสร้างหน้าเว็บหลัก */
    .block-container { 
        max-width: 950px;
        padding-top: 2rem;
        padding-left: 2.5rem;
        margin: auto;
    }

    /* 2 ปุ่มคำถามแนะนำ */
    div.stButton > button {
        width: 220px; height: 70px;
        border-radius: 20px;
        padding: 0px 5px;
        display: flex; align-items: center; justify-content: center; text-align: center;
        line-height: 1.3; font-size: 16px; font-weight: 400;
        background: #ffffff; color: #1e293b; border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    div.stButton > button:hover {
        background: #f8fafc; border-color: #94a3b8; 
        transform: translateY(-4px); box-shadow: 0 10px 20px rgba(0, 0, 0, 0.1); color: #0f172a;
    }

    /* 3 ปุ่มเมนู Popover */
    [data-testid="stPopover"] > button {
        height: 50px; min-height: 50px; width: auto; 
        border-radius: 25px; padding: 0 25px;
        background: #ffffff; border: none; color: #475569; font-weight: 600;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05); 
        display: inline-flex; justify-content: center;
    }
    [data-testid="stPopover"] > button:hover { color: #3b82f6; background: #f8fafc; }
    
    /* ขยายกล่องขาวรองรับ */
    [data-testid="stChatInput"] {
        border-radius: 30px !important; 
        background-color: #ffffff; 
        border: 1px solid #e2e8f0; 
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.08); 
        padding: 10px !important; /* เพิ่มพื้นที่ภายใน */
    }

    /* ขยายตัวหนังสือตอนพิมพ์ */
    [data-testid="stChatInput"] textarea {
        font-size: 1.2rem !important;  /* ตัวหนังสือใหญ่ขึ้น */
        line-height: 1.5 !important;
    }

    div.stButton > button[kind="primary"] {
        position: fixed !important;     
        top: 20px !important;           
        right: 45px !important;         
        z-index: 99999 !important;      
        
        font-size: 24px !important;     
        padding: 12px 30px !important;   
        font-weight: bold !important;
        
        background-color: #ffffff !important;
        color: #ef4444 !important;
        border: 2px solid #fee2e2 !important; 
        box-shadow: 0px 6px 12px rgba(0,0,0,0.1) !important;
        border-radius: 12px !important;
        width: auto !important;
        height: auto !important;
        margin-top: 0px !important;
    }
    
    div.stButton > button[kind="primary"]:hover {
        background-color: #fef2f2 !important;
        color: #b91c1c !important;
        border-color: #ef4444 !important;
        transform: scale(1.05) !important;
    }

    div[role="dialog"] button[kind="primary"],
    div[data-testid="stModal"] button[kind="primary"] {
        position: static !important;    
        top: auto !important;           
        right: auto !important;         
        z-index: 1 !important;          
        transform: none !important;     
        
        font-size: 16px !important;
        padding: 8px 16px !important;
        border: none !important;
        
        width: 100% !important;
        margin-top: 10px !important;
        background-color: #ff4b4b !important; 
        color: white !important;
        box-shadow: none !important;
    }
    
    div[role="dialog"] button[kind="primary"]:hover,
    div[data-testid="stModal"] button[kind="primary"]:hover {
        background-color: #ff3333 !important;
    }

    hr { display: none !important; }
    [data-testid="column"] { padding: 0 4px; }
</style>
""", unsafe_allow_html=True)


# CHAT DISPLAY & FEEDBACK
if "messages" not in st.session_state: st.session_state.messages = []
if "prompt_trigger" not in st.session_state: st.session_state.prompt_trigger = None

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        # ถ้าเป็นข้อความของ Assistant และมี log_id ให้แสดงปุ่ม
        if msg["role"] == "assistant":
            log_id = msg.get("log_id")
            if log_id:
                feedback_key = f"fb_{log_id}"
                # แสดงปุ่ม (thumbs)
                score = st.feedback("thumbs", key=feedback_key)
                if score is not None:
                    # บันทึกลง Database
                    data_loader.update_feedback(log_id, score)
                    feed_text = "Good" if score == 1 else "Bad"



# SUGGESTIONS & MENU


suggestions = [
    {"label": "ขอคู่มือการขอเบิกเงิน", "query": "ขอคู่มือการขอเบิกเงินทดรองจ่าย"},
    {"label": "ขอคู่มือการอัปโหลดใบเสร็จ", "query": "คู่มือการอัปโหลดใบเสร็จในระบบ RPA ตั้งแต่ขั้นตอนแรกจนถึงขั้นตอนสุดท้าย"},
    {"label": "เข้าสู่ระบบไม่ได้", "query": "เข้าสู่ระบบไม่ได้"},
    {"label": "รหัสใบเสร็จRPA คืออะไร", "query": "รหัสใบเสร็จRPA คืออะไร"}
]

if len(st.session_state.messages) == 0:
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<h4 style='text-align: center; color: #334155;'>คำถามแนะนำ</h4>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    cols = [c1, c2, c3, c4]
    for i, item in enumerate(suggestions):
        with cols[i]:
            st.button(item["label"], key=f"sug_full_{i}", on_click=set_ask, args=(item["query"],))
else:
    col_spacer, col_pop, col_rest = st.columns([0.2, 1.5, 8]) 
    with col_pop:
        with st.popover("เมนูคำถาม", use_container_width=True):
            st.markdown("###### เลือกหัวข้อ:")
            p_cols = st.columns(2)
            for i, item in enumerate(suggestions):
                p_cols[i % 2].button(item["label"], key=f"sug_pop_{i}", on_click=set_ask, args=(item["query"],))



# MAIN CHAT PROCESSING

chat_val = st.chat_input("พิมพ์คำถามที่นี่...")

if st.session_state.prompt_trigger:
    user_input = st.session_state.prompt_trigger
    st.session_state.prompt_trigger = None 
else:
    user_input = chat_val

if user_input:
    time.sleep(0.1)
    
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    rag_history = list(st.session_state.messages)[-3:]

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        log_source = None

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
                collected_data = [] # เก็บเป็น tuple
                
                for item, score in results:
                    itype = (item.get("type") or "info").lower()
                    th = get_threshold(itype)
                    
                    if (score / 100.0) >= th:
                        pass_count += 1
                        context_lines.append(f"<{itype}>{item.get('content','')}</{itype}>")
                        
                        # ดึงชื่อ Source
                        src_name = item.get("metadata", {}).get("source")
                        if src_name:
                            # เช็คถ้าไม่ซ้ำค่อยเพิ่ม
                            is_dup = any(d[0] == src_name for d in collected_data)
                            if not is_dup:
                                collected_data.append((src_name, score))
                

                log_source, debug_info = decide_log_sources(collected_data)
                
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
                        if c: 
                            if re.search(r'[\u4e00-\u9fff]', c):
                                continue 
                            full_response += c
                            message_placeholder.markdown(full_response + "▌")
                    message_placeholder.markdown(full_response)
                except Exception as e:
                    st.error(f"Gen Error: {e}")
                    full_response = "เกิดข้อผิดพลาดในการสร้างคำตอบค่ะ"

    # บันทึก Log โดยใช้ session_id เดิมที่คงที่
    saved_log_id = data_loader.save_chat_log(
        session_id=st.session_state.session_id,  
        user_input=user_input,
        ai_response=full_response,
        source=log_source
    )

    # เก็บ log_id ลง session
    st.session_state.messages.append({
        "role": "assistant", 
        "content": full_response,
        "log_id": saved_log_id  
    })
    
    st.rerun()