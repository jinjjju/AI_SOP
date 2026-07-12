from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

engine = create_engine(
    config.DATABASE_URL,
    # timeout: 호출 카운터 등 짧은 별도 세션이 잠깐의 락에 바로 죽지 않도록 대기
    connect_args={"check_same_thread": False, "timeout": 30}
    if config.DATABASE_URL.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate():
    """경량 마이그레이션 — 기존 SQLite DB에 새로 추가된 컬럼을 ALTER TABLE로 채운다.

    create_all은 새 테이블만 만들고 기존 테이블의 신규 컬럼은 추가하지 않으므로,
    모델과 실제 테이블 스키마를 비교해 빠진 컬럼을 기본값과 함께 추가한다.
    (main.py 기동 시와 seed.py에서 호출)"""
    from sqlalchemy import inspect, text

    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(engine.dialect)
                ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}"
                default = column.default.arg if column.default is not None else None
                if isinstance(default, (int, float)):
                    ddl += f" DEFAULT {default}"
                elif isinstance(default, str):
                    ddl += f" DEFAULT '{default}'"
                conn.execute(text(ddl))
