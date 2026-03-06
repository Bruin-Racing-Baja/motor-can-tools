import ctypes
import time
import pandas as pd
from sys import platform, path
from os import sep



class CSVReader:
    """
    Handles loading and querying CSV telemetry.
    Provides terminal telemetry when loading and accessing data.
    """

    def __init__(self, filepath):

        self.filepath = filepath

        print(f"[CSVReader] Loading CSV: {filepath}")

        self.df = pd.read_csv(filepath)

        # normalize column names
        self.df.columns = self.df.columns.str.strip()

        print(f"[CSVReader] Rows loaded: {len(self.df)}")
        print(f"[CSVReader] Columns detected: {list(self.df.columns)}")

        # convert timestamps if available
        if "cycle_start_us" in self.df.columns:

            self.df["cycle_start_s"] = self.df["cycle_start_us"] / 1_000_000.0

            print("[CSVReader] Converted cycle_start_us → cycle_start_s")

        print("[CSVReader] Initialization complete\n")

    def get_segment(self, start_time, end_time):
        """
        Return dataframe slice between times.
        """

        segment = self.df[
            (self.df["cycle_start_s"] >= start_time) &
            (self.df["cycle_start_s"] <= end_time)
        ].copy()

        segment.reset_index(drop=True, inplace=True)

        print(
            f"[CSVReader] Segment selected: "
            f"{start_time}s → {end_time}s | Rows: {len(segment)}"
        )

        return segment

    def get_column(self, column_name):
        """
        Return any column from the CSV.
        """

        if column_name not in self.df.columns:
            raise ValueError(f"[CSVReader] Column '{column_name}' not found")

        print(f"[CSVReader] Accessing column: {column_name}")

        return self.df[column_name]


# =====================================================
# WAVEFORM CONTROLLER
# =====================================================

class WaveformController:
    """
    Controls Digilent WaveForms hardware and generates signals.
    Depends on CSVReader.
    """

    def __init__(self, csv_reader):

        self.csv = csv_reader
        self.device_handle = ctypes.c_int(0)

        # --------------------------------
        # Load WaveForms SDK
        # --------------------------------

        if platform.startswith("win"):
            self.dwf = ctypes.cdll.dwf
            constants_path = "C:" + sep + "Program Files (x86)" + sep + "Digilent" + sep + "WaveFormsSDK" + sep + "samples" + sep + "py"

        elif platform.startswith("darwin"):
            self.dwf = ctypes.cdll.LoadLibrary("/Library/Frameworks/dwf.framework/dwf")
            constants_path = "/Applications/WaveForms.app/Contents/Resources/SDK/samples/py"

        else:
            self.dwf = ctypes.cdll.LoadLibrary("libdwf.so")
            constants_path = "/usr/share/digilent/waveforms/samples/py"

        path.append(constants_path)

        global constants
        import dwfconstants as constants

        self.constants = constants


    def start(self):
        """
        Opens Digilent device.
        """

        self.dwf.FDwfDeviceOpen(
            ctypes.c_int(-1),
            ctypes.byref(self.device_handle)
        )

        if self.device_handle.value == 0:
            time.sleep(0.1)
            # raise RuntimeError("Failed to open WaveForms device")

        print("Device opened.\n")


    def generate(self, channel, function, offset,
             frequency=1000, amplitude=1, symmetry=50):

        ch = ctypes.c_int(channel - 1)

        # Enable carrier node
        self.dwf.FDwfAnalogOutNodeEnableSet(
            self.device_handle,
            ch,
            self.constants.AnalogOutNodeCarrier,
            ctypes.c_bool(True)
        )

        # Set waveform function
        self.dwf.FDwfAnalogOutNodeFunctionSet(
            self.device_handle,
            ch,
            self.constants.AnalogOutNodeCarrier,
            function
        )

        # Set amplitude
        self.dwf.FDwfAnalogOutNodeAmplitudeSet(
            self.device_handle,
            ch,
            self.constants.AnalogOutNodeCarrier,
            ctypes.c_double(amplitude)
        )

        # Set offset
        self.dwf.FDwfAnalogOutNodeOffsetSet(
            self.device_handle,
            ch,
            self.constants.AnalogOutNodeCarrier,
            ctypes.c_double(offset)
        )

        # Set frequency
        self.dwf.FDwfAnalogOutNodeFrequencySet(
            self.device_handle,
            ch,
            self.constants.AnalogOutNodeCarrier,
            ctypes.c_double(frequency)
        )

        # Start waveform output
        self.dwf.FDwfAnalogOutConfigure(
            self.device_handle,
            ch,
            ctypes.c_bool(True)
        )

    def play_column(self, column, start_time, end_time, channel=1):
        """
        Generate waveform based on any CSV column.
        """

        segment = self.csv.get_segment(start_time, end_time)

        print(f"Segment rows: {len(segment)}")
        print("Looping...\n")

        while True:

            previous_time = None

            for _, row in segment.iterrows():

                value = row[column]
                current_time_us = row["cycle_start_us"]

                if value <= 0:
                    continue

                freq_hz = (value / 60.0) * 32
                freq_hz = max(freq_hz, 1)

                self.generate(
                    channel=channel,
                    function=self.constants.funcSquare,
                    offset=2.5,
                    frequency=freq_hz,
                    amplitude=2.5,
                    symmetry=50
                )

                if previous_time is not None:

                    delta_us = current_time_us - previous_time
                    sleep_time = delta_us / 1_000_000.0

                    if 0 < sleep_time < 1:
                        time.sleep(sleep_time)

                previous_time = current_time_us

                print(f"\r{column}: {value:.0f} | Hz: {freq_hz:.1f}", end="")


    def constant_engine_rpm(self, rpm, channel=1):

        freq_hz = (rpm / 60.0) * 32

        self.generate(
            channel=channel,
            function=self.constants.funcSquare,
            offset=2.5,
            frequency=freq_hz,
            amplitude=2.5,
            symmetry=50
        )

        print(f"Constant RPM: {rpm} | Frequency: {freq_hz:.2f} Hz")


START_TIME = 74
END_TIME = 88

CSV_FILE = "log_2025-06-01_20-50-58.csv"

