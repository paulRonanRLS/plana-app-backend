"""Prompt loading utilities with caching."""
from pathlib import Path

# Cache for loaded prompts (read once per process startup)
_prompt_cache: dict[str, str] = {}


def load_prompt(name: str) -> str:
    """
    Load a prompt file from app/prompts/ by filename.

    Args:
        name: Filename of the prompt (e.g., "recipe_extraction_v1.txt")

    Returns:
        The prompt text as a string

    Raises:
        FileNotFoundError: If the prompt file doesn't exist
        RuntimeError: If there's an error reading the file
    """
    if name in _prompt_cache:
        return _prompt_cache[name]

    prompt_dir = Path(__file__).parent.parent / "prompts"
    prompt_path = prompt_dir / name

    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {name}\n"
            f"Expected location: {prompt_path}\n"
            f"Available prompts: {list(p.name for p in prompt_dir.glob('*.txt')) if prompt_dir.exists() else '(prompts directory does not exist)'}"
        )

    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_text = f.read()
    except Exception as e:
        raise RuntimeError(f"Error reading prompt file {name}: {e}") from e

    _prompt_cache[name] = prompt_text
    return prompt_text


# Pre-load the extraction prompt
EXTRACTION_PROMPT = load_prompt("recipe_extraction_v1.txt")
