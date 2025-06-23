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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_driver():
    options = Options()
    options.page_load_strategy = 'eager'
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    
    # ★★★ 対策: 広告や不要な画像をブロックして高速化 ★★★
    prefs = {"profile.managed_default_content_settings.images": 2, "profile.default_content_setting_values.notifications": 2}
    options.add_experimental_option("prefs", prefs)

    if 'CHROME_BINARY_LOCATION' in os.environ:
        options.binary_location = os.environ['CHROME_BINARY_LOCATION']

    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

class RobustScraper:
    def __init__(self, driver):
        self.driver = driver
        self.site_configs = {
            'bengo4': {'name': '弁護士ドットコム', 'list_url': 'https://www.bengo4.com/times/', 'selectors': {'links': 'a.p-latestArticle__link, a.p-secondaryArticle__itemLink, a.c-list__itemLink', 'title': '.p-articleDetail__headText h1', 'content': '.p-articleDetail__body', 'date': '.p-articleDetail__meta time'}},
            'corporate_legal': {'name': '企業法務ナビ', 'list_url': 'https://www.corporate-legal.jp/news/', 'selectors': {'links': 'a.card-categories.news', 'title': 'h1.article_title', 'content': 'div.article_text_area', 'date': 'p.article_date'}},
            'ben54': {'name': '弁護士JPニュース', 'list_url': 'https://www.ben54.jp/news/', 'selectors': {'links': 'article a.c-news-card__link', 'title': 'h1.article_title', 'content': 'div.article_cont', 'date': 'span.date', 'cookie_button': '#cookie_accept'}}
        }

    def get_all_article_links(self, max_per_site=5) -> List[Dict]:
        all_links_info = []
        for site_key, config in self.site_configs.items():
            logger.info(f"サイト「{config['name']}」の記事リンクを取得します。")
            try:
                self.driver.get(config['list_url'])
                if 'cookie_button' in config['selectors']:
                    try:
                        WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, config['selectors']['cookie_button']))).click()
                        logger.info("Cookie同意ボタンをクリックしました。")
                    except TimeoutException:
                        logger.info("Cookie同意ボタンは見つかりませんでした。")
                
                WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, config['selectors']['links'])))
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                
                seen_urls = set()
                count = 0
                for link_elem in soup.select(config['selectors']['links']):
                    if count >= max_per_site: break
                    href = link_elem.get('href')
                    if href:
                        full_url = urljoin(config['list_url'], href.strip())
                        if full_url not in seen_urls:
                            all_links_info.append({'url': full_url, 'site_key': site_key})
                            seen_urls.add(full_url)
                            count += 1
                logger.info(f"  -> {count}件のリンクを取得しました。")
            except Exception as e:
                logger.error(f"「{config['name']}」のリンク取得中にエラー: {e}")
        return all_links_info

    def get_article_detail(self, url: str, site_key: str) -> Dict:
        config = self.site_configs[site_key]
        logger.info(f"記事詳細を取得中: {url}")
        try:
            # ★★★ 対策: 個別ページのタイムアウトを60秒に延長 ★★★
            self.driver.get(url)
            WebDriverWait(self.driver, 60).until(EC.presence_of_element_located((By.CSS_SELECTOR, f"{config['selectors']['title']}, {config['selectors']['content']}")))
            
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            title = (soup.select_one(config['selectors']['title']) or BeautifulSoup('', 'html.parser')).get_text(strip=True) or "タイトル不明"
            content_elem = soup.select_one(config['selectors']['content'])
            if content_elem:
                for unwanted in content_elem.select('script, style, .ad, .advertisement, [class*="related"], [class*="banner"]'):
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
            
            logger.info(f"  ✓ 取得完了: {title[:50]}...")
            return {'title': title, 'url': url, 'content': content, 'published_date': published_date, 'source': config['name']}
        except TimeoutException:
            logger.error(f"記事詳細の読み込みでタイムアウト: {url}")
            return None
        except Exception as e:
            logger.error(f"記事詳細の取得中にエラー ({url}): {e}")
            return None

def save_articles_json(articles: List[Dict], filepath: str):
    articles_for_json = []
    for article in articles:
        if isinstance(article.get('published_date'), datetime):
            article['published_date'] = article['published_date'].isoformat()
        articles_for_json.append(article)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(articles_for_json, f, ensure_ascii=False, indent=2)
    logger.info(f"記事データを保存しました: {filepath}")

def main():
    driver = None
    try:
        driver = setup_driver()
        scraper = RobustScraper(driver)
        
        # ステップ1: 全リンクを一括取得
        links_to_scrape = scraper.get_all_article_links(max_per_site=5)
        
        # ステップ2: 取得したリンクを一件ずつ処理
        all_articles = []
        for link_info in links_to_scrape:
            time.sleep(1) # サーバー負荷軽減
            article = scraper.get_article_detail(link_info['url'], link_info['site_key'])
            if article:
                all_articles.append(article)
                
        logger.info(f"全サイトのスクレイピング完了: 合計{len(all_articles)}件の記事を取得")
        save_articles_json(all_articles, 'articles.json')
        print(f"\n=== 取得結果 ===")
        print(f"総記事数: {len(all_articles)}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()
