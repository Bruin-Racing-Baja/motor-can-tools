import ctypes
import time
import pandas as pd
from sys import platform, path
from os import sep


# =====================================================
# CSV READER
# =====================================================

class CSVReader:
    """
    Handles loading and querying CSV telemetry.
    """

    def __init__(self, filepath):
        # Load CSV
        self.filepath = filepath
        self.df = pd.read_csv(filepath)

        # Normalize column names
        self.df.columns = self.df.columns.str.strip()

        # Convert timestamp to seconds if present
        if "cycle_start_us" in self.df.columns:
            self.df["cycle_start_s"] = self.df["cycle_start_us"] / 1_000_000.0

    def get_segment(self, start_time, end_time):
        """
        Return dataframe slice between start and end time.
        """

        segment = self.df[
            (self.df["cycle_start_s"] >= start_time) &
            (self.df["cycle_start_s"] <= end_time)
        ].copy()

        segment.reset_index(drop=True, inplace=True)

        return segment

    def get_column(self, column_name):
        """
        Return any column from the CSV.
        """

        if column_name not in self.df.columns:
            raise ValueError(f"Column '{column_name}' not found")

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

    # -------------------------------------------------
    # DEVICE START
    # -------------------------------------------------

    def start(self):
        """
        Opens Digilent device.
        """

        self.dwf.FDwfDeviceOpen(
            ctypes.c_int(-1),
            ctypes.byref(self.device_handle)
        )

        if self.device_handle.value == 0:
            raise RuntimeError("Failed to open WaveForms device")

        print("Device opened.\n")

    # -------------------------------------------------
    # WAVEFORM GENERATOR
    # -------------------------------------------------

    def generate(self, channel, function, offset,
                 frequency=1000, amplitude=1, symmetry=50):

        channel = ctypes.c_int(channel - 1)

        self.dwf.FDwfAnalogOutNodeEnableSet(
            self.device_handle,
            channel,
            self.constants.AnalogOutNodeCarrier,
            ctypes.c_bool(True)
        )

        self.dwf.FDwfAnalogOutNodeFunctionSet(
            self.device_handle,
            channel,
            self.constants.AnalogOutNodeCarrier,
            function
        )

        self.dwf.FDwfAnalogOutNodeFrequencySet(
            self.device_handle,
            channel,
            self.constants.AnalogOutNodeCarrier,
            ctypes.c_double(frequency)
        )

        self.dwf.FDwfAnalogOutNodeAmplitudeSet(
            self.device_handle,
            channel,
            self.constants.AnalogOutNodeCarrier,
            ctypes.c_double(amplitude)
        )

        self.dwf.FDwfAnalogOutNodeOffsetSet(
            self.device_handle,
            channel,
            self.constants.AnalogOutNodeCarrier,
            ctypes.c_double(offset)
        )

        self.dwf.FDwfAnalogOutNodeSymmetrySet(
            self.device_handle,
            channel,
            self.constants.AnalogOutNodeCarrier,
            ctypes.c_double(symmetry)
        )

        self.dwf.FDwfAnalogOutConfigure(
            self.device_handle,
            channel,
            ctypes.c_bool(True)
        )

    # -------------------------------------------------
    # PLAYBACK FROM CSV COLUMN
    # -------------------------------------------------

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

                # Convert RPM -> Hz for crank sensor simulation
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

    # -------------------------------------------------
    # CONSTANT RPM MODE
    # -------------------------------------------------

    def constant_engine_rpm(self, rpm, channel=1):
        """
        Generate constant RPM signal.
        """

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


# =====================================================
# USER SETTINGS
# =====================================================

START_TIME = 74
END_TIME = 88

CSV_FILE = "log_2025-06-01_20-50-58.csv"


# =====================================================
# MAIN PROGRAM
# =====================================================

if __name__ == "__main__":

    # Initialize CSV reader
    csv_reader = CSVReader(CSV_FILE)

    # Initialize waveform controller
    wave = WaveformController(csv_reader)

    # Start Digilent device
    wave.start()

    # ---------------------------------
    # OPTION 1: Playback CSV engine RPM
    # ---------------------------------

    wave.play_column(
        column="engine_rpm",
        start_time=START_TIME,
        end_time=END_TIME,
        channel=1
    )

    # ---------------------------------
    # OPTION 2: Constant RPM
    # ---------------------------------
    # wave.constant_engine_rpm(3500)