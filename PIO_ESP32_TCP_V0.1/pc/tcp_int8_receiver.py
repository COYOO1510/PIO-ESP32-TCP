#!/usr/bin/env python3
"""Receive framed signed int8 samples from the ESP32 TCP sender."""

from __future__ import annotations

import argparse
import csv
import socket
import struct
import time
from pathlib import Path


ESP32_HOST = "192.168.5.46"
PC_LOCAL_HOST = "192.168.5.2"
TCP_PORT = 5000

FRAME_MAGIC = 0xA55A
FRAME_DATA_SIZE = 8
FRAME_STRUCT = struct.Struct(f"<HII{FRAME_DATA_SIZE}b")
FRAME_MAGIC_BYTES = struct.pack("<H", FRAME_MAGIC)

PRINT_RECEIVED_FRAMES = True


def pop_frames(rx_stream: bytearray) -> list[tuple[int, int, tuple[int, ...]]]:
    frames: list[tuple[int, int, tuple[int, ...]]] = []

    while True:
        magic_index = rx_stream.find(FRAME_MAGIC_BYTES)
        if magic_index < 0:
            if len(rx_stream) > 1:
                del rx_stream[:-1]
            return frames

        if magic_index > 0:
            del rx_stream[:magic_index]

        if len(rx_stream) < FRAME_STRUCT.size:
            return frames

        frame_bytes = rx_stream[: FRAME_STRUCT.size]
        magic, frame_index, micros_time, *data = FRAME_STRUCT.unpack(frame_bytes)
        if magic != FRAME_MAGIC:
            del rx_stream[0]
            continue

        frames.append((frame_index, micros_time, tuple(data)))
        del rx_stream[: FRAME_STRUCT.size]


def print_frame(frame_index: int, micros_time: int, sample_start_index: int, data: tuple[int, ...]) -> None:
    sample_end_index = sample_start_index + len(data) - 1
    text = ", ".join(str(value) for value in data)
    print(
        f"frame[{frame_index}] micros={micros_time} us "
        f"data[{sample_start_index}..{sample_end_index}]: {text}"
    )


def run() -> None:
    parser = argparse.ArgumentParser(description="ESP32 TCP framed int8 receiver")
    parser.add_argument(
        "host",
        nargs="?",
        default=ESP32_HOST,
        help=f"ESP32 IP address, default: {ESP32_HOST}",
    )
    parser.add_argument("-p", "--port", type=int, default=TCP_PORT, help=f"TCP port, default: {TCP_PORT}")
    parser.add_argument(
        "--bind",
        default=PC_LOCAL_HOST,
        help=f"local PC IP address to bind, default: {PC_LOCAL_HOST}",
    )
    parser.add_argument("-b", "--buffer-size", type=int, default=65536, help="socket receive buffer")
    parser.add_argument("-l", "--limit", type=int, default=0, help="stop after N data samples, 0 means unlimited")
    parser.add_argument("--csv", type=Path, help="optional CSV file for parsed frame data")
    parser.add_argument("--raw", type=Path, help="optional raw binary output file")
    args = parser.parse_args()

    rx_buffer = bytearray(args.buffer_size)
    rx_stream = bytearray()
    total_frames = 0
    total_samples = 0
    total_bytes = 0
    report_frames = 0
    report_samples = 0
    report_bytes = 0
    start_time = time.perf_counter()
    report_time = start_time

    csv_file = args.csv.open("w", newline="") if args.csv else None
    raw_file = args.raw.open("wb") if args.raw else None

    try:
        csv_writer = csv.writer(csv_file) if csv_file else None
        if csv_writer:
            csv_writer.writerow(["frame_index", "micros_us", "sample_index", "value"])

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(10)
            if args.bind:
                sock.bind((args.bind, 0))
            sock.connect((args.host, args.port))
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, args.buffer_size)
            sock.settimeout(2)
            print(f"Connected from {sock.getsockname()[0]} to {args.host}:{args.port}")
            print(
                f"Frame format: magic=0x{FRAME_MAGIC:04X}, "
                f"frame_size={FRAME_STRUCT.size} bytes, data_size={FRAME_DATA_SIZE}"
            )

            while args.limit <= 0 or total_samples < args.limit:
                bytes_read = sock.recv_into(rx_buffer)
                if bytes_read == 0:
                    print("Connection closed by ESP32")
                    break

                view = memoryview(rx_buffer)[:bytes_read]
                if raw_file:
                    raw_file.write(view)

                rx_stream.extend(view)
                frames = pop_frames(rx_stream)

                for frame_index, micros_time, data in frames:
                    if args.limit > 0 and total_samples >= args.limit:
                        break

                    sample_start_index = total_samples

                    if PRINT_RECEIVED_FRAMES:
                        print_frame(frame_index, micros_time, sample_start_index, data)

                    if csv_writer:
                        csv_writer.writerows(
                            (frame_index, micros_time, sample_start_index + offset, value)
                            for offset, value in enumerate(data)
                        )

                    total_frames += 1
                    total_samples += len(data)
                    report_frames += 1
                    report_samples += len(data)

                total_bytes += bytes_read
                report_bytes += bytes_read

                now = time.perf_counter()
                if now - report_time >= 1.0:
                    elapsed = now - report_time
                    mbps = report_bytes * 8 / elapsed / 1_000_000
                    frames_per_second = report_frames / elapsed
                    ksps = report_samples / elapsed / 1000
                    print(
                        f"{total_frames:,} frames | {total_samples:,} samples | "
                        f"{frames_per_second:,.1f} frame/s | "
                        f"{ksps:,.1f} ksample/s | {mbps:.2f} Mbit/s"
                    )
                    report_frames = 0
                    report_samples = 0
                    report_bytes = 0
                    report_time = now

    finally:
        if csv_file:
            csv_file.close()
        if raw_file:
            raw_file.close()

    elapsed_total = time.perf_counter() - start_time
    if elapsed_total > 0:
        print(
            f"Done: {total_frames:,} frames, {total_samples:,} samples, "
            f"{total_bytes * 8 / elapsed_total / 1_000_000:.2f} Mbit/s average"
        )


if __name__ == "__main__":
    run()
