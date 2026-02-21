# ADR-001: Phase 2 アーキテクチャ刷新・モジュール分離

- **日付**: 2026-02-21
- **ステータス**: 承認済み
- **関連仕様書**: [phase2-architecture-refactoring.md](../Specifications/phase2-architecture-refactoring.md), [FEATURE_MASS_MUTE.md](../FEATURE_MASS_MUTE.md)

---

## 1. 背景

- `routes/survey.py` が 400行超に肥大化し、DB操作・DM送信・ルーティングが混在
- `cogs/` 配下がフラットファイル構造で、ロジックとインターフェースが未分離
- 将来の Rust (`database_bridge`) への段階的移行を見据え、副作用の隔離が急務

## 2. 調査で判明した既存規約

実装計画策定にあたり、各ディレクトリの README.md を事前に確認した。以下の規約が実装の設計判断に影響した。

### 2.1 `cogs/README.md` の規約

```
cogs/
└── 機能名/
    ├── __init__.py    # パッケージ定義
    ├── cog.py         # Discordコマンド・イベント定義 (Interface)
    └── logic.py       # ビジネスロジック (Implementation)
```

- **`cog.py`（インターフェース層）**: コマンド/イベント定義のみ。処理は `logic.py` へ委譲
- **`logic.py`（ロジック層）**: 具体的処理。`ctx` に非依存（推奨）
- **影響**: 当初の計画では `logic.py` が欠如していた。修正して `cog.py` + `logic.py` 分離を適用

### 2.2 `services/README.md` の規約

- ステートレス設計: `@staticmethod` で実装
- `ctx` 持ち込み禁止: プリミティブ型またはモデルオブジェクトを引数に取る
- エラーハンドリング: 内部で `try-except` し、呼び出し元には `True/False` や `Result` を返す

### 2.3 `common/README.md` の規約

- 純粋関数のみ（副作用なし）
- `import discord` すら避ける（推奨）
- 追加基準: 2つ以上の Cog で使い回す見込みがあること

### 2.4 `routes/README.md` の規約

- ルート関数にDB操作や複雑な計算を直接記述しない
- `services` / `common` を呼び出す「交通整理」に徹する
- `services` から `routes` を呼び出してはいけない（依存方向の厳守）

## 3. 設計判断

### 3.1 自己修復（Self-Healing）機能のトリガー選定

**判断**: 以下の3つのDiscordイベントを監視する

| イベント | 検知対象 | 理由 |
|:---|:---|:---|
| `on_guild_channel_create` | 新規チャンネル作成 | 対象名に一致する新チャンネルに即時権限適用 |
| `on_guild_channel_update` | チャンネル権限変更 | 「チャンネルの管理」権限による外部変更を検知・修復 |
| `on_guild_role_update` | ロール権限変更 | 「ロールの管理」権限による@everyone変更を検知し全対象を再チェック |

**検討した代替案**:
- `on_guild_channel_delete` → チャンネル削除は修復対象外（存在しないチャンネルは修復不可能）
- 定時タスクのみで修復 → リアルタイム性が低く、権限リセット直後に不整合が発生する期間が生じる

**結論**: イベント駆動の即時修復 + 定時タスクによるフォールバック（二重安全策）

### 3.2 `voice_keeper/` の services 層対応

**判断**: `voice_keeper` は以前 `main.py` + `services.py` という独自命名で作成されていた。Phase 2 にて `cog.py` + `logic.py` の正規規約に統一し、`services.py` の I/O 操作を `services/voice_keeper_service.py` に移動。`@staticmethod` 化でステートレス設計に統一。

### 3.3 `filter.py` の物理削除

**判断**: 仕様書 Phase 2 §5 に明記された削除要件に従い、`cogs/filter.py` を物理削除する。`bot.py` の `COGS` リストからも除外。

### 3.4 `.example` ファイルの廃止

**判断**: 削除したファイルのコードを `.example` として保存する方式を採用していたが、セキュリティリスクとサーバーリソースの観点から廃止。代替として `docs/legacy_code_reference.md` にロジックの概要を文書化し、完全なコードは Git 履歴から参照可能とする。

**理由**:
- `.example` に古いコードが残ると、脆弱なパターンが意図せず参照・流用される可能性
- リポジトリサイズの不必要な肥大化
- Git 履歴で完全なコードは常に復元可能

## 4. 変更前後のディレクトリ構造

### Before

```
discord_bot/
├── bot.py
├── config.py
├── database.py          # トップレベル
├── utils.py             # log_operation (DB INSERT)
├── cogs/
│   ├── filter.py        # 削除対象
│   ├── mass_mute.py     # フラットファイル
│   ├── survey.py        # フラットファイル
│   └── voice_keeper/    # 既にディレクトリ化済み
├── routes/
│   └── survey.py        # 400行超 (DB操作混在)
├── services/
│   └── README.md        # ガイドのみ
└── common/
    ├── time_utils.py
    └── types.py
```

### After

```
discord_bot/
├── bot.py               # COGS リスト更新
├── config.py
├── cogs/
│   ├── mass_mute/       # ディレクトリ化 + 自己修復機能追加
│   │   ├── __init__.py
│   │   ├── cog.py       # Interface
│   │   └── logic.py     # Business Logic
│   ├── survey/          # ディレクトリ化
│   │   ├── __init__.py
│   │   ├── cog.py       # Interface
│   │   └── logic.py     # Business Logic
│   └── voice_keeper/    # cog.py + logic.py に統一
│       ├── __init__.py
│       ├── cog.py       # Interface (旧 main.py)
│       └── logic.py     # Business Logic (新規)
├── routes/
│   └── survey.py        # 薄層化 (~260行)
├── services/
│   ├── database.py            # database.py を移動
│   ├── permission_service.py  # 権限操作
│   ├── survey_service.py      # アンケートDB操作
│   ├── notification_service.py # DM通知
│   ├── log_service.py         # 操作ログ
│   └── voice_keeper_service.py # VoiceKeeper I/O
├── common/
│   ├── time_utils.py
│   ├── types.py
│   └── survey_utils.py  # parse_questions
└── tests/
    ├── test_permission_service.py
    └── test_survey_utils.py
```

## 5. 削除されたファイル

| ファイル | 理由 | ロジック参照先 |
|:---|:---|:---|
| `cogs/filter.py` | 仕様変更により不要（Phase 2 §5） | `docs/legacy_code_reference.md` §1 |
| `cogs/mass_mute.py` | ディレクトリ化に伴う移行 | `docs/legacy_code_reference.md` §2 |
| `cogs/survey.py` | ディレクトリ化に伴う移行 | `docs/legacy_code_reference.md` §3 |
| `cogs/voice_keeper/main.py` | `cog.py` に移行 | `docs/legacy_code_reference.md` §4 |
| `cogs/voice_keeper/services.py` | services層に移動 | `docs/legacy_code_reference.md` §5 |
| `database.py` (トップレベル) | `services/database.py` へ移動 | `docs/legacy_code_reference.md` §6 |
| `utils.py` | `services/log_service.py` へ移動 | `docs/legacy_code_reference.md` §7 |

> 旧コードの完全なソースは Git 履歴（`feature/refactor-services-layer` ブランチ）から復元可能。
