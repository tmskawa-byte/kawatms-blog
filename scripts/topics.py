"""
Topics, subtopics, weekday → category routing.

kawatms-blog はカテゴリ4種固定:
    整備の現場 / 越境EC事業 / AI・自動化 / 対馬ライフ

投稿スケジュール (JST):
    月 → 整備の現場 - 新車情報
    水 → 整備の現場 - 整備情報
    金 → 整備の現場 - [道路交通法 / 新技術新TEC / 保険] ローテ
    日 → 整備の現場 - 5 サブテーマローテ (SEIBI_ROTATION)
          ※ シーディング期間中の一時設定。A8 等のアフィリエイト承認後、
            アドホック [越境EC / AI / 対馬ライフ] 復元時は
            determine_topic() の weekday==6 分岐を SUNDAY_ROTATION 利用に戻す。
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Tavily include_domains: 用途別に分ける
# ---------------------------------------------------------------------------
# 整備の現場（車・整備・道交法・保険）用 — 自動車専門メディア中心
# 2026-05-31 拡張: 16 → 23 ドメイン
#   - 全候補ドメインを web_fetch で疎通確認 (200/301 + 自動車関連コンテンツ実在)
#   - gqjapan.jp 等タイムアウトしたドメインは不採用
AUTO_DOMAINS: List[str] = [
    "response.jp",
    "motor-fan.jp",
    "kuruma-news.jp",
    "carview.yahoo.co.jp",
    "autocar.jp",
    "webcg.net",
    "bestcarweb.jp",
    "carsensor.net",
    "gazoo.com",
    "creative311.com",
    "young-machine.com",
    "ja.wikipedia.org",
    "nikkei.com",
    "nikkan.co.jp",
    "npa.go.jp",                # 警察庁
    "mlit.go.jp",               # 国土交通省
    # 2026-05-31 追加 ↓
    "car.watch.impress.co.jp",  # Car Watch (Impress) - 新型車・試乗・タイヤ
    "e-nenpi.com",              # e燃費 - 燃費・車種情報
    "goo-net.com",              # グーネット - 中古車・新車・整備
    "jaf.or.jp",                # JAF - ロードサービス・交通安全
    "driver-web.jp",            # ドライバーWeb (八重洲出版) - 専門誌系
    "minkara.carview.co.jp",    # みんカラ - 整備手帳・パーツレビュー
    "soumu.go.jp",              # 総務省 - 道路交通関連法令
]

# 越境EC事業 / AI・自動化用 — IT・ビジネスメディア
TECH_DOMAINS: List[str] = [
    "itmedia.co.jp",
    "ascii.jp",
    "internet.watch.impress.co.jp",
    "publickey1.jp",
    "gigazine.net",
    "techcrunch.com",
    "jetro.go.jp",        # 越境EC
    "ec-orange.jp",
    "netshop.impress.co.jp",
    "ja.wikipedia.org",
    "nikkei.com",
]

# 対馬ライフ用 — 観光・地方・旅行
LOCAL_DOMAINS: List[str] = [
    "tsushima-net.org",      # 対馬観光物産協会
    "city.tsushima.nagasaki.jp",
    "travel.rakuten.co.jp",
    "jalan.net",
    "tabippo.net",
    "jrkyushu.co.jp",
    "city.fukuoka.lg.jp",
    "ja.wikipedia.org",
]

# ---------------------------------------------------------------------------
# Subtopic 定義
# ---------------------------------------------------------------------------
# 整備の現場 — 5サブテーマ
# 2026-05-31 拡張: 各 candidates を 5 → 13〜15 個に増量
#   - Tavily で確実にヒットする mainstream な専門用語
#   - 整備士目線で実務的な話題
SEIBI_SUBTOPICS: Dict[str, Dict] = {
    "新車情報": {
        "candidates": [
            "新型軽自動車",
            "新型ハイブリッド国産",
            "新型SUV 国産",
            "マイナーチェンジ 国産",
            "新型ミニバン 国産",
            "新型コンパクトカー 国産",
            "新型EV 国産",
            "新型セダン 国産",
            "新型ワゴン 国産",
            "新型スポーツカー 国産",
            "新型ピックアップ",
            "新型 軽トラック",
            "フルモデルチェンジ 国産",
        ],
        "domains": AUTO_DOMAINS,
        "extra_query": "新型 発売 国産",
    },
    "整備情報": {
        "candidates": [
            "エンジンオイル交換 目安",
            "オイルフィルター 交換 時期",
            "ATF CVTフルード 交換",
            "クーラント 冷却水 交換",
            "タイヤ 寿命 点検",
            "タイヤ ローテーション 時期",
            "タイヤ空気圧 点検",
            "ホイールアライメント",
            "バッテリー 上がり 対処",
            "オルタネーター 故障",
            "ブレーキパッド 交換 時期",
            "ブレーキフルード 交換",
            "車検 費用 内訳",
            "12ヶ月点検 法定",
            "スパークプラグ 交換",
        ],
        "domains": AUTO_DOMAINS,
        "extra_query": "整備 メンテナンス",
    },
    "道路交通法": {
        "candidates": [
            "道路交通法改正",
            "あおり運転 罰則",
            "ながら運転 罰則",
            "電動キックボード ルール",
            "高齢者運転免許 更新",
            "飲酒運転 罰則",
            "違反点数 制度",
            "スピード違反 罰則",
            "一時停止 違反",
            "駐車禁止 違反",
            "通学路 速度制限",
            "自転車 道路交通法",
            "ヘッドライト 義務化",
            "シートベルト 違反",
            "チャイルドシート 法律",
        ],
        "domains": AUTO_DOMAINS,
        "extra_query": "罰則 違反点数 警察庁",
    },
    "新技術新TEC情報": {
        "candidates": [
            "EV 充電インフラ",
            "ADAS 衝突被害軽減ブレーキ",
            "自動運転レベル4",
            "全固体電池",
            "V2H 双方向充電",
            "水素 燃料電池車",
            "コネクテッドカー",
            "OTA アップデート 自動車",
            "アダプティブクルーズコントロール",
            "レーンキープアシスト",
            "自動駐車システム",
            "ヘッドアップディスプレイ",
            "自動車 軽量化技術",
            "リサイクル素材 自動車",
            "5G コネクテッドカー",
        ],
        "domains": AUTO_DOMAINS,
        "extra_query": "新技術",
    },
    "保険": {
        "candidates": [
            "自動車保険 見直し",
            "等級ダウン 1等級 3等級",
            "車両保険 範囲",
            "事故 任意保険 使うか",
            "ロードサービス 比較",
            "自賠責保険 強制保険",
            "自動車保険 ダイレクト型 比較",
            "弁護士費用特約",
            "人身傷害保険 補償範囲",
            "対人賠償 無制限 必要性",
            "車両保険 一般 エコノミー",
            "自動車保険 年齢条件",
            "保険料 安くする方法",
            "免責金額 設定",
            "自動車保険 解約 タイミング",
        ],
        "domains": AUTO_DOMAINS,
        "extra_query": "任意保険 自動車保険",
    },
}

# 金曜日 整備の現場 ローテーション順
FRIDAY_ROTATION = ["道路交通法", "新技術新TEC情報", "保険"]

# 日曜日 整備の現場 シーディング期間中ローテーション順 (2026-05-31 追加)
#   月: 新車情報 / 水: 整備情報 / 金: 道交法-新技術-保険 のローテ
#   と組み合わせて、日曜は 5 サブテーマを満遍なく回す
SEIBI_ROTATION = [
    "新車情報",
    "整備情報",
    "道路交通法",
    "新技術新TEC情報",
    "保険",
]

# 日曜日 アドホックカテゴリ ローテーション順 (A8 等アフィリエイト承認後の復元用)
#   シーディング期間中は SEIBI_ROTATION を使用、本配列は復元用として残置。
#   復元手順: determine_topic() の weekday==6 分岐を旧版に戻すだけで OK。
SUNDAY_ROTATION = ["越境EC事業", "AI・自動化", "対馬ライフ"]

# 越境EC事業 サブトピック
EKKYO_SUBTOPICS: Dict[str, Dict] = {
    "_default": {
        "candidates": [
            "BASE ショップ 立ち上げ",
            "海外発送 EMS 比較",
            "中古パーツ 輸出 関税",
            "Buyee 転送 サービス",
            "越境EC 決済 Wise Payoneer",
            "アフリカ向け 中古車 部品",
            "オーストラリア 中古車 規制",
        ],
        "domains": TECH_DOMAINS,
        "extra_query": "越境EC 輸出",
    },
}

# AI・自動化 サブトピック
AI_SUBTOPICS: Dict[str, Dict] = {
    "_default": {
        "candidates": [
            "AI API 業務自動化",
            "GitHub Actions 自動化",
            "Claude API 活用",
            "AI で 記事 自動生成",
            "AI 整備工場 活用事例",
            "ChatGPT 業務効率化",
            "ノーコード 自動化 Make Zapier",
        ],
        "domains": TECH_DOMAINS,
        "extra_query": "AI API 自動化",
    },
}

# 対馬ライフ サブトピック
TSUSHIMA_SUBTOPICS: Dict[str, Dict] = {
    "_default": {
        "candidates": [
            "対馬 観光 おすすめ",
            "対馬 グルメ 海鮮",
            "対馬 → 福岡 移動 ジェットフォイル",
            "対馬 ふるさと納税 返礼品",
            "対馬 ドライブ コース",
            "対馬 釣り スポット",
            "対馬 神社 観光",
        ],
        "domains": LOCAL_DOMAINS,
        "extra_query": "対馬 長崎",
    },
}

# カテゴリ → サブトピック辞書のマップ
CATEGORY_SUBTOPICS = {
    "整備の現場": SEIBI_SUBTOPICS,
    "越境EC事業": EKKYO_SUBTOPICS,
    "AI・自動化": AI_SUBTOPICS,
    "対馬ライフ": TSUSHIMA_SUBTOPICS,
}

# ---------------------------------------------------------------------------
# Candidate dedup state (2026-05-31 追加)
# ---------------------------------------------------------------------------
# state/recent_candidates.json の形式:
#   {
#       "新車情報": ["新型軽自動車", "新型ハイブリッド国産", ...],
#       "整備情報": ["エンジンオイル交換 目安", ...],
#       ...
#   }
# 各サブテーマで直近に選ばれた candidate を新しい順に保持する。
# pick_candidate() は直近 N=5 件を除外して残りからランダム選定し、
# 選んだ candidate を履歴の先頭に追加 (重複は前の方を残して 1 つにマージ)。
# 履歴は max_keep=10 件まで保持してそれ以降は古いものを破棄。
DEFAULT_STATE_DIR = Path("state")
DEFAULT_RECENT_CANDIDATES_FILE = "recent_candidates.json"


def _state_path(state_dir: Optional[Path] = None) -> Path:
    """state/recent_candidates.json の絶対パスを返す。"""
    base = Path(state_dir) if state_dir is not None else DEFAULT_STATE_DIR
    return base / DEFAULT_RECENT_CANDIDATES_FILE


def _load_recent_candidates(state_dir: Optional[Path] = None) -> Dict[str, List[str]]:
    """state ファイル不在 / 不正 JSON は空 dict にフォールバック。"""
    path = _state_path(state_dir)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        # 値が list[str] でないキーは捨てる (壊れたエントリの自浄)
        cleaned: Dict[str, List[str]] = {}
        for key, value in data.items():
            if isinstance(key, str) and isinstance(value, list):
                cleaned[key] = [v for v in value if isinstance(v, str)]
        return cleaned
    except (json.JSONDecodeError, OSError):
        return {}


def _save_recent_candidates(
    data: Dict[str, List[str]],
    state_dir: Optional[Path] = None,
) -> None:
    """state ディレクトリが無ければ作って書き込む。"""
    path = _state_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def pick_candidate(
    subtopic_key: str,
    candidates: List[str],
    recent_n: int = 5,
    max_keep: int = 10,
    update_state: bool = True,
    state_dir: Optional[Path] = None,
    rng: Optional[random.Random] = None,
) -> str:
    """
    subtopic_key の candidates から、直近 N 件と被らない 1 個をランダム選定。

    Args:
        subtopic_key: サブテーマ名 (e.g. "新車情報")
        candidates: 候補リスト (通常は SEIBI_SUBTOPICS[subtopic_key]["candidates"])
        recent_n: 直近何件を除外するか (デフォルト 5)
        max_keep: 履歴に何件まで保持するか (デフォルト 10)
        update_state: 選んだ candidate を state ファイルに反映するか
        state_dir: state ディレクトリ (テスト用。本番は None で OK)
        rng: random.Random 互換オブジェクト (テスト用)

    Returns:
        選ばれた candidate 文字列

    Raises:
        ValueError: candidates が空のとき
    """
    if not candidates:
        raise ValueError(f"candidates is empty for subtopic_key={subtopic_key!r}")

    chooser = rng if rng is not None else random

    recent = _load_recent_candidates(state_dir=state_dir)
    history = recent.get(subtopic_key, [])
    excluded = set(history[:recent_n])

    available = [c for c in candidates if c not in excluded]
    # 直近で全候補使い切ったら (= candidates <= recent_n のとき) 全候補から選び直す
    if not available:
        available = list(candidates)

    picked = chooser.choice(available)

    if update_state:
        # 履歴を更新: 先頭に picked、重複した古いエントリは除外、上限で切り捨て
        new_history = [picked] + [c for c in history if c != picked]
        recent[subtopic_key] = new_history[:max_keep]
        _save_recent_candidates(recent, state_dir=state_dir)

    return picked


# ---------------------------------------------------------------------------
# Weekday → (category, subtopic_key) の決定ロジック
# ---------------------------------------------------------------------------
def determine_topic(
    weekday: int,
    friday_index: int = 0,
    sunday_index: int = 0,
) -> Tuple[str, str, Dict]:
    """
    weekday: 0=月, 1=火, ..., 6=日 (Python の datetime.weekday() 準拠)
    friday_index, sunday_index: ローテーション state

    Returns: (category, subtopic_key, subtopic_meta_dict)
        subtopic_meta_dict は CATEGORY_SUBTOPICS[category][subtopic_key] の中身
        (candidates / domains / extra_query を持つ)
    """
    if weekday == 0:    # 月
        return "整備の現場", "新車情報", SEIBI_SUBTOPICS["新車情報"]
    elif weekday == 2:  # 水
        return "整備の現場", "整備情報", SEIBI_SUBTOPICS["整備情報"]
    elif weekday == 4:  # 金
        sub_key = FRIDAY_ROTATION[friday_index % len(FRIDAY_ROTATION)]
        return "整備の現場", sub_key, SEIBI_SUBTOPICS[sub_key]
    elif weekday == 6:  # 日 (シーディング期間中: 整備の現場 5 サブテーマローテ)
        sub_key = SEIBI_ROTATION[sunday_index % len(SEIBI_ROTATION)]
        return "整備の現場", sub_key, SEIBI_SUBTOPICS[sub_key]
    else:
        # 火・木・土。cron は組まれていないが手動 run 用にフォールバック。
        # デフォルトで「整備の現場」「整備情報」を返す。
        return "整備の現場", "整備情報", SEIBI_SUBTOPICS["整備情報"]


def build_query(category: str, subtopic_key: str, candidate: str) -> str:
    """
    Tavily 用クエリ文字列を組み立てる。
    """
    if category == "整備の現場":
        meta = SEIBI_SUBTOPICS[subtopic_key]
    else:
        meta = CATEGORY_SUBTOPICS[category]["_default"]
    extra = meta.get("extra_query", "")
    return f"{candidate} {extra}".strip()


def is_friday_rotation_advanced(weekday: int) -> bool:
    """金曜だけ friday_index を進めるべき。"""
    return weekday == 4


def is_sunday_rotation_advanced(weekday: int) -> bool:
    """日曜だけ sunday_index を進めるべき。"""
    return weekday == 6
