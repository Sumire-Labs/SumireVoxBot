# 修正案：キャッシュ効率を上げる
FROM python:3.14-slim

WORKDIR /app

# 先にシステムパッケージをインストール（ここは滅多に変わらないのでキャッシュさせる）
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# requirementsだけ先にコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 最後にソースコードをコピー（コードを書き換えるたびにここより下が実行される）
COPY . .

CMD ["python", "main.py"]