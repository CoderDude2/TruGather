from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from typing import NamedTuple
import datetime
import math
import sqlite3
import shutil
import re
import threading

BASE_DIR: Path = Path(__file__).resolve().parent
ERP_DIR: Path = Path(r"\\192.168.1.100\Trubox\####ERP_RM####")

prg_regex: re.Pattern = re.compile(r"(\d{4,})([A-Za-z.]+)")
asc_folder_regex: re.Pattern = re.compile(r"\d+.\d+_ASC_\((\d+)\)")
folder_regex: re.Pattern = re.compile(r"(\d+) ?\((\d+)?\) ?([A-Za-z\+ ]+)?")
first_line_regex:re.Pattern = re.compile(r"O(?P<id>[0-9]{4})\((?P<connection>[a-zA-Z0-9\-]+)\)")

def date_as_path(date=None) -> Path:
    if date is None:
        date = datetime.datetime.now().date()
    _day = f"D{'0' + str(date.day) if date.day < 10 else str(date.day)}"
    _month = f"M{'0' + str(date.month) if date.month < 10 else str(date.month)}"
    _year = f"Y{str(date.year)}"
    return Path(_year, _month, _day)


NC_FOLDER: Path = ERP_DIR / date_as_path() / r"1. CAM\3. NC files"
ALL_FOLDER: Path = NC_FOLDER / "ALL"

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
    OUT_OF_ORDER = 6


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

    case_type:str = ""

    if "ASC" in first_line:
        case_type = "ASC"
    elif "T-L" in first_line or "TLCS" in first_line or "TLOC" in first_line or "TL14" in first_line:
        case_type = "TLOC"
    elif "AOT14" in first_line:
        case_type = "AOT"
    elif "ATPL" in first_line:
        case_type = "ATPL"
    else:
        case_type = "DS"
    
    match case_type:
        case "DS":
            tools_to_check = ["T0200", "T0700", "T0800", "T0900"]
            tool_order = ["T0200", "T0200", "T0800", "T0700", "T0900"]
        case "ASC":
            tools_to_check = ["T0200", "T0800", "T1200", "T1300"]
            tool_order = ['T0200', 'T0200', 'T0800', 'T1300', 'T1300', 'T1200', 'T1200']
        case "TLOC":
            tools_to_check = ["T0200", "T0700", "T0800"]
            tool_order = ['T0200', 'T0200', 'T0800', 'T0200', 'T0800', 'T0800', 'T0700']
        case "AOT":
            tools_to_check = ["T0200", "T0700", "T0800"]
            tool_order = ['T0200', 'T0200', 'T0800', 'T0200', 'T0800', 'T0800', 'T0700']
        case _:
            tools_to_check = []
            tool_order = []


    contains_subprogram_0: bool = False
    contains_subprogram_1: bool = False
    contains_subprogram_2: bool = False

    contains_ug_101: bool = False
    contains_ug_102: bool = False
    contains_ug_103: bool = False
    contains_ug_104: bool = False
    contains_ug_105: bool = False

    actual_tool_order:list[str] = []

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
        
        for tool in tools_to_check:
            if tool in line:
                actual_tool_order.append(tool)

    
    if tool_order != actual_tool_order[0:len(tool_order)]:
        errors.append(
            NCError(ErrorType.OUT_OF_ORDER, "Operations are not in the correct order.")
        )

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
        if "all" not in str(file.resolve()).lower() and "_asc_" not in str(file.resolve()).lower():
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

    def get_file_id(self, nc_file: NCFile) -> int | None:
        file_id = self.cur.execute(
            "SELECT nc_file_id FROM nc_files WHERE nc_file_path = ?",
            (str(nc_file.path.resolve()),),
        ).fetchone()

        if not file_id:
            return None

        return file_id[0]

    def is_tracked(self, file_path: Path) -> bool:
        res = self.cur.execute(
            "SELECT nc_file_id FROM nc_files WHERE nc_file_path = ?", (str(file_path),)
        )
        if not res.fetchone():
            return False
        return True

    def get_all_nc_files(self) -> list[NCFile]:
        nc_files: list[NCFile] = []

        results = self.cur.execute(
            "SELECT nc_file_path, nc_file_modified_time FROM nc_files"
        )

        for row in results.fetchall():
            nc_files.append(NCFile(Path(row[0]), row[1]))
        return nc_files

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
                self.con.commit()

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

    def delete_nc_file(self, nc_file: NCFile) -> None:
        file_id = self.get_file_id(nc_file)
        gathered_path: Path = ALL_FOLDER / nc_file.path.name

        if not file_id:
            return

        if gathered_path.exists():
            gathered_path.unlink()

        self.cur.execute("DELETE FROM errors WHERE nc_file_id = ?", (file_id,))
        self.cur.execute(
            "DELETE FROM gathered_nc_files WHERE nc_file_id = ?", (file_id,)
        )
        self.cur.execute("DELETE FROM nc_files WHERE nc_file_id = ?", (file_id,))
        self.con.commit()
        print(f"{nc_file.path} removed from database")

        duplicate_ids = [
            row[0]
            for row in self.cur.execute(
                "SELECT nc_file_id FROM nc_files JOIN duplicates USING(nc_file_id) WHERE nc_file_name = ?",
                (nc_file.path.name,),
            ).fetchall()
        ]

        if not duplicate_ids:
            self.con.commit()
            return

        for duplicate_id in duplicate_ids:
            errors = self.cur.execute(
                "SELECT error_type, error_msg FROM errors WHERE nc_file_id = ?",
                (duplicate_id,),
            )
            if not errors.fetchone():
                self.cur.execute(
                    "DELETE FROM duplicates WHERE nc_file_id = ?", (duplicate_id,)
                )
                print("Removed file without errors")
                self.con.commit()
                return
        print("Removed file with errors")
        self.cur.execute(
            "DELETE FROM duplicates WHERE nc_file_id = ?", (duplicate_ids[0],)
        )
        self.con.commit()

    def is_gathered(self, nc_file: NCFile) -> bool:
        file_id = self.get_file_id(nc_file)

        res = self.cur.execute(
            "SELECT nc_file_id FROM gathered_nc_files WHERE nc_file_id = ?", (file_id,)
        ).fetchone()

        if not res:
            return False

        return True

    def gather_nc_file(self, nc_file: NCFile) -> None:
        file_id = self.get_file_id(nc_file)
        gathered_path: Path = ALL_FOLDER / nc_file.path.name

        if not file_id:
            return

        try:
            self.cur.execute(
                "INSERT INTO gathered_nc_files (gathered_nc_file_path, nc_file_id) VALUES (?, ?)",
                (str(gathered_path.resolve()), file_id),
            )
            print(f"{nc_file.path} gathered")
            self.con.commit()
        except sqlite3.IntegrityError:
            print(f"{nc_file.path} is a duplicate")

    def remove_nc_from_gather(self, nc_file: NCFile) -> None:
        file_id = self.get_file_id(nc_file)
        gathered_path: Path = ALL_FOLDER / nc_file.path.name

        if not file_id:
            return

        if gathered_path.exists():
            gathered_path.unlink()

        self.cur.execute(
            "DELETE FROM gathered_nc_files WHERE nc_file_id = ?", (file_id,)
        )
        self.con.commit()

    def update_nc_file(self, nc_file: NCFile) -> None:
        file_id = self.get_file_id(nc_file)

        if not file_id:
            return

        nc_errors: tuple[NCError, ...] = self.get_errors(nc_file)
        errors: tuple[NCError, ...] = check_file(nc_file.path)

        errors_to_remove: list[NCError] = []
        errors_to_add: list[NCError] = []

        for error in errors:
            if error not in nc_errors:
                errors_to_add.append(error)

        for nc_error in nc_errors:
            if nc_error not in errors:
                errors_to_remove.append(nc_error)

        self.cur.executemany(
            "INSERT OR IGNORE INTO errors (error_type, error_msg, nc_file_id) VALUES (?, ?, ?)",
            [(e.error_type.value, e.error_msg, file_id) for e in errors_to_add],
        )

        self.cur.executemany(
            "DELETE FROM errors WHERE error_type = ? AND error_msg = ? AND nc_file_id = ?",
            [(e.error_type.value, e.error_msg, file_id) for e in errors_to_remove],
        )

        self.cur.execute(
            "UPDATE nc_files SET nc_file_modified_time = ? WHERE nc_file_id = ?",
            (
                nc_file.path.stat().st_mtime,
                file_id,
            ),
        )
        self.con.commit()

    def get_duplicates(self) -> list[NCFile]:
        duplicates = [
            NCFile(Path(row[0]), row[1])
            for row in self.cur.execute(
                "SELECT nc_file_path, nc_file_modified_time FROM nc_files JOIN duplicates USING (nc_file_id)"
            ).fetchall()
        ]
        return duplicates

    def is_duplicate(self, nc_file: NCFile) -> bool:
        file_id = self.get_file_id(nc_file)

        res = self.cur.execute(
            "SELECT nc_file_id FROM duplicates WHERE nc_file_id = ?", (file_id,)
        )

        if res.fetchone():
            return True
        return False

    def get_errors(self, nc_file: NCFile) -> tuple[NCError, ...]:
        file_id = self.get_file_id(nc_file)
        errors: list[NCError] = []

        if file_id:
            results = self.cur.execute(
                "SELECT error_type, error_msg FROM errors WHERE nc_file_id = ?",
                (file_id,),
            )
            for row in results:
                errors.append(NCError(ErrorType(row[0]), row[1]))

        return tuple(errors)

    def is_modified(self, nc_file: NCFile) -> bool:
        file_id = self.get_file_id(nc_file)
        res = self.cur.execute(
            "SELECT nc_file_modified_time FROM nc_files WHERE nc_file_id = ?",
            (file_id,),
        ).fetchone()
        return nc_file.path.stat().st_mtime != res[0]

    def get_modified_files(self) -> list[NCFile]:
        modified_nc_files: list[NCFile] = []

        for nc_file in self.get_all_nc_files():
            if nc_file.path.stat().st_mtime != nc_file.modified_time:
                modified_nc_files.append(nc_file)

        return modified_nc_files


class FileProcessor:
    def __init__(self) -> None:
        self.processing_event = threading.Event()
        self.gathering_event = threading.Event()
        
        self.gathering_event.clear()
        self.processing_event.set()
        self.process_files_thread = threading.Thread(
            target=self.process_files,
            args=(
                self.processing_event,
                self.gathering_event,
            ),
        )
        self.process_files_thread.start()

    def gather_all_files(self) -> None:
        fm = FileManager()
        for nc_file in fm.get_all_nc_files():
            if fm.is_duplicate(nc_file):
                continue
            if not fm.is_gathered(nc_file) and not fm.get_errors(nc_file):
                fm.gather_nc_file(nc_file)

            if fm.is_gathered(nc_file) and fm.get_errors(nc_file):
                fm.remove_nc_from_gather(nc_file)

            if (
                fm.is_gathered(nc_file)
                and not (ALL_FOLDER / nc_file.path.name).exists()
            ):
                shutil.copy2(
                    nc_file.path.resolve(),
                    (ALL_FOLDER / nc_file.path.name).resolve(),
                )
        fm.con.close()
    
    def gather_all_asc_files(self) -> None:
        fm = FileManager()
        todays_date = datetime.datetime.now().date()

        asc_folder: Path|None = None
        for file in NC_FOLDER.iterdir():
            if file.is_dir() and asc_folder_regex.match(file.name):
                asc_folder = file
        
        if not asc_folder:
            asc_folder = NC_FOLDER / f'{todays_date.month}.{todays_date.day}_ASC_(0)'
        
        asc_folder.mkdir(exist_ok=True)
        for nc_file in fm.get_all_nc_files():
            if fm.is_duplicate(nc_file) or fm.get_errors(nc_file):
                continue
            
            with nc_file.path.open('r') as f:
                first_line = f.readline()
            
            if "ASC" in first_line:
                if not (asc_folder / nc_file.path.name).exists():
                    shutil.copy2(
                        nc_file.path.resolve(),
                        (asc_folder / nc_file.path.name).resolve(),
                    )     
        asc_folder.rename(NC_FOLDER / f'{todays_date.month}.{todays_date.day}_ASC_({len(list(asc_folder.iterdir()))})')
        fm.con.close()

    def process_files(
        self, processing_event: threading.Event, gathering_event: threading.Event
    ) -> None:
        fm = FileManager()

        while processing_event.is_set():
            try:
                for file in get_nc_files(NC_FOLDER):
                    if not fm.is_tracked(file):
                        fm.add_to_database(file)

                for nc_file in fm.get_all_nc_files():
                    if not nc_file.path.exists():
                        fm.delete_nc_file(nc_file)
                        continue

                    if fm.is_modified(nc_file):
                        print(nc_file, "is modified")
                        fm.update_nc_file(nc_file)
                    
                    if fm.is_gathered(nc_file) and fm.get_errors(nc_file):
                        fm.remove_nc_from_gather(nc_file)

                    if fm.is_duplicate(nc_file):
                        continue

                    if gathering_event.is_set():
                        if not fm.is_gathered(nc_file) and not fm.get_errors(nc_file):
                            fm.gather_nc_file(nc_file)
                        
                        if (
                            fm.is_gathered(nc_file)
                            and not (ALL_FOLDER / nc_file.path.name).exists()
                        ):
                            shutil.copy2(
                                nc_file.path.resolve(),
                                (ALL_FOLDER / nc_file.path.name).resolve(),
                            )
            except FileNotFoundError:
                if not ALL_FOLDER.exists():
                    ALL_FOLDER.mkdir()
            except OSError as e:
                print(f"WinError: {e.winerror}\n", f"\n{e}")
        fm.con.close()

    def start_gathering(self) -> None:
        self.gathering_event.set()

    def stop_gathering(self) -> None:
        self.gathering_event.clear()

    def stop_processing(self) -> None:
        self.processing_event.clear()


def main() -> None:
    fp = FileProcessor()
    while True:
        inp = input()

        if inp == "gather on":
            fp.start_gathering()
        elif inp == "gather off":
            fp.stop_gathering()
        elif inp == "end":
            fp.stop_processing()
            exit()
        else:
            print("Invalid Input")


if __name__ == "__main__":
    main()
