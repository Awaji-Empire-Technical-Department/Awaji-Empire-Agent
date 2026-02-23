# Phase 2 アーキテクチャ刷新 変更履歴

**実施日**: 2026-02-21
**ブランチ**: `feature/phase2-architecture-refactoring`
**関連仕様書**: [phase2-architecture-refactoring.md](Specifications/phase2-architecture-refactoring.md), [FEATURE_MASS_MUTE.md](FEATURE_MASS_MUTE.md)
**ADR**: [001-phase2-architecture-refactoring.md](adr/001-phase2-architecture-refactoring.md)

---

## 変更一覧

| 区分 | ファイル | 内容 |
|:---|:---|:---|
| **新規** | `services/permission_service.py` | 権限操作サービス（自己修復の核） |
| **新規** | `services/survey_service.py` | アンケートDB CRUD |
| **新規** | `services/notification_service.py` | DM送信サービス |
| **新規** | `services/log_service.py` | 操作ログ記録サービス |
| **新規** | `services/database.py` | DB接続（トップレベルから移動） |
| **新規** | `services/voice_keeper_service.py` | VoiceKeeper I/Oサービス |
| **新規** | `cogs/mass_mute/cog.py` | MassMuteCog（インターフェース層） |
| **新規** | `cogs/mass_mute/logic.py` | MassMuteLogic（ビジネスロジック） |
| **新規** | `cogs/survey/cog.py` | SurveyCog（インターフェース層） |
| **新規** | `cogs/survey/logic.py` | SurveyLogic（ビジネスロジック） |
| **新規** | `cogs/voice_keeper/cog.py` | VoiceKeeper（インターフェース層） |
| **新規** | `cogs/voice_keeper/logic.py` | VoiceKeeperLogic（ビジネスロジック） |
| **新規** | `common/survey_utils.py` | parse_questions 純粋関数 |
| **新規** | `tests/test_permission_service.py` | 権限サービスのユニットテスト 11件 |
| **新規** | `tests/test_survey_utils.py` | parse_questions のユニットテスト 9件 |
| **変更** | `routes/survey.py` | Service層に委譲して薄層化（414行→約260行） |
| **変更** | `bot.py` | COGS リストから filter 除外 |
| **変更** | `.gitignore` | テスト出力・キャッシュ・Antigravity を除外 |
| **削除** | `cogs/filter.py` | 仕様変更により不要（→ `.example` 保存） |
| **削除** | `cogs/mass_mute.py` | ディレクトリ化（→ `.example` 保存） |
| **削除** | `cogs/survey.py` | ディレクトリ化（→ `.example` 保存） |
| **削除** | `cogs/voice_keeper/main.py` | `cog.py` に移行（→ `.example` 保存） |
| **削除** | `cogs/voice_keeper/services.py` | services層に移動（→ `.example` 保存） |
| **削除** | `database.py` | `services/database.py` に移動（→ `.example` 保存） |
| **削除** | `utils.py` | `services/log_service.py` に移動（→ `.example` 保存） |

---

## 自己修復（Self-Healing）機能

mass_mute に追加された3つのDiscordイベントで権限の変更を即座に検知・修復:

1. **`on_guild_channel_create`** — 新規チャンネル作成時、対象名に一致すれば即座に権限設定
2. **`on_guild_channel_update`** — 「チャンネルの管理」権限による外部変更を検知→定義済み権限に自動復元
3. **`on_guild_role_update`** — @everyone ロール変更時、全対象チャンネルの権限を再検証・修復

フォールバック: 定時タスク（JST 0:00, 8:00, 16:00）による一括適用は従来通り機能。

---

## ディレクトリ構造（After）

```
discord_bot/
├── bot.py
├── config.py
├── cogs/
│   ├── mass_mute/
│   │   ├── __init__.py
│   │   ├── cog.py       # Interface
│   │   └── logic.py     # Business Logic
│   ├── survey/
│   │   ├── __init__.py
│   │   ├── cog.py       # Interface
│   │   └── logic.py     # Business Logic
│   └── voice_keeper/
│       ├── __init__.py
│       ├── cog.py       # Interface
│       └── logic.py     # Business Logic
├── routes/
│   └── survey.py        # 薄層化
├── services/
│   ├── database.py
│   ├── permission_service.py
│   ├── survey_service.py
│   ├── notification_service.py
│   ├── log_service.py
│   └── voice_keeper_service.py
├── common/
│   ├── time_utils.py
│   ├── types.py
│   └── survey_utils.py
└── tests/
    ├── test_permission_service.py
    └── test_survey_utils.py
```

---

## テスト結果

- `test_permission_service.py`: **11テスト全パス**
- `test_survey_utils.py`: **9テスト全パス**
- 全 `.py` ファイルの構文チェック: **パス**

---

## 手動確認事項

Bot起動後に以下を確認:

1. `LOADED: cogs.mass_mute` / `LOADED: cogs.survey` / `LOADED: cogs.voice_keeper` が出力される
2. `cogs.filter` が出力されない
3. テスト用チャンネルの権限を手動変更 → 自己修復が即座に発動する
4. 定時タスク `daily_mute_check` が正常動作する
5. Webダッシュボード（`routes/survey.py`）が正常動作する
