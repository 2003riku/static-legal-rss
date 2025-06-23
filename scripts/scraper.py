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
    
    # より自然なUser-Agent
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    
    # 画像読み込みを無効化して高速化
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_setting_values": {
            "cookies": 1, "images": 2, "javascript": 1, "plugins": 2,
            "popups": 2, "geolocation": 2, "notifications": 2, "media_stream": 2,
            "media_stream_mic": 2, "media_stream_camera": 2, "protocol_handlers": 2,
            "ppapi_broker": 2, "automatic_downloads": 2, "midi_sysex": 2,
            "push_messaging": 2, "ssl_cert_decisions": 2, "metro_switch_to_desktop": 2,
            "protected_media_identifier": 2, "app_banner": 2, "site_engagement": 2,
            "durable_storage": 2
        }
    }
    options.add_experimental_option("prefs", prefs)

    if 'CHROME_BINARY_LOCATION' in os.environ:
        options.binary_location = os.environ['CHROME_BINARY_LOCATION']

    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # JavaScriptでwebdriverプロパティを隠す
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        '''
    })
    
    return driver

class RobustScraper:
    def __init__(self, driver):
        self.driver = driver
        self.site_configs = {
            'bengo4': {
                'name': '弁護士ドットコム',
                'list_url': 'https://www.bengo4.com/times/',
                'selectors': {
                    'links': 'a[href*="/times/articles/"], .p-latestArticle__link, .p-secondaryArticle__itemLink, .c-list__itemLink, .news-item a, .article-item a, .topic-item a',
                    # 修正点: タイトル取得のセレクタに汎用的な `h1` を追加
                    'title': '.p-articleDetail__headText h1, article h1, .article-title h1, h1.article-title, h1',
                    'content': '.p-articleDetail__body, .article-content, .main-content, .content-body',
                    'date': '.p-articleDetail__meta time, .publish-date, .article-date, time'
                },
                'wait_strategy': 'dynamic',
                'needs_auth': True,
                'scroll_before_wait': True
            },
            'corporate_legal': {
                'name': '企業法務ナビ',
                'list_url': 'https://www.corporate-legal.jp/news/',
                'selectors': {
                    'links': '.news-item a, .article-link, .news-list-item a, h2.news-headline a, a[href*="/news/"]',
                    'title': 'h1.article-title, h1.news-title, .main-headline, .article-header h1, h1',
                    'content': '.article-content, .main-content, .news-body, .article-text, article .content, div.article_text_area',
                    'date': '.publish-date, .article-date, .news-date, time.published, .post-date, p.article_date, time'
                },
                'wait_strategy': 'standard',
                'cookie_selectors': '.cookie-consent, .privacy-banner, .gdpr-notice'
            },
            'ben54': {
                'name': '弁護士JPニュース',
                'list_url': 'https://www.ben54.jp/news/',
                'selectors': {
                    'links': '.news-list article a, .article-item .title-link, .news-item h2 a, [class*="article"] [class*="title"] a, a[href*="/news/"]',
                    'title': 'h1.article-title, .main-title, .news-title h1, [class*="title"] h1, h1',
                    'content': '.article-content, .main-content, .news-body, [class*="content"] [class*="body"], article .content, div.article_cont',
                    'date': '.publish-date, .article-date, time[datetime], [class*="date"], .meta-info .date, span.date',
                    'author': '.author-name, .byline, .article-author, [class*="author"]'
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
            selectors_list = [s.strip() for s in cookie_selectors.split(',')]
            for selector in selectors_list:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed():
                            buttons = element.find_elements(By.TAG_NAME, 'button')
                            for button in buttons:
                                if any(text in button.text.lower() for text in ['同意', 'accept', 'ok', '承認']):
                                    button.click()
                                    logger.info("Cookie同意バナーを処理しました")
                                    time.sleep(1)
                                    return
                except Exception:
                    pass

    def try_multiple_selectors(self, selectors: str, timeout: int = 10) -> Optional[str]:
        selector_list = [s.strip() for s in selectors.split(',')]
        for selector in selector_list:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    logger.debug(f"セレクタ '{selector}' で {len(elements)} 個の要素を発見")
                    return selector
            except Exception:
                continue
        return None

    def get_all_article_links(self, max_per_site=5) -> List[Dict]:
        all_links_info = []
        for site_key, config in self.site_configs.items():
            logger.info(f"サイト「{config['name']}」の記事リンクを取得します。")
            if config.get('needs_auth'):
                logger.warning(f"「{config['name']}」は認証が必要な可能性があります。公開コンテンツのみを取得します。")
            
            retry_count = 0
            max_retries = 2
            
            while retry_count <= max_retries:
                try:
                    self.driver.get(config['list_url'])
                    self.wait_for_page_load(config)
                    self.handle_cookie_consent(config)
                    
                    link_selector = self.try_multiple_selectors(config['selectors']['links'], timeout=20)
                    soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                    
                    found_links = []
                    if link_selector:
                        found_links = soup.select(link_selector)

                    if not found_links:
                        logger.warning(f"セレクタでリンクが見つかりません。URLパターンで代替検索します: {site_key}")
                        all_links_on_page = soup.find_all('a', href=True)
                        pattern = {
                            'bengo4': r'/times/articles/\d+',
                            'corporate_legal': r'/news/\d+',
                            'ben54': r'/news/\d+'
                        }.get(site_key)

                        if pattern:
                            for link in all_links_on_page:
                                if re.search(pattern, link.get('href', '')):
                                    found_links.append(link)
                    
                    seen_urls = set()
                    count = 0
                    for link_elem in found_links:
                        if count >= max_per_site:
                            break
                        
                        href = link_elem.get('href')
                        if href and href.strip() != '#' and not href.strip().startswith('javascript:'):
                            full_url = urljoin(config['list_url'], href.strip())
                            if self._is_valid_news_url(full_url, site_key) and full_url not in seen_urls:
                                all_links_info.append({'url': full_url, 'site_key': site_key})
                                seen_urls.add(full_url)
                                count += 1
                    
                    logger.info(f"  -> {count}件のリンクを取得しました。")
                    if count > 0:
                        break 
                    else:
                        raise Exception("記事リンクが0件でした")

                except Exception as e:
                    retry_count += 1
                    if retry_count > max_retries:
                        logger.error(f"「{config['name']}」のリンク取得中にエラー（リトライ回数超過）: {e}")
                    else:
                        logger.warning(f"「{config['name']}」のリンク取得中にエラー。リトライ {retry_count}/{max_retries}: {e}")
                        time.sleep(3)
        return all_links_info

    def _is_valid_news_url(self, url: str, site_key: str) -> bool:
        patterns = {
            'bengo4': r'/times/articles/\d+',
            'corporate_legal': r'/news/\d+',
            'ben54': r'/news/\d+'
        }
        pattern = patterns.get(site_key)
        if pattern:
            return bool(re.search(pattern, url))
        return True

    def clean_text(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def get_article_detail(self, url: str, site_key: str) -> Optional[Dict]:
        config = self.site_configs[site_key]
        logger.info(f"記事詳細を取得中: {url}")
        time.sleep(config.get('rate_limit', 2))
        
        retry_count = 0
        max_retries = 2
        
        while retry_count <= max_retries:
            try:
                self.driver.get(url)
                self.wait_for_page_load(config)
                self.handle_cookie_consent(config)
                
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                
                for unwanted_selector in ['script', 'style', '.ad', '.advertisement', '[class*="ad"]', '[class*="banner"]', '.sidebar', '.related-links', '.sns-share', '.footer-content', '[class*="related"]', '[class*="ranking"]']:
                    for element in soup.select(unwanted_selector):
                        element.decompose()
                
                title = "タイトル不明"
                for selector in [s.strip() for s in config['selectors']['title'].split(',')]:
                    title_elem = soup.select_one(selector)
                    if title_elem:
                        cleaned_title = self.clean_text(title_elem.get_text())
                        if cleaned_title:
                            title = cleaned_title
                            break
                
                content = "内容を取得できませんでした。"
                for selector in [s.strip() for s in config['selectors']['content'].split(',')]:
                    content_elem = soup.select_one(selector)
                    if content_elem:
                        text_parts = []
                        paragraphs = content_elem.find_all(['p', 'div'], recursive=False) or [content_elem]
                        for p in paragraphs[:5]:
                            text = self.clean_text(p.get_text())
                            if text and len(text) > 20:
                                text_parts.append(text)
                        if text_parts:
                            content = ' '.join(text_parts)[:300] + '...'
                            break
                        else: # 段落が見つからない場合
                             full_text = self.clean_text(content_elem.get_text())
                             if full_text:
                                 content = full_text[:300] + '...'
                                 break
                
                # 修正点: 日付取得とタイムゾーン正規化
                published_date = None
                date_selectors = [s.strip() for s in config['selectors']['date'].split(',')]
                for selector in date_selectors:
                    date_elem = soup.select_one(selector)
                    if date_elem:
                        if date_elem.get('datetime'):
                            try:
                                dt_str = date_elem['datetime'].strip()
                                if dt_str.upper().endswith('Z'):
                                    dt_str = dt_str[:-1] + '+00:00'
                                published_date = datetime.fromisoformat(dt_str)
                                break
                            except ValueError:
                                pass
                        
                        date_text = self.clean_text(date_elem.get_text())
                        date_text = re.sub(r'公開日：|更新日：|掲載日：|配信：', '', date_text).strip()
                        
                        patterns = [
                            (r'(\d{4})[/\.\-年](\d{1,2})[/\.\-月](\d{1,2})日?\s*(\d{1,2}):(\d{2})', 5),
                            (r'(\d{4})[/\.\-年](\d{1,2})[/\.\-月](\d{1,2})日?', 3)
                        ]
                        
                        for pattern, group_count in patterns:
                            match = re.search(pattern, date_text)
                            if match:
                                try:
                                    parts = [int(p) for p in match.groups()]
                                    if group_count == 5:
                                        published_date = datetime(parts[0], parts[1], parts[2], parts[3], parts[4])
                                    elif group_count == 3:
                                        published_date = datetime(parts[0], parts[1], parts[2])
                                    break
                                except:
                                    continue
                        if published_date:
                            break
                
                # タイムゾーンを統一
                if not isinstance(published_date, datetime):
                    published_date = datetime.now(JST) # フォールバック
                
                if published_date.tzinfo is None:
                    published_date = published_date.replace(tzinfo=JST) # Naive -> Aware
                else:
                    published_date = published_date.astimezone(JST) # Aware -> JSTに変換

                author = None
                if site_key == 'ben54' and 'author' in config['selectors']:
                    for selector in [s.strip() for s in config['selectors']['author'].split(',')]:
                        author_elem = soup.select_one(selector)
                        if author_elem:
                            author = self.clean_text(author_elem.get_text())
                            break
                
                logger.info(f"  ✓ 取得完了: {title[:50]}...")
                
                result = {
                    'title': title, 'url': url, 'content': content,
                    'published_date': published_date, 'source': config['name']
                }
                if author:
                    result['author'] = author
                
                return result
                
            except Exception as e:
                retry_count += 1
                if retry_count > max_retries:
                    logger.error(f"記事詳細の取得中にエラー（リトライ回数超過） ({url}): {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
                    return None
                else:
                    logger.warning(f"記事詳細の取得中にエラー。リトライ {retry_count}/{max_retries} ({url}): {e}")
                    time.sleep(3)
        return None

def save_articles_json(articles: List[Dict], filepath: str):
    articles_for_json = []
    for article in articles:
        # datetimeオブジェクトをISO 8601形式の文字列に変換
        if 'published_date' in article and isinstance(article['published_date'], datetime):
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
        
        links_to_scrape = scraper.get_all_article_links(max_per_site=5)
        logger.info(f"取得したリンク総数: {len(links_to_scrape)}")
        
        site_counts = {}
        for link_info in links_to_scrape:
            site_key = link_info['site_key']
            site_name = scraper.site_configs[site_key]['name']
            site_counts[site_name] = site_counts.get(site_name, 0) + 1
        
        logger.info("サイト別リンク取得結果:")
        for site_name, count in site_counts.items():
            logger.info(f"  - {site_name}: {count}件")
        
        all_articles = []
        for i, link_info in enumerate(links_to_scrape, 1):
            logger.info(f"処理中: {i}/{len(links_to_scrape)}")
            article = scraper.get_article_detail(link_info['url'], link_info['site_key'])
            if article:
                all_articles.append(article)
                
        logger.info(f"全サイトのスクレイピング完了: 合計{len(all_articles)}件の記事を取得")
        
        site_results = {}
        for article in all_articles:
            source = article['source']
            site_results[source] = site_results.get(source, 0) + 1
        
        print("\n=== 最終取得結果 ===")
        print(f"総記事数: {len(all_articles)}")
        for source, count in site_results.items():
            print(f"  - {source}: {count}件")
        
        print("\n=== 取得記事サンプル ===")
        for article in all_articles[:3]:
            print(f"\nタイトル: {article['title'][:50]}...")
            print(f"URL: {article['url']}")
            print(f"ソース: {article['source']}")
            # published_dateはdatetimeオブジェクトなので、表示用に文字列化
            date_str = article['published_date'].isoformat() if isinstance(article['published_date'], datetime) else str(article['published_date'])
            print(f"日付: {date_str}")
            print(f"内容: {article['content'][:100]}...")
        
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
