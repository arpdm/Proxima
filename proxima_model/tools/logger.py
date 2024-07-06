import pandas as pd


def save_time_series_data_to_file(dataframes, filename):
    """
    Appends a list of pandas DataFrames and saves the combined DataFrame to a CSV file.

    Args:
        dataframes (list of pd.DataFrame): List of pandas DataFrames to be appended.
        filename (str): The name of the CSV file to save the combined DataFrame.
    """
    combined_df = pd.concat(dataframes, axis=1).reset_index(drop=True)
    combined_df.to_csv(filename, index=False)
