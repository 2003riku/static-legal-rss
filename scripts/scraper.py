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

    chrome_binary_location = os.environ.get('CHROME_BINARY_LOCATION')
    if chrome_binary_location:
        options.binary_location = chrome_binary_location
        logger.info(f"Chrome binary location set to: {chrome_binary_location}")

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
                'link_pattern': r'/news/\d+$',
                'selectors': {
                    'links': 'main a',
                    'title': 'h1.title-articles, h1.article-title, h1.news-title, h1',
                    'content': 'div.l-cont1',
                    'date': 'h1.title-articles .text-s, .publish-date, time'
                },
                'wait_strategy': 'standard'
            },
            'ben54': {
                'name': '弁護士JPニュース',
                'list_url': 'https://www.ben54.jp/news/',
                'link_pattern': r'/news/\d+$',
                'selectors': {
                    'links': 'main a',
                    'title': 'h1.p-news__title, h1.article-title, h1',
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

    def get_all_article_links(self, max_per_site=10) -> List[Dict]:
        all_links_info = []
        for site_key, config in self.site_configs.items():
            logger.info(f"サイト「{config['name']}」の記事リンクを取得します。")
            try:
                self.driver.get(config['list_url'])
                self.wait_for_page_load(config)

                soup = BeautifulSoup(self.driver.page_source, 'html.parser')

                link_candidates = soup.select(config['selectors']['links'])
                link_pattern = config.get('link_pattern')

                seen_urls = set()
                count = 0
                for link_elem in link_candidates:
                    if count >= max_per_site:
                        break

                    href = link_elem.get('href')
                    if not href or href.strip() in ['#', ''] or href.strip().startswith('javascript:'):
                        continue

                    full_url = urljoin(config['list_url'], href.strip())

                    if link_pattern and not re.search(link_pattern, full_url):
                        continue

                    if full_url not in seen_urls:
                        all_links_info.append({'url': full_url, 'site_key': site_key})
                        seen_urls.add(full_url)
                        count += 1

                logger.info(f"  -> {count}件のリンクを取得しました。")
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

            for unwanted_selector in ['script', 'style', 'aside', 'footer', 'form', '.related', '.box-sns-share', '.l-mail-magazine-btn']:
                for element in soup.select(unwanted_selector):
                    element.decompose()

            title = "タイトル不明"
            title_elem = soup.select_one(config['selectors']['title'])
            if title_elem:
                title = self.clean_text(title_elem.get_text())

            content = "内容を取得できませんでした。"
            content_elem = soup.select_one(config['selectors']['content'])
            if content_elem:
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

        links_to_scrape = scraper.get_all_article_links(max_per_site=10)
        logger.info(f"取得したリンク総数: {len(links_to_scrape)}")

        all_articles = []
        for i, link_info in enumerate(links_to_scrape, 1):
            logger.info(f"処理中: {i}/{len(links_to_scrape)}")

            article = scraper.get_article_detail(link_info['url'], link_info['site_key'])

            if article and article['content'] != "内容を取得できませんでした。":
                all_articles.append(article)

        logger.info(f"全サイトのスクレイピング完了: 合計 {len(all_articles)} 件の記事を取得")

        save_articles_json(all_articles, 'articles.json')

    except Exception as e:
        logger.error(f"メイン処理でエラーが発生: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()
