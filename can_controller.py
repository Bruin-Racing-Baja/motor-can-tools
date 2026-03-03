import can
import struct
import time
import csv
import threading
import sys
import os

NODE_IDS = [0x01, 0x03]
COM_PORT = "COM15"
BITRATE = 250000

PRINT_CAN = False

CONSTANT_POSITION = "position"
CONSTANT_VELOCITY = "velocity"
CONSTANT_TORQUE   = "torque"

CONTROL_MODE = CONSTANT_VELOCITY

DEFAULT_VEL_LIMIT = 100.0
DEFAULT_CURRENT_SOFT_MAX = 20.0

CSV_PREFIX = "odrive_log_"
CSV_DIR = "csvs"

os.makedirs(CSV_DIR, exist_ok=True)

CAN_GET_ENCODER_ESTIMATES     = 0x09
CAN_GET_IQ                   = 0x14
CAN_GET_BUS_VOLTAGE_CURRENT  = 0x17
CAN_GET_ERRORS               = 0x03

CAN_SET_AXIS_STATE           = 0x07
CAN_SET_CONTROLLER_MODES     = 0x0B
CAN_SET_INPUT_POS            = 0x0C
CAN_SET_INPUT_VEL            = 0x0D
CAN_SET_INPUT_TORQUE         = 0x0E
CAN_SET_LIMITS               = 0x0F

AXIS_STATE_IDLE = 1
AXIS_STATE_CLOSED_LOOP_CONTROL = 8

CONTROL_MODE_TORQUE   = 1
CONTROL_MODE_VELOCITY = 2
CONTROL_MODE_POSITION = 3

INPUT_MODE_PASSTHROUGH = 1

state = {
    node_id: {
        "pos": None,
        "vel": None,
        "iq": None,
        "bus_v": None,
        "bus_i": None,
        "axis_err": None,
    }
    for node_id in NODE_IDS
}

setpoints = {
    node_id: {
        "pos": None,
        "vel": None,
        "iq": None,
    }
    for node_id in NODE_IDS
}

current_limits = {
    node_id: {
        "vel_limit": DEFAULT_VEL_LIMIT,
        "current_soft_max": DEFAULT_CURRENT_SOFT_MAX,
    }
    for node_id in NODE_IDS
}

def make_arbitration_id(node_id, cmd_id):
    return (node_id << 5) | cmd_id

def send_can(bus, node_id, cmd_id, payload=b""):
    msg = can.Message(
        arbitration_id=make_arbitration_id(node_id, cmd_id),
        data=payload.ljust(8, b"\x00"),
        is_extended_id=False
    )
    bus.send(msg)

def set_axis_state(bus, node_id, axis_state):
    send_can(bus, node_id, CAN_SET_AXIS_STATE, struct.pack("<I", axis_state))

def set_controller_mode(bus, node_id, control_mode, input_mode):
    send_can(bus, node_id, CAN_SET_CONTROLLER_MODES, struct.pack("<II", control_mode, input_mode))

def set_limits(bus, node_id, vel_limit, current_soft_max):
    send_can(bus, node_id, CAN_SET_LIMITS, struct.pack("<ff", vel_limit, current_soft_max))
    current_limits[node_id]["vel_limit"] = vel_limit
    current_limits[node_id]["current_soft_max"] = current_soft_max

def clear_setpoints(node_id):
    setpoints[node_id]["pos"] = None
    setpoints[node_id]["vel"] = None
    setpoints[node_id]["iq"]  = None

def send_command(bus, node_id, value):
    clear_setpoints(node_id)

    if CONTROL_MODE == CONSTANT_POSITION:
        setpoints[node_id]["pos"] = value
        send_can(bus, node_id, CAN_SET_INPUT_POS, struct.pack("<fhh", value, 0, 0))

    elif CONTROL_MODE == CONSTANT_VELOCITY:
        setpoints[node_id]["vel"] = value
        send_can(bus, node_id, CAN_SET_INPUT_VEL, struct.pack("<ff", value, 0.0))

    elif CONTROL_MODE == CONSTANT_TORQUE:
        setpoints[node_id]["iq"] = value
        send_can(bus, node_id, CAN_SET_INPUT_TORQUE, struct.pack("<f", value))

def parse_odrive_message(msg):
    node_id = (msg.arbitration_id >> 5) & 0x3F
    if node_id not in state:
        return

    cmd_id = msg.arbitration_id & 0x1F
    data = msg.data
    s = state[node_id]

    if cmd_id == CAN_GET_ENCODER_ESTIMATES:
        s["pos"], = struct.unpack("<f", data[0:4])
        s["vel"], = struct.unpack("<f", data[4:8])

    elif cmd_id == CAN_GET_IQ:
        s["iq"], = struct.unpack("<f", data[4:8])

    elif cmd_id == CAN_GET_BUS_VOLTAGE_CURRENT:
        s["bus_v"], = struct.unpack("<f", data[0:4])
        s["bus_i"], = struct.unpack("<f", data[4:8])

    elif cmd_id == CAN_GET_ERRORS:
        s["axis_err"], = struct.unpack("<I", data[4:8])

def input_thread(bus):
    while True:
        line = sys.stdin.readline().strip()
        if not line:
            continue

        parts = line.split(",")

        try:
            od_idx = int(parts[0]) - 1
        except:
            continue

        if od_idx < 0 or od_idx >= len(NODE_IDS):
            continue

        node_id = NODE_IDS[od_idx]

        if parts[1].lower() == "i":
            set_axis_state(bus, node_id, AXIS_STATE_IDLE)
            clear_setpoints(node_id)
            continue

        if parts[1].lower() == "c":
            try:
                new_current = float(parts[2])
            except:
                continue

            vel_limit = current_limits[node_id]["vel_limit"]
            set_limits(bus, node_id, vel_limit, new_current)
            continue

        try:
            value = float(parts[1])
        except:
            continue

        send_command(bus, node_id, value)

def main():
    bus = can.Bus(interface="slcan", channel=COM_PORT, bitrate=BITRATE)

    for node_id in NODE_IDS:
        set_axis_state(bus, node_id, AXIS_STATE_IDLE)
        time.sleep(0.05)

        set_limits(bus, node_id, DEFAULT_VEL_LIMIT, DEFAULT_CURRENT_SOFT_MAX)
        time.sleep(0.05)

        set_controller_mode(bus, node_id, CONTROL_MODE_VELOCITY, INPUT_MODE_PASSTHROUGH)
        time.sleep(0.05)

        set_axis_state(bus, node_id, AXIS_STATE_CLOSED_LOOP_CONTROL)

    threading.Thread(target=input_thread, args=(bus,), daemon=True).start()

    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    csv_filename = os.path.join(CSV_DIR, f"{CSV_PREFIX}{timestamp}.csv")

    start_time = time.time()

    with open(csv_filename, "w", newline="") as f:
        writer = csv.writer(f)

        writer.writerow([
            "time_s",
            "od1_setpoint_vel",
            "od1_pos",
            "od1_vel",
            "od1_iq",
            "od1_bus_v",
            "od1_bus_i",
            "od1_axis_err",
            "od2_setpoint_vel",
            "od2_pos",
            "od2_vel",
            "od2_iq",
            "od2_bus_v",
            "od2_bus_i",
            "od2_axis_err",
        ])

        while True:

            try:
                msg = bus.recv(timeout=0.01)
            except ValueError:
               continue
            if msg:
                parse_odrive_message(msg)

            t = time.time() - start_time

            s1 = state[NODE_IDS[0]]
            s2 = state[NODE_IDS[1]]
            sp1 = setpoints[NODE_IDS[0]]
            sp2 = setpoints[NODE_IDS[1]]

            writer.writerow([
                t,
                sp1["vel"],
                s1["pos"], s1["vel"], s1["iq"],
                s1["bus_v"], s1["bus_i"], s1["axis_err"],
                sp2["vel"],
                s2["pos"], s2["vel"], s2["iq"],
                s2["bus_v"], s2["bus_i"], s2["axis_err"],
            ])

            f.flush()

if __name__ == "__main__":
    main()