import re
from supabase import create_client, Client
from collections import defaultdict
import config

# Supabase Client Setup
try:
    supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
except Exception as e:
    print(f"[ERROR] Supabase Config Error: {e}")
    supabase = None

# Main Loader

def load_supabase_knowledge():
    if not supabase:
        print("[ERROR] Supabase connection failed.")
        return []

    knowledge_base = []
    print("[INFO] Gathering ALL data from Supabase...")

    # โหลดคู่มือจากตารางใหม่ (rpa_manuals)
    knowledge_base.extend(fetch_rpa_manuals())       
    
    # โหลดข้อมูลเสริมอื่นๆ
    knowledge_base.extend(fetch_funds())                 
    knowledge_base.extend(fetch_dictionary())            
    
    # โหลด Troubleshooting 
    knowledge_base.extend(fetch_troubleshooting_chunked()) 

    print(f"[INFO] Total Knowledge Loaded: {len(knowledge_base)} items.")
    return knowledge_base


# Sub-Loaders
def fetch_rpa_manuals():
    try:
        # ดึงข้อมูลทั้งหมดจากตาราง
        res = supabase.table("rpa_manuals").select("*").execute()
        rows = res.data or []
        chunks = []

        print(f"[INFO] Processing {len(rows)} records from 'rpa_manuals'...")

        for row in rows:
            # ดึง Field สำคัญ
            db_id = str(row.get("id"))
            source_doc = row.get("source_doc", "").strip()
            section = row.get("section", "").strip()
            topic = row.get("topic", "").strip()
            content = row.get("content", "").strip()
            data_type = row.get("data_type", "info")
            
            meta = row.get("metadata") or {}

            if not content: continue

            formatted_content = f"{source_doc} ({section})\nหัวข้อ: {topic}\nเนื้อหา:\n{content}"

            meta.update({
                "source": source_doc,
                "section": section,
                "topic": topic,
                "type": data_type
            })

            chunks.append({
                "id": f"manual:{db_id}",      # ID อ้างอิง
                "content": formatted_content, # ข้อความที่ใช้ทำ Vector
                "type": data_type,            # ประเภทข้อมูล
                "metadata": meta              
            })
        
        print(f"   > Loaded {len(chunks)} chunks from manuals.")
        return chunks

    except Exception as e:
        print(f"[ERROR] RPA Manuals Error: {e}")
        return []

def fetch_funds():
    try:
        res = supabase.table("research_funds").select("*").execute()
        rows = res.data or []
        chunks = []

        for row in rows:
            fund_abbr = (row.get("fund_abbr") or "").strip()
            fund_name = (row.get("fund_name_th") or "").strip()
            fiscal_year = str(row.get("fiscal_year", ""))
            
            # Content Format
            content = (
                f"ทุนวิจัย: {fund_name} ({fund_abbr})\n"
                f"ปีงบประมาณ: {fiscal_year}\n"
                f"แหล่งทุน: {row.get('source_agency','')}"
            )

            chunks.append({
                "id": f"fund:{_safe_id(fund_abbr)}:{fiscal_year}",
                "content": content,
                "type": "fact",
                "metadata": {
                    "fund_abbr": fund_abbr,
                    "fund_name_th": fund_name,
                    "fiscal_year": fiscal_year
                }
            })

        print(f"[INFO] Processed {len(chunks)} funds.")
        return chunks

    except Exception as e:
        print(f"[ERROR] Funds Error: {e}")
        return []

def fetch_dictionary():
    try:
        res = supabase.table("glossary_terms").select("*").execute()
        rows = res.data or []
        chunks = []

        for row in rows:
            word = (row.get("word") or "").strip()
            meaning = (row.get("meaning") or "").strip()

            if not word: continue

            chunks.append({
                "id": f"glossary:{_safe_id(word)}",
                "content": f"คำศัพท์: {word}\nความหมาย: {meaning}",
                "type": "definition",
                "metadata": {
                    "keywords": [word]
                }
            })

        print(f"[INFO] Processed {len(chunks)} glossary terms.")
        return chunks

    except Exception as e:
        print(f"[ERROR] Glossary Error: {e}")
        return []

def fetch_troubleshooting_chunked():
    try:
        stories = supabase.table("support_stories").select("*").execute().data or []
        chunks = []
        
        for s in stories:
            story_id = s.get("story_id")
            scenario = (s.get("scenario") or "").strip()
            solution = (s.get("solution") or "").strip()

            # แยกอาการ เอาไว้ค้นหา
            if scenario:
                chunks.append({
                    "id": f"ts:{story_id}:symptom",
                    "content": f"อาการปัญหา: {scenario}",
                    "type": "troubleshoot",
                    "metadata": {"type": "symptom"}
                })

            # วิธีแก้  เอาไว้ตอบ
            if solution:
                chunks.append({
                    "id": f"ts:{story_id}:solution",
                    "content": f"วิธีแก้ปัญหา ({scenario}): {solution}",
                    "type": "troubleshoot",
                    "metadata": {"type": "solution"}
                })

        print(f"[INFO] Processed {len(chunks)} troubleshooting items.")
        return chunks

    except Exception as e:
        print(f"[ERROR] Troubleshooting Error: {e}")
        return []

# Helper Functions

def _safe_id(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^A-Za-z0-9_\-\.ก-๙]+", "", s)
    return s[:50] if s else "unknown"