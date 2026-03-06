import time
import math
import pandas as pd


START_TIME = 74
END_TIME = 88

MOTOR_KV = 140.0
TORQUE_CONSTANT = 60.0 / (2 * math.pi * MOTOR_KV)


class TorqueSimulator:

    def __init__(self, can_controller, wave_controller, csv_reader):

        self.can = can_controller
        self.wave = wave_controller
        self.csv_reader = csv_reader

        print("[TorqueSim] Loading CSV")

        df = self.csv_reader.df.copy()
        df.columns = df.columns.str.strip()

        df["cycle_start_s"] = df["cycle_start_us"] / 1_000_000.0

        df = df[
            (df["cycle_start_s"] >= START_TIME) &
            (df["cycle_start_s"] <= END_TIME)
        ].copy()

        df.reset_index(drop=True, inplace=True)

        self.df = df

        print(f"[TorqueSim] Playback rows: {len(self.df)}")

    def start(self):

        previous_time = None

        print("[TorqueSim] Starting synchronized playback")

        for _, row in self.df.iterrows():

            rpm = row["engine_rpm"]
            vel_cmd = row["velocity_command"]
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


            if not pd.isna(vel_cmd):
                self.can.set_velocity(0x01, float(vel_cmd))


            if not pd.isna(iq):

                torque_nm = iq * TORQUE_CONSTANT
                self.can.set_torque(0x03, float(torque_nm))

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
                f"VelCmd {vel_cmd:.2f} | "
                f"Iq {iq:.2f}A | Torque {torque_nm:.3f}Nm",
                end=""
            )

        print("\n[TorqueSim] Playback complete")

        # hold rpm signal
        print("[TorqueSim] Holding RPM at 3000")
        
        self.wave.constant_engine_rpm(3000, channel=1)

        # idle motors
        print("[TorqueSim] Setting motors to IDLE")
        self.can.set_idle(0x01)
        self.can.set_idle(0x03)