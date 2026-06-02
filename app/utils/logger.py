from loguru import logger


def configure_logger() -> None:
    logger.remove()
    logger.add(
        "logs/trading-bot.log",
        rotation="10 MB",
        retention="14 days",
        level="INFO",
        enqueue=True,
    )
    logger.add(lambda msg: print(msg, end=""), level="INFO")


__all__ = ["configure_logger", "logger"]

