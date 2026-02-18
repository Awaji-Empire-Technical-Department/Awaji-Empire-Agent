from dataclasses import dataclass

@dataclass(frozen=True)
class WatchKey:
    guild_id: int
    channel_id: int  # ホストが抜けた元のVC
