from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import logging
from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    select,
    func,
)
from sqlalchemy.exc import SQLAlchemyError

DB_CONFIG = {
    'host': 'postgres',
    'port': 5432,
    'database': 'postgres',
    'username': 'postgres',
    'password': 'postgres'
}

DATABASE_URL = f"postgresql://{DB_CONFIG['username']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
logger = logging.getLogger(__name__)


class MetricLogger:
    _instance: Optional["MetricLogger"] = None
    _engine = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        db_url: Optional[str] = None,
        table_name: str = "agent_metrics",
        pool_pre_ping: bool = True,
        pool_size: int = 5,
        max_overflow: int = 10,
    ):
        if hasattr(self, "_initialized"):
            return

        self.db_url = db_url or DATABASE_URL
        self.table_name = table_name

        if MetricLogger._engine is None:
            MetricLogger._engine = create_engine(
                self.db_url,
                pool_pre_ping=pool_pre_ping,
                pool_size=pool_size,
                max_overflow=max_overflow,
                echo=False,
            )
        self.engine = MetricLogger._engine

        self.metadata = MetaData()
        self.table = Table(
            self.table_name,
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("timestamp", DateTime(timezone=True), nullable=False, index=True),
            Column("llm", String(100), nullable=False, index=True),
            Column("metric", String(100), nullable=False, index=True),
            Column("value", Float, nullable=False),
        )

        try:
            self.metadata.create_all(self.engine)
            logger.info(f"Tabla {self.table_name} verificada/creada")
        except SQLAlchemyError as e:
            logger.error(f"Error creando tabla {self.table_name}: {e}")
            raise

        self._initialized = True

    @contextmanager
    def _get_connection(self):
        with self.engine.begin() as conn:
            yield conn

    def log_metric(
        self, timestamp: datetime, llm: str, metric: str, value: float
    ) -> bool:
        stmt = self.table.insert().values(
            timestamp=timestamp, llm=llm, metric=metric, value=value
        )
        try:
            with self._get_connection() as conn:
                conn.execute(stmt)
            logger.debug(f"Métrica registrada: {llm}.{metric} = {value}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error registrando métrica: {e}")
            return False

    def dispose(self) -> None:
        if self.engine:
            self.engine.dispose()
            logger.info("Engine disposed.")
