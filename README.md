# SumireVoxBot

## 概要
discord.py と VOICEVOX エンジンを用いた読み上げBotです。辞書管理用のWeb管理画面と、サーバー別辞書をPostgreSQLで管理します。

## 必要環境
### ランタイム
- Python 3.14.2 (動作確認)
- FFmpeg (Discord の音声再生に必要)

### 外部サービス / ツール
- VOICEVOX エンジン (Docker イメージ: `voicevox/voicevox_engine:cpu-ubuntu20.04-latest`)
- PostgreSQL 15 (Docker イメージ: `postgres:15`)

## 環境変数
`.env.template` を参考に `.env` を用意してください。

- `DISCORD_TOKEN`: Discord Bot トークン
- `VOICEVOX_HOST` / `VOICEVOX_PORT`: VOICEVOX エンジン
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_HOST` / `POSTGRES_PORT`: PostgreSQL
- `ADMIN_USER` / `ADMIN_PASSWORD`: Web管理画面のBasic認証

## セットアップ
1) `.env.template` を参考に `.env` を用意する
2) Docker を起動し、`docker-compose up -d` で VOICEVOX と PostgreSQL を起動する
3) 依存パッケージをインストールする
4) Bot を起動する

```bash
pip install -r requirements.txt
python main.py
```

## Web管理画面
- URL: `http://localhost:8080`
- Basic認証: `.env` の `ADMIN_USER` / `ADMIN_PASSWORD`
- VOICEVOX のユーザー辞書を追加・削除できます

## 機能
- [x] 文字の音声読み上げ
- [x] 読み上げキャラクターの変更
- [x] 読み上げ速度の変更
- [x] 読み上げピッチの変更
- [x] URLの省略読み上げ
- [x] コードブロックの省略読み上げ
- [x] 長文の省略読み上げ
- [x] グローバル辞書
- [x] サーバーごとの辞書
- [x] 添付ファイルの通知
- [x] 辞書の参照
- [x] 辞書の適応読み上げ
