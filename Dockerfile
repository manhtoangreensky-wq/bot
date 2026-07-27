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
        tesseract-ocr \
        tesseract-ocr-all \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

# Sao chép cả direct requirements và khóa resolve đúng runtime Linux/Python 3.11.
COPY requirements.txt requirements.lock ./

# Cài đúng toàn bộ graph đã khóa; hashes làm sai lệch dependency fail-closed.
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

# Sao chép toàn bộ code còn lại vào container
COPY . .

# Lệnh để khởi chạy bot
CMD ["python", "bot.py"]
