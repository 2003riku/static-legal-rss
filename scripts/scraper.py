# ★★★ ここを修正(1) ★★★
import cloudscraper
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
from typing import List, Dict
import logging
import os
import re
from urllib.parse import urljoin

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StaticLegalScraper:
    """GitHub Pages用の静的RSS生成のためのスクレイパー"""
    
    def __init__(self):
        # ★★★ ここを修正(2) ★★★
        # requests.Session() から cloudscraper に変更してボット対策を回避
        self.session = cloudscraper.create_scraper()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # 各サイトの現在のHTML構造に合わせてCSSセレクタを更新済み
        self.site_configs = {
            'bengo4': {
                'name': '弁護士ドットコム',
                'base_url': 'https://www.bengo4.com',
                'list_url': 'https://www.bengo4.com/times/',
                'selectors': {
                    'article_links': 'a.p-topics-list-item__container',
                    'title': 'h1.p-article-header__title',
                    'content': 'div.story_body',
                    'date': 'time.p-article-header__date'
                }
            },
            'corporate_legal': {
                'name': '企業法務ナビ',
                'base_url': 'https://www.corporate-legal.jp',
                'list_url': 'https://www.corporate-legal.jp/news/',
                'selectors': {
                    'article_links': 'a.article-list--link',
                    'title': 'h1.article_title',
                    'content': 'div.article_text_area',
                    'date': 'p.article_date'
                }
            },
            'ben54': {
                'name': '弁護士JPニュース',
                'base_url': 'https://www.ben54.jp',
                'list_url': 'https://www.ben54.jp/news/',
                'selectors': {
                    'article_links': 'div.article_item a',
                    'title': 'h1.article_title',
                    'content': 'div.article_cont',
                    'date': 'span.date'
                }
            }
        }
    
    def get_article_links(self, site_key: str, max_links: int = 5) -> List[str]:
        """記事リンクを取得"""
        config = self.site_configs[site_key]
        try:
            logger.info(f"{config['name']}から記事リンクを取得中...")
            response = self.session.get(config['list_url'], timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            links = []
            for link_elem in soup.select(config['selectors']['article_links'])[:max_links]:
                href = link_elem.get('href')
                if href:
                    full_url = urljoin(config['list_url'], href)
                    if full_url not in links:
                        links.append(full_url)
            logger.info(f"{len(links)}件の記事リンクを取得しました")
            return links
        except Exception as e:
            logger.error(f"{config['name']}の記事リンク取得エラー: {e}")
            return []

    def extract_article_content(self, url: str, site_key: str) -> Dict:
        """個別記事の内容を抽出"""
        config = self.site_configs[site_key]
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            title_elem = soup.select_one(config['selectors']['title'])
            title = title_elem.get_text(strip=True) if title_elem else "タイトル不明"
            
            content_elem = soup.select_one(config['selectors']['content'])
            if content_elem:
                content = ' '.join(content_elem.get_text(strip=True).split())
                content = content[:300] + '...' if len(content) > 300 else content
            else:
                content = "内容を取得できませんでした。"

            published_date = datetime.now()
            date_elem = soup.select_one(config['selectors']['date'])
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                match = re.search(r'(\d{4})[/\.\-年](\d{1,2})[/\.\-月](\d{1,2})', date_text)
                if match:
                    year, month, day = map(int, match.groups())
                    published_date = datetime(year, month, day)
            
            return {
                'title': title,
                'url': url,
                'content': content,
                'published_date': published_date,
                'source': config['name']
            }
        except Exception as e:
            logger.error(f"記事内容抽出エラー ({url}): {e}")
            return None

    def scrape_site(self, site_key: str, max_articles: int = 5) -> List:
        """特定サイトから記事を取得"""
        config = self.site_configs[site_key]
        logger.info(f"{config['name']}からニュースを取得中...")
        article_links = self.get_article_links(site_key, max_articles)
        articles = []
        for i, link in enumerate(article_links, 1):
            logger.info(f"記事 {i}/{len(article_links)} を処理中: {link}")
            article = self.extract_article_content(link, site_key)
            if article:
                articles.append(article)
                logger.info(f"  ✓ 取得完了: {article['title'][:50]}...")
            time.sleep(1)
        return articles

    def scrape_all_sites(self, max_articles_per_site: int = 5) -> List:
        """全サイトから記事を取得"""
        all_articles = []
        for site_key in self.site_configs.keys():
            try:
                articles = self.scrape_site(site_key, max_articles_per_site)
                all_articles.extend(articles)
            except Exception as e:
                logger.error(f"{site_key}のスクレイピングエラー: {e}")
        logger.info(f"スクレイピング完了: 合計{len(all_articles)}件の記事を取得")
        return all_articles
    
    def save_articles_json(self, articles: List, filepath: str):
        """記事データをJSONファイルに保存"""
        articles_for_json = []
        for article in articles:
            article_copy = article.copy()
            article_copy['published_date'] = article['published_date'].isoformat()
            articles_for_json.append(article_copy)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(articles_for_json, f, ensure_ascii=False, indent=2)
        logger.info(f"記事データを保存しました: {filepath}")

if __name__ == "__main__":
    scraper = StaticLegalScraper()
    articles = scraper.scrape_all_sites(max_articles_per_site=5)
    scraper.save_articles_json(articles, 'articles.json')
    print(f"\n=== 取得結果 ===")
    print(f"総記事数: {len(articles)}")
