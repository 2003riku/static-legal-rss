import time
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse

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

# 日本標準時 (JST) のタイムゾーンを定義
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
    
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)

    if 'CHROME_BINARY_LOCATION' in os.environ:
        options.binary_location = os.environ['CHROME_BINARY_LOCATION']

    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
    })
    
    return driver

class RobustScraper:
    def __init__(self, driver):
        self.driver = driver
        self.site_configs = {
            'corporate_legal': {
                'name': '企業法務ナビ',
                'list_url': 'https://www.corporate-legal.jp/news/',
                'selectors': {
                    'links': '.news-item a, .article-link, .news-list-item a, h2.news-headline a, a[href*="/news/"]',
                    'title': 'h1.title-articles, h1.article-title, h1.news-title, h1',
                    # 修正点: ご提供のHTMLに基づきセレクタを更新
                    'content': 'div.l-cont1',
                    'date': 'h1.title-articles .text-s, .publish-date, time'
                },
                'wait_strategy': 'standard',
                'cookie_selectors': '.cookie-consent, .privacy-banner, .gdpr-notice'
            },
            'ben54': {
                'name': '弁護士JPニュース',
                'list_url': 'https://www.ben54.jp/news/',
                'selectors': {
                    'links': '.news-list article a, .article-item .title-link, .news-item h2 a, [class*="article"] [class*="title"] a, a[href*="/news/"]',
                    'title': 'h1.p-news__title, h1.article-title, h1',
                    # 修正点: ご提供のHTMLに基づきセレクタを更新
                    'content': '.p-news__contents',
                    'date': '.p-news__date, time[datetime]',
                    'author': '.p-news__meta .writer'
                },
                'wait_strategy': 'dynamic',
                'scroll_before_wait': True,
                'rate_limit': 3
            }
        }

    def wait_for_page_load(self, config: Dict, timeout: int = 30):
        strategy = config.get('wait_strategy', 'standard')
        if strategy == 'dynamic':
            try:
                WebDriverWait(self.driver, timeout).until(
                    lambda driver: driver.execute_script("return document.readyState") == "complete"
                )
            except TimeoutException:
                logger.warning("ページの完全読み込みがタイムアウトしましたが、処理を続行します")
            time.sleep(2)
            if config.get('scroll_before_wait'):
                try:
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                    time.sleep(1)
                    self.driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                except Exception as e:
                    logger.debug(f"スクロール処理でエラー: {e}")

    def handle_cookie_consent(self, config: Dict):
        cookie_selectors = config.get('cookie_selectors', '')
        if cookie_selectors:
            for selector in [s.strip() for s in cookie_selectors.split(',')]:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed():
                            for button in element.find_elements(By.TAG_NAME, 'button'):
                                if any(text in button.text.lower() for text in ['同意', 'accept', 'ok', '承認']):
                                    button.click()
                                    logger.info("Cookie同意バナーを処理しました")
                                    time.sleep(1)
                                    return
                except Exception:
                    pass

    def get_all_article_links(self, max_candidates_per_site=20) -> List[Dict]:
        all_links_info = []
        for site_key, config in self.site_configs.items():
            logger.info(f"サイト「{config['name']}」の記事リンク候補を取得します。")
            try:
                self.driver.get(config['list_url'])
                self.wait_for_page_load(config)
                self.handle_cookie_consent(config)
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                found_links = soup.select(config['selectors']['links'])
                seen_urls = set()
                count = 0
                for link_elem in found_links:
                    if count >= max_candidates_per_site:
                        break
                    href = link_elem.get('href')
                    if href and href.strip() != '#' and not href.strip().startswith('javascript:'):
                        full_url = urljoin(config['list_url'], href.strip())
                        if full_url not in seen_urls:
                            all_links_info.append({'url': full_url, 'site_key': site_key})
                            seen_urls.add(full_url)
                            count += 1
                logger.info(f"  -> {count}件のリンク候補を取得しました。")
            except Exception as e:
                logger.error(f"「{config['name']}」のリンク取得中にエラー: {e}")
        return all_links_info
        
    def clean_text(self, text: str) -> str:
        if not text:
            return ""
        return re.sub(r'\s+', ' ', text).strip()

    def get_article_detail(self, url: str, site_key: str) -> Optional[Dict]:
        config = self.site_configs[site_key]
        logger.info(f"記事詳細を取得中: {url}")
        time.sleep(config.get('rate_limit', 1))
        
        try:
            self.driver.get(url)
            self.wait_for_page_load(config)
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            for unwanted_selector in ['script', 'style', 'aside', 'footer', 'form', '.related', '.box-sns-share']:
                for element in soup.select(unwanted_selector):
                    element.decompose()
            
            title = "タイトル不明"
            title_elem = soup.select_one(config['selectors']['title'])
            if title_elem:
                title = self.clean_text(title_elem.get_text())
            
            content = "内容を取得できませんでした。"
            content_elem = soup.select_one(config['selectors']['content'])
            if content_elem:
                # 修正点: 本文抽出ロジックを改善
                paragraphs = content_elem.find_all('p')
                text_parts = [self.clean_text(p.get_text()) for p in paragraphs if len(self.clean_text(p.get_text())) > 20]
                if text_parts:
                    content = ' '.join(text_parts)[:500] + '...'

            published_date = None
            date_elem = soup.select_one(config['selectors']['date'])
            if date_elem:
                dt_str = date_elem.get('datetime', self.clean_text(date_elem.get_text()))
                if dt_str.upper().endswith('Z'):
                    dt_str = dt_str[:-1] + '+00:00'
                try:
                    published_date = datetime.fromisoformat(dt_str)
                except ValueError:
                    match = re.search(r'(\d{4})[/\.年](\d{1,2})[/\.月](\d{1,2})', dt_str)
                    if match:
                        published_date = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            
            if not isinstance(published_date, datetime):
                published_date = datetime.now(JST)
            
            if published_date.tzinfo is None:
                published_date = published_date.replace(tzinfo=JST)
            else:
                published_date = published_date.astimezone(JST)

            result = {'title': title, 'url': url, 'content': content, 'published_date': published_date, 'source': config['name']}
            logger.info(f"  ✓ 取得完了: {title[:50]}...")
            return result
            
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
        
        TARGET_ARTICLES_COUNT = 10
        now = datetime.now(JST)
        # 約6ヶ月前の記事をターゲットにする (5ヶ月前～7ヶ月前の記事を対象)
        DATE_FROM = now - timedelta(days=210)
        DATE_TO = now - timedelta(days=150)
        
        logger.info(f"取得対象期間: {DATE_FROM.strftime('%Y-%m-%d')} から {DATE_TO.strftime('%Y-%m-%d')}")

        links_to_scrape = scraper.get_all_article_links(max_candidates_per_site=50) # 候補を多めに取得
        logger.info(f"取得したリンク候補総数: {len(links_to_scrape)}")
        
        all_articles = []
        for i, link_info in enumerate(links_to_scrape, 1):
            if len(all_articles) >= TARGET_ARTICLES_COUNT:
                logger.info(f"目的の {TARGET_ARTICLES_COUNT} 件の記事を取得したため、処理を終了します。")
                break

            logger.info(f"処理中: {i}/{len(links_to_scrape)} (現在 {len(all_articles)} 件取得済み)")
            
            article = scraper.get_article_detail(link_info['
