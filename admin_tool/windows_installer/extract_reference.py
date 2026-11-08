"""Extract a hash-verified reference MSI without installing or registering it."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def extract(msi_path: Path, output: Path) -> None:
    output = output.resolve()
    output.relative_to((ROOT / "temp").resolve())
    output.mkdir(parents=True, exist_ok=False)
    api = ctypes.WinDLL("msi", use_last_error=True)
    handle = wintypes.UINT
    api.MsiOpenDatabaseW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(handle)]
    api.MsiDatabaseOpenViewW.argtypes = [handle, wintypes.LPCWSTR, ctypes.POINTER(handle)]
    api.MsiViewExecute.argtypes = [handle, handle]
    api.MsiViewFetch.argtypes = [handle, ctypes.POINTER(handle)]
    api.MsiRecordGetStringW.argtypes = [handle, wintypes.UINT, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.MsiRecordReadStream.argtypes = [handle, wintypes.UINT, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    api.MsiCloseHandle.argtypes = [handle]

    def check(result: int) -> None:
        if result:
            raise OSError(result, ctypes.FormatError(result))

    database = handle()
    check(api.MsiOpenDatabaseW(str(msi_path.resolve()), None, ctypes.byref(database)))

    def rows(query: str, fields: int):
        view = handle()
        check(api.MsiDatabaseOpenViewW(database, query, ctypes.byref(view)))
        try:
            check(api.MsiViewExecute(view, 0))
            while True:
                record = handle()
                result = api.MsiViewFetch(view, ctypes.byref(record))
                if result == 259:  # ERROR_NO_MORE_ITEMS
                    break
                check(result)
                try:
                    values = []
                    for index in range(1, fields + 1):
                        size = wintypes.DWORD(4096)
                        value = ctypes.create_unicode_buffer(size.value)
                        check(api.MsiRecordGetStringW(record, index, value, ctypes.byref(size)))
                        values.append(value.value)
                    yield values
                finally:
                    api.MsiCloseHandle(record)
        finally:
            api.MsiCloseHandle(view)

    try:
        directories = {key: (parent, name) for key, parent, name in rows("SELECT `Directory`, `Directory_Parent`, `DefaultDir` FROM `Directory`", 3)}
        components = dict(rows("SELECT `Component`, `Directory_` FROM `Component`", 2))
        files = list(rows("SELECT `File`, `Component_`, `FileName` FROM `File`", 3))
        cabinet = output.parent / (output.name + ".cab")
        view, record = handle(), handle()
        check(api.MsiDatabaseOpenViewW(database, "SELECT `Data` FROM `_Streams` WHERE `Name` = 'payload.cab'", ctypes.byref(view)))
        try:
            check(api.MsiViewExecute(view, 0))
            check(api.MsiViewFetch(view, ctypes.byref(record)))
            buffer = ctypes.create_string_buffer(1024 * 1024)
            with cabinet.open("xb") as stream:
                while True:
                    size = wintypes.DWORD(len(buffer))
                    check(api.MsiRecordReadStream(record, 1, buffer, ctypes.byref(size)))
                    if not size.value:
                        break
                    stream.write(buffer.raw[:size.value])
        finally:
            if record.value:
                api.MsiCloseHandle(record)
            api.MsiCloseHandle(view)
    finally:
        api.MsiCloseHandle(database)

    expanded = output.parent / (output.name + "-cabinet")
    expanded.mkdir(exist_ok=False)
    subprocess.run(["expand.exe", "-F:*", str(cabinet), str(expanded)], check=True, capture_output=True)

    def directory_path(key: str) -> Path:
        if key == "INSTALLDIR":
            return output
        parent, name = directories[key]
        if not parent:
            raise ValueError(f"File directory is outside INSTALLDIR: {key}")
        name = name.split(":", 1)[0].split("|")[-1]
        path = directory_path(parent) / name
        path.resolve().relative_to(output)
        return path

    for alias, component, name in files:
        source = expanded / alias
        source.resolve().relative_to(expanded)
        destination = directory_path(components[component]) / name.split("|")[-1]
        destination.resolve().relative_to(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
    print(f"Extracted {len(files)} reference files to {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--msi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    extract(args.msi, args.output)
