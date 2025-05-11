import sys
import os

class Logger:
    def __init__(self, filename=None, disable_print=False):
        self.filename = filename
        self.disable_print = disable_print
        self.default_stdout = sys.stdout
        self.file = None  # Track the open file explicitly

    def __enter__(self):
        if self.disable_print:
            self.file = open(os.devnull, "w")
        elif self.filename:
            self.file = open(self.filename, "w")
        else:
            self.file = None
        
        if self.file:
            sys.stdout = self.file
        
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            sys.stdout.flush()
            sys.stdout = self.default_stdout
            self.file.close()
            self.file = None
        else:
            sys.stdout = self.default_stdout

    def enable(self):
        sys.stdout = self.default_stdout

    def disable(self):
        self._close_file()
        self.file = open(os.devnull, "w")
        sys.stdout = self.file

    def set_file(self, filename):
        self._close_file()
        self.file = open(filename, "w")
        sys.stdout = self.file

    def reset(self):
        self._close_file()
        sys.stdout = self.default_stdout

    def _close_file(self):
        if self.file:
            sys.stdout.flush()
            self.file.close()
            self.file = None
