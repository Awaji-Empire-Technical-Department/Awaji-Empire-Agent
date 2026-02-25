// db/permission_repo.rs
// Why: 権限判定のビジネスロジックを担当する。
//      Python 側から送られた「現在のビットフラグ」と「期待されるビットフラグ」を比較し、
//      修復が必要か、およびターゲットとするビットフラグを算出する。
//
// チャンネル名は .env から以下のキーで読み込む:
//   MUTE_ONLY_CHANNEL_NAMES  = 配信コメント,xxx  (カンマ区切り)
//   READ_ONLY_CHANNEL_NAMES  = 参加ログ,yyy      (カンマ区切り)

use std::env;

use crate::db::models::{PermissionEvaluateRequest, PermissionEvaluateResponse};

// Discord 権限ビット定義 (v10)
// 参照: https://discord.com/developers/docs/topics/permissions#permissions-bitwise-permission-flags
const PERM_VIEW_CHANNEL: i64 = 1 << 10;
const PERM_SEND_MESSAGES: i64 = 1 << 11;
const PERM_MENTION_EVERYONE: i64 = 1 << 17;
const PERM_MANAGE_WEBHOOKS: i64 = 1 << 29;

/// カンマ区切りの環境変数を Vec<String> に変換するヘルパー。
fn env_csv(key: &str) -> Vec<String> {
    env::var(key)
        .unwrap_or_default()
        .split(',')
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect()
}

/// 権限判定リポジトリ。
pub struct PermissionRepo;

impl PermissionRepo {
    /// チャンネル名に基づいて、期待される権限上書き (Overwrite) を取得する。
    /// ポリシーは .env ファイルから読み込まれる。
    ///   MUTE_ONLY_CHANNEL_NAMES = 配信コメント,xxx  (カンマ区切り)
    ///   READ_ONLY_CHANNEL_NAMES = 参加ログ,yyy      (カンマ区切り)
    pub fn get_policy(channel_name: &str) -> Option<(i64, i64, &'static str)> {
        let mute_only_names = env_csv("MUTE_ONLY_CHANNEL_NAMES");
        let read_only_names = env_csv("READ_ONLY_CHANNEL_NAMES");

        if mute_only_names.iter().any(|n| n == channel_name) {
            // allow: VIEW_CHANNEL, SEND_MESSAGES
            // deny:  MENTION_EVERYONE, MANAGE_WEBHOOKS
            let allow = PERM_VIEW_CHANNEL | PERM_SEND_MESSAGES;
            let deny = PERM_MENTION_EVERYONE | PERM_MANAGE_WEBHOOKS;
            return Some((allow, deny, "MUTE_ONLY"));
        }

        if read_only_names.iter().any(|n| n == channel_name) {
            // allow: VIEW_CHANNEL
            // deny:  SEND_MESSAGES, MENTION_EVERYONE, MANAGE_WEBHOOKS
            let allow = PERM_VIEW_CHANNEL;
            let deny = PERM_SEND_MESSAGES | PERM_MENTION_EVERYONE | PERM_MANAGE_WEBHOOKS;
            return Some((allow, deny, "READ_ONLY"));
        }

        None
    }

    /// 現在の権限状態を評価し、期待値との差異を返す。
    pub fn evaluate(req: PermissionEvaluateRequest) -> PermissionEvaluateResponse {
        match Self::get_policy(&req.channel_name) {
            None => PermissionEvaluateResponse {
                needs_repair: false,
                target_allow: req.current_allow,
                target_deny: req.current_deny,
                reason: Some(
                    "Not a target channel for automated permission management".to_string(),
                ),
            },
            Some((expected_allow, expected_deny, policy_name)) => {
                let needs_repair =
                    req.current_allow != expected_allow || req.current_deny != expected_deny;

                PermissionEvaluateResponse {
                    needs_repair,
                    target_allow: expected_allow,
                    target_deny: expected_deny,
                    reason: Some(format!("Policy applied: {}", policy_name)),
                }
            }
        }
    }
}
