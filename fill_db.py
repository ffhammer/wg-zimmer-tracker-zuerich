from src.database import check_for_new_data_and_update
from src.logger import logger

logger.success(check_for_new_data_and_update())
