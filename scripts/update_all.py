# scripts/update_all.py

import os
import sys
import subprocess
import logging
from datetime import datetime

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_command(command, description):
    """コマンドを実行し、結果をログ出力"""
    logger.info(f"開始: {description}")
    try:
        # shell=Trueを避け、コマンドをリストで渡すことでセキュリティを向上
        result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
        logger.info(f"完了: {description}")
        if result.stdout:
            logger.info(f"出力:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"標準エラー出力:\n{result.stderr}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"エラー: {description}")
        logger.error(f"エラー出力:\n{e.stderr}")
        return False

def main():
    """メイン処理"""
    logger.info("=== 法律ニュースRSS更新開始 ===")
    start_time = datetime.now()
    
    # --- ★ 修正箇所 ★ ---
    # os.chdirを削除。このスクリプトはリポジトリのルートから実行されることを想定。
    
    # 1. スクレイピング実行
    if not run_command([sys.executable, "scripts/scraper.py"], "ニュース記事のスクレイピング"):
        logger.error("スクレイピングに失敗しました")
        sys.exit(1)
    
    # 2. RSS生成実行
    if not run_command([sys.executable, "scripts/rss_generator.py"], "RSSフィードの生成"):
        logger.error("RSS生成に失敗しました")
        sys.exit(1)
    
    end_time = datetime.now()
    duration = end_time - start_time
    
    logger.info(f"=== 法律ニュースRSS更新完了 ===")
    logger.info(f"実行時間: {duration.total_seconds():.2f}秒")
    
    # --- ★ 修正箇所 ★ ---
    # メタデータファイルのパスをルートからの相対パスに修正
    try:
        import json
        with open('metadata.json', 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        logger.info(f"総記事数: {metadata.get('total_articles', 'N/A')}")
        logger.info(f"対応サイト: {', '.join(metadata.get('sources',))}")
    except Exception as e:
        logger.warning(f"統計情報の読み込みに失敗: {e}")

if __name__ == "__main__":
    main()
