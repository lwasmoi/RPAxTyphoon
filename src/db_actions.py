from src.data_loader import get_db_connection
import config

def confirm_sync_metadata():
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as cur:
            sql = f"""
                UPDATE {config.DB_SCHEMA}.system_metadata 
                SET last_updated = CURRENT_TIMESTAMP, 
                    pending_update = FALSE 
                WHERE key = 'bot_sync_status' AND pending_update = TRUE;
            """
            cur.execute(sql)
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        print(f"Update failed: {e}")
        return False
    finally:
        conn.close()