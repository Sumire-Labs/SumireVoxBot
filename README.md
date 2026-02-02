# SumireVox 🌸

SumireVoxは、Discordのボイスチャネルでテキストチャットを読み上げる、VOICEVOXを利用したDiscord Botです。

## 🚀 主な機能

- **テキスト読み上げ**: 指定したチャンネルのメッセージをVOICEVOXで読み上げます。
- **音声カスタマイズ**: 読み上げキャラクター、速度、ピッチをユーザーごとに設定可能です。
- **辞書機能**: 読み間違いを修正するための単語登録・削除機能。
- **自動入退出**: ユーザーがVCに入った際の自動接続や、誰もいなくなった際の自動切断に対応。
- **スラッシュコマンド**: 最新のDiscord機能であるスラッシュコマンドに完全対応。

## 🛠 動作環境

- Docker / Docker Compose
- Discord Bot Token
- VOICEVOX Engine (Dockerで同梱)
- PostgreSQL (Dockerで同梱)

## 📦 セットアップ

### 1. リポジトリのクローン

```bash
git clone https://github.com/your-username/SumireVox.git
cd SumireVox
```

### 2. 環境変数の設定

`.env` ファイルを作成し、以下の項目を設定してください。

```env
DISCORD_TOKEN=your_discord_bot_token_here
ADMIN_USER=your_discord_user_id

# データベース設定 (docker-compose.ymlと合わせる)
POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_DB=sumire_vox
POSTGRES_HOST=db
POSTGRES_PORT=5432

# VOICEVOX設定
VOICEVOX_HOST=voicevox_engine
VOICEVOX_PORT=50021
```

### 3. 起動

Docker Composeを使用して起動します。

```bash
docker-compose up -d --build
```

## 🎮 コマンド一覧

| コマンド | 説明 |
| :--- | :--- |
| `/join` | ボイスチャンネルに接続し、そのテキストチャンネルの読み上げを開始します。 |
| `/leave` | ボイスチャンネルから切断します。 |
| `/set_voice` | 自分の読み上げキャラクター、速度、ピッチを設定します。 |
| `/add_word` | 辞書に新しい単語と読み方を登録します。 |
| `/remove_word` | 辞書から単語を削除します。 |
| `/dictionary` | 登録されている単語一覧を表示します。 |
| `/config` | 現在の設定（音声、通知設定など）を確認します。 |
| `/ping` | Botの応答速度（レイテンシ）を確認します。 |
| `/sync` | (管理者用) スラッシュコマンドの同期とCogのリロードを行います。 |

## 📝 ライセンス

このプロジェクトは [MIT License](LICENSE) の下で公開されています。

## 🙏 謝辞

- [VOICEVOX](https://voicevox.hiroshiba.jp/): 無料で使える中品質なテキスト読み上げソフトウェア
- [discord.py](https://github.com/Rapptz/discord.py): Python用のDiscord APIラッパー
