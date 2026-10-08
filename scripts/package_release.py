"""Export only source/config/docs/synthetic examples; never copy Git history or local data."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOP = {"README.md", "requirements.txt", "environment.yml", "pyproject.toml", ".gitignore", ".gitattributes", ".env.example", "CONTRIBUTING.md", "LICENSE", "LICENSE.md"}
DIRECTORIES = {"src", "scripts", "configs", "tests", "examples", "docs", ".github"}
SUFFIXES = {".py", ".md", ".json", ".jsonl", ".csv", ".txt", ".toml", ".yml", ".yaml"}


def selected_files():
    files = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if not path.is_file() or path.is_symlink():
            continue
        if relative.as_posix() in TOP or (
            relative.parts[0] in DIRECTORIES and path.suffix in SUFFIXES
            and "__pycache__" not in relative.parts
            and relative.parts[:2] != ("docs", "history")
        ):
            files.append(path)
    return sorted(files)


def main():
    files = selected_files()
    secrets = []
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                value = value.strip().strip('"\'')
                if any(word in key.upper() for word in ("KEY", "TOKEN", "PASSWORD", "SECRET")) and len(value) >= 12:
                    secrets.append(value)
    for path in files:
        content = path.read_text(encoding="utf-8-sig")
        if any(secret in content for secret in secrets) or re.search(r"(?:sk-[A-Za-z0-9]{24,}|gh[pousr]_[A-Za-z0-9]{24,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)", content):
            raise ValueError(f"Possible credential in {path.relative_to(ROOT)}; export stopped")
    output = ROOT / "archive/release"
    output.mkdir(parents=True, exist_ok=True)
    manifest = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    with zipfile.ZipFile(output / "SEC-RAG-source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
        archive.writestr("release_manifest.json", json.dumps(manifest, indent=2))
    (output / "release_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Prepared {len(files)} files: {output / 'SEC-RAG-source.zip'}")
    print("No .env, Git history, raw data, real guideline documents, experiment outputs or archive included.")


if __name__ == "__main__":
    main()
