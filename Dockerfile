FROM python:3.11-slim

WORKDIR /app

# FFmpeg renders SubDub output. Fontconfig and Noto provide real glyphs for
# Vietnamese, CJK, Thai, Arabic, Devanagari and Cyrillic subtitles.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        fontconfig \
        fonts-dejavu-core \
        fonts-noto-core \
        fonts-noto-cjk \
        fonts-noto-extra \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

# Sao chép file cài đặt thư viện vào trước
COPY requirements.txt .

# Tiến hành cài đặt các thư viện bằng Python 3.11
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ code còn lại vào container
COPY . .

# Lệnh để khởi chạy bot
CMD ["python", "bot.py"]
