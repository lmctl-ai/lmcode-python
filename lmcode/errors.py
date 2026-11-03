"""Stable public error types for bytecode loading and execution."""
from __future__ import annotations
from functools import wraps


class LmcodeError(Exception):
    def __init__(self, code: str, message: str, line: int = 0, column: int = 0):
        super().__init__(message)
        self.code = code
        self.message = message
        self.line = line
        self.column = column
        self.has_invocation_dry = False
        self.invocation_dry = False

    def locate(self, line: int, column: int) -> None:
        if self.line or not line:
            return
        self.line = line
        self.column = column
        suffix = ":" + str(column) if column else ""
        self.message = "dsl line " + str(line) + suffix + ": " + self.message
        self.args = (self.message,)


class LoadError(LmcodeError):
    pass


class RunError(LmcodeError):
    pass


class HostError(RunError):
    def __init__(self, message: str):
        super().__init__("RUN_HOST", message)


def load_error(message: str, code: str = "LOAD_BAD_BYTECODE") -> LoadError:
    return LoadError(code, message)


def run_error(message: str, code: str = "RUN_ERROR") -> RunError:
    return RunError(code, message)


def sdk_errors(code="RUN_HOST"):
    """Translate native failures at public SDK boundaries; preserve existing SDK errors."""
    def decorate(function):
        @wraps(function)
        def checked(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except LmcodeError:
                raise
            except Exception as error:
                message = ("memory allocation failed" if isinstance(error, MemoryError) else
                           "maximum recursion depth exceeded" if isinstance(error, RecursionError) else str(error))
                if code == "RUN_HOST":
                    raise HostError(message) from None
                error_type = LoadError if code.startswith("LOAD_") else LmcodeError
                raise error_type(code, message) from None
        return checked
    return decorate
