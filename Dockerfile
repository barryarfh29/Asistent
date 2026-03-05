# Gunakan image python versi ringan
FROM python:3.10-slim

# Set working directory di dalam container
WORKDIR /app

# Install dependencies sistem yang dibutuhkan untuk enkripsi tgcrypto
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy file requirements terlebih dahulu (agar build cache lebih efisien)
COPY requirements.txt .

# Install library python
RUN pip install --no-cache-dir -r requirements.txt

# Copy seluruh kode project ke dalam container
COPY . .

# Jalankan bot
CMD ["python", "main.py"]
