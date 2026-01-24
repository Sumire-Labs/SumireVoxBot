# SumireVoxBot

## 概要
discord.py と VOICEVOX エンジンを用いた読み上げBotです。

## 依存関係
### Python パッケージ
- discord.py
- python-dotenv
- aiohttp
- aiofiles
- asyncpg

### 外部サービス / ツール
- VOICEVOX エンジン (Docker イメージ: `voicevox/voicevox_engine:cpu-ubuntu20.04-latest`)
- PostgreSQL 15 (Docker イメージ: `postgres:15`)
- FFmpeg (Discord の音声再生に必要)

## セットアップ
1) `.env.template` を参考に `.env` を用意する
2) Docker を起動し、`docker-compose up -d` で VOICEVOX と PostgreSQL を起動する
3) Python パッケージをインストールする

```bash
pip install discord.py python-dotenv aiohttp aiofiles asyncpg
```

## 機能
- [x] 文字の音声読み上げ
- [x] 読み上げキャラクターの変更
- [x] 読み上げ速度の変更
- [x] 読み上げピッチの変更
- [x] URLの省略読み上げ
- [x] コードブロックの省略読み上げ
- [x] 長文の省略読み上げ
- [ ] グローバル辞書
- [ ] サーバーごとの辞書
- [x] 添付ファイルの通知
