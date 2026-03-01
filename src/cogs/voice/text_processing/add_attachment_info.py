# src/cogs/voice/text_processing/add_attachment_info.py
def add_attachment_info(content: str, attachment_count: int) -> str:
    if attachment_count > 0:
        content += f"、{attachment_count}件の添付ファイル"
    return content
