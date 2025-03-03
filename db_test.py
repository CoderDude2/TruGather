from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from typing import Generator
import sqlite3
import math
import time
import re
import os
import glob

prg_regex = re.compile(r"(\d{4,})([A-Za-z.]+)")
asc_folder_regex = re.compile(r"\d+.\d+_ASC_\((\d+)\)")
folder_regex = re.compile(r"(\d+) ?\((\d+)?\) ?([A-Za-z\+ ]+)?")


BASE_DIR: Path = Path(__file__).resolve().parent

DB_FILE: Path = BASE_DIR / "data.db"


class ErrorType(Enum):
    INVALID_NAME = 1
    PART_LENGTH = 2
    INTERNAL_NAME = 3
    MISSING_UG_VALUE = 4
    MISSING_SUBPROGRAM = 5


@dataclass
class NCFile:
    file_path: Path
    file_name: str
    modified_time: float


@dataclass
class NCError:
    error_type: ErrorType
    error_msg: str | None = None


class FileDB:
    def __init__(self) -> None:
        self.con: sqlite3.Connection = sqlite3.connect(DB_FILE)
        self.cur: sqlite3.Cursor = self.con.cursor()
        self.init_db()

    def init_db(self) -> None:
        self.cur.execute(
            (
                "CREATE TABLE "
                "IF NOT EXISTS nc_files ("
                "nc_file_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "nc_file_path TEXT NOT NULL UNIQUE,"
                "nc_file_name TEXT NOT NULL,"
                "nc_file_modified_time INTEGER NOT NULL)"
            )
        )

        self.cur.execute(
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

    def add_nc_file(self, nc_file: NCFile):
        self.cur.execute(
            "INSERT OR IGNORE INTO nc_files (nc_file_path, nc_file_name, nc_file_modified_time) VALUES (?, ?, ?)",
            (
                str(nc_file.file_path.resolve()),
                nc_file.file_name,
                nc_file.file_path.stat().st_mtime,
            ),
        )
        self.con.commit()

    def delete_nc_file(self, nc_file: NCFile):
        nc_file_id = self.get_file_id(nc_file)

        self.cur.execute("DELETE from errors WHERE nc_file_id = ?", (nc_file_id,))

        self.cur.execute("DELETE FROM nc_files WHERE nc_file_id = ?", (nc_file_id,))
        self.con.commit()

    def update_nc_file_time(self, nc_file: NCFile):
        nc_file_id = self.get_file_id(nc_file)
        print(nc_file_id)
        self.cur.execute(
            "UPDATE nc_files SET nc_file_modified_time = ? WHERE nc_file_id = ?",
            (
                nc_file.file_path.stat().st_mtime,
                nc_file_id,
            ),
        )
        self.con.commit()

    def add_errors(self, nc_file: NCFile, nc_errors: tuple[NCError, ...]) -> None:
        file_id: int | None = self.get_file_id(nc_file)

        if file_id and nc_errors:
            nc_errors_list = [
                (e.error_type.value, e.error_msg, file_id) for e in nc_errors
            ]
            self.cur.executemany(
                "INSERT OR IGNORE INTO errors (error_type, error_msg, nc_file_id) VALUES (?, ?, ?)",
                nc_errors_list,
            )
            self.con.commit()

    def delete_error(self, nc_file: NCFile, nc_error: NCError):
        file_id = self.get_file_id(nc_file)

        self.cur.execute(
            "DELETE FROM errors "
            "WHERE nc_file_id = ? "
            "AND error_type = ? "
            "AND error_msg = ?",
            (file_id, nc_error.error_type.value, nc_error.error_msg),
        )
        self.con.commit()

    def get_all_nc_files(self) -> list[NCFile]:
        nc_file_list: list[NCFile] = []

        res = self.cur.execute("SELECT * FROM nc_files")
        for row in res:
            nc_file_list.append(NCFile(Path(row[1]), row[2], row[3]))
        return nc_file_list

    def get_nc_file_by_file_id(self, nc_file_id: int) -> NCFile | None:
        res = self.cur.execute(
            "SELECT * FROM nc_files WHERE nc_file_id = ?", (nc_file_id,)
        ).fetchone()
        if not res:
            return None
        return NCFile(res[1], res[2], res[3])

    def get_all_errors(self) -> list[NCError]:
        error_list: list[NCError] = []
        res = self.cur.execute("SELECT * FROM errors")
        for row in res:
            error_list.append(NCError(ErrorType(row[1]), row[2]))
        return error_list

    def get_errors_by_file_id(self, nc_file_id: int) -> tuple[NCError, ...]:
        nc_errors: list[NCError] = []

        res = self.cur.execute(
            "SELECT * FROM errors WHERE nc_file_id = ?", (nc_file_id,)
        )

        for row in res:
            nc_errors.append(NCError(ErrorType(row[1]), row[2]))

        return tuple(nc_errors)

    def get_errors_for_nc_file(self, nc_file: NCFile) -> tuple[NCError, ...]:
        file_id = self.get_file_id(nc_file)
        return self.get_errors_by_file_id(file_id)

    def get_file_id(self, nc_file: NCFile) -> int | None:
        res = self.cur.execute(
            "SELECT nc_file_id FROM nc_files WHERE nc_file_path = ?",
            (str(nc_file.file_path.resolve()),),
        ).fetchone()
        if not res:
            return None
        return res[0]

    def get_nc_file(self, nc_file: NCFile) -> NCFile | None:
        res = self.cur.execute(
            "SELECT nc_file_path, nc_file_name, nc_file_modified_time FROM nc_files WHERE nc_file_path = ?",
            (str(nc_file.file_path.resolve()),),
        ).fetchone()
        if not res:
            return None
        return NCFile(res[0], res[1], res[2])

    def get_files_by_name(self, nc_file_name: str) -> list[NCFile] | None:
        nc_file_list: list[NCFile] = []
        res = self.cur.execute(
            "SELECT nc_file_path, nc_file_name, nc_file_modified_time FROM nc_files WHERE nc_file_name = ?",
            (nc_file_name,),
        )

        if not res:
            return None

        nc_file_list = [NCFile(row[0], row[1], row[3]) for row in res]

        return nc_file_list

    def close_db(self) -> None:
        self.con.close()


def get_nc_files(nc_file_path: Path) -> Generator[NCFile | None, None, None]:
    for file in nc_file_path.rglob("*.prg"):
        if file.is_file() and file.suffix.lower() == ".prg":
            yield NCFile(file.absolute(), file.name, file.stat().st_mtime)


def check_file(nc_file: NCFile) -> tuple[NCError, ...]:
    errors: list[NCError] = []
    part_length: float = 0
    cut_off: float = 0

    with nc_file.file_path.open("r") as file:
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

    if nc_file.file_path.stem not in first_line:
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

    if not prg_regex.match(nc_file.file_name):
        errors.append(NCError(ErrorType.INVALID_NAME, "Incorrect file name."))

    if nc_file.file_name == "4001.prg" and case_type == "ASC":
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


def main() -> None:
    file_db = FileDB()

    for nc_file in get_nc_files(Path("./nc")):
        if nc_file and not file_db.get_nc_file(nc_file):
            file_db.add_nc_file(nc_file)
            file_db.add_errors(nc_file, check_file(nc_file))

    for nc_file in file_db.get_all_nc_files():
        if not nc_file.file_path.exists():
            file_db.delete_nc_file(nc_file)
            continue

        if nc_file.modified_time != nc_file.file_path.stat().st_mtime:
            nc_errors = file_db.get_errors_for_nc_file(nc_file)
            errors = check_file(nc_file)

            if errors:
                file_db.add_errors(nc_file, errors)

            for nc_error in nc_errors:
                if nc_error not in errors:
                    file_db.delete_error(nc_file, nc_error)

            file_db.update_nc_file_time(nc_file)

    for nc_file in file_db.get_all_nc_files():
        print(nc_file.file_name)
        print(file_db.get_errors_for_nc_file(nc_file))
        print(nc_file.modified_time)
        print()

    # for error in file_db.get_all_errors():
    #     print(error)

    # if nc_file.file_path.stat().st_mtime != nc_file.modified_time:
    #     errors = check_file(nc_file)
    #     nc_errors = file_db.get_errors_for_nc_file(nc_file)

    #     for nc_error in nc_errors:
    #         if nc_error not in errors:
    #             print(nc_error)

    # file_db.update_nc_file_time(nc_file)
    # errors = check_file(nc_file)
    # if errors:
    # file_db.add_errors(nc_file, errors)

    for error in file_db.get_all_errors():
        print(error)

    # nc_file = NCFile(Path("./nc/Ashley/2 (10)/608.prg"), "608.prg")
    # print(file_db.get_errors_for_nc_file(nc_file))

    file_db.close_db()


if __name__ == "__main__":
    main()
