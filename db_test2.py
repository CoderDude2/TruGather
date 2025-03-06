from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from typing import NamedTuple
import sqlite3
import shutil
import math
import re

prg_regex = re.compile(r"(\d{4,})([A-Za-z.]+)")
asc_folder_regex = re.compile(r"\d+.\d+_ASC_\((\d+)\)")
folder_regex = re.compile(r"(\d+) ?\((\d+)?\) ?([A-Za-z\+ ]+)?")

BASE_DIR: Path = Path(__file__).resolve().parent
NC_FOLDER: Path = BASE_DIR / "nc"
ALL_FOLDER: Path = NC_FOLDER / "ALL"

DB_FILE: Path = BASE_DIR / "data.db"


class NCFile(NamedTuple):
    path: Path
    modified_time: float


class ErrorType(Enum):
    INVALID_NAME = 1
    PART_LENGTH = 2
    INTERNAL_NAME = 3
    MISSING_UG_VALUE = 4
    MISSING_SUBPROGRAM = 5


@dataclass
class NCError:
    error_type: ErrorType
    error_msg: str | None = None


def check_file(file_path: Path) -> tuple[NCError, ...]:
    errors: list[NCError] = []
    part_length: float = 0
    cut_off: float = 0

    with file_path.open("r") as file:
        first_line = file.readline()
        contents = file.readlines()

    if "ASC" in first_line:
        case_type = "ASC"
    elif "T-L" in first_line or "TLCS" in first_line or "TLOC" in first_line:
        case_type = "TLOC"
    elif "AOT14" in first_line:
        case_type = "AOT"
    elif "ATPL" in first_line:
        case_type = "ATPL"
    else:
        case_type = "DS"

    contains_subprogram_0 = False
    contains_subprogram_1 = False
    contains_subprogram_2 = False

    contains_ug_101 = False
    contains_ug_102 = False
    contains_ug_103 = False
    contains_ug_104 = False
    contains_ug_105 = False

    for i, line in enumerate(contents):
        if "$0" in line:
            contains_subprogram_0 = True

        if "$1" in line:
            contains_subprogram_1 = True

        if "$2" in line:
            contains_subprogram_2 = True

        if "#100=" in line:
            if line.split("=")[1].strip() != "":
                part_length = float(line.split("=")[1].strip())

        if "T0100 (CUT-OFF)" in line:
            if case_type == "ATPL":
                cut_off = float(contents[i + 4].split(" ")[2][1:])
            else:
                cut_off = float(contents[i + 2][4:])

        if "#101=" in line:
            contains_ug_101 = True

        if "#102=" in line:
            contains_ug_102 = True

        if "#103=" in line:
            contains_ug_103 = True

        if "#104=" in line:
            contains_ug_104 = True

        if "#105=" in line:
            contains_ug_105 = True

    if file_path.stem not in first_line:
        errors.append(
            NCError(
                ErrorType.INTERNAL_NAME,
                "File name does not match name on first line of file.",
            )
        )

    if not contains_subprogram_0:
        errors.append(NCError(ErrorType.MISSING_SUBPROGRAM, "Missing $0 subprogram."))
    if not contains_subprogram_1:
        errors.append(NCError(ErrorType.MISSING_SUBPROGRAM, "Missing $1 subprogram."))
    if not contains_subprogram_2:
        errors.append(NCError(ErrorType.MISSING_SUBPROGRAM, "Missing $2 subprogram."))

    if round(math.fabs(part_length - cut_off), 4) > 0.015:
        errors.append(
            NCError(ErrorType.PART_LENGTH, "Part-length and cut-off do not match.")
        )

    if not prg_regex.match(file_path.name):
        errors.append(NCError(ErrorType.INVALID_NAME, "Incorrect file name."))

    if file_path.name == "4001.prg" and case_type == "ASC":
        errors.append(
            NCError(ErrorType.INVALID_NAME, "4001 is not a valid name for ASC files.")
        )

    if case_type == "ASC" or case_type == "TLOC" or case_type == "AOT":
        if not contains_ug_101:
            errors.append(NCError(ErrorType.MISSING_UG_VALUE, "Missing #101 value"))
        if not contains_ug_102:
            errors.append(NCError(ErrorType.MISSING_UG_VALUE, "Missing #102 value"))
        if not contains_ug_103:
            errors.append(NCError(ErrorType.MISSING_UG_VALUE, "Missing #103 value"))
        if not contains_ug_104:
            errors.append(NCError(ErrorType.MISSING_UG_VALUE, "Missing #104 value"))
        if not contains_ug_105:
            errors.append(NCError(ErrorType.MISSING_UG_VALUE, "Missing #105 value"))
    return tuple(errors)


def get_nc_files(file_path: Path) -> list[Path]:
    nc_files: list[Path] = []

    for file in file_path.rglob("*.prg", case_sensitive=False):
        if "all" not in str(file.resolve()).lower():
            nc_files.append(file)

    return nc_files


def init_db() -> None:
    with sqlite3.connect(DB_FILE) as con:
        cur: sqlite3.Cursor = con.cursor()

        cur.execute(
            (
                "CREATE TABLE "
                "IF NOT EXISTS nc_files ("
                "nc_file_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "nc_file_path TEXT NOT NULL UNIQUE,"
                "nc_file_name TEXT NOT NULL,"
                "nc_file_modified_time REAL NOT NULL)"
            )
        )

        cur.execute(
            (
                "CREATE TABLE "
                "IF NOT EXISTS gathered_nc_files ("
                "gathered_nc_file_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "gathered_nc_file_path TEXT NOT NULL UNIQUE,"
                "nc_file_id INTEGER NOT NULL,"
                "FOREIGN KEY(nc_file_id) REFERENCES nc_files(nc_file_id))"
            )
        )

        cur.execute(
            (
                "CREATE TABLE "
                "IF NOT EXISTS duplicates ("
                "duplicate_file_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "nc_file_id INTEGER NOT NULL UNIQUE,"
                "FOREIGN KEY(nc_file_id) REFERENCES nc_files(nc_file_id))"
            )
        )

        cur.execute(
            (
                "CREATE TABLE "
                "IF NOT EXISTS errors ("
                "error_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "error_type INTEGER NOT NULL,"
                "error_msg TEXT NOT NULL,"
                "nc_file_id INTEGER NOT NULL,"
                "UNIQUE(error_type, error_msg, nc_file_id)"
                "FOREIGN KEY(nc_file_id) REFERENCES nc_files(nc_file_id))"
            )
        )


def add_to_database(file_path: Path) -> None:
    try:
        with sqlite3.connect(DB_FILE) as con:
            cur: sqlite3.Cursor = con.cursor()
            cur.execute(
                "INSERT INTO nc_files (nc_file_path, nc_file_name, nc_file_modified_time) VALUES (?, ?, ?)",
                (str(file_path.resolve()), file_path.name, file_path.stat().st_mtime),
            )
            if cur.lastrowid:
                file_id: int = cur.lastrowid
                cur.executemany(
                    "INSERT OR IGNORE INTO errors (error_type, error_msg, nc_file_id) VALUES (?, ?, ?)",
                    [
                        (e.error_type.value, e.error_msg, file_id)
                        for e in check_file(file_path)
                    ],
                )

                results = cur.execute(
                    "SELECT nc_file_path FROM nc_files WHERE nc_file_name = ? AND nc_file_id != ?",
                    (file_path.name, file_id),
                )

                if results.fetchone():
                    cur.execute(
                        "INSERT INTO duplicates (nc_file_id) VALUES (?)", (file_id,)
                    )
            print(f"{file_path} added to database")
            con.commit()
    except PermissionError:
        print("File is being used by another process")
        pass


def get_duplicates() -> list[NCFile]:
    with sqlite3.connect(DB_FILE) as con:
        cur: sqlite3.Cursor = con.cursor()
        duplicates = [
            NCFile(Path(row[0]), row[1])
            for row in cur.execute(
                "SELECT nc_file_path, nc_file_modified_time FROM nc_files JOIN duplicates USING (nc_file_id)"
            ).fetchall()
        ]
        return duplicates


def is_duplicate(nc_file: NCFile) -> bool:
    file_id = get_file_id(nc_file)
    with sqlite3.connect(DB_FILE) as con:
        cur: sqlite3.Cursor = con.cursor()

        res = cur.execute(
            "SELECT nc_file_id FROM duplicates WHERE nc_file_id = ?", (file_id,)
        )

        if res.fetchone():
            return True
        return False


def delete_nc_file(nc_file: NCFile) -> None:
    file_id: int | None = get_file_id(nc_file)
    gathered_path: Path = ALL_FOLDER / nc_file.path.name

    if not file_id:
        return

    if gathered_path.exists():
        gathered_path.unlink()

    with sqlite3.connect(DB_FILE) as con:
        cur: sqlite3.Cursor = con.cursor()
        cur.execute("DELETE FROM errors WHERE nc_file_id = ?", (file_id,))
        cur.execute("DELETE FROM gathered_nc_files WHERE nc_file_id = ?", (file_id,))
        cur.execute("DELETE FROM nc_files WHERE nc_file_id = ?", (file_id,))
        print(f"{nc_file.path} removed from database")

        duplicate_ids = [
            row[0]
            for row in cur.execute(
                "SELECT nc_file_id FROM nc_files JOIN duplicates USING(nc_file_id) WHERE nc_file_name = ?",
                (nc_file.path.name,),
            ).fetchall()
        ]

        if not duplicate_ids:
            return

        for duplicate_id in duplicate_ids:
            errors = cur.execute(
                "SELECT error_type, error_msg FROM errors WHERE nc_file_id = ?",
                (duplicate_id,),
            )
            if not errors.fetchone():
                cur.execute(
                    "DELETE FROM duplicates WHERE nc_file_id = ?", (duplicate_id,)
                )
                print("Removed file without errors")
                return
        print("Removed file with errors")
        cur.execute("DELETE FROM duplicates WHERE nc_file_id = ?", (duplicate_ids[0],))


def is_gathered(nc_file: NCFile) -> bool:
    file_id: int | None = get_file_id(nc_file)

    with sqlite3.connect(DB_FILE) as con:
        cur: sqlite3.Cursor = con.cursor()

        res = cur.execute(
            "SELECT nc_file_id FROM gathered_nc_files WHERE nc_file_id = ?", (file_id,)
        ).fetchone()

        if not res:
            return False

        return True


def gather_nc_file(nc_file: NCFile) -> None:
    file_id: int | None = get_file_id(nc_file)
    gathered_path: Path = ALL_FOLDER / nc_file.path.name

    if not file_id:
        return

    try:
        with sqlite3.connect(DB_FILE) as con:
            cur: sqlite3.Cursor = con.cursor()
            cur.execute(
                "INSERT INTO gathered_nc_files (gathered_nc_file_path, nc_file_id) VALUES (?, ?)",
                (str(gathered_path.resolve()), file_id),
            )
        print(f"{nc_file.path} gathered")
    except sqlite3.IntegrityError:
        print(f"{nc_file.path} is a duplicate")


def remove_nc_from_gather(nc_file: NCFile) -> None:
    file_id: int | None = get_file_id(nc_file)

    if not file_id:
        return

    gathered_path: Path = ALL_FOLDER / nc_file.path.name

    if gathered_path.exists():
        gathered_path.unlink()

    with sqlite3.connect(DB_FILE) as con:
        cur: sqlite3.Cursor = con.cursor()
        cur.execute("DELETE FROM gathered_nc_files WHERE nc_file_id = ?", (file_id,))
        con.commit()


def update_nc_file(nc_file: NCFile) -> None:
    file_id: int | None = get_file_id(nc_file)

    if not file_id:
        return

    nc_errors: tuple[NCError, ...] = get_errors(nc_file)
    errors: tuple[NCError, ...] = check_file(nc_file.path)

    errors_to_remove: list[NCError] = []
    errors_to_add: list[NCError] = []

    for error in errors:
        if error not in nc_errors:
            errors_to_add.append(error)

    for nc_error in nc_errors:
        if nc_error not in errors:
            errors_to_remove.append(nc_error)

    with sqlite3.connect(DB_FILE) as con:
        cur: sqlite3.Cursor = con.cursor()

        cur.executemany(
            "INSERT OR IGNORE INTO errors (error_type, error_msg, nc_file_id) VALUES (?, ?, ?)",
            [(e.error_type.value, e.error_msg, file_id) for e in errors_to_add],
        )

        cur.executemany(
            "DELETE FROM errors WHERE error_type = ? AND error_msg = ? AND nc_file_id = ?",
            [(e.error_type.value, e.error_msg, file_id) for e in errors_to_remove],
        )

        cur.execute(
            "UPDATE nc_files SET nc_file_modified_time = ? WHERE nc_file_id = ?",
            (
                nc_file.path.stat().st_mtime,
                file_id,
            ),
        )
        con.commit()


def is_tracked(file_path: Path) -> bool:
    with sqlite3.connect(DB_FILE) as con:
        cur: sqlite3.Cursor = con.cursor()

        res = cur.execute(
            "SELECT nc_file_id FROM nc_files WHERE nc_file_path = ?", (str(file_path),)
        )
        if not res.fetchone():
            return False
        return True


def get_all_nc_files() -> list[NCFile]:
    with sqlite3.connect(DB_FILE) as con:
        cur: sqlite3.Cursor = con.cursor()

        nc_files: list[NCFile] = []

        results = cur.execute(
            "SELECT nc_file_path, nc_file_modified_time FROM nc_files"
        )

        for row in results.fetchall():
            nc_files.append(NCFile(Path(row[0]), row[1]))
        return nc_files


def get_file_id(nc_file: NCFile) -> int | None:
    with sqlite3.connect(DB_FILE) as con:
        cur: sqlite3.Cursor = con.cursor()
        file_id = cur.execute(
            "SELECT nc_file_id FROM nc_files WHERE nc_file_path = ?",
            (str(nc_file.path.resolve()),),
        ).fetchone()

        if not file_id:
            return None

        return file_id[0]


def get_errors(nc_file: NCFile) -> tuple[NCError, ...]:
    file_id = get_file_id(nc_file)
    errors: list[NCError] = []
    with sqlite3.connect(DB_FILE) as con:
        cur: sqlite3.Cursor = con.cursor()

        if file_id:
            results = cur.execute(
                "SELECT error_type, error_msg FROM errors WHERE nc_file_id = ?",
                (file_id,),
            )
            for row in results:
                errors.append(NCError(ErrorType(row[0]), row[1]))

    return tuple(errors)


def is_modified(nc_file: NCFile) -> bool:
    file_id: int | None = get_file_id(nc_file)
    with sqlite3.connect(DB_FILE) as con:
        cur: sqlite3.Cursor = con.cursor()
        res = cur.execute(
            "SELECT nc_file_modified_time FROM nc_files WHERE nc_file_id = ?",
            (file_id,),
        ).fetchone()
        return nc_file.path.stat().st_mtime != res[0]


def get_modified_files() -> list[NCFile]:
    modified_nc_files: list[NCFile] = []

    for nc_file in get_all_nc_files():
        if nc_file.path.stat().st_mtime != nc_file.modified_time:
            modified_nc_files.append(nc_file)

    return modified_nc_files


def main() -> None:
    init_db()
    run = True
    while run:
        try:
            for file in get_nc_files(NC_FOLDER):
                if not is_tracked(file):
                    add_to_database(file)

            for nc_file in get_all_nc_files():
                if not nc_file.path.exists():
                    delete_nc_file(nc_file)
                    continue

                if is_modified(nc_file):
                    print(nc_file, "is modified")
                    update_nc_file(nc_file)

                if is_duplicate(nc_file):
                    continue

                if not is_gathered(nc_file) and not get_errors(nc_file):
                    gather_nc_file(nc_file)

                if is_gathered(nc_file) and get_errors(nc_file):
                    remove_nc_from_gather(nc_file)

                if (
                    is_gathered(nc_file)
                    and not (ALL_FOLDER / nc_file.path.name).exists()
                ):
                    shutil.copy2(
                        nc_file.path.resolve(),
                        (ALL_FOLDER / nc_file.path.name).resolve(),
                    )
        except KeyboardInterrupt:
            run = False
        except FileNotFoundError:
            if not ALL_FOLDER.exists():
                ALL_FOLDER.mkdir()


if __name__ == "__main__":
    main()

    with sqlite3.connect(DB_FILE) as con:
        cur: sqlite3.Cursor = con.cursor()

        res = cur.execute(
            "SELECT nc_file_path FROM nc_files JOIN duplicates USING(nc_file_id)"
        )
        print("Duplicates:")
        for duplicate in get_duplicates():
            print(duplicate)
