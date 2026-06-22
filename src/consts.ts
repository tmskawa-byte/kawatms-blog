// Place any global data in this file.
// You can import this data from anywhere in your site by using the `import` keyword.

export const SITE_TITLE = "対馬モーターサービス blog";
export const SITE_DESCRIPTION =
	"長崎県対馬市の自動車整備工場「対馬モーターサービス」（個人事業主／適格請求書発行事業者）が運営するブログ。整備の現場・越境EC事業・AI API による業務自動化・対馬ライフを発信します。";
export const SITE_URL = "https://tsushima-motor.com";

// AdSense publisher IDs are intentionally public: they are included in the page source.
export const ADSENSE_CLIENT = "ca-pub-1731762204000076";

export const CATEGORIES = [
	{
		name: "整備の現場",
		emoji: "🚗",
		description: "車検、整備、新車情報、修理事例 など",
	},
	{
		name: "越境EC事業",
		emoji: "🌍",
		description: "eBay、BE FORWARD、補助金、開発日誌 など",
	},
	{
		name: "AI・自動化",
		emoji: "🤖",
		description: "API活用、bot 開発、ツール検証 など",
	},
	{
		name: "対馬ライフ",
		emoji: "🏝",
		description: "離島でのビジネス、地域、文化 など",
	},
] as const;

// 業務情報（LocalBusiness / AutoRepair 構造化データ用）
export const BUSINESS_INFO = {
	name: "対馬モーターサービス",
	legalName: "対馬モーターサービス（個人事業主）",
	url: SITE_URL,
	logo: `${SITE_URL}/og.jpg`,
	telephone: "0920-52-0158",
	priceRange: "¥¥",
	postalCode: "817-0016",
	streetAddress: "厳原町東里62-1",
	addressLocality: "対馬市",
	addressRegion: "長崎県",
	addressCountry: "JP",
	// Google マップで「対馬モーターサービス」の正確な座標
	latitude: 34.2173745,
	longitude: 129.2923812,
	openingHours: [
		{
			days: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
			opens: "08:30",
			closes: "17:30",
		},
		{
			days: ["Saturday", "Sunday"],
			opens: "08:30",
			closes: "12:00",
		}, // 土日 午前中営業
		{
			days: "PublicHolidays",
			opens: "00:00",
			closes: "00:00",
		}, // 祝日休み（営業時間ゼロ）
	],
	sameAs: [
		"https://www.instagram.com/kawatms",
		"https://www.threads.net/@kawatms",
	],
	services: [
		"車検",
		"自動車整備",
		"タイヤ交換",
		"オイル交換",
		"鈑金塗装",
		"中古車買取",
	],
} as const;

export type CategoryName = (typeof CATEGORIES)[number]["name"];

export function getCategoryMeta(name: string) {
	return CATEGORIES.find((c) => c.name === name);
}
