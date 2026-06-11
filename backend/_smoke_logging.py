import asyncio
import logging

import main  # noqa: F401 — full app wiring incl. setup_logging()
from config.logging_config import request_id_var


async def t():
    request_id_var.set("req-test1")
    logging.getLogger("botbeam.auth").info("smoke line inside request context")


asyncio.run(t())
logging.getLogger("botbeam").info("smoke line outside request context")
print("IMPORT-OK")
