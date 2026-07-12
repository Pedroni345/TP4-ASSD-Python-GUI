import serial
import struct
import matplotlib.pyplot as plt

PORT = "COM6"     # replace with your ST-Link VCP port (Device Manager / ls /dev/tty*)
BAUD = 115200
N_SAMPLES = 512

ser = serial.Serial(PORT, BAUD, timeout=2)

plt.ion()
fig, (ax_v, ax_i) = plt.subplots(2, 1, sharex=True)

line_v, = ax_v.plot(range(N_SAMPLES), [0] * N_SAMPLES, color="tab:blue")
ax_v.set_ylim(-32768, 32767)
ax_v.set_ylabel("I (raw)")

line_i, = ax_i.plot(range(N_SAMPLES), [0] * N_SAMPLES, color="tab:orange")
ax_i.set_ylim(32768, -32767)
ax_i.set_ylabel("V (raw)")
ax_i.set_xlabel("sample")

HEADER = bytes.fromhex("AA55AA55")
BLOCK_BYTES = N_SAMPLES * 2          # bytes per channel block (int16)
FRAME_BYTES = BLOCK_BYTES * 2        # V block + I block


def read_frame():
    # sync to the 4-byte header
    buf = b""
    while True:
        b = ser.read(1)
        if not b:
            return None
        buf = (buf + b)[-4:]
        if buf == HEADER:
            break

    data = ser.read(FRAME_BYTES)
    if len(data) != FRAME_BYTES:
        return None

    # first half of the payload is V, second half is I
    v_samples = struct.unpack("<%dh" % N_SAMPLES, data[:BLOCK_BYTES])
    i_samples = struct.unpack("<%dh" % N_SAMPLES, data[BLOCK_BYTES:])
    return v_samples, i_samples


while True:
    frame = read_frame()
    if frame:
        v_samples, i_samples = frame
        line_v.set_ydata(v_samples)
        line_i.set_ydata(i_samples)
        ax_v.relim()
        ax_v.autoscale_view()
        ax_i.relim()
        ax_i.autoscale_view()
        fig.canvas.draw()
        fig.canvas.flush_events()
