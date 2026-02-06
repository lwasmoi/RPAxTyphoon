# 1. Base Image
FROM python:3.9-slim

# 2. Config
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 3. Copy Requirements
COPY requirements.txt .

# 4. Install (เหลือแค่นี้พอ! ไม่ต้องลง torch แยกแล้ว)
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy Code
COPY . .

# 6. Run
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]