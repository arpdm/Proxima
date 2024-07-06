import pandas as pd
import sys
import os


def save_time_series_data_to_file(dataframes, filename):
    """
    Appends a list of pandas DataFrames and saves the combined DataFrame to a CSV file.

    Args:
        dataframes (list of pd.DataFrame): List of pandas DataFrames to be appended.
        filename (str): The name of the CSV file to save the combined DataFrame.
    """
    combined_df = pd.concat(dataframes, axis=1).reset_index(drop=True)
    combined_df.to_csv(filename, index=False)


class Logger:
    def __init__(self, filename=None, disable_print=False):
        self.filename = filename
        self.disable_print = disable_print
        self.default_stdout = sys.stdout

    def __enter__(self):
        if self.disable_print:
            sys.stdout = open(os.devnull, "w")
        elif self.filename:
            sys.stdout = open(self.filename, "w")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self.default_stdout

    def enable(self):
        sys.stdout = self.default_stdout

    def disable(self):
        sys.stdout = open(os.devnull, "w")

    def set_file(self, filename):
        sys.stdout = open(filename, "w")

    def reset(self):
        sys.stdout.close()
        sys.stdout = self.default_stdout
