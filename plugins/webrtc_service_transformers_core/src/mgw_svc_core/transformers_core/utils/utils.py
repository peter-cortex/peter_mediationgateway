
import logging

from pathlib import Path
import urllib.request

logger = logging.getLogger("utils")

# This code is based on https://github.com/streamlit/demo-self-driving/blob/230245391f2dda0cb464008195a470751c01770b/streamlit_app.py#L48  # noqa: E501
def download_file(url, download_to: Path, expected_size=None):
    # Don't download the file twice.
    # (If possible, verify the download using the file length.)
    if download_to.exists():
        if expected_size:
            if download_to.stat().st_size == expected_size:
                return

    download_to.parent.mkdir(parents=True, exist_ok=True)

    logger.warning("Downloading %s..." % url)
    with open(download_to, "wb") as output_file:
        with urllib.request.urlopen(url) as response:
            length = int(response.info()["Content-Length"])
            counter = 0.0
            MEGABYTES = 2.0 ** 20.0
            while True:
                data = response.read(8192)
                if not data:
                    break
                counter += len(data)
                output_file.write(data)

class CustomFormatter(logging.Formatter):

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)