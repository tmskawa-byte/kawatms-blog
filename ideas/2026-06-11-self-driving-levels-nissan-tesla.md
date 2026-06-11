---
title: "日産レベル4到達 / テスラ FSD のニュース、整備士が正直に解説：実は市販車はまだ Level 2 です"
status: idea
priority: high
category: AI・自動化
tags: ["自動運転", "日産", "テスラ", "AI", "整備士目線", "SAE J3016"]
created: 2026-06-11
source: ケンちゃん時事フォロー + サイちゃん fact check
---

## 概要

「日産がレベル4到達」「テスラ FSD」のニュースで世間が誤解しがちなポイントを、整備士が SAE 基準（J3016）で整理して解説する。

事実：
- 日産の **次世代 ProPILOT は Level 2**（2027 年度導入予定）
- 日産の **Level 4 はみなとみらい実証実験 / 2027 年度モビリティサービス目標**（市販車じゃない、サービス）
- テスラ **FSD (Supervised) は Level 2**（個人向け車両）
- テスラ **Robotaxi はテキサス州が Level 4 認定**（限定地域・自社認証ベース）
- Unsupervised FSD は **2026 Q4 以降** に持ち越し

→ つまり「市販車はまだ Level 2、Level 4 はサービス・限定運用」が現状の正確な姿。

## 構成イメージ

- H2: 自動運転レベル 0〜5 の早見表（SAE J3016 基準、表で整理）
- H2: なぜ Level 2 と Level 4 の違いがニュースで混乱するのか
- H2: 日産のレベル4は「実証実験中・2027 年サービス目標」が正確
  - 次世代 ProPILOT（Level 2）と Level 4 モビリティサービスの違い
- H2: テスラ FSD の「Full Self-Driving」表記の罠
  - 個人車は Level 2、Robotaxi は Level 4（テキサス州限定）
- H2: 国交省「自動運転レベル分け」公式図（2017 年計画版）
  - 出典：国土交通省 別添3（政府標準利用規約2.0）
  - 画像：public/blog-assets/jidouunten-mlit-2017.jpeg
- H2: 2017 年計画 vs 2026 年現実のギャップ
  - 2017 年計画：2020 年に Level 4 移動サービス、2025 年目途に完全自動運転
  - 2026 年現実：日産が横浜で実証実験中（2027 年度サービス目標）、Tesla Unsupervised FSD は 2026 Q4 持ち越し
  - メーカーの公式アナウンスは「目標」で、実車整備の現場に降りてくるのは数年後
- H2: 整備の現場で何が変わる？レベル別に整理
  - Level 2 = ACC / LKA の調整、カメラ・レーダー校正
  - Level 3 以上 = LiDAR、冗長ブレーキ、通信モジュール
  - Level 4 サービス車 = 専用整備拠点が必要に
- H2: まとめ：ニュースは「市販車かサービス車か」で切り分けて読む

## 早見表（記事本文の表用、原案）

| Lv | 名称 | 操作主体 | 監視主体 | 緊急時対応 | 実例 |
|---|---|---|---|---|---|
| 0 | 運転自動化なし | 人 | 人 | 人 | 一般的な自動車 |
| 1 | 運転支援 | 人 + 1 機能 | 人 | 人 | ACC 単独、LKA 単独 |
| 2 | 部分運転自動化 | システム（条件下） | **人** | 人 | テスラ FSD、日産 ProPILOT、ホンダ SENSING |
| 3 | 条件付き運転自動化 | システム | システム（要求時のみ人） | 人 | ホンダ レジェンド（渋滞時） |
| 4 | 高度運転自動化 | システム | システム | システム | 日産（みなとみらい実証）、Waymo、Tesla Robotaxi（テキサス） |
| 5 | 完全運転自動化 | システム | システム | システム | **まだ実用化なし** |

## 参考リンク

- 日産 次世代 ProPILOT 公式リリース：https://global.nissannews.com/ja-JP/releases/250922-01-j
- Nissan ProPilot 2026 年版解説（renue）：https://renue.co.jp/posts/nissan-autonomous-driving-propilot-ai-guide-2026
- Tesla Autopilot - Wikipedia：https://en.wikipedia.org/wiki/Tesla_Autopilot
- Tesla unsupervised FSD Q4 2026（Electrek）：https://electrek.co/2026/04/22/tesla-elon-musk-unsupervised-fsd-consumer-cars-q4-delay-again/
- 国交省「自動運転のレベル分けについて」（別添3、官民ITS構想・ロードマップ2017 ベース）：public/blog-assets/jidouunten-mlit-2017.jpeg（リポ内）

## 重要な制約

- 「日産がレベル4到達した」と断定する書き方は NG（誤報になる）→ 「実証実験中」「2027 年度サービス目標」が正確
- 「テスラ FSD は完全自動運転」も NG → Supervised の表記が必須、市販車は Level 2
- 整備士目線で「事実関係を整理する」スタンス。煽らない。
