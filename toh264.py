#!/usr/bin/env python

# Copyright 2022 Tancredi Orlando <tancredi.orlando@gmail.com>
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

###############################################################################

import argparse
import logging
import sys
import subprocess

from dataclasses import dataclass
from enum import Enum
from math import floor, log10
from pathlib import Path

###############################################################################

Second = int
Microsecond = int
Byte = int
Kilobit = int
Megabyte = int
KilobitPerSecond = int

###############################################################################

FFMPEG_BIN = Path('/usr/bin/ffmpeg')
FFPROBE_BIN = Path('/usr/bin/ffprobe')

###############################################################################

class AnsiCode(Enum):
    DEFAULT = '\x1b[0m'
    RED = '\x1b[31m'
    GREEN = '\x1b[32m'
    YELLOW = '\x1b[33m'
    CYAN = '\x1b[36m'


LogLevelToAnsiCode = dict[int, AnsiCode]

LOG_LEVEL_COLOR: LogLevelToAnsiCode = {
    logging.CRITICAL: AnsiCode.RED,
    logging.ERROR: AnsiCode.RED,
    logging.WARNING: AnsiCode.YELLOW,
    logging.INFO: AnsiCode.GREEN,
    logging.DEBUG: AnsiCode.CYAN
}


class AnsiLoggingStreamHandler(logging.StreamHandler):
    # Overriding from logging.Handler(Filtered)
    def format(self, record: logging.LogRecord) -> str:
        level = record.levelno
        text = super().format(record)
        color = self.mapping[level].value
        return color + text + AnsiCode.DEFAULT.value

    # Overriding from logging.StreamHandler(Handler)
    def __init__(self, mapping: LogLevelToAnsiCode):
        self.mapping = mapping
        super().__init__(stream=None)


LOG_FORMAT = "%(levelname).1s: %(message)s"

logging.basicConfig(
    format=LOG_FORMAT,
    handlers=[AnsiLoggingStreamHandler(LOG_LEVEL_COLOR)]
)

log = logging.getLogger()
log.setLevel(logging.DEBUG)

###############################################################################

@dataclass
class Duration:
    seconds: Second
    microseconds: Microsecond

    def to_seconds(self) -> Second:
        return self.seconds + round(decimal_to_float(self.microseconds))

###############################################################################

def bytes_to_kilobits(size: Byte) -> Kilobit:
    return round(size * 8 / 1000)


def megabytes_to_bytes(size: Megabyte) -> Byte:
    return size * 10**6


def decimal_to_float(decimal: int) -> float:
    """Convert 123 into 0.123"""
    return decimal * 10 ** (- (floor(log10(decimal)) + 1))


def to_kbps(size: Byte, duration: Duration) -> KilobitPerSecond:
    return round(bytes_to_kilobits(size) / duration.to_seconds())

###############################################################################

def run(*args: str) -> subprocess.CompletedProcess:
    with subprocess.Popen(
            args,
            encoding='utf-8',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
    ) as process:
        cmd = ' '.join(process.args)  # type: ignore
        log.info(f"Running: {cmd}")
        stdout, stderr = process.communicate()
        process.wait()

    return subprocess.CompletedProcess(
        process.args, process.returncode,
        stdout, stderr
    )


def ffmpeg(*args: str) -> subprocess.CompletedProcess:
    return run(FFMPEG_BIN.as_posix(), *args)


def ffprobe(*args: str) -> subprocess.CompletedProcess:
    return run(FFPROBE_BIN.as_posix(), *args)

###############################################################################

def get_duration(path: Path) -> Duration:
    process = ffprobe(
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        path.as_posix()
    )

    return Duration(*[int(s) for s in process.stdout.strip().split('.')])

###############################################################################

def constant_rate_factor_transcoding(
        input_path: Path,
        output_path: Path,
        frame_per_seconds: int,
        constant_rate_factor: int,
        audio_bitrate: KilobitPerSecond,
        audio_mono: bool
):
    ffmpeg(
        '-loglevel', 'warning', '-stats',
        '-y',
        '-i', input_path.as_posix(),
        '-filter:v', f'fps={frame_per_seconds}',
        '-c:v', 'libx264', '-crf', str(constant_rate_factor),
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', f'{audio_bitrate}k',
        *(['-ac', '1'] if audio_mono is True else []),
        '-profile:v', 'high', '-preset', 'veryslow',
        '-movflags', '+faststart',
        output_path.as_posix()
    )

###############################################################################

def two_pass_transcoding(
        input_path: Path,
        output_path: Path,
        frame_per_seconds: int,
        target_size: Megabyte,
        audio_bitrate: KilobitPerSecond,
        audio_mono: bool
):
    duration = get_duration(input_path)
    total_bitrate = to_kbps(megabytes_to_bytes(target_size), duration)
    video_bitrate = total_bitrate - audio_bitrate

    ffmpeg(
        '-loglevel', 'warning', '-stats',
        '-y',
        '-i', input_path.as_posix(),
        '-filter:v', f'fps={frame_per_seconds}',
        '-c:v', 'libx264', '-b:v', f'{video_bitrate}k',
        '-pix_fmt', 'yuv420p',
        '-pass', '1',
        '-profile:v', 'high', '-preset', 'veryslow',
        '-an',
        '-f', 'null', '/dev/null'
    )

    ffmpeg(
        '-loglevel', 'warning', '-stats',
        '-y',
        '-i', input_path.as_posix(),
        '-filter:v', f'fps={frame_per_seconds}',
        '-c:v', 'libx264', '-b:v', f'{video_bitrate}k',
        '-pix_fmt', 'yuv420p',
        '-pass', '2',
        '-c:a', 'aac', '-b:a', f'{audio_bitrate}k',
        *(['-ac', '1'] if audio_mono is True else []),
        '-profile:v', 'high', '-preset', 'veryslow',
        '-movflags', '+faststart',
        output_path.as_posix()
    )

###############################################################################

class ArgumentDefaultsHelpFormatter(argparse.HelpFormatter):
    def _get_help_string(self, action):
        if action.default is argparse.SUPPRESS:
            return action.help
        if action.default is None:
            return action.help
        return action.help + ' (default: %(default)s)'


def make_argument_parser():
    parser = argparse.ArgumentParser(
        formatter_class=ArgumentDefaultsHelpFormatter
    )

    ###########################################################################

    behavior_group = parser.add_argument_group("General behaviour")

    behavior_group.add_argument(
        '-f', '--force',
        action='store_true',
        default=False,
        help="Overwrite output file if it exists",
        dest='force'
    )

    ###########################################################################

    io_group = parser.add_argument_group("Files")

    io_group.add_argument(
        '-i', '--in',
        type=Path,
        required=True,
        help="Input file",
        metavar='PATH',
        dest='input_path'
    )

    io_group.add_argument(
        '-o', '--out',
        type=Path,
        required=True,
        help="Output file",
        metavar='PATH',
        dest='output_path'
    )

    ###########################################################################

    encoder_group = parser.add_argument_group("Encoding")

    encoder_group.add_argument(
        '-fps', '--frame-per-seconds',
        default=30,
        type=int,
        help="Frame per seconds",
        metavar='FPS',
        dest='frame_per_seconds'
    )

    encoder_group.add_argument(
        '-ab', '--audio-bitrate',
        type=int,
        required=True,
        help="Audio bitrate in kbps",
        metavar='BITRATE',
        dest='audio_bitrate'
    )

    encoder_group.add_argument(
        '-m', '--mono',
        action='store_true',
        default=False,
        help="Downmix audio to mono",
        dest='audio_mono'
    )

    ###########################################################################

    video_group = encoder_group.add_mutually_exclusive_group(required=True)

    video_group.add_argument(
        '-crf', '--constant-rate-factor',
        type=int,
        choices=range(1, 51 + 1),
        help="CRF value between 0 and 51",
        metavar='CRF',
        dest='constant_rate_factor'
    )

    video_group.add_argument(
        '-s', '--target-size',
        type=int,
        help="Desired file size in MB",
        metavar='SIZE',
        dest='target_size'
    )

    ###########################################################################

    return parser

###############################################################################

def fatal(message: str):
    log.error(message)
    sys.exit(1)


def main():
    argument_parser = make_argument_parser()
    args = argument_parser.parse_args()

    if args.input_path.is_file() is False:
        fatal("Input file does not exist or is not a file.")

    if args.input_path == args.output_path:
        fatal("Input file and output file can't be the same.")

    if args.output_path.exists() is True and args.force is False:
        fatal("Output file exists. If you want to overwrite it use --force.")

    if args.constant_rate_factor is not None:
        return constant_rate_factor_transcoding(
            args.input_path, args.output_path,
            args.frame_per_seconds, args.constant_rate_factor,
            args.audio_bitrate, args.audio_mono
        )

    if args.target_size is not None:
        return two_pass_transcoding(
            args.input_path, args.output_path,
            args.frame_per_seconds, args.target_size,
            args.audio_bitrate, args.audio_mono
        )

###############################################################################

if __name__ == '__main__':
    main()
