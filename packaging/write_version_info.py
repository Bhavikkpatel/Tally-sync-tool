"""Generate PyInstaller Windows version-info resource for a product build."""
from __future__ import annotations

import argparse
from pathlib import Path


PRODUCTS = {
    "pluschwood": {
        "company": "Pluschwood",
        "product": "Pluschwood Tally Sync",
        "internal": "PluschwoodTallySync",
        "copyright": "Copyright (c) Pluschwood",
    },
    "autosync": {
        "company": "AutoSync",
        "product": "AutoSync Tally Sync",
        "internal": "AutoSyncTallySync",
        "copyright": "Copyright (c) AutoSync",
    },
}


def parse_version(text: str) -> tuple[int, int, int, int]:
    parts = [int(part) for part in text.strip().lstrip("vV").split(".") if part.isdigit()]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])  # type: ignore[return-value]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", choices=sorted(PRODUCTS), required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    meta = PRODUCTS[args.product]
    major, minor, patch, build = parse_version(args.version)
    version_str = f"{major}.{minor}.{patch}.{build}"
    filevers = (major, minor, patch, build)
    prodvers = filevers

    content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={filevers!r},
    prodvers={prodvers!r},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('CompanyName', {meta['company']!r}),
            StringStruct('FileDescription', {meta['product']!r}),
            StringStruct('FileVersion', {version_str!r}),
            StringStruct('InternalName', {meta['internal']!r}),
            StringStruct('LegalCopyright', {meta['copyright']!r}),
            StringStruct('OriginalFilename', {meta['internal'] + '.exe'!r}),
            StringStruct('ProductName', {meta['product']!r}),
            StringStruct('ProductVersion', {version_str!r}),
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
