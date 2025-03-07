from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from typing import NamedTuple
import datetime
import math
import sqlite3
import shutil
import re


BASE_DIR: Path = Path(__file__).resolve().parent
ERP_DIR: Path = Path(r'\\192.168.1.100\Trubox\####ERP_RM####')

prg_regex: re.Pattern = re.compile(r"(\d{4,})([A-Za-z.]+)")
asc_folder_regex: re.Pattern = re.compile(r"\d+.\d+_ASC_\((\d+)\)")
folder_regex: re.Pattern = re.compile(r"(\d+) ?\((\d+)?\) ?([A-Za-z\+ ]+)?")


def date_as_path(date=None) -> Path:
    if date is None:
        date = datetime.datetime.now().date()
    _day = f"D{'0' + str(date.day) if date.day < 10 else str(date.day)}"
    _month = f"M{'0' + str(date.month) if date.month < 10 else str(date.month)}"
    _year = f"Y{str(date.year)}"
    return Path(_year, _month, _day)


NC_FOLDER: Path = ERP_DIR / date_as_path() / r"1. CAM\3. NC files"
ALL_FOLDER: Path = BASE_DIR / "nc" / "ALL"

DB_FILE: Path = BASE_DIR / "data2.db"


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

    case_type: str = "DS"
    if "ASC" in first_line:
        case_type = "ASC"
    elif "T-L" in first_line or "TLCS" in first_line or "TLOC" in first_line:
        case_type = "TLOC"
    elif "AOT14" in first_line:
        case_type = "AOT"
    elif "ATPL" in first_line:
        case_type = "ATPL"

    contains_subprogram_0: bool = False
    contains_subprogram_1: bool = False
    contains_subprogram_2: bool = False

    contains_ug_101: bool = False
    contains_ug_102: bool = False
    contains_ug_103: bool = False
    contains_ug_104: bool = False
    contains_ug_105: bool = False

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

class FileManager:
    def __init__(self) -> None:
        self.con: sqlite3.Connection = sqlite3.connect(DB_FILE)
        self.cur: sqlite3.Cursor = self.con.cursor()
        self.init_db()

    def init_db(self):
        self.cur.execute(
            (
                "CREATE TABLE "
                "IF NOT EXISTS nc_files ("
                "nc_file_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "nc_file_path TEXT NOT NULL UNIQUE,"
                "nc_file_name TEXT NOT NULL,"
                "nc_file_modified_time REAL NOT NULL)"
            )
        )

        self.cur.execute(
            (
                "CREATE TABLE "
                "IF NOT EXISTS gathered_nc_files ("
                "gathered_nc_file_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "gathered_nc_file_path TEXT NOT NULL UNIQUE,"
                "nc_file_id INTEGER NOT NULL,"
                "FOREIGN KEY(nc_file_id) REFERENCES nc_files(nc_file_id))"
            )
        )

        self.cur.execute(
            (
                "CREATE TABLE "
                "IF NOT EXISTS duplicates ("
                "duplicate_file_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "nc_file_id INTEGER NOT NULL UNIQUE,"
                "FOREIGN KEY(nc_file_id) REFERENCES nc_files(nc_file_id))"
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
    
    def add_to_database(self, file_path: Path) -> None:
        try:
            self.cur.execute(
                "INSERT INTO nc_files (nc_file_path, nc_file_name, nc_file_modified_time) VALUES (?, ?, ?)",
                (str(file_path.resolve()), file_path.name, file_path.stat().st_mtime),
            )
            if self.cur.lastrowid:
                file_id: int = self.cur.lastrowid
                self.cur.executemany(
                    "INSERT OR IGNORE INTO errors (error_type, error_msg, nc_file_id) VALUES (?, ?, ?)",
                    [
                        (e.error_type.value, e.error_msg, file_id)
                        for e in check_file(file_path)
                    ],
                )

                results = self.cur.execute(
                    "SELECT nc_file_path FROM nc_files WHERE nc_file_name = ? AND nc_file_id != ?",
                    (file_path.name, file_id),
                )

                if results.fetchone():
                    self.cur.execute(
                        "INSERT INTO duplicates (nc_file_id) VALUES (?)", (file_id,)
                    )
            print(f"{file_path} added to database")
            self.con.commit()
        except PermissionError:
            print("File is being used by another process")
    
    def get_duplicates(self) -> list[NCFile]:
        duplicates = [
            NCFile(Path(row[0]), row[1])
            for row in self.cur.execute(
                "SELECT nc_file_path, nc_file_modified_time FROM nc_files JOIN duplicates USING (nc_file_id)"
            ).fetchall()
        ]
        return duplicates


if __name__ == "__main__":
    fm = FileManager()
