import { glob } from "astro/loaders";
import { defineCollection } from "astro:content";
import { z } from "astro/zod";

const blog = defineCollection({
	// Load Markdown and MDX files in the `src/content/blog/` directory.
	loader: glob({ base: "./src/content/blog", pattern: "**/*.{md,mdx}" }),
	// Type-check frontmatter using a schema
	schema: z.object({
		title: z.string(),
		description: z.string(),
		// Transform string to Date object
		pubDate: z.coerce.date(),
		updatedDate: z.coerce.date().optional(),
		slug: z.string().optional(),
		heroImage: z.string().optional(),
		tags: z.array(z.string()).optional(),
		category: z.enum([
			"整備の現場",
			"AI・自動化",
			"対馬ライフ",
		]),
		// アフィリエイト広告（PR）を含む場合 true。
		// 記事冒頭にステマ規制（景表法）対応の表示が挿入される。
		containsAffiliate: z.boolean().optional().default(false),
	}),
});

export const collections = { blog };
