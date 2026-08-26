import * as cheerio from "cheerio"
import type { NewsItem } from "@shared/types"

// 自定义资讯源：东方财富
// 方式一：官方 JSON 接口（海外代理实测返回过真实数据，最稳）
// 方式二：网页爬取兜底（JSON 失败时自动切换）
export default defineSource(async () => {
  // ① JSON 接口（首选）
  try {
    const response: any = await myFetch(
      "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?client=web&biz=web_news_col&column=350&order=1&needInteractData=0&page_index=1&page_size=30&req_trace=newsnow"
    )
    const data = typeof response === "string" ? JSON.parse(response) : response
    const list: any[] = data?.data?.list ?? []
    const items: NewsItem[] = []
    const seen = new Set<string>()
    for (const it of list) {
      const title = (it.title || "").trim()
      const url = it.url || ""
      if (title && url && !seen.has(title)) {
        seen.add(title)
        items.push({
          id: it.code || url,
          title,
          url,
          pubDate: it.showTime ? new Date(it.showTime).getTime() : undefined,
        })
      }
    }
    if (items.length) return items.slice(0, 30)
  } catch {}
  // ② 网页兜底
  try {
    const response: any = await myFetch("https://www.eastmoney.com/")
    const $ = cheerio.load(response)
    const news: NewsItem[] = []
    const seen = new Set<string>()
    $("a[href*='finance.eastmoney.com/a/']").each((_, el) => {
      const $el = $(el)
      const url = $el.attr("href")
      const title = $el.text().trim()
      if (url && title && !seen.has(title)) {
        seen.add(title)
        news.push({ url, title, id: url })
      }
    })
    if (news.length) return news.slice(0, 30)
  } catch {}
  return []
})
