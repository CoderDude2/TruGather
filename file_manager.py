from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from typing import NamedTuple

import datetime
import math
import sqlite3
import shutil
import re

prg_regex = re.compile(r"(\d{4,})([A-Za-z.]+)")
asc_folder_regex = re.compile(r"\d+.\d+_ASC_\((\d+)\)")
folder_regex = re.compile(r"(\d+) ?\((\d+)?\) ?([A-Za-z\+ ]+)?")


def date_as_path(date=None) -> Path:
    if date is None:
        date = datetime.datetime.now().date()
    _day = f"D{'0' + str(date.day) if date.day < 10 else str(date.day)}"
    _month = f"M{'0' + str(date.month) if date.month < 10 else str(date.month)}"
    _year = f"Y{str(date.year)}"
    return Path(_year, _month, _day)


BASE_DIR: Path = Path(__file__).resolve().parent
NC_FOLDER: Path = Path(
    r"\\192.168.1.100\Trubox\####ERP_RM####\Y2025\M03\D06\1. CAM\3. NC files"
)
ALL_FOLDER: Path = BASE_DIR / "nc" / "ALL"

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


def asc_folder_exists(dir_path) -> bool:
    for entry in os.listdir(dir_path):
        if asc_folder_regex.match(entry) and os.path.isdir(
            os.path.join(dir_path, entry)
        ):
            return True
    return False


def create_asc_folder(dir_path):
    if not asc_folder_exists(dir_path):
        todays_date = datetime.datetime.now()
        os.mkdir(
            os.path.join(dir_path, f"{todays_date.month}.{todays_date.day}_ASC_(0)")
        )


def get_asc_folder(dir_path):
    for entry in os.listdir(dir_path):
        if asc_folder_regex.match(entry) and os.path.isdir(
            os.path.join(dir_path, entry)
        ):
            return entry


def update_asc_folder(dir_path):
    todays_date = datetime.datetime.now()
    asc_folder = get_asc_folder(dir_path)
    if asc_folder:
        new_asc_folder = f"{todays_date.month}.{todays_date.day}_ASC_({len(os.listdir(os.path.join(dir_path, asc_folder)))})"

        try:
            os.rename(
                os.path.join(dir_path, asc_folder),
                os.path.join(dir_path, new_asc_folder),
            )
        except OSError:
            print("Folder not found:", dir_path)


def copy_to_asc(file_path):
    asc_folder = os.path.join(REMOTE_PRG_PATH, get_asc_folder(REMOTE_PRG_PATH))

    file_name = os.path.basename(file_path)
    file_mtime = os.stat(file_path).st_mtime

    if file_name not in os.listdir(asc_folder):
        xcopy(file_path, os.path.join(asc_folder, file_name))
    elif file_name in os.listdir(asc_folder):
        all_file_mtime = os.stat(os.path.join(asc_folder, file_name)).st_mtime

        if file_mtime != all_file_mtime:
            xcopy(file_path, os.path.join(asc_folder, file_name))


def copy_to_all(file_path):
    all_folder = os.path.join(REMOTE_PRG_PATH, "ALL")

    file_name = os.path.basename(file_path)
    file_mtime = os.stat(file_path).st_mtime

    if file_name not in os.listdir(all_folder):
        xcopy(file_path, os.path.join(REMOTE_PRG_PATH, "ALL", file_name))
    elif file_name in os.listdir(all_folder):
        all_file_mtime = os.stat(os.path.join(all_folder, file_name)).st_mtime

        if file_mtime != all_file_mtime:
            xcopy(file_path, os.path.join(all_folder, file_name))


def is_asc_file(file_path) -> bool:
    try:
        with open(file_path, "r") as file:
            firstline = file.readline()
        if "ASC" in firstline:
            return True
        return False
    except (FileNotFoundError, UnicodeDecodeError, PermissionError, OSError) as e:
        print(e)
        return False


class FileManager:
    def __init__(self):
        self.processed_files = {}

    def process(self) -> bool:
        updated = False

        keys_to_remove = []
        for key in self.processed_files:
            entry = self.processed_files[key]
            if not os.path.exists(os.path.join(entry["location"], key)):
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.processed_files[key]
            updated = True

        for root, dirs, files in os.walk(REMOTE_PRG_PATH):
            if "ALL" not in os.path.basename(root) and not asc_folder_regex.match(
                os.path.basename(root)
            ):
                for name in files:
                    if ".prg" in name.lower():
                        try:
                            f_stat = os.stat(os.path.join(root, name))
                            if name not in self.processed_files.keys():
                                self.processed_files[name] = {
                                    "location": root,
                                    "mtime": f_stat.st_mtime,
                                    "errors": check_file(os.path.join(root, name)),
                                    "duplicates": [],
                                }
                                updated = True
                            else:
                                # Remove any duplicates that no longer exist
                                existing_duplicates = []
                                for duplicate in self.processed_files[name][
                                    "duplicates"
                                ]:
                                    if (
                                        os.path.exists(
                                            os.path.join(duplicate["location"], name)
                                        )
                                        and duplicate["location"]
                                        != self.processed_files[name]["location"]
                                    ):
                                        existing_duplicates.append(duplicate)

                                if len(existing_duplicates) != len(
                                    self.processed_files[name]["duplicates"]
                                ):
                                    self.processed_files[name] = {
                                        "location": root,
                                        "mtime": f_stat.st_mtime,
                                        "errors": check_file(os.path.join(root, name)),
                                        "duplicates": existing_duplicates,
                                    }
                                    updated = True
                                if (
                                    self.processed_files[name]["mtime"]
                                    != f_stat.st_mtime
                                    and self.processed_files[name]["location"] == root
                                ):
                                    self.processed_files[name] = {
                                        "location": root,
                                        "mtime": f_stat.st_mtime,
                                        "errors": check_file(os.path.join(root, name)),
                                        "duplicates": self.processed_files[name][
                                            "duplicates"
                                        ],
                                    }
                                    updated = True
                                elif self.processed_files[name]["location"] != root:
                                    duplicate_file = {
                                        "location": root,
                                        "mtime": f_stat.st_mtime,
                                        "errors": check_file(os.path.join(root, name)),
                                    }
                                    duplicate_file["errors"].append(
                                        IssueType.DUPLICATE_PRG_ERR
                                    )
                                    if (
                                        duplicate_file
                                        not in self.processed_files[name]["duplicates"]
                                    ):
                                        self.processed_files[name]["duplicates"].append(
                                            duplicate_file
                                        )
                                        updated = True
                        except PermissionError:
                            print(f"File: {name}, is open in another process.")
                        except FileNotFoundError:
                            print("Could not find the file", name)
        return updated

    def copy_all_valid_files(self):
        if not os.path.exists(os.path.join(REMOTE_PRG_PATH, "ALL")):
            os.mkdir(os.path.join(REMOTE_PRG_PATH, "ALL"))

        for name, data in self.processed_files.items():
            file_path = os.path.join(data["location"], name)
            if len(data["errors"]) == 0:
                copy_to_all(file_path)

    def copy_asc_files(self):
        if not asc_folder_exists(REMOTE_PRG_PATH):
            create_asc_folder(REMOTE_PRG_PATH)
        for name, data in self.processed_files.items():
            file_path = os.path.join(data["location"], name)
            if len(data["errors"]) == 0 and is_asc_file(file_path):
                copy_to_asc(file_path)
        update_asc_folder(REMOTE_PRG_PATH)

    def save(self, json_file_path):
        serialized_processed_files = {}

        serialized_processed_files["date"] = f"{TODAYS_DATE.month}{TODAYS_DATE.day}"

        for key, entry in self.processed_files.items():
            location = entry["location"]
            mtime = entry["mtime"]
            errors = [error.value for error in entry["errors"]]
            serialized_duplicates = []

            for duplicate in entry["duplicates"]:
                duplicate_location = duplicate["location"]
                duplicate_mtime = duplicate["mtime"]
                duplicate_errors = [error.value for error in duplicate["errors"]]
                serialized_duplicate = {
                    "location": duplicate_location,
                    "mtime": duplicate_mtime,
                    "errors": duplicate_errors,
                }
                serialized_duplicates.append(serialized_duplicate)

            serialized_processed_files[key] = {
                "location": location,
                "mtime": mtime,
                "errors": errors,
                "duplicates": serialized_duplicates,
            }
        with open(json_file_path, "w+") as file:
            file.write(json.dumps(serialized_processed_files, indent=2))

    def load(self, json_file_path):
        if os.path.exists(json_file_path):
            with open(json_file_path, "r") as file:
                contents = file.read()
            json_data = json.loads(contents)
            if json_data["date"] != f"{TODAYS_DATE.month}{TODAYS_DATE.day}":
                self.processed_files = {}
            else:
                del json_data["date"]
                for key, entry in json_data.items():
                    deserialized_location = entry["location"]
                    deserialized_mtime = entry["mtime"]
                    deserialized_errors = [IssueType(i) for i in entry["errors"]]
                    deserialized_duplicates = []

                    for duplicate in entry["duplicates"]:
                        deserialized_duplicate_location = duplicate["location"]
                        deserialized_duplicate_mtime = duplicate["mtime"]
                        deserialized_duplicate_errors = [
                            IssueType(i) for i in duplicate["errors"]
                        ]
                        deserialized_duplicate = {
                            "location": deserialized_duplicate_location,
                            "mtime": deserialized_duplicate_mtime,
                            "errors": deserialized_duplicate_errors,
                        }
                        deserialized_duplicates.append(deserialized_duplicate)

                    deserialized_entry = {
                        "location": deserialized_location,
                        "mtime": deserialized_mtime,
                        "errors": deserialized_errors,
                        "duplicates": deserialized_duplicates,
                    }
                    self.processed_files[key] = deserialized_entry
        else:
            self.processed_files = {}


if __name__ == "__main__":
    fm = FileManager()
    fm.load("data.json")
    # fm.process()
    fm.save("data.json")
