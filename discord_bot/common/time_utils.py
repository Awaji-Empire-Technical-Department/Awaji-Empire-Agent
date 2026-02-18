from datetime import datetime
from zoneinfo import ZoneInfo

def is_active_time(start_hour: int, end_hour: int, tz: ZoneInfo) -> bool:
    """
    稼働時間判定（深夜帯・日跨ぎ対応）
    - start_hour: 0〜24
    - end_hour: 0〜24（24は“24時”として扱う）
    判定は [start, end) の半開区間
    """
    now = datetime.now(tz)
    h = now.hour  # 0-23

    # 正規化（end=24 を保持）
    start = start_hour
    end = end_hour

    # ざっくり防御
    if start < 0: start = 0
    if end < 0: end = 0
    if start > 24: start = start % 24
    if end > 24: end = end % 24

    # 0〜24 全時間稼働
    if start == 0 and end == 24:
        return True

    # start==end は「全時間稼働」扱いに寄せる（運用で便利）
    if start == end:
        return True

    # end==24 は 24として比較できるが、h は 0-23 なので通常通りOK
    if start < end:
        return start <= h < end
    else:
        # 日跨ぎ（例: 22〜6）
        return (h >= start) or (h < end)
