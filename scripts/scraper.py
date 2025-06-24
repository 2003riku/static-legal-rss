import time
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

def setup_driver():
    options = Options()
    options.page_load_strategy = 'eager'
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    chrome_binary_location = os.environ.get('CHROME_BINARY_LOCATION')
    if chrome_binary_location:
        options.binary_location = chrome_binary_location
        logger.info(f"Chrome binary location set to: {chrome_binary_location}")
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"})
    return driver

class RobustScraper:
    def __init__(self, driver):
        self.driver = driver
        self.site_configs = {
            'corporate_legal': {
                'name': '企業法務ナビ',
                'list_url': 'https://www.corporate-legal.jp/news/',
                'link_pattern': r'/news/\d+$',
                'selectors': {
                    'links': 'div.l-main div.container a[href*="/news/"]',
                    'title': 'h1.title-articles, h1.article-title, h1.news-title, h1',
                    'content': 'div.l-cont1',
                    'date': 'time[datetime], .publish-date, h1.title-articles .text-s'
                },
                'pagination_selector': 'a.next.page-numbers' # 次のページへのリンク
            },
            'ben54': {
                'name': '弁護士JPニュース',
                'list_url': 'https://www.ben54.jp/news/list',
                'link_pattern': r'/news/\d+',
                'selectors': {
                    'links': 'ul.c-list li.p-news-list a',
                    'title': 'h1.p-ttl__lv1',
                    'content': 'div.p-news__contents',
                    'date': 'time[datetime]',
                },
                'wait_selector': 'ul.c-list',
                'pagination_selector': 'li.p-btn__next a' # 次のページへのリンク
            }
        }

    def wait_for_page_load(self, timeout: int = 15):
        try:
            WebDriverWait(self.driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")
            time.sleep(2) # 動的コンテンツの描画を待つ
        except TimeoutException:
            logger.warning("ページの完全読み込みがタイムアウトしましたが、処理を続行します")

    # ▼ ここからが大幅な改修箇所 ▼
    def get_all_article_links(self, max_per_site=100) -> List[Dict]:
        all_links_info = []
        for site_key, config in self.site_configs.items():
            logger.info(f"サイト「{config['name']}」の記事リンクを取得します (最大{max_per_site}件)。")
            site_links = []
            seen_urls = set()
            
            try:
                self.driver.get(config['list_url'])
                self.wait_for_page_load()
                
                page_count = 1
                while len(site_links) < max_per_site:
                    logger.info(f"  -> {page_count}ページ目をスクレイピング中...")
                    
                    if config.get('wait_selector'):
                        WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, config['wait_selector'])))
                    
                    soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                    link_candidates = soup.select(config['selectors']['links'])
                    
                    found_new_link = False
                    for link_elem in link_candidates:
                        if len(site_links) >= max_per_site: break
                        
                        href = link_elem.get('href')
                        if not href: continue
                        
                        full_url = urljoin(self.driver.current_url, href.strip())
                        
                        if config.get('link_pattern') and not re.search(config['link_pattern'], full_url):
                            continue
                        
                        if full_url not in seen_urls:
                            site_links.append({'url': full_url, 'site_key': site_key})
                            seen_urls.add(full_url)
                            found_new_link = True
                    
                    # 現在のページで目標数に達したか、新しいリンクが一つも見つからなかったら終了
                    if len(site_links) >= max_per_site or not found_new_link:
                        break

                    # 次のページへのナビゲーション
                    pagination_selector = config.get('pagination_selector')
                    if not pagination_selector:
                        logger.info("  -> ページネーション設定がないため、1ページで終了します。")
                        break
                        
                    try:
                        next_button = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, pagination_selector))
                        )
                        # JavaScriptでクリックすることで、広告などに隠れているボタンもクリックできる
                        self.driver.execute_script("arguments[0].click();", next_button)
                        page_count += 1
                        self.wait_for_page_load() # 次のページの読み込みを待つ
                    except (NoSuchElementException, TimeoutException):
                        logger.info("  -> 「次のページ」ボタンが見つかりませんでした。最後のページに到達したと判断します。")
                        break

                all_links_info.extend(site_links)
                logger.info(f"  => 合計 {len(site_links)} 件のリンクを取得しました。")

            except Exception as e:
                logger.error(f"「{config['name']}」のリンク取得中にエラー: {e}", exc_info=True)
                
        return all_links_info
    # ▲ ここまでが大幅な改修箇所 ▲
    
    # ... 他の関数 (clean_text, get_article_detail, etc.) は変更なし ...
    def clean_text(self, text: str) -> str:
        if not text: return ""
        return re.sub(r'\s+', ' ', text).strip()

    def get_article_detail(self, url: str, site_key: str) -> Optional[Dict]:
        config = self.site_configs[site_key]
        logger.info(f"記事詳細を取得中: {url}")
        time.sleep(1) # サイトへの配慮

        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, config['selectors']['title'])))
            time.sleep(1)
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            for unwanted_selector in ['script', 'style', 'aside', 'footer', 'form', ".related", "header"]:
                for element in soup.select(unwanted_selector):
                    element.decompose()
            
            title_elem = soup.select_one(config['selectors']['title'])
            title = self.clean_text(title_elem.get_text()) if title_elem else "タイトル不明"

            content = "内容を取得できませんでした。"
            content_elem = soup.select_one(config['selectors']['content'])
            if content_elem:
                text_parts = [self.clean_text(p.get_text()) for p in content_elem.find_all('p') if len(self.clean_text(p.get_text())) > 20]
                if text_parts: content = ' '.join(text_parts)[:500] + '...'
            
            published_date = None
            date_elem = soup.select_one(config['selectors']['date'])
            if date_elem:
                dt_str = date_elem.get('datetime', self.clean_text(date_elem.get_text()))
                try: published_date = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                except ValueError:
                    match = re.search(r'(\d{4})[/\.年]\s*(\d{1,2})[/\.月]\s*(\d{1,2})', dt_str)
                    if match: published_date = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            
            if not isinstance(published_date, datetime): published_date = datetime.now(JST)
            published_date = published_date.astimezone(JST) if published_date.tzinfo else published_date.replace(tzinfo=JST)
            
            result = {'title': title, 'url': url, 'content': content, 'published_date': published_date, 'source': config['name']}
            
            if title == "タイトル不明": logger.warning(f"  - タイトルが取得できませんでした。")
            else: logger.info(f"  ✓ 取得完了: {title[:50]}...")
            return result
        except Exception as e:
            logger.error(f"記事詳細の取得中にエラー ({url}): {e}")
            return None

def save_articles_json(articles: List[Dict], filepath: str):
    # ... 変更なし ...
    articles_for_json = []
    for article in articles:
        new_article = article.copy()
        if isinstance(new_article.get('published_date'), datetime):
            new_article['published_date'] = new_article['published_date'].isoformat()
        articles_for_json.append(new_article)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(articles_for_json, f, ensure_ascii=False, indent=2)
    logger.info(f"記事データを保存しました: {filepath}")

def main():
    # ... ここは変更なし、100のまま ...
    driver = None
    try:
        driver = setup_driver()
        scraper = RobustScraper(driver)
        links_to_scrape = scraper.get_all_article_links(max_per_site=100)
        logger.info(f"取得したリンク総数: {len(links_to_scrape)}")

        all_articles = []
        if links_to_scrape:
            for i, link_info in enumerate(links_to_scrape, 1):
                logger.info(f"詳細処理中: {i}/{len(links_to_scrape)}")
                article = scraper.get_article_detail(link_info['url'], link_info['site_key'])
                if article and article.get('content') != "内容を取得できませんでした。" and article.get('title') != "タイトル不明":
                    all_articles.append(article)
        
        logger.info(f"全サイトのスクレイピング完了: 合計 {len(all_articles)} 件の記事を取得")
        save_articles_json(all_articles, 'articles.json')
    except Exception as e:
        logger.error(f"メイン処理でエラーが発生: {e}", exc_info=True)
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()
