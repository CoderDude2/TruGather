from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from typing import NamedTuple
import http.client as httplib
import datetime
import math
import sqlite3
import shutil
import re
import threading


TODAYS_DATE: str = datetime.datetime.isoformat(datetime.datetime.now())[:10]
BASE_DIR: Path = Path(__file__).resolve().parent
ERP_DIR: Path = Path(r"\\192.168.1.100\Trubox\####ERP_RM####")

prg_regex: re.Pattern = re.compile(r"(\d{4,})([A-Za-z.]+)")
asc_folder_regex: re.Pattern = re.compile(r"\d+.\d+_ASC_\((\d+)\)")
folder_regex: re.Pattern = re.compile(r"(\d+) ?\((\d+)?\) ?([A-Za-z\+ ]+)?")
first_line_regex: re.Pattern = re.compile(
    r"O(?P<id>[0-9]{4})\((?P<connection>[a-zA-Z0-9\-]+)\)"
)


def date_as_path(date=None) -> Path:
    if date is None:
        date = datetime.datetime.now().date()
    _day = f"D{'0' + str(date.day) if date.day < 10 else str(date.day)}"
    _month = f"M{'0' + str(date.month) if date.month < 10 else str(date.month)}"
    _year = f"Y{str(date.year)}"
    return Path(_year, _month, _day)


NC_FOLDER: Path = ERP_DIR / date_as_path() / r"1. CAM\3. NC files"
ALL_FOLDER: Path = NC_FOLDER / "ALL"

DB_FILE: Path = BASE_DIR / "files.db"


class NCFile(NamedTuple):
    path: Path
    modified_time: float


@dataclass
class Tool:
    tool_identifier: str
    order: list[int] | None = None
    min_count: int | None = None
    max_count: int | None = None


class ErrorType(Enum):
    INVALID_NAME = 1
    PART_LENGTH = 2
    INTERNAL_NAME = 3
    MISSING_UG_VALUE = 4
    MISSING_SUBPROGRAM = 5
    OUT_OF_ORDER = 6
    INVALID_OPERATION_COUNT = 7


@dataclass
class NCError:
    error_type: ErrorType
    error_msg: str | None = None


def is_internet_connected() -> bool:
    conn = httplib.HTTPConnection("192.168.1.100", timeout=5)
    try:
        conn.request("HEAD", "/")
        return True
    except Exception:
        return False
    finally:
        conn.close()


def check_file(nc_file: NCFile) -> tuple[NCError, ...]:
    errors: list[NCError] = []
    part_length: float = 0
    cut_off: float = 0
    case_type: str = ""
    contains_text: bool = False

    with nc_file.path.open("r") as file:
        first_line = file.readline()
        contents = file.readlines()

    if "ASC" in first_line:
        case_type = "ASC"
    elif (
        "T-L" in first_line
        or "TLCS" in first_line
        or "TLOC" in first_line
        or "TL14" in first_line
    ):
        case_type = "TLOC"
    elif "AOT14" in first_line:
        case_type = "AOT"
    elif "ATPL" in first_line:
        case_type = "ATPL"
    else:
        case_type = "DS"

    match case_type:
        case "DS":
            tools_to_check = [
                Tool("T0200", min_count=2, max_count=2, order=[0, 1]),
                Tool("T0700", min_count=1, max_count=None, order=[3]),
                Tool("T0800", min_count=1, order=[2]),
                Tool("T0900", min_count=1, order=[4]),
            ]
        case "ASC":
            tools_to_check = [
                Tool("T0200", min_count=2, max_count=2, order=[0, 1]),
                Tool("T0800", min_count=1, order=[2]),
                Tool("T1200", min_count=1, order=[4]),
                Tool("T1300", min_count=1, order=[3]),
            ]
        case "TLOC":
            tools_to_check = [
                Tool("T0200", min_count=3, max_count=3, order=[0, 1, 3]),
                Tool("T0800", min_count=2, order=[2, 4]),
                Tool("T0700", min_count=1, order=[5]),
            ]
        case "AOT":
            tools_to_check = [
                Tool("T0200", min_count=3, max_count=3, order=[0, 1, 3]),
                Tool("T0800", min_count=2, order=[2, 4]),
                Tool("T0700", min_count=1, order=[5]),
            ]
        case "ATPL":
            return tuple(errors)

    contains_subprogram_0: bool = False
    contains_subprogram_1: bool = False
    contains_subprogram_2: bool = False

    contains_ug_101: bool = False
    contains_ug_102: bool = False
    contains_ug_103: bool = False
    contains_ug_104: bool = False
    contains_ug_105: bool = False

    tool_index: int = 0
    tool_order_map: dict[str, list[int]] = {
        k: [] for k in [t.tool_identifier for t in tools_to_check]
    }

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
            try:
                if case_type == "ATPL":
                    cut_off = float(contents[i + 4].split(" ")[2][1:])
                else:
                    cut_off = float(contents[i + 2][4:])
            except ValueError:
                cut_off = 0
            except IndexError:
                cut_off = 0

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

        if "TEXT" in line.upper():
            contains_text = True

        for tool in tools_to_check:
            if tool.tool_identifier in line:
                if len(tool_order_map[tool.tool_identifier]) < tool.min_count:
                    tool_order_map[tool.tool_identifier].append(tool_index)
                    tool_index += 1

    missing_operations: bool = False
    for tool in tools_to_check:
        order: list[int] = tool_order_map[tool.tool_identifier]
        if len(order) < tool.min_count:
            err_msg: str = f"{tool.tool_identifier} count is {len(order)}, should have at least {tool.min_count}"
            if tool.max_count and tool.max_count == tool.min_count:
                err_msg: str = f"{tool.tool_identifier} count is {len(order)}, should have {tool.min_count}"

            errors.append(
                NCError(
                    ErrorType.INVALID_OPERATION_COUNT,
                    err_msg,
                )
            )
            missing_operations = True

    if not missing_operations:
        for tool in tools_to_check:
            order = tool_order_map[tool.tool_identifier]
            if tool.order != order:
                errors.append(
                    NCError(
                        ErrorType.OUT_OF_ORDER,
                        f"{tool.tool_identifier} is not in the correct order",
                    )
                )
                break

    if nc_file.path.stem not in first_line:
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

    if not prg_regex.match(nc_file.path.name):
        errors.append(NCError(ErrorType.INVALID_NAME, "Incorrect file name."))

    if (
        nc_file.path.name == "4001.prg"
        and case_type == "ASC"
        and contains_text is False
    ):
        errors.append(
            NCError(ErrorType.INVALID_NAME, "4001 is not a valid name for ASC files.")
        )

    if case_type == "ASC" or case_type == "TLOC" or case_type == "AOT":
        if all(
            [
                contains_ug_101 is False,
                contains_ug_102 is False,
                contains_ug_103 is False,
                contains_ug_104 is False,
                contains_ug_105 is False,
            ]
        ):
            errors.append(NCError(ErrorType.MISSING_UG_VALUE, "Missing all UG values"))
        else:
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


def get_nc_files(file_path: Path) -> list[NCFile]:
    nc_files: list[NCFile] = []

    for file in file_path.rglob("*.prg", case_sensitive=False):
        if (
            "all" not in str(file.resolve()).lower()
            and "_asc_" not in str(file.resolve()).lower()
        ):
            nc_files.append(NCFile(file.resolve(), file.stat().st_mtime))

    return nc_files


class FileManager:
    def __init__(self) -> None:
        self.con: sqlite3.Connection = sqlite3.connect(DB_FILE)
        self.cur: sqlite3.Cursor = self.con.cursor()
        self.init_db()

    def init_db(self) -> None:
        self.cur.execute(
            (
                "CREATE TABLE "
                "IF NOT EXISTS date ("
                "date_id INTEGER PRIMARY KEY UNIQUE,"
                "current_day TEXT NOT NULL UNIQUE)"
            )
        )

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
                "IF NOT EXISTS errors ("
                "error_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "error_type INTEGER NOT NULL,"
                "error_msg TEXT NOT NULL,"
                "nc_file_id INTEGER NOT NULL,"
                "UNIQUE(error_type, error_msg, nc_file_id)"
                "FOREIGN KEY(nc_file_id) REFERENCES nc_files(nc_file_id))"
            )
        )

        self.con.commit()

        res = self.cur.execute(
            "SELECT current_day from date WHERE date_id = ?", (1,)
        ).fetchone()

        if not res:
            self.cur.execute(
                "INSERT INTO date (date_id, current_day) VALUES (?, ?)",
                (
                    1,
                    TODAYS_DATE,
                ),
            )
            self.con.commit()
            return

        if res[0] != TODAYS_DATE:
            self.cur.execute(
                "UPDATE date SET current_day = ? WHERE date_id = ?",
                (
                    TODAYS_DATE,
                    1,
                ),
            )
            self.cur.execute("DELETE FROM errors")
            self.cur.execute("DELETE FROM gathered_nc_files")
            self.cur.execute("DELETE FROM nc_files")
            self.con.commit()

    def get_file_id(self, nc_file: NCFile) -> int | None:
        file_id = self.cur.execute(
            "SELECT nc_file_id FROM nc_files WHERE nc_file_path = ?",
            (str(nc_file.path.resolve()),),
        ).fetchone()

        if not file_id:
            return None

        return file_id[0]

    def is_tracked(self, nc_file: NCFile) -> bool:
        res = self.cur.execute(
            "SELECT nc_file_id FROM nc_files WHERE nc_file_path = ?",
            (str(nc_file.path),),
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

    def get_case_counts(self) -> dict[str, int]:
        nc_files = self.get_all_nc_files()
        case_count: dict[str, int] = {}

        case_count["ASC"] = 0
        case_count["TL/AOT"] = 0
        case_count["DS"] = 0
        case_count["AOTP"] = 0

        for nc_file in nc_files:
            with nc_file.path.open("r") as file:
                first_line = file.readline()
            first_line = "ASC"
            if "ASC" in first_line:
                case_count["ASC"] += 1
            elif (
                "T-L" in first_line
                or "TLCS" in first_line
                or "TLOC" in first_line
                or "TL14" in first_line
            ):
                case_count["TL/AOT"] += 1
            elif "AOT14" in first_line:
                case_count["TL/AOT"] += 1
            elif "ATPL" in first_line:
                case_count["AOTP"] += 1
            else:
                case_count["DS"] += 1
        return case_count

    def get_associate_counts(self) -> dict[str, int]:
        return dict()

    def add_to_database(self, nc_file: NCFile) -> None:
        try:
            self.cur.execute(
                "INSERT INTO nc_files (nc_file_path, nc_file_name, nc_file_modified_time) VALUES (?, ?, ?)",
                (str(nc_file.path), nc_file.path.name, nc_file.path.stat().st_mtime),
            )
            if self.cur.lastrowid:
                file_id: int = self.cur.lastrowid
                self.cur.executemany(
                    "INSERT OR IGNORE INTO errors (error_type, error_msg, nc_file_id) VALUES (?, ?, ?)",
                    [
                        (e.error_type.value, e.error_msg, file_id)
                        for e in check_file(nc_file)
                    ],
                )
            self.con.commit()
        except PermissionError:
            pass

    def delete_nc_file(self, nc_file: NCFile) -> None:
        file_id = self.get_file_id(nc_file)
        gathered_path: Path = ALL_FOLDER / nc_file.path.name

        if not file_id:
            return

        self.cur.execute("DELETE FROM errors WHERE nc_file_id = ?", (file_id,))
        self.cur.execute(
            "DELETE FROM gathered_nc_files WHERE gathered_nc_file_path = ?",
            (str(gathered_path.resolve()),),
        )
        self.cur.execute("DELETE FROM nc_files WHERE nc_file_id = ?", (file_id,))
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
            self.con.commit()
        except sqlite3.IntegrityError:
            self.cur.execute(
                "UPDATE gathered_nc_files SET nc_file_id = ? WHERE gathered_nc_file_path = ?",
                (file_id, str(gathered_path.resolve())),
            )
            self.con.commit()

    def can_gather(self, nc_file: NCFile) -> bool:
        res = self.cur.execute(
            "SELECT nc_file_name, nc_file_modified_time FROM gathered_nc_files JOIN nc_files USING (nc_file_id) WHERE nc_file_name = ?",
            (nc_file.path.name,),
        ).fetchone()

        if self.get_errors(nc_file):
            return False

        if not res:
            return True

        if res and (nc_file.path.stat().st_mtime > res[1]):
            return True

        return False

    def remove_nc_from_gather(self, nc_file: NCFile) -> None:
        file_id = self.get_file_id(nc_file)

        if not file_id:
            return

        self.cur.execute(
            "DELETE FROM gathered_nc_files WHERE nc_file_id = ?", (file_id,)
        )
        self.con.commit()

    def update_nc_file(self, nc_file: NCFile) -> None:
        file_id = self.get_file_id(nc_file)

        if not file_id:
            return

        nc_errors: tuple[NCError, ...] = self.get_errors(nc_file)
        errors: tuple[NCError, ...] = check_file(nc_file)

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

    def get_nc_files_by_name(self, nc_file: NCFile) -> list[NCFile]:
        nc_files: list[NCFile] = []

        res = self.cur.execute(
            "SELECT nc_file_path, nc_file_modified_time FROM nc_files WHERE nc_file_name = ?",
            (nc_file.path.name,),
        )
        for row in res.fetchall():
            nc_files.append(NCFile(Path(row[0]), row[1]))
        return nc_files

    def get_duplicates(self) -> list[NCFile]:
        res = self.cur.execute(
            (
                "SELECT nc_file_path, nc_file_modified_time FROM nc_files "
                "WHERE "
                "NOT EXISTS ("
                "SELECT 1 FROM gathered_nc_files WHERE nc_file_id = nc_files.nc_file_id"
                ")"
            )
        )
        duplicates: list[NCFile] = []
        for row in res.fetchall():
            duplicate_nc = NCFile(Path(row[0]), row[1])
            if len(self.get_nc_files_by_name(duplicate_nc)) > 1:
                duplicates.append(duplicate_nc)
        return duplicates

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
        self.internet_connected_event = threading.Event()

        self.gathering_event.clear()
        self.processing_event.set()
        self.check_connection_thread = threading.Thread(
            target=self.check_connection,
            args=(self.internet_connected_event,),
            daemon=True,
        )

        self.process_files_thread = threading.Thread(
            target=self.process_files,
            args=(
                self.processing_event,
                self.gathering_event,
                self.internet_connected_event,
            ),
        )
        self.check_connection_thread.start()
        self.process_files_thread.start()

    def check_connection(self, internet_connected_event: threading.Event):
        while True:
            if is_internet_connected():
                internet_connected_event.set()
            else:
                internet_connected_event.clear()

    def gather_all_files(self) -> None:
        fm = FileManager()
        try:
            for nc_file in fm.get_all_nc_files():
                if not is_internet_connected():
                    break
                if fm.is_gathered(nc_file):
                    gathered_nc_file_path: Path = (
                        ALL_FOLDER / nc_file.path.name
                    ).resolve()

                    if not gathered_nc_file_path.exists():
                        shutil.copy2(nc_file.path.resolve(), gathered_nc_file_path)

                        if (
                            gathered_nc_file_path.exists()
                            and gathered_nc_file_path.stat().st_mtime
                            != nc_file.modified_time
                        ):
                            shutil.copy2(nc_file.path.resolve(), gathered_nc_file_path)

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
        except FileNotFoundError:
            pass

        fm.con.close()

    def gather_all_asc_files(self) -> None:
        fm = FileManager()
        todays_date = datetime.datetime.now().date()
        try:
            if not is_internet_connected():
                fm.con.close()
                return
            asc_folder: Path | None = None
            for file in NC_FOLDER.iterdir():
                if file.is_dir() and asc_folder_regex.match(file.name):
                    asc_folder = file

            if not asc_folder:
                asc_folder = (
                    NC_FOLDER / f"{todays_date.month}.{todays_date.day}_ASC_(0)"
                )

            asc_folder.mkdir(exist_ok=True)
            for nc_file in fm.get_all_nc_files():
                if not is_internet_connected():
                    break
                if fm.get_errors(nc_file):
                    continue
                with nc_file.path.open("r") as f:
                    first_line = f.readline()

                if "ASC" in first_line:
                    if not (asc_folder / nc_file.path.name).exists():
                        shutil.copy2(
                            nc_file.path.resolve(),
                            (asc_folder / nc_file.path.name).resolve(),
                        )
            fm.con.close()
            asc_folder.rename(
                NC_FOLDER
                / f"{todays_date.month}.{todays_date.day}_ASC_({len(list(asc_folder.iterdir()))})"
            )
        except FileNotFoundError:
            fm.con.close()

        fm.con.close()

    def process_files(
        self,
        processing_event: threading.Event,
        gathering_event: threading.Event,
        internet_connected_event: threading.Event,
    ) -> None:
        fm = FileManager()

        while processing_event.is_set():
            if internet_connected_event.is_set():
                try:
                    for nc_file in fm.get_all_nc_files():
                        gathered_nc_file_path: Path = (
                            ALL_FOLDER / nc_file.path.name
                        ).resolve()
                        if not internet_connected_event.is_set():
                            break

                        if not nc_file.path.exists():
                            if (
                                fm.is_gathered(nc_file)
                                and gathered_nc_file_path.exists()
                            ):
                                gathered_nc_file_path.unlink()
                            fm.delete_nc_file(nc_file)
                            continue

                        if fm.is_modified(nc_file):
                            fm.update_nc_file(nc_file)

                        if fm.can_gather(nc_file):
                            fm.gather_nc_file(nc_file)

                        if gathering_event.is_set() and not fm.get_errors(nc_file):
                            if fm.is_gathered(nc_file):
                                if not gathered_nc_file_path.exists():
                                    shutil.copy2(
                                        nc_file.path.resolve(), gathered_nc_file_path
                                    )

                                if (
                                    gathered_nc_file_path.exists()
                                    and gathered_nc_file_path.stat().st_mtime
                                    != nc_file.modified_time
                                ):
                                    shutil.copy2(
                                        nc_file.path.resolve(), gathered_nc_file_path
                                    )

                    for file in get_nc_files(NC_FOLDER):
                        if not fm.is_tracked(file):
                            if not internet_connected_event.is_set():
                                break
                            fm.add_to_database(file)
                            if fm.can_gather(file):
                                fm.gather_nc_file(file)

                except FileNotFoundError:
                    if not ALL_FOLDER.exists():
                        ALL_FOLDER.mkdir()
                except OSError:
                    pass
        fm.con.close()

    def start_gathering(self) -> None:
        self.gathering_event.set()

    def stop_gathering(self) -> None:
        self.gathering_event.clear()

    def stop_processing(self) -> None:
        self.processing_event.clear()
