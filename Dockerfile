FROM python:3.11-slim

WORKDIR /app

# Sao chép file cài đặt thư viện vào trước
COPY requirements.txt .

# Tiến hành cài đặt các thư viện bằng Python 3.11
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ code còn lại vào container
COPY . .

# Lệnh để khởi chạy bot
CMD ["python", "bot.py"]