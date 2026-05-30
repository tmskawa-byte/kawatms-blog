"""
Topics, subtopics, weekday → category routing.

kawatms-blog はカテゴリ4種固定:
    整備の現場 / 越境EC事業 / AI・自動化 / 対馬ライフ

投稿スケジュール (JST):
    月 → 整備の現場 - 新車情報
    水 → 整備の現場 - 整備情報
    金 → 整備の現場 - [道路交通法 / 新技術新TEC / 保険] ローテ
    日 → アドホック [越境EC事業 / AI・自動化 / 対馬ライフ] ローテ
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Tavily include_domains: 用途別に分ける
# ---------------------------------------------------------------------------
# 整備の現場（車・整備・道交法・保険）用 — 自動車専門メディア中心
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
    "npa.go.jp",          # 警察庁
    "mlit.go.jp",         # 国土交通省
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
SEIBI_SUBTOPICS: Dict[str, Dict] = {
    "新車情報": {
        "candidates": [
            "新型軽自動車",
            "新型ハイブリッド国産",
            "新型SUV 国産",
            "マイナーチェンジ 国産",
            "新型ミニバン 国産",
        ],
        "domains": AUTO_DOMAINS,
        "extra_query": "新型 発売 国産",
    },
    "整備情報": {
        "candidates": [
            "エンジンオイル交換 目安",
            "タイヤ 寿命 点検",
            "バッテリー 上がり 対処",
            "車検 費用 内訳",
            "ブレーキパッド 交換 時期",
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
        ],
        "domains": AUTO_DOMAINS,
        "extra_query": "新技術",
    },
    "保険": {
        "candidates": [
            "自動車保険 見直し",
            "等級ダウン 1等級 3等級",
            "車両保険 範囲",
            "事故 任意保険 使う か",
            "ロードサービス 比較",
        ],
        "domains": AUTO_DOMAINS,
        "extra_query": "任意保険 自動車保険",
    },
}

# 金曜日 整備の現場 ローテーション順
FRIDAY_ROTATION = ["道路交通法", "新技術新TEC情報", "保険"]

# 日曜日 アドホックカテゴリ ローテーション順
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
    elif weekday == 6:  # 日
        category = SUNDAY_ROTATION[sunday_index % len(SUNDAY_ROTATION)]
        return category, "_default", CATEGORY_SUBTOPICS[category]["_default"]
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
