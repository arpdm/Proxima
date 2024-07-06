"""
plotting_util.py
================

Description:
    This module contains utility functions for plotting time series data.
    Specifically, it includes a function to plot any time series data with labels
    using Matplotlib, supporting both lists and pandas DataFrame inputs.

Author:
    Arpi Derm <arpiderm@gmail.com>

Created:
    July 5, 2024

Dependencies:
    - matplotlib: Plotting library for Python (https://matplotlib.org/)
    - pandas: Data analysis and manipulation library for Python (https://pandas.pydata.org/)

Usage:
    Import the `plot_ts` function from this module to plot time series data:
        from plotting_util import plot_ts

    Example:
        plot_ts(data_series_1, "Label 1", data_series_2, "Label 2")

License:
    MIT License

Functions:
    - plot_ts: Plots time series data with labels for the x-axis and y-axis.

"""

import matplotlib.pyplot as plt


def plot_ts(
    data_series_1,
    label_1,
    data_series_2=None,
    label_2=None,
    x_label="Time",
    y_label="Value",
    title="Time Series Data",
):
    """
    Plots time series data.

    Args:
        data_series_1 (list or pandas.Series): A list or pandas Series of values for the first data series.
        label_1 (str): Label for the first data series.
        data_series_2 (list or pandas.Series, optional): A list or pandas Series of values for the second data series.
        label_2 (str, optional): Label for the second data series.
        x_label (str, optional): Label for the x-axis. Defaults to "Time".
        y_label (str, optional): Label for the y-axis. Defaults to "Value".
        title (str, optional): Title of the plot. Defaults to "Time Series Data".
    """
    plt.plot(data_series_1, label=label_1)
    if data_series_2 is not None:
        plt.plot(data_series_2, label=label_2)
    plt.xlabel(x_label)
    plt.ylabel(y_label)
    plt.title(title)
    plt.legend()
    plt.show()
