from app.config import get_settings
from app.services.trading_worker import run_trading_worker
from app.utils.logger import configure_logger


if __name__ == "__main__":
    configure_logger()
    run_trading_worker(get_settings())
