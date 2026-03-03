from ad2 import CSVReader, WaveformController
from can_controller import ODriveCAN


# --------------------------------
# USER SETTINGS
# --------------------------------

CSV_FILE = "log_2025-06-01_20-50-58.csv"

START_TIME = 74
END_TIME = 88

ENGINE_RPM_COLUMN = "engine_rpm"


# --------------------------------
# MAIN
# --------------------------------

def main():

    # --------------------------------
    # Initialize CSV reader
    # --------------------------------
    csv_reader = CSVReader(CSV_FILE)

    # --------------------------------
    # Initialize waveform generator
    # --------------------------------
    wave = WaveformController(csv_reader)

    wave.start()

    # --------------------------------
    # Initialize CAN motor controller
    # --------------------------------
    can = ODriveCAN()

    can.start()

    # --------------------------------
    # Example commands
    # --------------------------------

    # set torque example
    # can.set_torque(0x01, 5)

    # set velocity example
    # can.set_velocity(0x03, 20)

    # --------------------------------
    # Run waveform playback
    # --------------------------------

    wave.play_column(
        column=ENGINE_RPM_COLUMN,
        start_time=START_TIME,
        end_time=END_TIME,
        channel=1
    )

    # --------------------------------
    # Alternative: constant RPM
    # --------------------------------

    # wave.constant_engine_rpm(3500)


# --------------------------------
# ENTRY POINT
# --------------------------------

if __name__ == "__main__":
    main()