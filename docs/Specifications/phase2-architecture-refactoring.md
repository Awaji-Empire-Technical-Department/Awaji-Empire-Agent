# [Phase 2] アーキテクチャ刷新・モジュール分離仕様書

## 1. 背景と目的

現在、`routes/survey.py` が 400行を超えるなど、特定のファイルに「入力受付」「DB操作」「外部API通信」が混在し、保守性が低下しています。
また、将来的に **ロジック層を Rust (database_bridge) へ段階的に移行** することを容易にするため、副作用を伴うコードを Python 側で完全に隔離します。

## 2. ディレクトリ構造の役割分担 (I/O境界)

| ディレクトリ | 役割 | I/O (副作用) | 依存方向 |
| :--- | :--- | :---: | :--- |
| **`cogs/`** | **Discord I/F**<br>コマンド・イベントの受付。 | あり | -> `services`, `common` |
| **`routes/`** | **Web I/F**<br>Webフォーム、URLハンドリング。 | あり | -> `services`, `common` |
| **`services/`** | **Logic (副作用有)**<br>DB操作、Discord API操作、I/O。 | **あり** | -> `common` |
| **`common/`** | **Logic (副作用無)**<br>計算、文字列整形、定数。 | **なし** | 独立 |

## 3. 具体的なリファクタリング指示

### ① `database.py` の移行

- **現状**: トップディレクトリに存在。
- **変更**: **`services/database.py`** へ移動。
- **意図**: DB操作は最大の副作用。最終的にこの中身が Rust ブリッジ（`database_bridge`）へのコネクタに置き換わります。

### ② `routes/survey.py` (400行) の解体

- **現状**: ルート関数内に `aiomysql` や `httpx` (DM送信) が直書きされている。
- **変更**:
  - DB操作（`INSERT/UPDATE` 等） → `services/survey_service.py` へ。
  - DM通知ロジック (`send_dm_notification`) → `services/notification_service.py` へ。
- **目標**: `routes/` 側はリクエストを受け取ってサービスを呼び出すだけの 50行程度のコードにする。

### ③ `cogs/` のディレクトリ化と `mass_mute.py` の分離

- **現状**: `cogs/` 直下にファイルが散乱。
- **変更**: `cogs/mass_mute/cog.py` のようにフォルダ分け。
- **ロジックの抽出**: `execute_mute_logic` 内のパーミッション操作は、他の Cog からも使い回せるよう `services/permission_service.py` へ切り出す。

### ④ `utils.py` の整理

- **`log_operation`**: DBへの INSERT を伴うため、**`services/utils.py`** （または logger サービス）へ移動。
- **純粋な計算処理**: `common/` へ移動。

## 4. 厳守ルール：Rust 移行を成功させるために

1. **`Context` (ctx) の持ち込み禁止**: `services/` に `ctx` を渡さないでください。代わりに `user_id` や `guild_id` などのプリミティブな型を渡します。
2. **ステートレス設計**: Service クラスはメンバ変数を持たず、`@staticmethod` で実装してください。これにより、将来のバイナリ呼び出し（Rust）への差し替えが容易になります。
3. **副作用の明示**: `common/` は `import discord` すら避ける勢いで、純粋な計算のみに留めてください。

## 5. 削除対象

- **`filter.py`**: 仕様変更により不要となったため、リポジトリから物理削除します。
