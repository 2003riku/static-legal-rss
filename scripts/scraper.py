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
import cloudscraper

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Selenium WebDriver Setup ---
def setup_driver():
    """Selenium WebDriverをセットアップする"""
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

# --- スクレイパークラス ---
class HybridScraper:
    def __init__(self):
        self.driver = None
        self.cloudscraper = cloudscraper.create_scraper()
        self.cloudscraper.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        })
    
    def get_driver(self):
        """必要になった場合にのみSeleniumドライバを初期化"""
        if self.driver is None:
            logger.info("Selenium WebDriverを初期化しています...")
            self.driver = setup_driver()
        return self.driver

    def close_driver(self):
        """Seleniumドライバを閉じる"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            logger.info("Selenium WebDriverを終了しました。")
            
    # --- サイト別スクレイピングメソッド ---

    def scrape_bengo4(self, max_articles=5) -> List[Dict]:
        """弁護士ドットコム: JSON解析方式"""
        logger.info("サイト「弁護士ドットコム」のスクレイピングを開始します (JSON解析方式)。")
        url = 'https://www.bengo4.com/times/'
        try:
            response = self.cloudscraper.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            json_data_tag = soup.find('script', {'id': '__NEXT_DATA__'})
            if not json_data_tag:
                logger.error("弁護士ドットコム: __NEXT_DATA__ JSONが見つかりません。")
                return []
                
            data = json.loads(json_data_tag.string)
            articles_data = data.get('props', {}).get('pageProps', {}).get('articles', [])
            
            articles = []
            for article_json in articles_data[:max_articles]:
                article_url = urljoin(url, f"/times/articles/{article_json.get('id')}/")
                articles.append({
                    'title': article_json.get('title', 'タイトル不明'),
                    'url': article_url,
                    'content': article_json.get('description', '内容不明')[:300] + '...',
                    'published_date': datetime.fromisoformat(article_json.get('publishedAt').replace('Z', '+00:00')),
                    'source': '弁護士ドットコム'
                })
            logger.info(f"弁護士ドットコムで{len(articles)}件の記事を取得しました。")
            return articles
        except Exception as e:
            logger.error(f"弁護士ドットコムのスクレイピング中にエラー: {e}", exc_info=True)
            return []

    def scrape_corporate_legal(self, max_articles=5) -> List[Dict]:
        """企業法務ナビ: CloudScraper方式"""
        logger.info("サイト「企業法務ナビ」のスクレイピングを開始します (CloudScraper方式)。")
        url = 'https://www.corporate-legal.jp/news/'
        try:
            response = self.cloudscraper.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            links_elems = soup.select('a.card-categories.news')
            article_links = [urljoin(url, elem.get('href')) for elem in links_elems][:max_articles]
            
            articles = []
            for link in article_links:
                time.sleep(1)
                page_res = self.cloudscraper.get(link, timeout=30)
                page_soup = BeautifulSoup(page_res.content, 'html.parser')
                
                title = page_soup.select_one('h1.article_title')
                title = title.get_text(strip=True) if title else "タイトル不明"

                content_elem = page_soup.select_one('div.article_text_area')
                content = ' '.join(content_elem.get_text(strip=True).split())[:300] + '...' if content_elem else "内容不明"

                date_elem = page_soup.select_one('p.article_date')
                published_date = datetime.now()
                if date_elem:
                    match = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', date_elem.get_text())
                    if match:
                        published_date = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                
                articles.append({'title': title, 'url': link, 'content': content, 'published_date': published_date, 'source': '企業法務ナビ'})
                logger.info(f"  ✓ 取得完了: {title[:50]}...")
            
            logger.info(f"企業法務ナビで{len(articles)}件の記事を取得しました。")
            return articles
        except Exception as e:
            logger.error(f"企業法務ナビのスクレイピング中にエラー: {e}", exc_info=True)
            return []

    def scrape_ben54(self, max_articles=5) -> List[Dict]:
        """弁護士JPニュース: Selenium方式"""
        logger.info("サイト「弁護士JPニュース」のスクレイピングを開始します (Selenium方式)。")
        driver = self.get_driver()
        url = 'https://www.ben54.jp/news/'
        articles = []
        try:
            driver.get(url)
            
            # Cookie同意ボタン対策
            try:
                WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#cookie_accept"))).click()
                logger.info("弁護士JPニュース: Cookie同意ボタンをクリックしました。")
            except TimeoutException:
                logger.info("弁護士JPニュース: Cookie同意ボタンは見つかりませんでした。")

            # 記事一覧が表示されるまで待つ
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.c-news-card--small a.c-news-card__link")))
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            link_elems = soup.select('article a.c-news-card__link')
            article_links = []
            seen_urls = set()
            for elem in link_elems:
                if len(article_links) >= max_articles: break
                href = elem.get('href')
                if href and href not in seen_urls:
                    article_links.append(href)
                    seen_urls.add(href)

            for link in article_links:
                time.sleep(1)
                driver.get(link)
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1.article_title")))
                page_soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                title = page_soup.select_one('h1.article_title').get_text(strip=True)
                content_elem = page_soup.select_one('div.article_cont')
                content = ' '.join(content_elem.get_text(strip=True).split())[:300] + '...' if content_elem else "内容不明"
                
                date_elem = page_soup.select_one('span.date')
                published_date = datetime.now()
                if date_elem:
                    match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})', date_elem.get_text())
                    if match:
                        published_date = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))

                articles.append({'title': title, 'url': link, 'content': content, 'published_date': published_date, 'source': '弁護士JPニュース'})
                logger.info(f"  ✓ 取得完了: {title[:50]}...")

            logger.info(f"弁護士JPニュースで{len(articles)}件の記事を取得しました。")
            return articles
        except Exception as e:
            logger.error(f"弁護士JPニュースのスクレイピング中にエラー: {e}", exc_info=True)
            return []

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
    scraper = HybridScraper()
    all_articles = []
    try:
        # サイトごとに最適化されたメソッドを呼び出す
        all_articles.extend(scraper.scrape_bengo4(max_articles=5))
        all_articles.extend(scraper.scrape_corporate_legal(max_articles=5))
        all_articles.extend(scraper.scrape_ben54(max_articles=5))
        
        logger.info(f"全サイトのスクレイピング完了: 合計{len(all_articles)}件の記事を取得")
        save_articles_json(all_articles, 'articles.json')
        print(f"\n=== 取得結果 ===")
        print(f"総記事数: {len(all_articles)}")
    finally:
        scraper.close_driver()

if __name__ == "__main__":
    main()
