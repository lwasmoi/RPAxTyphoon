# 1. ใช้ Python 3.9 แบบ Slim (ขนาดเล็ก)
FROM python:3.9-slim

# 2. ป้องกัน Python สร้างไฟล์ .pyc
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. เตรียมติดตั้ง Dependency พื้นฐานของ Linux (จำเป็นสำหรับบาง Library)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 4. สร้างโฟลเดอร์ทำงานข้างใน Container
WORKDIR /app

# 5. ก๊อปปี้ไฟล์ requirements.txt เข้าไปก่อน
COPY requirements.txt .

# 6. ติดตั้ง Library (ขั้นตอนนี้จะนานหน่อย เพราะมี Torch)
RUN pip install --no-cache-dir -r requirements.txt

# 7. ก๊อปปี้โค้ดทั้งหมดเข้าไป
COPY . .

# 8. เปิด Port 8501
EXPOSE 8501

# 9. คำสั่งรันแอป
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]