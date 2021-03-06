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
import json
import logging
import re
import sys
import subprocess

from dataclasses import dataclass, field
from enum import Enum
from math import floor, log10
from pathlib import Path
from typing import Optional, Union


###############################################################################

Second = int
Microsecond = int
Byte = int
Kilobit = int
Megabyte = int
KilobitPerSecond = int
FramesPerSecond = int
Width = int
Height = int


###############################################################################

DEV_NULL = Path('/dev/null')
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


LOG_LEVEL_COLOR: LogLevelToAnsiCode = {
    logging.CRITICAL: AnsiCode.RED,
    logging.ERROR: AnsiCode.RED,
    logging.WARNING: AnsiCode.YELLOW,
    logging.INFO: AnsiCode.GREEN,
    logging.DEBUG: AnsiCode.CYAN
}


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

    def __str__(self) -> str:
        return "{}.{}".format(self.seconds, self.microseconds)


@dataclass
class Resolution:
    width: Width
    height: Height


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

def run(
        *args: str,
        capture_output=False,
        log_cmd=False
) -> subprocess.CompletedProcess:
    arg_stdout = subprocess.PIPE if capture_output is True else None
    arg_stderr = subprocess.PIPE if capture_output is True else None

    with subprocess.Popen(
            args,
            encoding='utf-8',
            stdout=arg_stdout,
            stderr=arg_stderr
    ) as process:
        if log_cmd is True:
            cmd = ' '.join(process.args)  # type: ignore
            log.debug(f"Running: {cmd}")

        stdout, stderr = process.communicate()
        process.wait()

    return subprocess.CompletedProcess(
        process.args, process.returncode,
        stdout, stderr
    )


def ffmpeg(*args: str) -> subprocess.CompletedProcess:
    return run(FFMPEG_BIN.as_posix(), *args, log_cmd=True)


def ffprobe(*args: str) -> subprocess.CompletedProcess:
    return run(FFPROBE_BIN.as_posix(), *args, capture_output=True)


###############################################################################

# *sighs*
# The MediaInfo type represents the information returned by ffprobe encoded as
# JSON. We're not really doing any type checking here given that its structure
# is very dynamic. We're using this type in order to track the data flow.
MediaInfo = dict

def get_media_info(path: Path) -> MediaInfo:
    process = ffprobe(
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format', '-show_streams',
        path.as_posix()
    )

    return json.loads(process.stdout)


def get_duration(info: MediaInfo) -> Duration:
    duration_str = info['format']['duration']
    return Duration(*[int(s) for s in duration_str.split('.')])


def get_resolution(info: MediaInfo) -> Resolution:
    width = info['streams'][0]['width']
    height = info['streams'][0]['height']
    return Resolution(width, height)


###############################################################################

@dataclass
class FfmpegOnePassOptions:
    options: list[str] = field(default_factory=list)


@dataclass
class FfmpegTwoPassOptions:
    first_pass_options: list[str] = field(default_factory=list)
    second_pass_options: list[str] = field(default_factory=list)


FfmpegOptions = Union[FfmpegOnePassOptions, FfmpegTwoPassOptions]


def run_ffmpeg(options: FfmpegOptions):
    if isinstance(options, FfmpegOnePassOptions):
        ffmpeg(*options.options)
        return

    if isinstance(options, FfmpegTwoPassOptions):
        log.info("Running first pass")
        ffmpeg(*options.first_pass_options)
        log.info("Running second pass")
        ffmpeg(*options.second_pass_options)
        return


###############################################################################

@dataclass
class VideoConfig:
    frames_per_second: Optional[int]
    resolution: Optional[Resolution]
    resolution_width: Optional[Width]
    resolution_height: Optional[Height]


@dataclass
class ConstantRateFactorConfig:
    crf: int


@dataclass
class TwoPassConfig:
    target_size: Megabyte


H264Config = Union[ConstantRateFactorConfig, TwoPassConfig]


@dataclass
class AudioConfig:
    mono: bool
    bitrate: KilobitPerSecond


@dataclass
class TranscodingConfig:
    input_path: Path
    output_path: Path
    video_config: VideoConfig
    h264_config: H264Config
    audio_config: AudioConfig


###############################################################################

FFMPEG_QUIET_OPTIONS = ['-loglevel', 'warning', '-stats', '-y']
H264_CODEC_OPTIONS = ['-c:v', 'libx264']
PIX_FMT_OPTIONS = ['-pix_fmt', 'yuv420p']
AAC_CODEC_OPTIONS = ['-c:a', 'aac']
H264_PROFILE_OPTIONS = ['-profile:v', 'high']
H264_PRESET_OPTIONS = ['-preset', 'veryslow']
MP4_OPTIONS = ['-movflags', '+faststart']
FIRST_PASS_OPTIONS = ['-pass', '1']
SECOND_PASS_OPTIONS = ['-pass', '2']
NO_AUDIO_OPTIONS = ['-an']
NULL_CONTAINER_OPTIONS = ['-f', 'null']


def input_options(path: Path):
    return ['-i', path.as_posix()]


def output_options(path: Path):
    return [path.as_posix()]


def fps_filter_options(fps: Optional[FramesPerSecond]):
    return [f'fps={fps}'] if fps is not None else []


def resolution_filter_options(
        resolution: Optional[Resolution],
        resolution_width: Optional[Width],
        resolution_height: Optional[Height]
):
    if resolution is not None:
        return [f'scale={resolution.width}:{resolution.height}']
    if resolution_width is not None:
        return [f'scale={resolution_width}:-1']
    if resolution_height is not None:
        return [f'scale=-1:{resolution_height}']
    return []


def filter_options(
        fps: Optional[FramesPerSecond],
        resolution: Optional[Resolution],
        resolution_width: Optional[Width],
        resolution_height: Optional[Height]
):
    filters = [
        *fps_filter_options(fps),
        *resolution_filter_options(resolution, resolution_width, resolution_height)
    ]

    if len(filters) == 0:
        return []

    filters_str = ",".join(filters)
    return ['-filter:v', filters_str]


def h264_crf_options(crf: KilobitPerSecond):
    return [*H264_CODEC_OPTIONS, '-crf', str(crf)]


def h264_twopass_options(bitrate: KilobitPerSecond):
    return [*H264_CODEC_OPTIONS, '-b:v', f'{bitrate}k']


def aac_options(bitrate: KilobitPerSecond, mono: bool):
    return [*AAC_CODEC_OPTIONS,
            '-b:a', f'{bitrate}k',
            *(['-ac', '1'] if mono is True else [])]


###############################################################################

def config_to_options(
        config: TranscodingConfig,
        media_info: MediaInfo
) -> FfmpegOptions:
    if isinstance(config.h264_config, ConstantRateFactorConfig):
        log.info("Transcoding in constant rate factor mode")

        return FfmpegOnePassOptions([
            *FFMPEG_QUIET_OPTIONS,
            *input_options(config.input_path),
            *filter_options(
                config.video_config.frames_per_second,
                config.video_config.resolution,
                config.video_config.resolution_width,
                config.video_config.resolution_height
            ),
            *h264_crf_options(config.h264_config.crf),
            *PIX_FMT_OPTIONS,
            *aac_options(config.audio_config.bitrate, config.audio_config.mono),
            *H264_PROFILE_OPTIONS,
            *H264_PRESET_OPTIONS,
            *MP4_OPTIONS,
            *output_options(config.output_path)
        ])

    if isinstance(config.h264_config, TwoPassConfig):
        log.info("Transcoding in two-pass mode")

        duration = get_duration(media_info)
        total_bitrate = to_kbps(megabytes_to_bytes(config.h264_config.target_size),
                                duration)
        video_bitrate = total_bitrate - config.audio_config.bitrate

        log.info(f"Video duration: {duration} s")
        log.info(f"Target size: {config.h264_config.target_size} MB")
        log.info(f"Target bitrate: {total_bitrate} kbps")
        log.info(f"Audio bitrate: {config.audio_config.bitrate} kbps")
        log.info(f"Video bitrate: {video_bitrate} kbps")

        return FfmpegTwoPassOptions([
            *FFMPEG_QUIET_OPTIONS,
            *input_options(config.input_path),
            *filter_options(
                config.video_config.frames_per_second,
                config.video_config.resolution,
                config.video_config.resolution_width,
                config.video_config.resolution_height
            ),
            *h264_twopass_options(video_bitrate),
            *PIX_FMT_OPTIONS,
            *FIRST_PASS_OPTIONS,
            *H264_PROFILE_OPTIONS,
            *NO_AUDIO_OPTIONS,
            *NULL_CONTAINER_OPTIONS,
            *output_options(DEV_NULL)
        ], [
            *FFMPEG_QUIET_OPTIONS,
            *input_options(config.input_path),
            *filter_options(
                config.video_config.frames_per_second,
                config.video_config.resolution,
                config.video_config.resolution_width,
                config.video_config.resolution_height
            ),
            *h264_twopass_options(video_bitrate),
            *PIX_FMT_OPTIONS,
            *SECOND_PASS_OPTIONS,
            *aac_options(config.audio_config.bitrate, config.audio_config.mono),
            *H264_PROFILE_OPTIONS,
            *output_options(config.output_path)
        ])


###############################################################################

class ArgumentDefaultsHelpFormatter(argparse.HelpFormatter):
    def _get_help_string(self, action):
        if action.default is argparse.SUPPRESS:
            return action.help
        if action.default is None:
            return action.help
        return action.help + ' (default: %(default)s)'


class ResolutionArgParseAction(argparse.Action):
    PATTERN = re.compile(r'(\d+)x(\d+)')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __call__(self, parser, namespace, resolution, option_string=None):
        match = self.PATTERN.fullmatch(resolution)
        if match is None:
            parser.error(f"Provided value {resolution} is not a valid "
                         f"resolution in the WIDTHxHEIGHT format.")
        else:
            setattr(namespace, self.dest,
                    Resolution(int(match.group(1)), int(match.group(2))))


###############################################################################

def make_argument_parser():
    parser = argparse.ArgumentParser(
        formatter_class=ArgumentDefaultsHelpFormatter
    )

    ###########################################################################

    behavior_group = parser.add_argument_group("general behaviour")

    behavior_group.add_argument(
        '-f', '--force',
        action='store_true',
        default=False,
        help="Overwrite output file if it exists",
        dest='force'
    )

    ###########################################################################

    io_group = parser.add_argument_group("files")

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

    video_group = parser.add_argument_group("video")

    video_group.add_argument(
        '-fps', '--frames-per-second',
        default=30,
        type=int,
        help="Frames per second",
        metavar='FPS',
        dest='frames_per_second'
    )

    ###########################################################################

    scale_group = video_group.add_mutually_exclusive_group()

    scale_group.add_argument(
        '-s', '--scale',
        action=ResolutionArgParseAction,
        help="Resolution",
        metavar='WIDTHxHEIGHT',
        dest='resolution'
    )

    scale_group.add_argument(
        '-sw', '--scale-width',
        type=Width,
        help="Resolution width",
        metavar='WIDTH',
        dest='resolution_width'
    )

    scale_group.add_argument(
        '-sh', '--scale-height',
        type=Height,
        help="Resolution height",
        metavar='HEIGHT',
        dest='resolution_height'
    )

    ###########################################################################

    h264_group = video_group.add_mutually_exclusive_group(required=True)

    h264_group.add_argument(
        '-crf', '--constant-rate-factor',
        type=int,
        choices=range(0, 51 + 1),
        help="CRF value between 0 and 51",
        metavar='CRF',
        dest='constant_rate_factor'
    )

    h264_group.add_argument(
        '-t', '--target-size',
        type=int,
        help="Desired file size in MB",
        metavar='SIZE',
        dest='target_size'
    )

    ###########################################################################

    audio_group = parser.add_argument_group("audio")

    audio_group.add_argument(
        '-ab', '--audio-bitrate',
        type=int,
        required=True,
        help="Audio bitrate in kbps",
        metavar='BITRATE',
        dest='audio_bitrate'
    )

    audio_group.add_argument(
        '-m', '--mono',
        action='store_true',
        default=False,
        help="Downmix audio to mono",
        dest='audio_mono'
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

    ###########################################################################

    if args.input_path.is_file() is False:
        fatal("Input file does not exist or is not a file.")

    if args.input_path == args.output_path:
        fatal("Input file and output file can't be the same.")

    if args.output_path.exists() is True and args.force is False:
        fatal("Output file exists. If you want to overwrite it use --force.")

    ###########################################################################

    media_info = get_media_info(args.input_path)
    file_resolution = get_resolution(media_info)

    if (
        args.resolution is not None
        and file_resolution.width % args.resolution.width != 0
        and file_resolution.height % args.resolution.height != 0
    ):
        fatal("Specified resolution does not keep the aspect ratio.")

    ###########################################################################

    config = TranscodingConfig(
        input_path=args.input_path,
        output_path=args.output_path,
        video_config=VideoConfig(
            frames_per_second=args.frames_per_second,
            resolution=args.resolution,
            resolution_width=args.resolution_width,
            resolution_height=args.resolution_height
        ),
        h264_config=(
            ConstantRateFactorConfig(crf=args.constant_rate_factor)
            if args.constant_rate_factor is not None
            else TwoPassConfig(target_size=args.target_size)
        ),
        audio_config=AudioConfig(
            mono=args.audio_mono,
            bitrate=args.audio_bitrate
        )
    )

    ffmpeg_options = config_to_options(config, media_info)

    run_ffmpeg(ffmpeg_options)


###############################################################################

if __name__ == '__main__':
    main()
