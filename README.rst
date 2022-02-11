toh264
======

A simple single-file self-contained wrapper around ffmpeg.

Installation
------------

The easy way
~~~~~~~~

Just copy the ``toh264.py`` to any place in your filesystem.


The pip way
~~~~~~~~~~~

Run ``pip install .`` from this directory or run
``pip install git+https://github.com/turlando/toh264.git@v0.0.1``


Usage
-----

::

    usage: toh264 [-h] [-f] -i PATH -o PATH [-fps FPS]
                  [-s WIDTHxHEIGHT | -sw WIDTH | -sh HEIGHT]
		  (-crf CRF | -t SIZE) -ab BITRATE [-m]
    options:
      -h, --help            show this help message and exit

    general behaviour:
      -f, --force           Overwrite output file if it exists (default: False)

    files:
      -i PATH, --in PATH    Input file
      -o PATH, --out PATH   Output file

    video:
      -fps FPS, --frames-per-second FPS
			    Frames per second (default: 30)
      -s WIDTHxHEIGHT, --scale WIDTHxHEIGHT
			    Resolution
      -sw WIDTH, --scale-width WIDTH
			    Resolution width
      -sh HEIGHT, --scale-height HEIGHT
			    Resolution height
      -crf CRF, --constant-rate-factor CRF
			    CRF value between 0 and 51
      -t SIZE, --target-size SIZE
			    Desired file size in MB

    audio:
      -ab BITRATE, --audio-bitrate BITRATE
			    Audio bitrate in kbps
      -m, --mono            Downmix audio to mono (default: False)
