from pydantic import BaseModel, Field
from typing import Dict


class GuildSettings(BaseModel):
    """
    サーバー（ギルド）ごとの設定を管理するモデル
    JSONBから変換したり、デフォルト値を一括管理したりします。
    """
    # 自動接続
    auto_join: bool = Field(default=False, description="ボイスチャンネルへの自動接続")

    # 自動接続設定
    # {"bot_id": {"voice": "channel_id", "text": "channel_id"},...}
    auto_join_config: Dict[str, Dict[str, int]] = Field(default_factory=dict)

    # 文字数制限
    max_chars: int = Field(default=50, ge=10, le=500, description="読み上げ文字数の上限")

    # 入退出の読み上げ
    read_vc_status: bool = Field(default=False, description="ユーザーの入退出を通知")

    # メンション読み上げ
    read_mention: bool = Field(default=True, description="メンションを名前で読み上げるか")

    # 絵文字読み上げ
    read_emoji: bool = Field(default=True, description="絵文字を読み上げるか")

    # さん付け
    add_suffix: bool = Field(default=False, description="ユーザー名の後に『さん』を付ける")
    
    # ローマ字読み
    read_romaji: bool = Field(default=False, description="ローマ字を読み上げるか")

    # 添付ファイル読み上げ
    read_attachments: bool = Field(default=True, description="添付ファイルの存在を読み上げるか")

    # コードブロックを省略
    skip_code_blocks: bool = Field(default=True, description="コードブロックを省略する")

    # URLを省略
    skip_urls: bool = Field(default=True, description="URLを省略する")

class GuildDict(BaseModel):
    # 単語
    word: str = Field(description="元の読み")

    # 読み
    reading: str = Field(description="新しい読み")
