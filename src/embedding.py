import numpy as np
import os
import time
import httpx
import config

# ตั้งค่า Timeout 
TIMEOUT = httpx.Timeout(45.0, connect=10.0, read=45.0)
HTTP = httpx.Client(
    timeout=TIMEOUT, 
    headers={"Content-Type": "application/json"},
    verify=False 
)
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
    if not data_list:
        return None

    
    if not force_refresh and cache_file and os.path.exists(cache_file):
        try:
            vectors = np.load(cache_file)
            print(f"[INFO] Loaded vectors from cache: {cache_file}")
            return vectors.astype("float32")
        except:
            pass

    print(f"[INFO] Building vectors for {len(data_list)} items...")
    
    first_vec = np.array([])
    idx_start = 0
    for i, item in enumerate(data_list):
        content = item.get("content", "").strip()
        if content:
            first_vec = get_embedding_remote(content)
            if first_vec.size > 0:
                idx_start = i
                break
    
    if first_vec.size == 0:
        print("[ERROR] API Error: Cannot get initial embedding dimension. Aborting.")
        return None
        
    embed_dim = first_vec.shape[0]
    vectors = np.zeros((len(data_list), embed_dim), dtype="float32")
    
    # ใส่ค่าตัวแรกที่หาเจอลงในตำแหน่งที่ถูกต้อง
    vectors[idx_start] = first_vec

    # วนลูปทำที่เหลือ
    start_time = time.time()
    for i in range(len(data_list)):
        if i == idx_start: continue 
        
        if i % 25 == 0:
            print(f"   Processing {i}/{len(data_list)}...", end="\r")
        
        content = data_list[i].get("content", "")
        if not content.strip(): continue 
        
        vec = get_embedding_remote(content)
        if vec.size == embed_dim:
            vectors[i] = vec

    # บันทึก Cache 
    if cache_file:
        
        temp_file = f"{cache_file}"
        np.save(temp_file, vectors)
        
        os.replace(temp_file, cache_file) 
        
        print(f"\n[INFO] Saved and replaced cache successfully: {cache_file}")

    return vectors