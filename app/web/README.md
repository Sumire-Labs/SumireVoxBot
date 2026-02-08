# SumireVoxBot 🌸

SumireVoxBotは、VOICEVOXを使用したDiscord読み上げBotです。
Dockerを使用して簡単にセットアップでき、複数のBotインスタンスを同時に実行することも可能です。

## ✨ 主な機能

- **読み上げ機能**: ボイスチャンネル内のテキストをVOICEVOXの豊富な音声で読み上げます。
- **マルチデバイス対応**: 複数のBotを個別の設定で動作させることが可能です。
- **ユーザー設定**: 各ユーザーがお好みの話者、速度、ピッチをカスタマイズできます。
- **辞書機能**: サーバーごとに読み上げ辞書を登録・管理できます。
- **自動入退出**: ユーザーの接続に合わせて自動的にボイスチャンネルに参加・退出する設定が可能です。

## 🚀 セットアップ手順

### 前提条件
- [Docker](https://www.docker.com/) および [Git](https://git-scm.com/) がインストールされていること。
- Discord Botのトークンを取得済みであること（[Discord Developer Portal](https://discord.com/developers/applications)）。

### 簡単セットアップ (推奨)

Windowsの場合は PowerShell スクリプト、Linux/macOSの場合は Shell スクリプトを使用して、対話形式でセットアップできます。

#### Windows (PowerShell)
```powershell
./setup.ps1
```

#### Linux / macOS
```bash
chmod +x setup.sh
./setup.sh
```

これらのスクリプトは以下の処理を自動で行います：
1. `docker-compose.yml` の生成
2. `.env` ファイルの作成（トークンの入力が必要）
3. 必要なディレクトリの作成
4. Dockerコンテナの起動

### 手動セットアップ

1. リポジトリをクローンします。
2. `.env.template` を `.env` にコピーし、`DISCORD_TOKEN` を設定します。
3. `docker-compose up -d` を実行します。

## 🎮 使用方法

コマンドのプレフィックスは `/` (スラッシュコマンド) です。

### 音声関連コマンド
- `/join`: 実行者が参加しているボイスチャンネルに参加します。
- `/leave`: ボイスチャンネルから退出します。
- `/set_voice`: 自分の使用する話者、速度、ピッチを設定します。
- `/config`: 現在のサーバー設定やユーザー設定を確認します。

### 辞書関連コマンド
- `/add_word`: 新しい単語とその読みを辞書に追加します。
- `/remove_word`: 辞書から単語を削除します。
- `/dictionary`: 現在登録されている辞書一覧を表示します。

### その他
- `/ping`: Botの応答速度を確認します。

## ⚙️ 環境変数

`.env` ファイルで以下の設定が可能です。

| 変数名 | 説明 | デフォルト値 |
| :--- | :--- | :--- |
| `DISCORD_TOKEN` | Discord Botのトークン | (必須) |
| `COMMANDS_SYNC` | 起動時にコマンドを同期するか | `true` |
| `VOICEVOX_HOST` | VOICEVOXエンジンのホスト名 | `voicevox_engine` (Docker内) |
| `VOICEVOX_PORT` | VOICEVOXエンジンのポート番号 | `50021` |
| `POSTGRES_USER` | データベースのユーザー名 | `user` |
| `POSTGRES_PASSWORD` | データベースのパスワード | `password` |
| `POSTGRES_DB` | データベース名 | `sumire_vox` |

## 🛠️ 開発者向け

### コマンドの同期
開発者（Botのオーナー）は `/sync` コマンドを使用して、Cogのリロードとコマンドのグローバル同期を実行できます。

## 📄 ライセンス

このプロジェクトは [LICENSE](LICENSE.md) ファイルに記載されているライセンスの下で公開されています。

---
Powered by [VOICEVOX](https://voicevox.hiroshiba.jp/)
