# database.py
import os
from sqlalchemy import create_engine
from config import DB_CONFIG  # config.pyにDB設定があると仮定

# SQLAlchemyのEngineを作成（これがコネクションプールなどを管理してくれます）
# 接続文字列の例: mysql+pymysql://user:password@host/db_name
DATABASE_URL = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}/{DB_CONFIG['database']}"

engine = create_engine(
    DATABASE_URL,
    pool_recycle=3600, # 接続切れ対策
    echo=False         # SQLログを出したい場合はTrue
)

def get_engine():
    return engine
