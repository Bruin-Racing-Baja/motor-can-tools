import time

from ad2 import CSVReader, WaveformController
from can_controller import ODriveCAN
from torque_sim import TorqueSimulator


CSV_FILE = "log_2025-06-01_20-50-58.csv"
NODE_ID = 0x01


def main():

    print("\n===== Baja Dyno Simulator =====\n")


    csv_reader = CSVReader(CSV_FILE)


    wave = WaveformController(csv_reader)
    wave.start()

    can = ODriveCAN()
    can.start()

    sim = TorqueSimulator(
        can_controller=can,
        wave_controller=wave,
        csv_reader=csv_reader,
        node_id=NODE_ID
    )

    sim.start()

    # Keep program alive
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()