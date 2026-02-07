# ⚙️ Awaji Empire Agent - 全体構成アーキテクチャ

## 1. 概要

本プロジェクトは、淡路帝国のサーバー管理を自動化し、ユーザー体験を向上させるための統合プラットフォームです。物理サーバー(Proxmox)からエッジネットワーク(Cloudflare)までを一貫して自前で構築しています。

## 2. システム構成図

物理レイヤーから外部サービス連携までの全体像を示します。

![System Architecture](./assets/runtime_architecture.png)

## 3. インフラストラクチャ詳細

### 3.1 物理サーバー (Node) スペック

本システムの基盤となる物理マシンの構成です。

| コンポーネント | スペック | 備考 |
| :--- | :--- | :--- |
| **CPU** | Intel Core i3 9100F | 4コア/4スレッド。VM・CTの並列稼働を支える心臓部。 |
| **GPU** | NVIDIA GeForce GT 710 | **望まれざる客。** 映像出力用。 |
| **RAM** | 16GB | Proxmox上での複数サービス稼働に余裕を持たせた容量。 |
| **SSD** | 500GB | 高速なディスクI/Oにより、DBアクセスを高速化。 |

### 3.2 仮想化・ネットワーク

- **Hypervisor**: Proxmox VE 9.1 上で Ubuntu 24.04 LTS (VM) と MariaDB (CT) を稼働。
- **Network**: Cloudflare Tunnel を使用し、自宅回線のIPを公開せずに `dashboard.awajiempire.net` を運用。
- **Database**: MariaDB を中央ハブとし、BotとWebアプリ間でリアルタイムなデータ共有を実現。

## 4. 機能別ドキュメント

詳細なロジックは各ドキュメントを参照してください。

- [メッセージフィルタリング機能](./FEATURE_FILTER.md)
- [通知マスミュート機能](./FEATURE_MASS_MUTE.md)
- [内製アンケートシステム](./FEATURE_SURVEY.md)
- [寝落ち検知機能](./FEATURE_VOICE_KEEPER.md)

## 5. 今後の展望：Rustによるデータアクセス層の再構築 (検討中)

システムの堅牢性と安全性をさらに高めるため、現在 Python (Quart) で行っている MariaDB との通信部を、Rust による独立したエージェントへ移行する構成を検討しています。

### 5.1 背景と目的

- **OSトレンドへの適応**: Ubuntu 26.04 LTS のコアシステムにおける Rust 採用の流れを汲み、システム全体のメモリ安全性を向上させます。
  - 参照: [Ubuntu、26.04 LTSのコアシステムにRustを導入へ - ZDNET Japan](https://japan.zdnet.com/article/35243565/)
- **型安全性の確保**: `sqlx` 等のライブラリを活用し、コンパイル時にクエリの妥当性を検証することで、実行時のランタイムエラーを最小化します。
- **リソース管理の最適化**: Discord Bot や Web アプリからの DB 接続を集約し、コネクションプールを最適化することで、物理サーバー (Proxmox 実行環境) への負荷を軽減します。

### 5.2 構成案

現在の `/discord_bot` 内の DB ロジックを切り出し、Rust 製の「DBブリッジ」を介して MariaDB にアクセスするハイブリッド構成を目指します。
