# import re
# from supabase import create_client, Client
# import config

# # Supabase Client Setup
# try:
#     supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
# except Exception as e:
#     print(f"[ERROR] Supabase Config Error: {e}")
#     supabase = None

# def load_supabase_knowledge():
#     if not supabase:
#         print("[ERROR] Supabase connection failed.")
#         return []

#     knowledge_base = []
#     print("[INFO] Gathering ALL data from Supabase...")

#     # โหลดข้อมูลจาก 4 แหล่งหลัก
#     knowledge_base.extend(fetch_rpa_manuals())       
#     knowledge_base.extend(fetch_funds())                 
#     knowledge_base.extend(fetch_dictionary())            
#     knowledge_base.extend(fetch_troubleshooting_chunked()) 

#     print(f"[INFO] Total Knowledge Loaded: {len(knowledge_base)} items.")
#     return knowledge_base

# def fetch_rpa_manuals():
#     try:
#         res = supabase.table('view_rpa_manuals').select('*').execute()
#         rows = res.data or []
#         chunks = []
#         print(f"[INFO] Processing {len(rows)} records from 'view_rpa_manuals'...")

#         for row in rows:
#             db_id = str(row.get("chunk_id"))          
#             content = row.get("chunk_content", "").strip() 
#             topic = row.get("topic", "").strip()
#             section = row.get("section", "").strip()   
#             source_doc = row.get("document_title", "").strip() 
#             raw_type = row.get("data_type") or "info" 
#             step_num = row.get("step_number")
#             fund_abbr = row.get("fund_abbr")
#             cat_main = row.get("category_main", "")
#             cat_sub = row.get("category_sub", "")
#             category_text = f"{cat_main} > {cat_sub}" if cat_main and cat_sub else (cat_sub or cat_main)
#             if not content: continue
#             formatted_content = f"เอกสาร: {source_doc}\nหมวดหมู่: {category_text}\nหัวข้อ: {topic}\nเนื้อหา:\n{content}"

#             chunks.append({
#                 "id": f"manual:{db_id}",
#                 "content": formatted_content,
#                 "type": raw_type, 
#                 "metadata": {
#                     "source": source_doc,
#                     "topic": topic,
#                     "section": section,
#                     "category": cat_sub,      
#                     "category_group": cat_main, 
#                     "step_number": step_num,
#                     "fund_abbr": fund_abbr
#                 }
#             })
        
#         return chunks

#     except Exception as e:
#         print(f"[ERROR] RPA Manuals Error: {e}")
#         return []
    
# def fetch_funds():
#     try:
#         res = supabase.table("research_funds").select("*").execute()
#         rows = res.data or []
#         chunks = []

#         for row in rows:
#             status = str(row.get("status", "")).strip().lower()
#             fund_abbr = (row.get("fund_abbr") or "").strip()
#             fund_name = (row.get("fund_name_th") or row.get("fund_name_en") or "").strip()
#             fiscal_year = str(row.get("fiscal_year", ""))

#             if status == 'disable':
#                 content = (
#                     f"[SYSTEM WARNING: ข้อมูลสถานะทุน]\n"
#                     f"ทุนวิจัย: {fund_name} ({fund_abbr})\n"
#                     f"สถานะปัจจุบัน:  ปิดโครงการ\n"
#                     f"ปีงบประมาณ: {fiscal_year}\n"
#                     f"ข้อควรระวัง: โครงการนี้สิ้นสุดระยะเวลาแล้ว ข้อมูลระเบียบหรือคู่มือการเบิกจ่ายที่เกี่ยวข้องอาจไม่สามารถใช้งานได้ในปัจจุบัน กรุณาตรวจสอบสถานะก่อนดำเนินการ"
#                 )
#             else:
#                 content = (
#                     f"ทุนวิจัย: {fund_name} ({fund_abbr})\n"
#                     f"ปีงบประมาณ: {fiscal_year}\n"
#                     f"สถานะทุน:  สถานะทำงาน \n"
#                     f"แหล่งทุน: {row.get('source_agency','')}\n"
#                     f"ช่วงเวลา: {row.get('start_period','')} ถึง {row.get('end_period','')}"
#                 )

#             chunks.append({
#                 "id": f"fund:{_safe_id(fund_abbr)}:{fiscal_year}",
#                 "content": content,
#                 "type": "fact", 
#                 "metadata": {
#                     "source": fund_name, 
#                     "fund_abbr": fund_abbr,
#                     "fiscal_year": fiscal_year,
#                     "status": status 
#                 }
#             })
#         return chunks

#     except Exception as e:
#         print(f"[ERROR] Funds Error: {e}")
#         return []

# def fetch_dictionary():
#     try:
#         res = supabase.table("glossary_terms").select("*").execute()
#         rows = res.data or []
#         chunks = []

#         for row in rows:
#             word = (row.get("word") or "").strip()
#             meaning = (row.get("meaning") or "").strip()
#             word_type = row.get("word_type") or "General Term"

#             if not word: continue

#             chunks.append({
#                 "id": f"glossary:{_safe_id(word)}",
#                 "content": f"คำศัพท์: {word} ({word_type})\nความหมาย: {meaning}",
#                 "type": "definition",
#                 "metadata": {
#                     "source": word_type,  
#                     "keywords": [word]
#                 }
#             })
#         return chunks

#     except Exception as e:
#         print(f"[ERROR] Glossary Error: {e}")
#         return []

# def fetch_troubleshooting_chunked():
#     try:
#         # ใช้ solution ที่ Refine format มาแล้วใน DB
#         stories = supabase.table("view_support_stories").select("*").execute().data or []
#         chunks = []
        
#         for s in stories:
#             story_id = s.get("id") or s.get("story_id")
#             scenario = (s.get("problem") or "").strip()
#             solution = (s.get("solution") or "").strip()
#             category_name = s.get("category_name")

#             full_content = f"หมวดหมู่: {category_name}\nอาการ: {scenario}\nวิธีแก้: {solution}"

#             if scenario or solution:
#                 chunks.append({
#                     "id": f"ts:{story_id}",
#                     "content": full_content,
#                     "type": "troubleshoot",
#                     "metadata": {
#                         "source": category_name,  
#                         "category": category_name, 
#                         "type": "solution"
#                     }
#                 })
#         return chunks

#     except Exception as e:
#         print(f"[ERROR] Troubleshooting Error: {e}")
#         return []

# def _safe_id(s: str) -> str:
#     s = (s or "").strip()
#     s = re.sub(r"\s+", "_", s)
#     s = re.sub(r"[^A-Za-z0-9_\-\.ก-๙]+", "", s)
#     return s[:50] if s else "unknown"

# def save_chat_log(session_id: str, user_input: str, ai_response: str, source: str = None):
#     if not supabase:
#         return None
#     try:
#         data = {
#             "session_id": session_id,
#             "user_input": user_input,
#             "ai_response": ai_response,
#             "relevant_source": source
#         }
#         response = supabase.table("chat_logs").insert(data).execute()
        
#         if response.data and len(response.data) > 0:
#             return response.data[0]['id'] 
#         return None
#     except Exception as e:
#         print(f"[ERROR] Save Log Failed: {e}")
#         return None

# def update_feedback(log_id: int, score: int):
#     if not supabase or not log_id: return
#     try:
#         supabase.table("chat_logs").update({"feedback_score": score}).eq("id", log_id).execute()
#     except Exception as e:
#         print(f"[ERROR] Update Feedback Failed: {e}")



import re
import psycopg2
from psycopg2.extras import RealDictCursor
import config

# ฟังก์ชันเชื่อมต่อ Database
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=config.DB_HOST,
            database=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASS,
            port=config.DB_PORT
        )
        return conn
    except Exception as e:
        print(f"[ERROR] DB Connection Failed: {e}")
        return None

def load_supabase_knowledge():
    # เปลี่ยนแค่ข้อความ Log เล็กน้อยเพื่อให้รู้ว่าต่อ DB ไหน
    knowledge_base = []
    print("[INFO] Gathering ALL data from PostgreSQL...")

    knowledge_base.extend(fetch_rpa_manuals())       
    knowledge_base.extend(fetch_funds())                 
    knowledge_base.extend(fetch_dictionary())            
    knowledge_base.extend(fetch_troubleshooting_chunked()) 

    print(f"[INFO] Total Knowledge Loaded: {len(knowledge_base)} items.")
    return knowledge_base

def fetch_rpa_manuals():
    conn = get_db_connection()
    if not conn: return []
    
    chunks = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # ดึงข้อมูลจาก View ตาม Logic เดิม
            cur.execute(f"SELECT * FROM {config.DB_SCHEMA}.view_rpa_manuals")
            rows = cur.fetchall()
            
            print(f"[INFO] Processing {len(rows)} records from 'view_rpa_manuals'...")

            for row in rows:
                db_id = str(row.get("chunk_id"))          
                content = row.get("chunk_content", "").strip() 
                topic = row.get("topic", "").strip()
                section = row.get("section", "").strip()   
                source_doc = row.get("document_title", "").strip() 
                raw_type = row.get("data_type") or "info" 
                step_num = row.get("step_number")
                fund_abbr = row.get("fund_abbr")
                
                cat_main = row.get("category_main", "")
                cat_sub = row.get("category_sub", "")
                category_text = f"{cat_main} > {cat_sub}" if cat_main and cat_sub else (cat_sub or cat_main)
                
                if not content: continue
                
                formatted_content = f"เอกสาร: {source_doc}\nหมวดหมู่: {category_text}\nหัวข้อ: {topic}\nเนื้อหา:\n{content}"

                chunks.append({
                    "id": f"manual:{db_id}",
                    "content": formatted_content,
                    "type": raw_type, 
                    "metadata": {
                        "source": source_doc,
                        "topic": topic,
                        "section": section,
                        "category": cat_sub,      
                        "category_group": cat_main, 
                        "step_number": step_num,
                        "fund_abbr": fund_abbr
                    }
                })
        return chunks

    except Exception as e:
        print(f"[ERROR] RPA Manuals Error: {e}")
        return []
    finally:
        conn.close()
    
def fetch_funds():
    conn = get_db_connection()
    if not conn: return []

    chunks = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT * FROM {config.DB_SCHEMA}.research_funds")
            rows = cur.fetchall()

            for row in rows:
                # ดึงค่าดิบจาก DB และแปลงเป็นสถานะมาตรฐาน 
                raw_status = str(row.get("status", "")).strip().lower()
                
                # เช็คว่าใช่สถานะเปิดหรือไม่ 
                if raw_status in ['y','yes', 'enable', 'active', 'true', '1','Y']:
                    std_status = "active"
                else:
                    std_status = "inactive"

                fund_abbr = (row.get("fund_abbr") or "").strip()
                fund_name = (row.get("fund_name_th") or row.get("fund_name_en") or "").strip()
                fiscal_year = str(row.get("fiscal_year", ""))

                # สร้าง Content ตามสถานะ
                if std_status == "active":
                    content = (
                        f"ทุนวิจัย: {fund_name} ({fund_abbr})\n"
                        f"ปีงบประมาณ: {fiscal_year}\n"
                        f"สถานะทุน: 🟢 ทำงาน)\n"
                        f"แหล่งทุน: {row.get('source_agency','')}\n"
                        f"ช่วงเวลา: {row.get('start_period','')} ถึง {row.get('end_period','')}"
                    )
                else:
                    content = (
                        f"[SYSTEM WARNING: ข้อมูลสถานะทุน]\n"
                        f"ทุนวิจัย: {fund_name} ({fund_abbr})\n"
                        f"สถานะปัจจุบัน: 🔴 ยุติการทำงาน\n"
                        f"ปีงบประมาณ: {fiscal_year}\n..."
                    )

                chunks.append({
                    "id": f"fund:{_safe_id(fund_abbr)}:{fiscal_year}",
                    "content": content,
                    "type": "fact", 
                    "metadata": {
                        "source": fund_name, 
                        "fund_abbr": fund_abbr,
                        "fiscal_year": fiscal_year,
                        "status": std_status  
                    }
                })
        return chunks

    except Exception as e:
        print(f"[ERROR] Funds Error: {e}")
        return []
    finally:
        conn.close()

def fetch_dictionary():
    conn = get_db_connection()
    if not conn: return []

    chunks = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT * FROM {config.DB_SCHEMA}.glossary_terms")
            rows = cur.fetchall()

            for row in rows:
                word = (row.get("word") or "").strip()
                meaning = (row.get("meaning") or "").strip()
                word_type = row.get("word_type") or "General Term"

                if not word: continue

                chunks.append({
                    "id": f"glossary:{_safe_id(word)}",
                    "content": f"คำศัพท์: {word} ({word_type})\nความหมาย: {meaning}",
                    "type": "definition",
                    "metadata": {
                        "source": word_type,  
                        "keywords": [word]
                    }
                })
        return chunks

    except Exception as e:
        print(f"[ERROR] Glossary Error: {e}")
        return []
    finally:
        conn.close()

def fetch_troubleshooting_chunked():
    conn = get_db_connection()
    if not conn: return []
    
    chunks = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT * FROM {config.DB_SCHEMA}.view_support_stories")
            rows = cur.fetchall()
            
            for s in rows:
                story_id = s.get("id") or s.get("story_id")
                scenario = (s.get("problem") or "").strip()
                solution = (s.get("solution") or "").strip()
                category_name = s.get("category_name")

                full_content = f"หมวดหมู่: {category_name}\nอาการ: {scenario}\nวิธีแก้: {solution}"

                if scenario or solution:
                    chunks.append({
                        "id": f"ts:{story_id}",
                        "content": full_content,
                        "type": "troubleshoot",
                        "metadata": {
                            "source": category_name,  
                            "category": category_name, 
                            "type": "solution"
                        }
                    })
        return chunks

    except Exception as e:
        print(f"[ERROR] Troubleshooting Error: {e}")
        return []
    finally:
        conn.close()

def _safe_id(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^A-Za-z0-9_\-\.ก-๙]+", "", s)
    return s[:50] if s else "unknown"

def save_chat_log(session_id: str, user_input: str, ai_response: str, source: str = None):
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor() as cur:
            # ใช้ SQL Insert แทน Supabase Method
            sql = f"""
                INSERT INTO {config.DB_SCHEMA}.chat_logs 
                (session_id, user_input, ai_response, relevant_source) 
                VALUES (%s, %s, %s, %s) 
                RETURNING id
            """
            cur.execute(sql, (session_id, user_input, ai_response, source))
            new_id = cur.fetchone()[0]
            conn.commit() # Postgres ต้อง commit
            return new_id
    except Exception as e:
        print(f"[ERROR] Save Log Failed: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def update_feedback(log_id: int, score: int):
    conn = get_db_connection()
    if not conn or not log_id: return
    try:
        with conn.cursor() as cur:
            # ใช้ SQL Update
            sql = f"UPDATE {config.DB_SCHEMA}.chat_logs SET feedback_score = %s WHERE id = %s"
            cur.execute(sql, (score, log_id))
            conn.commit()
    except Exception as e:
        print(f"[ERROR] Update Feedback Failed: {e}")
        conn.rollback()
    finally:
        conn.close()
        