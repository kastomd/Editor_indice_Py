from pathlib import Path

def hide_user(path):
    parts = list(Path(path).parts)

    if "Users" in parts:
        i = parts.index("Users")
        if len(parts) > i + 1:
            parts[i + 1] = "<user>"

    return str(Path(*parts))
