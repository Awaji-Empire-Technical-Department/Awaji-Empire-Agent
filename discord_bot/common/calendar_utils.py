# common/calendar_utils.py
# カレンダー登録URL生成ユーティリティ。OAuthなし・URLパラメータのみで実現する。

from datetime import datetime, timedelta
from urllib.parse import quote


_DT_FMT_IN  = "%Y-%m-%d %H:%M:%S"  # DB から来る形式
_DT_FMT_GCL = "%Y%m%dT%H%M%SZ"     # Google Calendar 形式


def _parse_dt(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    for fmt in (_DT_FMT_IN, "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None


def _gcal_fmt(dt: datetime) -> str:
    return dt.strftime(_DT_FMT_GCL)


def _outlook_fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def build_calendar_urls(
    title: str,
    start_str: str | None,
    end_str: str | None,
    location: str | None = None,
    description: str | None = None,
) -> dict:
    """
    Google Calendar / Outlook の登録URLと .ics ダウンロードパスを返す。

    start_str / end_str は DB の CAST(... AS CHAR) 形式 ("2024-12-01 13:00:00")。
    end_str が None の場合は start + 2時間をデフォルトとする。
    start_str が None の場合は日時なしURLを返す（タイトル・場所のみ）。
    """
    start_dt = _parse_dt(start_str)
    end_dt   = _parse_dt(end_str) if end_str else (start_dt + timedelta(hours=2) if start_dt else None)

    loc  = location or ""
    desc = description or ""

    # ---- Google Calendar ----
    if start_dt and end_dt:
        gcal_url = (
            "https://calendar.google.com/calendar/render"
            f"?action=TEMPLATE"
            f"&text={quote(title)}"
            f"&dates={_gcal_fmt(start_dt)}/{_gcal_fmt(end_dt)}"
            f"&location={quote(loc)}"
            f"&details={quote(desc)}"
        )
    else:
        gcal_url = (
            "https://calendar.google.com/calendar/render"
            f"?action=TEMPLATE"
            f"&text={quote(title)}"
            f"&location={quote(loc)}"
            f"&details={quote(desc)}"
        )

    # ---- Outlook (live.com) ----
    if start_dt and end_dt:
        outlook_url = (
            "https://outlook.live.com/calendar/deeplink/compose"
            f"?subject={quote(title)}"
            f"&startdt={quote(_outlook_fmt(start_dt))}"
            f"&enddt={quote(_outlook_fmt(end_dt))}"
            f"&location={quote(loc)}"
            f"&body={quote(desc)}"
        )
    else:
        outlook_url = (
            "https://outlook.live.com/calendar/deeplink/compose"
            f"?subject={quote(title)}"
            f"&location={quote(loc)}"
            f"&body={quote(desc)}"
        )

    return {
        "google":  gcal_url,
        "outlook": outlook_url,
        "has_datetime": start_dt is not None,
    }


def build_ics(
    title: str,
    start_str: str | None,
    end_str: str | None,
    location: str | None = None,
    description: str | None = None,
) -> str:
    """Apple Calendar / その他向けの .ics テキストを返す。"""
    import uuid

    start_dt = _parse_dt(start_str)
    end_dt   = _parse_dt(end_str) if end_str else (start_dt + timedelta(hours=2) if start_dt else None)

    now_str   = datetime.utcnow().strftime(_DT_FMT_GCL)
    start_str_ = _gcal_fmt(start_dt) if start_dt else now_str
    end_str_   = _gcal_fmt(end_dt)   if end_dt   else now_str

    return "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Awaji Empire//Event//JA",
        "BEGIN:VEVENT",
        f"UID:{uuid.uuid4()}",
        f"DTSTAMP:{now_str}",
        f"DTSTART:{start_str_}",
        f"DTEND:{end_str_}",
        f"SUMMARY:{title}",
        f"LOCATION:{location or ''}",
        f"DESCRIPTION:{description or ''}",
        "END:VEVENT",
        "END:VCALENDAR",
    ])
