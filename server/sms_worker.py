#!/usr/bin/env python3
"""Detached SMS reply worker (process mode).

Used when SMS_ASYNC_MODE=process (PythonAnywhere uWSGI has threads disabled).
Railway defaults to SMS_ASYNC_MODE=thread and does not need this script.
"""
from __future__ import annotations

import base64
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("sms_worker")


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    if len(argv) < 2:
        logger.error("usage: sms_worker.py <phone> <base64-body>")
        return 2

    phone_number = argv[0]
    try:
        body = base64.b64decode(argv[1].encode("ascii")).decode("utf-8")
    except Exception:
        logger.exception("invalid base64 body")
        return 2

    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        os.chdir(here)
    except OSError:
        pass

    # Railway / local: flask_app.py. PA may also expose sproutMe.py.
    try:
        from flask_app import _sms_reply_worker
    except ImportError:
        from sproutMe import _sms_reply_worker  # type: ignore

    logger.info("sms worker start for %s", phone_number[-4:] if phone_number else "")
    _sms_reply_worker(phone_number, body)
    logger.info("sms worker done for %s", phone_number[-4:] if phone_number else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
