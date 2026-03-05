import time
import math
import pandas as pd


MOTOR_KV = 140.0
TORQUE_CONSTANT = 60.0 / (2 * math.pi * MOTOR_KV)


class TorqueSimulator:

    def __init__(self, can_controller, wave_controller, csv_reader, node_id=0x01):

        self.can = can_controller
        self.wave = wave_controller
        self.csv_reader = csv_reader
        self.node_id = node_id

        print("[TorqueSim] Loading CSV")

        self.df = pd.read_csv(self.csv_reader.csv_file)
        self.df.columns = self.df.columns.str.strip()

        required = [
            "cycle_start_us",
            "engine_rpm",
            "iq_measured"
        ]

        for col in required:
            if col not in self.df.columns:
                raise ValueError(f"CSV missing column: {col}")

        print(f"[TorqueSim] Rows loaded: {len(self.df)}")


    def start(self):

        previous_time = None

        print("[TorqueSim] Starting synchronized playback")

        for _, row in self.df.iterrows():

            rpm = row["engine_rpm"]
            iq = row["iq_measured"]
            current_time = row["cycle_start_us"]

            if rpm <= 0:
                continue


            freq_hz = (rpm / 60.0) * 32

            self.wave.generate(
                channel=1,
                function=self.wave.constants.funcSquare,
                offset=2.5,
                frequency=freq_hz,
                amplitude=2.5,
                symmetry=50
            )

            if not pd.isna(iq):
                torque_nm = iq * TORQUE_CONSTANT
                self.can.set_torque(self.node_id, float(torque_nm))
            else:
                torque_nm = 0

            if previous_time is not None:

                delta_us = current_time - previous_time
                sleep_time = delta_us / 1_000_000.0

                if 0 < sleep_time < 1:
                    time.sleep(sleep_time)

            previous_time = current_time

            print(
                f"\rRPM {rpm:.0f} | Hz {freq_hz:.1f} | "
                f"Iq {iq:.2f}A | Torque {torque_nm:.3f}Nm",
                end=""
            )

        print("\n[TorqueSim] Playback complete")