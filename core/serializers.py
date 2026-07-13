from typing import Any


def extract_text(content: Any) -> str:
    """从 LLM 响应内容中提取纯文本。

    Args:
        content: 字符串、内容块列表或其他可转为字符串的对象。

    Returns:
        合并后的纯文本内容。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)
