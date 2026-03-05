import can
import struct
import time
import csv
import threading
import os


class ODriveCAN:

    NODE_IDS = [0x01, 0x03]
    COM_PORT = "COM15"
    BITRATE = 250000

    CSV_PREFIX = "odrive_log_"
    CSV_DIR = "csvs"

    DEFAULT_VEL_LIMIT = 100.0
    DEFAULT_CURRENT_SOFT_MAX = 20.0

    CAN_GET_ENCODER_ESTIMATES = 0x09
    CAN_GET_IQ = 0x14
    CAN_GET_BUS_VOLTAGE_CURRENT = 0x17
    CAN_GET_ERRORS = 0x03

    CAN_SET_AXIS_STATE = 0x07
    CAN_SET_CONTROLLER_MODES = 0x0B
    CAN_SET_INPUT_POS = 0x0C
    CAN_SET_INPUT_VEL = 0x0D
    CAN_SET_INPUT_TORQUE = 0x0E
    CAN_SET_LIMITS = 0x0F

    AXIS_STATE_IDLE = 1
    AXIS_STATE_CLOSED_LOOP_CONTROL = 8

    CONTROL_MODE_TORQUE = 1
    CONTROL_MODE_VELOCITY = 2
    CONTROL_MODE_POSITION = 3

    INPUT_MODE_PASSTHROUGH = 1

    def __init__(self):

        os.makedirs(self.CSV_DIR, exist_ok=True)

        self.bus = can.Bus(interface="slcan", channel=self.COM_PORT, bitrate=self.BITRATE)

        self.running = False

        # Live telemetry state
        self.state = {
            node: {
                "pos": None,
                "vel": None,
                "iq": None,
                "bus_v": None,
                "bus_i": None,
                "axis_err": None
            }
            for node in self.NODE_IDS
        }

        # Command setpoints
        self.setpoints = {
            node: {
                "pos": None,
                "vel": None,
                "iq": None
            }
            for node in self.NODE_IDS
        }

    # ------------------------------------------------
    # CAN UTILITIES
    # ------------------------------------------------

    def _arb(self, node, cmd):
        return (node << 5) | cmd

    def _send(self, node, cmd, payload=b""):
        msg = can.Message(
            arbitration_id=self._arb(node, cmd),
            data=payload.ljust(8, b"\x00"),
            is_extended_id=False
        )
        self.bus.send(msg)

    # ------------------------------------------------
    # INITIALIZATION
    # ------------------------------------------------

    def start(self):

        for node in self.NODE_IDS:

            self.set_idle(node)
            time.sleep(0.05)

            self.set_limits(node,
                            self.DEFAULT_VEL_LIMIT,
                            self.DEFAULT_CURRENT_SOFT_MAX)

            time.sleep(0.05)

            self._set_controller_mode(node,
                                      self.CONTROL_MODE_VELOCITY,
                                      self.INPUT_MODE_PASSTHROUGH)

            time.sleep(0.05)

            self._set_axis_state(node,
                                 self.AXIS_STATE_CLOSED_LOOP_CONTROL)

        self.running = True

        threading.Thread(
            target=self._logging_loop,
            daemon=True
        ).start()

    # ------------------------------------------------
    # INTERNAL COMMANDS
    # ------------------------------------------------

    def _set_axis_state(self, node, state):
        self._send(node,
                   self.CAN_SET_AXIS_STATE,
                   struct.pack("<I", state))

    def _set_controller_mode(self, node, control, input_mode):
        self._send(node,
                   self.CAN_SET_CONTROLLER_MODES,
                   struct.pack("<II", control, input_mode))

    # ------------------------------------------------
    # PUBLIC CONTROL FUNCTIONS
    # ------------------------------------------------

    def set_idle(self, node):
        self._set_axis_state(node, self.AXIS_STATE_IDLE)

    def set_velocity(self, node, velocity):

        self.setpoints[node]["vel"] = velocity

        self._set_controller_mode(node,
                                  self.CONTROL_MODE_VELOCITY,
                                  self.INPUT_MODE_PASSTHROUGH)

        self._send(node,
                   self.CAN_SET_INPUT_VEL,
                   struct.pack("<ff", velocity, 0.0))

    def set_torque(self, node, torque):

        self.setpoints[node]["iq"] = torque

        self._set_controller_mode(node,
                                  self.CONTROL_MODE_TORQUE,
                                  self.INPUT_MODE_PASSTHROUGH)

        self._send(node,
                   self.CAN_SET_INPUT_TORQUE,
                   struct.pack("<f", torque))

    def set_position(self, node, pos):

        self.setpoints[node]["pos"] = pos

        self._set_controller_mode(node,
                                  self.CONTROL_MODE_POSITION,
                                  self.INPUT_MODE_PASSTHROUGH)

        self._send(node,
                   self.CAN_SET_INPUT_POS,
                   struct.pack("<fhh", pos, 0, 0))

    # ------------------------------------------------
    # LIMITS
    # ------------------------------------------------

    def set_limits(self, node, vel_limit, current_soft_max):

        self._send(node,
                   self.CAN_SET_LIMITS,
                   struct.pack("<ff", vel_limit, current_soft_max))

    def set_current_soft_max(self, node, amps):

        self.set_limits(node,
                        self.DEFAULT_VEL_LIMIT,
                        amps)

    def set_velocity_limit(self, node, vel):

        self.set_limits(node,
                        vel,
                        self.DEFAULT_CURRENT_SOFT_MAX)

    # ------------------------------------------------
    # CAN PARSER
    # ------------------------------------------------

    def _parse(self, msg):

        node = (msg.arbitration_id >> 5) & 0x3F
        cmd = msg.arbitration_id & 0x1F

        if node not in self.state:
            return

        data = msg.data
        s = self.state[node]

        if cmd == self.CAN_GET_ENCODER_ESTIMATES:
            s["pos"], = struct.unpack("<f", data[0:4])
            s["vel"], = struct.unpack("<f", data[4:8])

        elif cmd == self.CAN_GET_IQ:
            s["iq"], = struct.unpack("<f", data[4:8])

        elif cmd == self.CAN_GET_BUS_VOLTAGE_CURRENT:
            s["bus_v"], = struct.unpack("<f", data[0:4])
            s["bus_i"], = struct.unpack("<f", data[4:8])

        elif cmd == self.CAN_GET_ERRORS:
            s["axis_err"], = struct.unpack("<I", data[4:8])

    # ------------------------------------------------
    # LOGGING THREAD
    # ------------------------------------------------

    def _logging_loop(self):

        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        csv_filename = os.path.join(self.CSV_DIR, f"{self.CSV_PREFIX}{timestamp}.csv")

        start_time = time.time()

        with open(csv_filename, "w", newline="") as f:

            writer = csv.writer(f)

            writer.writerow([
                "time_s",
                "od1_setpoint_pos",
                "od1_setpoint_vel",
                "od1_setpoint_iq",
                "od1_pos",
                "od1_vel",
                "od1_iq",
                "od1_bus_v",
                "od1_bus_i",
                "od1_axis_err",
                "od2_setpoint_pos",
                "od2_setpoint_vel",
                "od2_setpoint_iq",
                "od2_pos",
                "od2_vel",
                "od2_iq",
                "od2_bus_v",
                "od2_bus_i",
                "od2_axis_err",
            ])

            f.flush()

            print(f"[Logger] Writing to {csv_filename}")

            while self.running:

                try:

                    msg = self.bus.recv(timeout=0.01)

                    if msg:
                        self._parse(msg)

                    t = time.time() - start_time

                    s1 = self.state[self.NODE_IDS[0]]
                    s2 = self.state[self.NODE_IDS[1]]

                    sp1 = self.setpoints[self.NODE_IDS[0]]
                    sp2 = self.setpoints[self.NODE_IDS[1]]

                    writer.writerow([
                        t,
                        sp1["pos"], sp1["vel"], sp1["iq"],
                        s1["pos"], s1["vel"], s1["iq"],
                        s1["bus_v"], s1["bus_i"], s1["axis_err"],
                        sp2["pos"], sp2["vel"], sp2["iq"],
                        s2["pos"], s2["vel"], s2["iq"],
                        s2["bus_v"], s2["bus_i"], s2["axis_err"],
                    ])

                    f.flush()

                except Exception as e:
                    print("[Logger] error:", e)
                    time.sleep(0.05)