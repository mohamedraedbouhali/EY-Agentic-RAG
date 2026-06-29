FROM python:3.12-slim

WORKDIR /app

# System packages: poppler for pdf2image, libGL + libglib2 for easyocr
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/lists/*

# Install CPU-only PyTorch first so pip doesn't pull the 2.5 GB CUDA variant
RUN pip install --no-cache-dir --timeout=120 --retries=5 \
    torch==2.4.1 \
    torchvision==0.19.1 \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=120 --retries=5 -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
