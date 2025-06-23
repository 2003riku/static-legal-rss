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

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_driver():
    """Selenium WebDriverをセットアップする"""
    options = Options()
    options.add_argument("--headless")  # ヘッドレスモードで実行
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    
    # GitHub Actions環境でのChromeバイナリのパスを指定
    if 'CHROME_BINARY_LOCATION' in os.environ:
        options.binary_location = os.environ['CHROME_BINARY_LOCATION']

    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


class SeleniumScraper:
    """Seleniumを使用して動的コンテンツを扱うスクレイパー"""
    def __init__(self, driver):
        self.driver = driver
        self.site_configs = {
            'bengo4': {
                'name': '弁護士ドットコム',
                'base_url': 'https://www.bengo4.com',
                'list_url': 'https://www.bengo4.com/times/',
                'selectors': {
                    'wait_for': '.p-topics-list-item__container, .p-secondaryArticle a', # ページ読み込み完了の目印
                    'article_links': '.p-topics-list-item__container, .p-secondaryArticle a',
                    'title': '.p-articleDetail__headText h1',
                    'content': '.p-articleDetail__body',
                    'date': '.p-articleDetail__meta time'
                }
            },
            'corporate_legal': {
                'name': '企業法務ナビ',
                'list_url': 'https://www.corporate-legal.jp/news/',
                'selectors': {
                    'wait_for': 'ul.article-list > li.article-list--item',
                    'article_links': 'ul.article-list > li.article-list--item > a.article-list--link',
                    'title': 'h1.article_title',
                    'content': 'div.article_text_area',
                    'date': 'p.article_date'
                }
            },
            'ben54': {
                'name': '弁護士JPニュース',
                'list_url': 'https://www.ben54.jp/news/',
                'selectors': {
                    'wait_for': 'div.article_item',
                    'article_links': 'div.article_item > a',
                    'title': 'h1.article_title',
                    'content': 'div.article_cont',
                    'date': 'span.date'
                }
            }
        }

    def get_page_source(self, url: str, wait_for_selector: str) -> str:
        """指定したURLのページソースを、要素が表示されるまで待ってから取得"""
        logger.info(f"URLにアクセス中: {url}")
        self.driver.get(url)
        try:
            # 指定したセレクタの要素が表示されるまで最大20秒待つ
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector))
            )
            logger.info("ページの読み込み完了。")
            return self.driver.page_source
        except Exception as e:
            logger.error(f"ページの読み込み待機中にタイムアウトまたはエラー: {e}")
            return ""

    def get_article_links(self, site_key: str, max_links: int = 5) -> List[str]:
        config = self.site_configs[site_key]
        list_url = config['list_url']
        
        page_source = self.get_page_source(list_url, config['selectors']['wait_for'])
        if not page_source:
            return []
            
        soup = BeautifulSoup(page_source, 'html.parser')
        links = []
        seen_urls = set()

        for link_elem in soup.select(config['selectors']['article_links']):
            if len(links) >= max_links:
                break
            href = link_elem.get('href')
            if href:
                full_url = urljoin(list_url, href.strip())
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    links.append(full_url)
        
        logger.info(f"{config['name']}で{len(links)}件の記事リンクを取得しました")
        return links

    def extract_article_content(self, url: str, site_key: str) -> Dict:
        config = self.site_configs[site_key]
        page_source = self.get_page_source(url, config['selectors']['title'])
        if not page_source:
            return None
            
        soup = BeautifulSoup(page_source, 'html.parser')
        
        title_elem = soup.select_one(config['selectors']['title'])
        title = title_elem.get_text(strip=True) if title_elem else "タイトル不明"
        
        content_elem = soup.select_one(config['selectors']['content'])
        if content_elem:
            for unwanted in content_elem.select('.rel_kiji, .kijinaka_ad, script, style'):
                unwanted.decompose()
            content = ' '.join(content_elem.get_text(strip=True).split())
            content = content[:300] + '...' if len(content) > 300 else content
        else:
            content = "内容を取得できませんでした。"

        published_date = datetime.now()
        date_elem = soup.select_one(config['selectors']['date'])
        if date_elem:
            date_text = re.sub(r'公開日：', '', date_elem.get_text(strip=True))
            match = re.search(r'(\d{4})[/\.\-年](\d{1,2})[/\.\-月](\d{1,2})', date_text)
            if match:
                year, month, day = map(int, match.groups())
                published_date = datetime(year, month, day)
        
        return {'title': title, 'url': url, 'content': content, 'published_date': published_date, 'source': config['name']}

    def scrape_site(self, site_key: str, max_articles: int = 5) -> List:
        logger.info(f"サイト「{self.site_configs[site_key]['name']}」のスクレイピングを開始します。")
        article_links = self.get_article_links(site_key, max_articles)
        
        if not article_links:
            logger.warning(f"サイト「{self.site_configs[site_key]['name']}」から取得する記事リンクがありません。")
            return []
            
        articles = []
        for i, link in enumerate(article_links, 1):
            logger.info(f"記事 {i}/{len(article_links)} を処理中: {link}")
            time.sleep(2) # サーバー負荷軽減
            article = self.extract_article_content(link, site_key)
            if article:
                articles.append(article)
                logger.info(f"  ✓ 取得完了: {article['title'][:50]}...")
        return articles

def save_articles_json(articles: List, filepath: str):
    articles_for_json = [{'published_date': a['published_date'].isoformat(), **{k: v for k, v in a.items() if k != 'published_date'}} for a in articles]
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
