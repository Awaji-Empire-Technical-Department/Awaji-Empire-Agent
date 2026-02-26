// lobby/game_link.rs
// Why: 仮想IP(WARP)を東方憑依華専用のフォーマットに変換する。
// 憑依華は12桁の0埋めIPとポート(例: 100.096.018.005:10800)しか認識しないため、
// バックエンド側でこの変換を事前に行い、安全（生のIPを隠蔽）かつ確実な文字列を提供する。

pub struct GameLinkFormatter;

impl GameLinkFormatter {
    /// 仮想IPアドレス文字列（例: "100.96.18.5"）を受け取り、
    /// "100.096.018.005:10800" の形式にフォーマットする。
    pub fn format(virtual_ip: &str) -> Option<String> {
        let parts: Vec<&str> = virtual_ip.split('.').collect();
        if parts.len() != 4 {
            return None;
        }

        let mut formatted_parts = Vec::new();
        for p in parts {
            let num: u8 = p.parse().ok()?;
            formatted_parts.push(format!("{:03}", num));
        }

        Some(format!("{}:10800", formatted_parts.join(".")))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_format_valid_ip() {
        assert_eq!(
            GameLinkFormatter::format("100.96.18.5"),
            Some("100.096.018.005:10800".to_string())
        );
        assert_eq!(
            GameLinkFormatter::format("192.168.0.1"),
            Some("192.168.000.001:10800".to_string())
        );
    }

    #[test]
    fn test_format_invalid_ip() {
        assert_eq!(GameLinkFormatter::format("100.96.18"), None);
        assert_eq!(GameLinkFormatter::format("invalid"), None);
        assert_eq!(GameLinkFormatter::format("100.96.18.256"), None);
    }
}
