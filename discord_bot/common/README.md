# 📂commonフォルダの使用方法について

## common package

このディレクトリは、Bot全体で使い回す「共通ロジック/共通型」を集約するための場所です。
各Cogが特定の機能に閉じた実装になりすぎないようにし、再利用性と保守性を高めます。

---

## 目的
- 複数のCogで繰り返し登場する「純粋な処理」を1箇所にまとめる
- 依存関係（import）を単純にし、機能追加時の修正範囲を限定する
- Discord API操作やI/Oをcommonに入れないことで副作用を防ぐ

---

## common に置いてよいもの ✅
### 1. 純粋関数（副作用なし）
- 日付/時間判定（例：稼働時間判定）
- 文字列変換/整形
- バリデーション（入力チェック）

例：
- `time_utils.py`: `is_active_time(start_hour, end_hour, tz)` など

### 2. 型定義 / dataclass（副作用なし）
- タスク管理キー
- DTO（データ受け渡し用の構造体）

例：
- `types.py`: `WatchKey(guild_id, channel_id)` など

### 3. 「Discordへの依存が薄い」補助
- Discordの型を *importしない* / あるいは型ヒント程度に留める（推奨はDiscord非依存）

---

## common に置いてはいけないもの ❌
### 1. Discord API操作（副作用あり）
- `member.move_to(...)`, `channel.send(...)`, `fetch_*` など
- 「切断」「通知」「権限チェック」などの実際の操作は各Cog/Serviceへ

理由：
- テストしにくい
- importしただけで副作用が発生しやすい
- 依存関係が複雑化する

### 2. 設定読み込み（env / config）
- `os.getenv(...)` をcommonにまとめない（今回は方針として、各Cogで読む）
- 設定はCog内で管理する（または将来必要なら config 専用パッケージを検討）

### 3. ログ設定（basicConfigなど）
- `logging.basicConfig(...)` は **bot.py** で管理する
- commonは「loggerを使う」だけに留める（推奨）

### 4. DB接続 / ファイルI/O / ネットワークI/O
- DB・ファイル・HTTPなどは common ではなく専用モジュール（例：database.py, routes/, webapp.py）へ

---

## 命名と構成ルール
- ファイル名は役割が明確な名詞/動詞にする（例：`time_utils.py`, `string_utils.py`）
- 1ファイルに何でも入れない（巨大な `common.py` は作らない）
- 追加する場合は「再利用される見込みがあるか」を基準に判断する

---

## 依存方向（重要）
- ✅ `cogs/*` → `common/*` への依存はOK
- ❌ `common/*` → `cogs/*` への依存は禁止（循環依存の元）

---

## 追加時のチェックリスト
- [ ] 副作用（Discord操作/I/O）が無いか？
- [ ] 2つ以上のCogで使う見込みがあるか？
- [ ] commonがcogsに依存していないか？
- [ ] 関数/型の名前が一般化されすぎていないか？（用途が不明確になっていないか？）

