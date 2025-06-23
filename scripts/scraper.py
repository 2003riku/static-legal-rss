import time
import json
import logging
import os
import re
from datetime import datetime
from typing import List, Dict
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    if 'CHROME_BINARY_LOCATION' in os.environ:
        options.binary_location = os.environ['CHROME_BINARY_LOCATION']
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

class SeleniumScraper:
    def __init__(self, driver):
        self.driver = driver
        # ★★★ 全サイトのセレクタを最終調査に基づき全面的に修正 ★★★
        self.site_configs = {
            'bengo4': {
                'name': '弁護士ドットコム',
                'list_url': 'https://www.bengo4.com/times/',
                'selectors': {
                    'list_wait': 'a.p-latestArticle__link, a.p-secondaryArticle__itemLink, a.c-list__itemLink',
                    'article_links': 'a.p-latestArticle__link, a.p-secondaryArticle__itemLink, a.c-list__itemLink',
                    'article_wait': '.p-articleDetail__headText h1, .p-articleDetail__body', # タイトルか本文のどちらかを待つ
                    'title': '.p-articleDetail__headText h1',
                    'content': '.p-articleDetail__body',
                    'date': '.p-articleDetail__meta time'
                }
            },
            'corporate_legal': {
                'name': '企業法務ナビ',
                'list_url': 'https://www.corporate-legal.jp/news/',
                'selectors': {
                    'list_wait': 'a.card-categories.news',
                    'article_links': 'a.card-categories.news',
                    'article_wait': 'h1.article_title, div.article_text_area', # タイトルか本文のどちらかを待つ
                    'title': 'h1.article_title',
                    'content': 'div.article_text_area',
                    'date': 'p.article_date'
                }
            },
            'ben54': {
                'name': '弁護士JPニュース',
                'list_url': 'https://www.ben54.jp/news/',
                'selectors': {
                    'list_wait': 'article a.c-news-card__link',
                    'article_links': 'article a.c-news-card__link',
                    'article_wait': 'h1.article_title, div.article_cont', # タイトルか本文のどちらかを待つ
                    'title': 'h1.article_title',
                    'content': 'div.article_cont',
                    'date': 'span.date',
                    'cookie_accept_button': '#cookie_accept'
                }
            }
        }

    def get_page_source(self, url: str, site_key: str, wait_type: str) -> str:
        logger.info(f"URLにアクセス中: {url}")
        config = self.site_configs[site_key]
        wait_selector = config['selectors'][f'{wait_type}_wait']
        
        try:
            self.driver.get(url)
            if 'cookie_accept_button' in config['selectors']:
                try:
                    cookie_button = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, config['selectors']['cookie_accept_button'])))
                    cookie_button.click()
                    logger.info("Cookie同意ボタンをクリックしました。")
                    time.sleep(1)
                except TimeoutException:
                    logger.info("Cookie同意ボタンは見つかりませんでした。")
            
            WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector)))
            logger.info("ページの読み込み完了。")
            return self.driver.page_source
        except TimeoutException:
            logger.error(f"ページの読み込み待機中にタイムアウト: {url} (セレクタ: {wait_selector})")
            return ""
        except Exception as e:
            logger.error(f"ページ取得中にエラー: {e}", exc_info=True)
            return ""

    def get_article_links(self, site_key: str, max_links: int = 5) -> List[str]:
        config = self.site_configs[site_key]
        page_source = self.get_page_source(config['list_url'], site_key, 'list')
        if not page_source: return []
            
        soup = BeautifulSoup(page_source, 'html.parser')
        links, seen_urls = [], set()
        for link_elem in soup.select(config['selectors']['article_links']):
            if len(links) >= max_links: break
            href = link_elem.get('href')
            if href:
                full_url = urljoin(config['list_url'], href.strip())
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    links.append(full_url)
        logger.info(f"{config['name']}で{len(links)}件の記事リンクを取得しました")
        return links

    def extract_article_content(self, url: str, site_key: str) -> Dict:
        config = self.site_configs[site_key]
        page_source = self.get_page_source(url, site_key, 'article')
        if not page_source: return None
            
        soup = BeautifulSoup(page_source, 'html.parser')
        title = (soup.select_one(config['selectors']['title']) or BeautifulSoup('', 'html.parser')).get_text(strip=True) or "タイトル不明"
        
        content_elem = soup.select_one(config['selectors']['content'])
        if content_elem:
            for unwanted in content_elem.select('script, style, .ad, .advertisement, .related-articles'):
                unwanted.decompose()
            content = ' '.join(content_elem.get_text(strip=True).split())[:300] + '...'
        else:
            content = "内容を取得できませんでした。"
        
        published_date = datetime.now()
        date_elem = soup.select_one(config['selectors']['date'])
        if date_elem:
            date_text = re.sub(r'公開日：', '', date_elem.get_text(strip=True))
            match = re.search(r'(\d{4})[/\.\-年](\d{1,2})[/\.\-月](\d{1,2})', date_text)
            if match:
                published_date = datetime(*(int(g) for g in match.groups()))
        
        return {'title': title, 'url': url, 'content': content, 'published_date': published_date, 'source': config['name']}

    def scrape_site(self, site_key: str, max_articles: int = 5) -> List[Dict]:
        logger.info(f"サイト「{self.site_configs[site_key]['name']}」のスクレイピングを開始します。")
        article_links = self.get_article_links(site_key, max_articles)
        
        if not article_links: return []
            
        articles = []
        for i, link in enumerate(article_links, 1):
            logger.info(f"記事 {i}/{len(article_links)} を処理中: {link}")
            time.sleep(1)
            article = self.extract_article_content(link, site_key)
            if article:
                articles.append(article)
                logger.info(f"  ✓ 取得完了: {article['title'][:50]}...")
        return articles

def save_articles_json(articles: List, filepath: str):
    articles_for_json = []
    for article in articles:
        article_copy = article.copy()
        if isinstance(article_copy.get('published_date'), datetime):
            article_copy['published_date'] = article_copy['published_date'].isoformat()
        articles_for_json.append(article_copy)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(articles_for_json, f, ensure_ascii=False, indent=2)
    logger.info(f"記事データを保存しました: {filepath}")

def main():
    driver = None
    try:
        driver = setup_driver()
        scraper = SeleniumScraper(driver)
        all_articles = []
        for site_key in scraper.site_configs.keys():
            try:
                articles = scraper.scrape_site(site_key, max_articles=5)
                all_articles.extend(articles)
            except Exception as e:
                logger.error(f"{site_key}のスクレイピング中に予期せぬエラー: {e}", exc_info=True)
        logger.info(f"全サイトのスクレイピング完了: 合計{len(all_articles)}件の記事を取得")
        save_articles_json(all_articles, 'articles.json')
        print(f"\n=== 取得結果 ===")
        print(f"総記事数: {len(all_articles)}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()
