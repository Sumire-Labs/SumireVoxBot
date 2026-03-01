# src/cogs/voice/text_processing/process_mentions.py
def process_mentions(content: str, mentions: list) -> str:
    for mention in mentions:
        content = content.replace(
            f"@{mention.display_name}",
            f"メンション{mention.display_name}"
        )
    return content
