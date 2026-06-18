from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent

def load_prompt(name: str) -> str:
    """加载 prompts 目录下的 .md 文件内容"""
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()
