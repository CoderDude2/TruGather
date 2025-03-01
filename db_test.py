from pathlib import Path
import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Generator


BASE_DIR: Path = Path(__file__).resolve().parent

DB_FILE: Path = BASE_DIR / "data.db"


class ErrorType(Enum):
    INVALID_NAME = 1
    PART_LENGTH = 2


class WarningType(Enum):
    DUPLICATE_PRG = 1


@dataclass
class NCFile:
    file_path: Path
    file_name: str


@dataclass
class NCError:
    error_type: ErrorType
    error_msg: str


@dataclass
class NCWarning:
    warning_type: WarningType
    warning_msg: str


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
                "nc_file_name TEXT NOT NULL UNIQUE,"
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
                "FOREIGN KEY(nc_file_id) REFERENCES nc_files(nc_file_id))"
            )
        )

    def add_nc_file(self, nc_file: NCFile):
        self.cur.execute(
            "INSERT INTO nc_files (nc_file_path, nc_file_name, nc_file_modified_time) VALUES (?, ?, ?)",
            (
                str(nc_file.file_path.resolve()),
                nc_file.file_name,
                nc_file.file_path.stat().st_mtime,
            ),
        )
        self.con.commit()

    def get_all_nc_files(self) -> list[NCFile]:
        nc_file_list: list[NCFile] = []

        res = self.cur.execute("SELECT * FROM nc_files")
        for row in res:
            nc_file_list.append(NCFile(Path(row[1]), row[2]))
        return nc_file_list

    def get_nc_file_by_file_id(self, nc_file_id: int) -> NCFile | None:
        res = self.cur.execute(
            "SELECT * FROM nc_files WHERE nc_file_id = ?", (nc_file_id,)
        ).fetchone()
        if not res:
            return None
        return NCFile(res[1], res[2])

    def get_all_errors(self) -> list[NCError]:
        error_list: list[NCError] = []
        res = self.cur.execute("SELECT * FROM errors")
        for row in res:
            error_list.append(NCError(ErrorType(row[1]), row[2]))
        return error_list

    def get_errors_by_file_id(self, nc_file_id: int) -> tuple[NCError,...]:
        nc_errors: list[NCError] = []

        res = self.cur.execute(
            "SELECT * FROM errors WHERE nc_file_id = ?", (nc_file_id,)
        )

        for row in res:
            nc_errors.append(NCError(ErrorType(row[1]), row[2]))

        return tuple(nc_errors)

    def get_errors_for_nc_file(self,nc_file: NCFile) -> tuple[NCError,...]:
        file_id = self.get_file_id_by_path(nc_file.file_path)

        return self.get_errors_by_file_id(file_id)

    def get_file_id_by_path(self, nc_file_path: Path) -> int | None:
        res = self.cur.execute(
            "SELECT nc_file_id FROM nc_files WHERE nc_file_path = ?",
            (str(nc_file_path.resolve()),),
        ).fetchone()
        if not res:
            return None
        return res[0]
    
    def get_files_by_name(self, nc_file_name: str) -> list[NCFile] | None:
        nc_file_list: list[NCFile] = []
        res = self.cur.execute(
            "SELECT nc_file_path, nc_file_name FROM nc_files WHERE nc_file_name = ?",
            (nc_file_name,)
        )

        if not res:
            return None
        
        nc_file_list = [NCFile(row[0], row[1]) for row in res]

        return nc_file_list  

    def close_db(self) -> None:
        self.con.close()


def get_nc_files(nc_file_path: Path) -> Generator[NCFile|None, None, None]:
    for file in nc_file_path.iterdir():
        if file.is_file() and file.suffix.lower() == '.prg':
            yield NCFile(file.absolute(), file.name)


def main() -> None:
    file_db = FileDB()

    for nc_file in file_db.get_all_nc_files():
        print(nc_file, file_db.get_errors_for_nc_file(nc_file))

    file_db.close_db()


if __name__ == "__main__":
    main()
