# SumireVoxBot 🌸

SumireVoxBot は、Discord のボイスチャットでテキストを読み上げる Discord Bot です。
VOICEVOX エンジンを利用して、高品質な音声合成による読み上げ機能を提供します。

## 🚀 特徴
- **VOICEVOX 連携**: 複数のキャラクター音声での読み上げ。
- **自動接続/切断**: 設定に基づいた VC への自動入室および空室時の自動退室。
- **マルチインスタンス対応**: Docker を使用して複数の Bot インスタンスを同時に実行可能。
- **辞書機能**: カスタム単語の登録が可能。

## 🛠 技術スタック
- **言語**: Python 3.10+
- **フレームワーク**: 
  - [discord.py](https://github.com/Rapptz/discord.py) (Discord API への接続)
- **データベース**: PostgreSQL (設定およびユーザーデータの保存)
- **音声合成**: [VOICEVOX](https://voicevox.hiroshiba.jp/)
- **インフラ**: Docker / Docker Compose

## 📋 必要条件
- Docker および Docker Compose
- Discord Bot トークン
- FFmpeg (ローカル実行の場合)

## ⚙️ セットアップと実行

### 1. リポジトリのクローン
```bash
git clone https://github.com/your-repo/SumireVoxBot.git
cd SumireVoxBot
```

### 2. 環境変数の設定
`.env.template` をコピーして `.env.common` および各 Bot 用の環境変数ファイル（`.env.bot1` など）を作成します。

```bash
cp .env.template .env.common
# 必要に応じて各 Bot 用のファイルを作成
cp .env.template .env.bot1
```

`.env` ファイルに Discord トークンやデータベース情報を入力してください。

### 3. Docker Compose による起動
```bash
docker-compose up -d --build
```

これにより、以下のサービスが起動します：
- `voicevox_engine`: 音声合成エンジン
- `db`: PostgreSQL データベース
- `bot1` (～ `bot3`): Discord Bot インスタンス

## 📝 スクリプトとエントリポイント
- `main.py`: Bot のメインエントリポイント。
- `docker-compose.yml`: プロジェクト全体のオーケストレーション。

## 🔑 環境変数
`.env` ファイルで使用される主な変数：

| 変数名 | 説明 | デフォルト値 |
|--------|------|--------------|
| `DISCORD_TOKEN` | Discord Bot のトークン | (必須) |
| `VOICEVOX_HOST` | VOICEVOX エンジンのホスト名 | `voicevox_engine` |
| `VOICEVOX_PORT` | VOICEVOX エンジンのポート | `50021` |
| `POSTGRES_USER` | DB ユーザー名 | `user` |
| `POSTGRES_PASSWORD` | DB パスワード | `password` |
| `POSTGRES_DB` | DB 名 | `sumire_vox` |
| `DEV_GUILD_ID` | 開発用サーバーの ID (コマンド同期用) | `0` |

## 🎮 主なコマンド
スラッシュコマンド（`/`）を使用します。

- `/join`: 実行者が参加しているボイスチャンネルに Bot を接続します。
- `/leave`: ボイスチャンネルから Bot を切断します。
- `/set_voice`: 読み上げに使用する声（スピーカーID）、速度、ピッチを設定します。
- `/dictionary`: サーバー固有の辞書を表示・編集します。
- `/config`: Bot の設定（自動接続、通知など）を確認・変更します。
- `/ping`: Bot の応答速度を確認します。

## 📁 プロジェクト構造
```text
SumireVoxBot/
├── main.py              # Bot のエントリポイント
├── Dockerfile           # Bot の Docker イメージ定義
├── docker-compose.yml   # サービス定義
├── requirements.txt     # Python 依存関係
├── src/
│   ├── cogs/            # Discord Bot の機能モジュール（読み上げ、コマンド等）
│   ├── core/            # コアロジック（VOICEVOXクライアント、DB接続等）
│   ├── queries/         # SQL クエリ
│   └── utils/           # ユーティリティ（ロガー、ビュー等）
├── logs/                # ログファイル
└── voicevox_config/     # VOICEVOX の設定保存領域
```

## 📄 ライセンス
このプロジェクトは [GNU Lesser General Public License v3.0](LICENSE.md) のもとで公開されています。
