"""
Topics, subtopics, weekday → category routing.

kawatms-blog はカテゴリ3種固定:
    整備の現場 / AI・自動化 / 対馬ライフ

投稿スケジュール (JST) — 2026-06-07 pivot:
    毎日 07:00 JST 投稿、整備の現場 7 サブテーマ曜日固定ローテ
    月 → 整備の現場 - 新車情報            (#1)
    火 → 整備の現場 - 整備情報            (#2)
    水 → 整備の現場 - 道路交通法          (#3)
    木 → 整備の現場 - 新技術新TEC情報     (#4)
    金 → 整備の現場 - 保険               (#5)
    土 → 整備の現場 - リコール情報        (#6)
    日 → 整備の現場 - 事故の判例          (#7)

旧仕様メモ:
    旧 cron: 月水金日 (4日/週)、金=道交法/新技術/保険ローテ、日=5サブテーマローテ
    旧アドホックカテゴリは現在の自動投稿対象外。
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

# ---------------------------------------------------------------------------
# 2026-06-07 追加: per-subtopic 拡張用ドメインリスト
# ---------------------------------------------------------------------------
# 政府公式縛りやめて日本ソース広めに。AUTO_DOMAINS と合成して各サブテーマで使う。
MAKER_DOMAINS: List[str] = [
    "toyota.jp",
    "nissan.co.jp",
    "honda.co.jp",
    "mazda.co.jp",
    "subaru.jp",
    "suzuki.co.jp",
    "daihatsu.co.jp",
    "global.toyota",        # トヨタ グローバルニュース日本語版
    "lexus.jp",
    "mitsubishi-motors.co.jp",
]

# 保険系: 業界団体 + 大手ダイレクト型・代理店型公式
INSURANCE_DOMAINS: List[str] = [
    "sonpo.or.jp",                       # 日本損害保険協会
    "jihi-hokenrengoukai.or.jp",         # 自賠責保険連合会
    "tokiomarine-nichido.co.jp",
    "sompo-japan.co.jp",
    "ms-ins.com",                        # 三井住友海上
    "aioinissaydowa.co.jp",
    "axa-direct.co.jp",
    "sonysonpo.co.jp",
    "saisonjidousha.com",
    "rakuten-ins.co.jp",
]

# 法律・弁護士系: 道路交通法・事故判例解説
LAW_DOMAINS: List[str] = [
    "bengo4.com",                # 弁護士ドットコム
    "lawyers.coconala.com",      # ココナラ法律相談
    "atombengo.com",             # アトム法律事務所
    "vbest.jp",                  # ベリーベスト法律事務所
    "best-legal.jp",
    "jiko-pro.com",              # 交通事故解決ナビ
    "ben54.jp",
]

# 判例検索・裁判所系: 事故判例
PRECEDENT_DOMAINS: List[str] = [
    "courts.go.jp",              # 裁判所
    "minemurabengoshi.jp",
    "nibengo.com",
    "n-legal.co.jp",
]

# 全国紙: リコール・判例の信頼性ソース
NEWSPAPER_DOMAINS: List[str] = [
    "nikkei.com",
    "asahi.com",
    "yomiuri.co.jp",
    "mainichi.jp",
]

# AI・自動化用 — IT・ビジネスメディア
TECH_DOMAINS: List[str] = [
    "itmedia.co.jp",
    "ascii.jp",
    "internet.watch.impress.co.jp",
    "publickey1.jp",
    "gigazine.net",
    "techcrunch.com",
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
        "domains": AUTO_DOMAINS + MAKER_DOMAINS,
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
        "domains": AUTO_DOMAINS,  # AUTO_DOMAINS に jaf.or.jp / goo-net.com / minkara 等あり既に広め
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
        "domains": AUTO_DOMAINS + LAW_DOMAINS,
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
        "domains": AUTO_DOMAINS + MAKER_DOMAINS,
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
        "domains": AUTO_DOMAINS + INSURANCE_DOMAINS + LAW_DOMAINS,
        "extra_query": "任意保険 自動車保険",
    },
    # ---------------------------------------------------------------------
    # 2026-06-07 追加: pivot で 5→7 サブテーマ拡張
    # ---------------------------------------------------------------------
    "リコール情報": {
        "candidates": [
            "リコール 国土交通省 トヨタ",
            "リコール 国土交通省 日産",
            "リコール 国土交通省 ホンダ",
            "リコール 国土交通省 マツダ",
            "リコール 国土交通省 スバル",
            "リコール 国土交通省 スズキ",
            "リコール 国土交通省 ダイハツ",
            "リコール 軽自動車",
            "リコール ハイブリッド",
            "リコール EV 電気自動車",
            "リコール エアバッグ",
            "リコール ブレーキ",
            "リコール 燃料 装置",
            "リコール 届出 メーカー",
            "リコール 改善対策 サービスキャンペーン",
        ],
        "domains": AUTO_DOMAINS + MAKER_DOMAINS + NEWSPAPER_DOMAINS,
        "extra_query": "リコール 届出",
    },
    "事故の判例": {
        "candidates": [
            "交通事故 判例 過失割合",
            "交通事故 裁判例 損害賠償",
            "追突事故 過失割合 判例",
            "右折 直進 事故 過失割合",
            "自転車 自動車 事故 判例",
            "歩行者 横断歩道 事故 判例",
            "高速道路 事故 判例",
            "駐車場 事故 過失割合",
            "信号無視 事故 判例",
            "飲酒運転 事故 損害賠償",
            "あおり運転 損害賠償 判例",
            "ながら運転 事故 判例",
            "高齢運転者 事故 判例",
            "整備不良 事故 責任",
            "車検切れ 事故 保険",
        ],
        "domains": PRECEDENT_DOMAINS + LAW_DOMAINS + NEWSPAPER_DOMAINS,
        "extra_query": "判例 過失割合 損害賠償",
    },
}

# ---------------------------------------------------------------------------
# 2026-06-07 pivot: 曜日固定ローテーション (整備の現場 7 サブテーマ)
# ---------------------------------------------------------------------------
# Python の datetime.weekday(): 0=月, 1=火, ..., 6=日
WEEKDAY_SEIBI_MAP: Dict[int, str] = {
    0: "新車情報",       # 月
    1: "整備情報",       # 火
    2: "道路交通法",     # 水
    3: "新技術新TEC情報", # 木
    4: "保険",          # 金
    5: "リコール情報",   # 土
    6: "事故の判例",     # 日
}

# ---------------------------------------------------------------------------
# 旧仕様残置 (2026-06-07 までは現役だったローテ。将来復元用に残しておく)
# ---------------------------------------------------------------------------
# 旧 金曜日 整備の現場 ローテーション順
FRIDAY_ROTATION = ["道路交通法", "新技術新TEC情報", "保険"]

# 旧 日曜日 整備の現場 シーディング期間中ローテーション順
SEIBI_ROTATION = [
    "新車情報",
    "整備情報",
    "道路交通法",
    "新技術新TEC情報",
    "保険",
]

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

    2026-06-07 pivot 以降は曜日固定ローテ。WEEKDAY_SEIBI_MAP を引くだけ。
    friday_index / sunday_index は旧仕様との後方互換のため引数に残しているが
    新ロジックでは参照しない（呼び出し側を変えずに済むため）。

    Returns: (category, subtopic_key, subtopic_meta_dict)
        subtopic_meta_dict は SEIBI_SUBTOPICS[subtopic_key] の中身
        (candidates / domains / extra_query を持つ)
    """
    sub_key = WEEKDAY_SEIBI_MAP.get(weekday, "整備情報")
    if sub_key not in SEIBI_SUBTOPICS:
        sub_key = "整備情報"
    return "整備の現場", sub_key, SEIBI_SUBTOPICS[sub_key]


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
