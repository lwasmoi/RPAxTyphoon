import numpy as np
import os
import time
import httpx
import config

# ตั้งค่า Timeout 
TIMEOUT = httpx.Timeout(45.0, connect=10.0, read=45.0)
HTTP = httpx.Client(timeout=TIMEOUT, headers={"Content-Type": "application/json"})

def _normalize(vec: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(vec)
    if n == 0:
        return vec
    return vec / (n + 1e-12)

def _to_vec(data) -> np.ndarray:    
    # OpenAI Style { "data": [ { "embedding": [...] } ] }
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        if len(data["data"]) > 0:
            emb = data["data"][0].get("embedding")
            if isinstance(emb, list):
                return np.array(emb, dtype="float32")

    # Ollama/Local Style { "embedding": [...] }
    if isinstance(data, dict):
        if "embedding" in data and isinstance(data["embedding"], list):
            return np.array(data["embedding"], dtype="float32")
        
        # { "embeddings": [...] }
        if "embeddings" in data:
            vecs = data["embeddings"]
            if isinstance(vecs, list) and len(vecs) > 0:
                # กรณีส่งกลับมาเป็น List ซ้อน List เอาตัวแรก
                if isinstance(vecs[0], list):
                    return np.array(vecs[0], dtype="float32")
                return np.array(vecs, dtype="float32")

        # { "vectors": [...] }
        if "vectors" in data and isinstance(data["vectors"], list):
            return np.array(data["vectors"], dtype="float32")

    # Direct List [ ... ]
    if isinstance(data, list) and len(data) > 0:
        if isinstance(data[0], list):
            return np.array(data[0], dtype="float32")
        return np.array(data, dtype="float32")

    return np.array([], dtype="float32")

def get_embedding_remote(text: str, retries: int = 3) -> np.ndarray:
    """ส่ง Text ไปแปลงเป็น Vector (มี Retry Logic)"""
    # Pre-process text: แปลงเป็น string, ลบ new line, ตัดช่องว่าง
    text = str(text or "").replace("\n", " ").strip()
    
    if not text:
        return np.array([], dtype="float32")

    payload = {
        "model": config.UNI_EMBED_MODEL, 
        "input": text
    }

    for attempt in range(retries):
        try:
            resp = HTTP.post(config.UNI_EMBED_URL, json=payload)

            # Retry กรณี Server Busy (429) หรือ Error 5xx
            if resp.status_code == 429 or (500 <= resp.status_code <= 599):
                wait_time = 0.5 * (2 ** attempt) # Exponential backoff
                time.sleep(wait_time)
                continue

            if resp.status_code != 200:
                print(f"[WARN] Embedding Error {resp.status_code}: {resp.text[:100]}")
                return np.array([], dtype="float32")

            data = resp.json()
            vec = _to_vec(data)

            if vec.size == 0:
                return np.array([], dtype="float32")

            return _normalize(vec)

        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError):
            time.sleep(0.5 * (2 ** attempt))
        except Exception as e:
            print(f"[ERROR] Embedding Exception: {e}")
            break

    return np.array([], dtype="float32")

def build_vector_store(data_list, cache_file=None, force_refresh=False):
    """สร้าง Vector Database โดยไล่ทำทีละรายการ"""
    if not data_list:
        return None

    # ลองโหลดจาก Cache ก่อน
    if not force_refresh and cache_file and os.path.exists(cache_file):
        try:
            vectors = np.load(cache_file)
            # เช็คว่าจำนวนแถวตรงกันไหม
            if vectors.ndim == 2 and vectors.shape[0] == len(data_list):
                print(f"[INFO] Loaded vectors from cache: {cache_file} (Shape: {vectors.shape})")
                return vectors.astype("float32")
            else:
                print(f"[WARN] Cache mismatch (Data: {len(data_list)} vs Cache: {vectors.shape[0]}). Rebuilding...")
        except Exception as e:
            print(f"[WARN] Cache load failed: {e}, rebuilding...")

    print(f"[INFO] Building vectors via API ({config.UNI_EMBED_MODEL}) for {len(data_list)} items...")
    
    # หา Dimension จากข้อมูลตัวแรก (Dynamic Dimension Detection)
    first_content = data_list[0].get("content", "")
    first_vec = get_embedding_remote(first_content)
    
    if first_vec.size == 0:
        print("[ERROR] Failed to get embedding for the first item. Aborting.")
        return None
        
    embed_dim = first_vec.shape[0]
    print(f"   - Detected Dimension: {embed_dim}")

    # จองพื้นที่ Memory (Zero Array)
    vectors = np.zeros((len(data_list), embed_dim), dtype="float32")
    vectors[0] = first_vec # ใส่ตัวแรกที่หามาแล้วลงไป

    # วนลูปทำตัวที่เหลือ
    start_time = time.time()
    for i in range(1, len(data_list)):
        # แสดง Progress ทุกๆ 25 ตัว
        if i % 25 == 0:
            elapsed = time.time() - start_time
            print(f"   Processing {i}/{len(data_list)} ({elapsed:.1f}s)...", end="\r")
        
        content = data_list[i].get("content", "")
        vec = get_embedding_remote(content)
        
        # Safety Check: ถ้าได้ Vector มาไม่ครบ หรือ Error ให้เป็น 0 ไว้ก่อน
        if vec.size == embed_dim:
            vectors[i] = vec
        else:
            # ปล่อยให้เป็น 0 (Row of zeros) เพื่อไม่ให้โปรแกรมพัง
            pass 

    total_time = time.time() - start_time
    print(f"\n[INFO] Embedding complete. Total time: {total_time:.1f}s")
    
    # บันทึก Cache
    if cache_file:
        try:
            np.save(cache_file, vectors)
            print(f"[INFO] Saved cache to: {cache_file}")
        except Exception as e:
            print(f"[ERROR] Failed to save cache: {e}")

    return vectors