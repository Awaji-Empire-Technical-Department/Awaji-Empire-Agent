# services/database.py
# Why: DB操作は最大の副作用であり、services/ に配置する。
#      将来的にこの中身が Rust ブリッジ（database_bridge）へのコネクタに置き換わる。
import os
from sqlalchemy import create_engine


def _build_database_url() -> str:
    """環境変数からDB接続URLを構築する。

    Why: config.py の DB_CONFIG に依存するのではなく、環境変数を直接参照する設計に統一。
         config.py は Discord Bot 固有の設定（チャンネル名等）に限定し、
         DB接続情報は .env から取得する方針。
    """
    user = os.getenv('DB_USER', 'root')
    password = os.getenv('DB_PASS', '')
    host = os.getenv('DB_HOST', '127.0.0.1')
    database = os.getenv('DB_NAME', 'bot_db')
    return f"mysql+pymysql://{user}:{password}@{host}/{database}"


engine = create_engine(
    _build_database_url(),
    pool_recycle=3600,  # 接続切れ対策
    echo=False          # SQLログを出したい場合はTrue
)


def get_engine():
    return engine
