import os
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import tkinter as tk
from tkinter import ttk
from matplotlib.widgets import Slider, CheckButtons

CSV_PREFIX = "odrive_log_"
CSV_DIR = "csvs"
REFRESH_HZ = 20
WINDOW_MIN = 1.0
WINDOW_MAX = 60.0

os.makedirs(CSV_DIR, exist_ok=True)

def list_logs():
    return sorted(
        [
            os.path.join(CSV_DIR, f)
            for f in os.listdir(CSV_DIR)
            if f.startswith(CSV_PREFIX) and f.endswith(".csv")
        ],
        key=os.path.getmtime,
        reverse=True
    )

def main():
    root = tk.Tk()
    root.title("ODrive Log Selector")
    root.geometry("420x300")

    selected_log = tk.StringVar(value="<LIVE>")

    frame = ttk.Frame(root)
    frame.pack(fill="both", expand=True, padx=10, pady=10)

    ttk.Label(frame, text="Select Log").pack(anchor="w")

    list_frame = ttk.Frame(frame)
    list_frame.pack(fill="both", expand=True)

    scrollbar = ttk.Scrollbar(list_frame)
    scrollbar.pack(side="right", fill="y")

    listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, height=12)
    listbox.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=listbox.yview)

    def refresh_logs():
        listbox.delete(0, tk.END)
        listbox.insert(tk.END, "<LIVE>")
        for log in list_logs():
            listbox.insert(tk.END, os.path.basename(log))

    refresh_logs()

    def on_select(_):
        sel = listbox.curselection()
        if sel:
            selected_log.set(listbox.get(sel[0]))

    listbox.bind("<<ListboxSelect>>", on_select)
    ttk.Button(frame, text="Refresh", command=refresh_logs).pack(pady=5)

    plt.ion()
    fig, axes = plt.subplots(3, 2, sharex=True, figsize=(14, 9))
    plt.subplots_adjust(left=0.06, right=0.96, top=0.90, bottom=0.30)

    ax_pos_1, ax_pos_2 = axes[0]
    ax_vel_1, ax_vel_2 = axes[1]
    ax_iq_1,  ax_iq_2  = axes[2]

    lines = {
        ("od1", "pos"): ax_pos_1.plot([], [], lw=1)[0],
        ("od1", "vel"): ax_vel_1.plot([], [], lw=1)[0],
        ("od1", "iq"):  ax_iq_1.plot([], [], lw=1)[0],
        ("od2", "pos"): ax_pos_2.plot([], [], lw=1)[0],
        ("od2", "vel"): ax_vel_2.plot([], [], lw=1)[0],
        ("od2", "iq"):  ax_iq_2.plot([], [], lw=1)[0],
    }

    sp_lines = {
        ("od1", "pos"): ax_pos_1.plot([], [], "k--", lw=1)[0],
        ("od1", "vel"): ax_vel_1.plot([], [], "k--", lw=1)[0],
        ("od1", "iq"):  ax_iq_1.plot([], [], "k--", lw=1)[0],
        ("od2", "pos"): ax_pos_2.plot([], [], "k--", lw=1)[0],
        ("od2", "vel"): ax_vel_2.plot([], [], "k--", lw=1)[0],
        ("od2", "iq"):  ax_iq_2.plot([], [], "k--", lw=1)[0],
    }

    ax_pos_1.set_title("ODrive 1")
    ax_pos_2.set_title("ODrive 2")
    ax_pos_1.set_ylabel("Position")
    ax_vel_1.set_ylabel("Velocity")
    ax_iq_1.set_ylabel("Current / Torque")
    ax_iq_1.set_xlabel("Time (s)")
    ax_iq_2.set_xlabel("Time (s)")

    slider_ax = plt.axes([0.18, 0.16, 0.58, 0.045])
    window_slider = Slider(
        ax=slider_ax,
        label="Time Window (log)",
        valmin=0.0,
        valmax=1.0,
        valinit=0.5
    )

    log_min = np.log10(WINDOW_MIN)
    log_max = np.log10(WINDOW_MAX)

    def slider_to_seconds(p):
        return float(10 ** (log_min + p * (log_max - log_min)))

    window_text = fig.text(0.5, 0.22, "", ha="center")

    check_ax = plt.axes([0.80, 0.145, 0.16, 0.10])
    checks = CheckButtons(check_ax, ["Full log"], [False])

    def full_log_enabled():
        return bool(checks.get_status()[0])

    def update_window_text():
        if full_log_enabled():
            window_text.set_text("Window: FULL LOG")
        else:
            window_text.set_text(
                f"Window: last {slider_to_seconds(window_slider.val):.2f}s"
            )

    window_slider.on_changed(lambda _: update_window_text())
    checks.on_clicked(lambda _: update_window_text())
    update_window_text()

    def on_click(event):
        if selected_log.get() == "<LIVE>" or event.inaxes not in axes.flatten():
            return

        ax = event.inaxes
        var = "pos" if ax in (ax_pos_1, ax_pos_2) else \
              "vel" if ax in (ax_vel_1, ax_vel_2) else "iq"
        od = "od1" if ax in (ax_pos_1, ax_vel_1, ax_iq_1) else "od2"

        csv_path = os.path.join(CSV_DIR, selected_log.get())
        df = pd.read_csv(csv_path)

        fig2, ax2 = plt.subplots(figsize=(8, 4))
        ax2.plot(df["time_s"], df[f"{od}_{var}"], label="measured")

        sp_col = f"{od}_setpoint_{var}"
        if sp_col in df:
            ax2.plot(df["time_s"], df[sp_col], "k--", label="setpoint")

        ax2.legend()
        ax2.set_title(f"{selected_log.get()} — {od.upper()} {var}")
        ax2.set_xlabel("Time (s)")
        ax2.grid(True)
        plt.show()

    fig.canvas.mpl_connect("button_press_event", on_click)

    while True:
        try:
            root.update()

            logs = list_logs()
            if not logs:
                time.sleep(0.2)
                continue

            csv_file = (
                logs[0]
                if selected_log.get() == "<LIVE>"
                else os.path.join(CSV_DIR, selected_log.get())
            )

            if not os.path.exists(csv_file):
                time.sleep(0.2)
                continue

            df = pd.read_csv(csv_file)

            if not full_log_enabled():
                w = slider_to_seconds(window_slider.val)
                tmax = df["time_s"].max()
                df = df[df["time_s"] >= tmax - w]

            for od in ("od1", "od2"):
                for var in ("pos", "vel", "iq"):
                    lines[(od, var)].set_data(df["time_s"], df[f"{od}_{var}"])
                    sp_col = f"{od}_setpoint_{var}"
                    if sp_col in df:
                        sp_lines[(od, var)].set_data(df["time_s"], df[sp_col])

            for ax in axes.flatten():
                ax.relim()
                ax.autoscale_view()

            fig.suptitle(f"ODrive Viewer\n{os.path.basename(csv_file)}", fontsize=12)
            fig.canvas.draw_idle()
            fig.canvas.flush_events()
            time.sleep(1.0 / REFRESH_HZ)

        except Exception as e:
            print("Plotter error:", e)
            time.sleep(0.5)

if __name__ == "__main__":
    main()