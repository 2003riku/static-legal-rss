import json
import os
from datetime import datetime, timezone, timedelta
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
import logging
from typing import List, Dict

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StaticRSSGenerator:
    """GitHub Pages用の静的RSS生成器"""
    
    def __init__(self):
        self.channel_info = {
            'title': '法律ニュース総合RSS',
            'link': 'https://2003riku.github.io/static-legal-rss/',
            'description': '複数の法律関連サイトから取得した最新ニュースを統合配信',
            'language': 'ja',
            'generator': 'Static Legal RSS Tool'
        }
    
    def categorize_article(self, title: str, content: str) -> str:
        """記事のカテゴリを自動判定"""
        title_lower = title.lower()
        content_lower = content.lower()
        text = f"{title_lower} {content_lower}"
        
        categories = {
            '刑事法': ['刑事', '逮捕', '起訴', '判決', '裁判', '犯罪', '容疑', '検察', '警察'],
            '民事法': ['民事', '損害賠償', '契約', '不法行為', '債権', '債務', '相続', '離婚'],
            '企業法': ['企業', '会社法', '株主', '取締役', 'コンプライアンス', 'M&A', '株式'],
            '労働法': ['労働', '雇用', '解雇', '残業', 'ハラスメント', '労災', '賃金'],
            '憲法': ['憲法', '人権', '表現の自由', '選挙', '政治', '国会', '内閣'],
            '行政法': ['行政', '許可', '認可', '規制', '官庁', '公務員', '地方自治'],
            '税法': ['税', '税務', '確定申告', '消費税', '所得税', '法人税'],
            '知的財産法': ['特許', '商標', '著作権', '知的財産', 'IP', '発明'],
            '国際法': ['国際', '外国', '条約', '貿易', '外交', '海外'],
            '一般法律': []
        }
        
        for category, keywords in categories.items():
            if category == '一般法律': continue
            for keyword in keywords:
                if keyword in text:
                    return category
        
        return '一般法律'
    
    # ▼ ここからが変更箇所 ▼
    def create_rss_item(self, article: Dict) -> Element:
        """RSS itemエレメントを作成"""
        item = Element('item')
        SubElement(item, 'title').text = article['title']
        SubElement(item, 'link').text = article['url']
        description = SubElement(item, 'description')
        # 概要から【サイト名】を削除
        description.text = article['content']
        pub_date = SubElement(item, 'pubDate')
        if isinstance(article['published_date'], str):
            pub_datetime = datetime.fromisoformat(article['published_date'])
        else:
            pub_datetime = article['published_date']
        if pub_datetime.tzinfo is None:
            jst = timezone(timedelta(hours=+9))
            pub_datetime = pub_datetime.replace(tzinfo=jst)
        pub_date.text = pub_datetime.strftime('%a, %d %b %Y %H:%M:%S %z')
        guid = SubElement(item, 'guid', isPermaLink='true')
        guid.text = article['url']
        category = SubElement(item, 'category')
        category.text = self.categorize_article(article['title'], article['content'])
        # <source> タグを完全に削除
        return item
    
    def generate_rss_feed(self, articles: List) -> str:
        """RSSフィードを生成（統合フィード専用に変更）"""
        articles = sorted(articles, key=lambda x: datetime.fromisoformat(x['published_date']), reverse=True)
        
        rss = Element('rss', version='2.0', attrib={'xmlns:atom': 'http://www.w3.org/2005/Atom'})
        channel = SubElement(rss, 'channel')
        
        SubElement(channel, 'title').text = self.channel_info['title']
        SubElement(channel, 'link').text = self.channel_info['link']
        SubElement(channel, 'description').text = self.channel_info['description']
        SubElement(channel, 'language').text = self.channel_info['language']
        
        jst = timezone(timedelta(hours=+9))
        SubElement(channel, 'lastBuildDate').text = datetime.now(jst).strftime('%a, %d %b %Y %H:%M:%S %z')
        SubElement(channel, 'generator').text = self.channel_info['generator']
        
        atom_link = SubElement(channel, 'atom:link')
        atom_link.set('href', f"{self.channel_info['link']}rss/combined.xml")
        atom_link.set('rel', 'self')
        atom_link.set('type', 'application/rss+xml')
        
        for article in articles:
            item = self.create_rss_item(article)
            channel.append(item)
        
        rough_string = tostring(rss, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ", encoding="utf-8").decode()
    # ▲ 変更ここまで ▲
    
    def save_rss_file(self, rss_content: str, filepath: str):
        """RSSファイルを保存"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(rss_content)
        logger.info(f"RSSファイルを保存しました: {filepath}")
    
    # ▼ メタデータ生成関数を修正 ▼
    def generate_metadata(self, articles: List) -> Dict:
        """メタデータを生成"""
        # 'sources' キーを削除
        return {
            'last_updated': datetime.now().isoformat(),
            'total_articles': len(articles),
            'categories': list(set(self.categorize_article(article['title'], article['content']) for article in articles))
        }
    # ▲ 修正ここまで ▲
    
    def save_metadata(self, metadata: Dict, filepath: str):
        """メタデータをJSONファイルに保存"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        logger.info(f"メタデータを保存しました: {filepath}")

# ▼ main関数を修正 ▼
def main():
    """メイン処理"""
    generator = StaticRSSGenerator()
    
    if not os.path.exists('articles.json'):
        logger.error("articles.jsonが見つかりません。先にscraper.pyを実行してください。")
        return
    
    with open('articles.json', 'r', encoding='utf-8') as f:
        articles = json.load(f)
    
    logger.info(f"{len(articles)}件の記事を読み込みました")
    
    # 統合RSSフィードのみを生成
    combined_rss = generator.generate_rss_feed(articles)
    generator.save_rss_file(combined_rss, 'rss/combined.xml')
    
    # サイト別のRSS生成処理を削除
    
    # メタデータ生成・保存
    metadata = generator.generate_metadata(articles)
    generator.save_metadata(metadata, 'metadata.json')
    
    logger.info("RSS生成完了")
# ▲ 修正ここまで ▲

if __name__ == "__main__":
    main()
