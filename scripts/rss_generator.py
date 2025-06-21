import json
import os
from datetime import datetime
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
            'link': 'https://your-username.github.io/static-legal-rss/',
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
            '一般法律': []  # デフォルトカテゴリ
        }
        
        for category, keywords in categories.items():
            if category == '一般法律':
                continue
            for keyword in keywords:
                if keyword in text:
                    return category
        
        return '一般法律'
    
    def create_rss_item(self, article: Dict) -> Element:
        """RSS itemエレメントを作成"""
        item = Element('item')
        
        # タイトル
        title = SubElement(item, 'title')
        title.text = article['title']
        
        # リンク
        link = SubElement(item, 'link')
        link.text = article['url']
        
        # 説明
        description = SubElement(item, 'description')
        description.text = f"【{article['source']}】{article['content']}"
        
        # 公開日時
        pub_date = SubElement(item, 'pubDate')
        if isinstance(article['published_date'], str):
            pub_datetime = datetime.fromisoformat(article['published_date'])
        else:
            pub_datetime = article['published_date']
        pub_date.text = pub_datetime.strftime('%a, %d %b %Y %H:%M:%S %z')
        if not pub_date.text.endswith(' +0900'):
            pub_date.text = pub_datetime.strftime('%a, %d %b %Y %H:%M:%S') + ' +0900'
        
        # GUID
        guid = SubElement(item, 'guid')
        guid.set('isPermaLink', 'true')
        guid.text = article['url']
        
        # カテゴリ
        category = SubElement(item, 'category')
        category.text = self.categorize_article(article['title'], article['content'])
        
        # ソース
        source = SubElement(item, 'source')
        source.set('url', article['url'])
        source.text = article['source']
        
        return item
    
    def generate_rss_feed(self, articles: List[Dict], site_filter: str = None) -> str:
        """RSSフィードを生成"""
        # サイトフィルタリング
        if site_filter:
            site_names = {
                'bengo4': '弁護士ドットコム',
                'corporate_legal': '企業法務ナビ',
                'ben54': '弁護士JPニュース'
            }
            target_site = site_names.get(site_filter)
            if target_site:
                articles = [a for a in articles if a['source'] == target_site]
        
        # 日付でソート（新しい順）
        articles = sorted(articles, key=lambda x: x['published_date'] if isinstance(x['published_date'], datetime) else datetime.fromisoformat(x['published_date']), reverse=True)
        
        # RSS要素作成
        rss = Element('rss')
        rss.set('version', '2.0')
        rss.set('xmlns:atom', 'http://www.w3.org/2005/Atom')
        
        channel = SubElement(rss, 'channel')
        
        # チャンネル情報
        title = SubElement(channel, 'title')
        if site_filter:
            site_names = {
                'bengo4': '弁護士ドットコム',
                'corporate_legal': '企業法務ナビ',
                'ben54': '弁護士JPニュース'
            }
            title.text = f"{site_names.get(site_filter, 'Unknown')} - 法律ニュースRSS"
        else:
            title.text = self.channel_info['title']
        
        link = SubElement(channel, 'link')
        link.text = self.channel_info['link']
        
        description = SubElement(channel, 'description')
        description.text = self.channel_info['description']
        
        language = SubElement(channel, 'language')
        language.text = self.channel_info['language']
        
        last_build_date = SubElement(channel, 'lastBuildDate')
        last_build_date.text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0900')
        
        generator = SubElement(channel, 'generator')
        generator.text = self.channel_info['generator']
        
        # Atom link
        atom_link = SubElement(channel, 'atom:link')
        atom_link.set('href', f"{self.channel_info['link']}rss/{'combined' if not site_filter else site_filter}.xml")
        atom_link.set('rel', 'self')
        atom_link.set('type', 'application/rss+xml')
        
        # 記事アイテム追加
        for article in articles[:20]:  # 最新20件
            item = self.create_rss_item(article)
            channel.append(item)
        
        # XML文字列に変換
        rough_string = tostring(rss, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ", encoding=None)
    
    def save_rss_file(self, rss_content: str, filepath: str):
        """RSSファイルを保存"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(rss_content)
        
        logger.info(f"RSSファイルを保存しました: {filepath}")
    
    def generate_metadata(self, articles: List[Dict]) -> Dict:
        """メタデータを生成"""
        return {
            'last_updated': datetime.now().isoformat(),
            'total_articles': len(articles),
            'sources': list(set(article['source'] for article in articles)),
            'categories': list(set(self.categorize_article(article['title'], article['content']) for article in articles))
        }
    
    def save_metadata(self, metadata: Dict, filepath: str):
        """メタデータをJSONファイルに保存"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        logger.info(f"メタデータを保存しました: {filepath}")

def main():
    """メイン処理"""
    generator = StaticRSSGenerator()
    
    # 記事データを読み込み
    if not os.path.exists('articles.json'):
        logger.error("articles.jsonが見つかりません。先にscraper.pyを実行してください。")
        return
    
    with open('articles.json', 'r', encoding='utf-8') as f:
        articles = json.load(f)
    
    logger.info(f"{len(articles)}件の記事を読み込みました")
    
    # 統合RSSフィード生成
    combined_rss = generator.generate_rss_feed(articles)
    generator.save_rss_file(combined_rss, 'rss/combined.xml')
    
    # サイト別RSSフィード生成
    site_keys = ['bengo4', 'corporate_legal', 'ben54']
    for site_key in site_keys:
        site_rss = generator.generate_rss_feed(articles, site_key)
        generator.save_rss_file(site_rss, f'rss/{site_key}.xml')
    
    # メタデータ生成・保存
    metadata = generator.generate_metadata(articles)
    generator.save_metadata(metadata, 'metadata.json')
    
    logger.info("RSS生成完了")
    
    # 統計表示
    print(f"\n=== RSS生成結果 ===")
    print(f"総記事数: {len(articles)}")
    print(f"生成ファイル:")
    print(f"  - rss/combined.xml (統合フィード)")
    for site_key in site_keys:
        print(f"  - rss/{site_key}.xml")
    print(f"  - metadata.json")

if __name__ == "__main__":
    main()

