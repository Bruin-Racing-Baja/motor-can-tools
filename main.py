from ad2 import CSVReader, WaveformController
from can_controller import ODriveCAN
from torque_sim import TorqueSimulator

import time


CSV_FILE = "log_2025-06-01_20-50-58.csv"

NODE_IDS = [0x01, 0x03]

CURRENT_LIMIT = 12
VELOCITY_LIMIT = 40.0


def main():

    print("\n===== Baja Dyno Simulator =====\n")

    # ---------------------------
    # CSV reader
    # ---------------------------

    csv_reader = CSVReader(CSV_FILE)

    # ---------------------------
    # AD2 waveform controller
    # ---------------------------

    wave = WaveformController(csv_reader)
    wave.start()

    # ---------------------------
    # CAN controller
    # ---------------------------

    can = ODriveCAN()
    can.start()

    # ---------------------------
    # Apply safety limits
    # ---------------------------

    print("[MAIN] Setting current and velocity limits")

    for node in NODE_IDS:

        can.set_limits(
            node,
            vel_limit=VELOCITY_LIMIT,
            current_soft_max=CURRENT_LIMIT
        )

        print(f"[MAIN] Node {node} → {CURRENT_LIMIT}A , {VELOCITY_LIMIT} T/s")

    time.sleep(0.2)

    # ---------------------------
    # Start simulator
    # ---------------------------

    sim = TorqueSimulator(
        can_controller=can,
        wave_controller=wave,
        csv_reader=csv_reader
    )

    sim.start()



if __name__ == "__main__":
    main()