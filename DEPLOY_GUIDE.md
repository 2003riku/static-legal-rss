# GitHub Pages完全デプロイガイド

## 🎯 このガイドについて

このガイドでは、法律ニュース総合RSSツールをGitHub Pagesに完全無料でデプロイし、永続的に運用する方法を詳しく説明します。

## 📋 事前準備

### 必要なもの
- GitHubアカウント（無料）
- 基本的なGitの知識
- テキストエディタ

### 推奨環境
- Windows 10/11、macOS、またはLinux
- Git（最新版）
- 任意のテキストエディタ（VS Code推奨）

## 🚀 ステップバイステップデプロイ手順

### ステップ1: GitHubリポジトリの作成

1. **GitHubにログイン**
   - https://github.com にアクセス
   - アカウントにログイン

2. **新しいリポジトリを作成**
   - 右上の「+」ボタンをクリック
   - 「New repository」を選択

3. **リポジトリ設定**
   ```
   Repository name: static-legal-rss
   Description: 法律ニュース総合RSS - 完全無料版
   Visibility: Public（重要：GitHub Pages無料版はPublicのみ）
   Initialize with README: ✅ チェック
   ```

4. **「Create repository」をクリック**

### ステップ2: ローカル環境の準備

1. **リポジトリをクローン**
   ```bash
   git clone https://github.com/your-username/static-legal-rss.git
   cd static-legal-rss
   ```

2. **プロジェクトファイルを配置**
   - 提供されたプロジェクトファイル一式をコピー
   - 以下のファイル構成になることを確認：
   ```
   static-legal-rss/
   ├── index.html
   ├── README.md
   ├── scripts/
   │   ├── scraper.py
   │   ├── rss_generator.py
   │   └── update_all.py
   └── .github/workflows/
       └── update-rss.yml
   ```

### ステップ3: 初期設定の調整

1. **index.htmlの設定更新**
   ```html
   <!-- GitHubユーザー名を実際のものに変更 -->
   <link>https://your-username.github.io/static-legal-rss/</link>
   ```

2. **RSS生成器の設定更新**
   `scripts/rss_generator.py`の`channel_info`を更新：
   ```python
   self.channel_info = {
       'title': '法律ニュース総合RSS',
       'link': 'https://your-username.github.io/static-legal-rss/',
       'description': '複数の法律関連サイトから取得した最新ニュースを統合配信',
       'language': 'ja',
       'generator': 'Static Legal RSS Tool'
   }
   ```

### ステップ4: 初期コミット

1. **ファイルをステージング**
   ```bash
   git add .
   ```

2. **コミット**
   ```bash
   git commit -m "Initial commit: Static Legal RSS Tool"
   ```

3. **プッシュ**
   ```bash
   git push origin main
   ```

### ステップ5: GitHub Pagesの有効化

1. **リポジトリの設定ページに移動**
   - GitHubのリポジトリページで「Settings」タブをクリック

2. **Pagesセクションを選択**
   - 左サイドバーの「Pages」をクリック

3. **ソースの設定**
   ```
   Source: GitHub Actions
   ```

4. **設定を保存**

### ステップ6: GitHub Actionsの確認

1. **Actionsタブに移動**
   - リポジトリページの「Actions」タブをクリック

2. **ワークフローの実行確認**
   - 「Update Legal RSS Feed」ワークフローが表示されることを確認
   - 初回は手動実行が必要な場合があります

3. **手動実行（必要な場合）**
   - ワークフロー名をクリック
   - 「Run workflow」ボタンをクリック
   - 「Run workflow」を再度クリック

### ステップ7: 動作確認

1. **サイトへのアクセス**
   - `https://your-username.github.io/static-legal-rss/`
   - 数分後にサイトが表示されることを確認

2. **RSSフィードの確認**
   - `https://your-username.github.io/static-legal-rss/rss/combined.xml`
   - XMLが正しく表示されることを確認

## ⚙️ 高度な設定

### カスタムドメインの設定（オプション）

1. **独自ドメインの準備**
   - ドメインレジストラでドメインを取得
   - DNS設定でCNAMEレコードを追加：
   ```
   www.your-domain.com CNAME your-username.github.io
   ```

2. **GitHub Pagesでの設定**
   - Settings > Pages > Custom domain
   - ドメイン名を入力して保存

### セキュリティ設定

1. **HTTPS強制**
   - Settings > Pages > "Enforce HTTPS"にチェック

2. **ブランチ保護**
   - Settings > Branches > "Add rule"
   - mainブランチの保護ルールを設定

## 🔧 メンテナンス・運用

### 定期的な確認事項

1. **GitHub Actions実行状況**
   - 月1回程度、Actionsタブで実行状況を確認
   - エラーが発生していないかチェック

2. **無料枠の使用量確認**
   - Settings > Billing > Usage
   - GitHub Actionsの実行時間を確認

3. **RSSフィードの動作確認**
   - 月1回程度、実際のRSSフィードをチェック
   - 記事が正しく取得されているか確認

### アップデート方法

1. **スクリプトの更新**
   ```bash
   git pull origin main
   # ファイルを編集
   git add .
   git commit -m "Update scripts"
   git push origin main
   ```

2. **自動デプロイ**
   - プッシュ後、GitHub Actionsが自動実行
   - 数分後にサイトが更新される

## 🚨 トラブルシューティング

### よくある問題と解決方法

#### 問題1: GitHub Pagesが表示されない
**症状**: 404エラーまたは空白ページ
**原因**: 
- GitHub Pagesが有効化されていない
- index.htmlが存在しない
- ワークフローが実行されていない

**解決方法**:
1. Settings > Pagesでソースが正しく設定されているか確認
2. リポジトリルートにindex.htmlがあるか確認
3. Actionsタブでワークフローを手動実行

#### 問題2: RSSフィードが空
**症状**: XMLは表示されるが記事がない
**原因**:
- スクレイピングが失敗している
- 対象サイトの構造が変更された

**解決方法**:
1. Actionsタブでエラーログを確認
2. scripts/scraper.pyのセレクタを更新
3. 手動でワークフローを再実行

#### 問題3: GitHub Actions実行時間超過
**症状**: ワークフローが途中で停止
**原因**: 無料枠の実行時間（2,000分/月）を超過

**解決方法**:
1. 実行頻度を減らす（12時間間隔など）
2. 取得記事数を制限
3. 有料プランへのアップグレード検討

#### 問題4: スクレイピングエラー
**症状**: 特定サイトからの記事取得が失敗
**原因**:
- サイト構造の変更
- アクセス制限
- ネットワークエラー

**解決方法**:
1. エラーログでHTTPステータスコードを確認
2. セレクタの更新
3. User-Agentの変更
4. アクセス間隔の調整

### ログの確認方法

1. **GitHub Actionsログ**
   ```
   1. Actionsタブをクリック
   2. 失敗したワークフローをクリック
   3. 失敗したジョブをクリック
   4. エラーメッセージを確認
   ```

2. **ブラウザ開発者ツール**
   ```
   1. F12キーで開発者ツールを開く
   2. Consoleタブでエラーメッセージを確認
   3. Networkタブでリクエスト状況を確認
   ```

## 📊 パフォーマンス最適化

### 実行時間の短縮

1. **並列処理の活用**
   ```python
   # scripts/scraper.pyで並列処理を実装
   from concurrent.futures import ThreadPoolExecutor
   ```

2. **キャッシュの活用**
   ```python
   # 前回取得結果との差分のみ処理
   ```

3. **取得記事数の制限**
   ```python
   # 最新10件のみ取得するよう制限
   max_articles_per_site = 10
   ```

### 帯域幅の最適化

1. **画像の最適化**
   - 不要な画像の削除
   - 画像サイズの最適化

2. **ファイルサイズの削減**
   - CSSの最小化
   - JavaScriptの最小化

## 🔒 セキュリティ考慮事項

### アクセス制御

1. **リポジトリの可視性**
   - Publicリポジトリのため、コードは公開される
   - 機密情報は含めない

2. **API キーの管理**
   - GitHub Secretsを使用
   - 環境変数での管理

### スクレイピング倫理

1. **利用規約の遵守**
   - 各サイトのrobots.txtを確認
   - 利用規約を遵守

2. **適切なアクセス間隔**
   - 過度なアクセスを避ける
   - User-Agentの適切な設定

## 💡 応用・拡張

### 機能拡張のアイデア

1. **通知機能**
   - 重要ニュースのSlack通知
   - メール通知機能

2. **分析機能**
   - 記事トレンド分析
   - キーワード頻度分析

3. **UI改善**
   - レスポンシブデザイン
   - ダークモード対応

### 他分野への応用

1. **技術ニュース**
   - IT関連サイトのRSS統合

2. **経済ニュース**
   - 経済・金融サイトの統合

3. **学術情報**
   - 論文・研究情報の統合

## 📞 サポート・コミュニティ

### ヘルプの取得

1. **GitHub Issues**
   - バグ報告・機能要望
   - コミュニティサポート

2. **ドキュメント**
   - README.mdの詳細情報
   - コメント付きソースコード

3. **GitHub Discussions**
   - 質問・議論
   - ベストプラクティス共有

### 貢献方法

1. **コード貢献**
   - フォーク → 改善 → プルリクエスト

2. **ドキュメント改善**
   - 誤字脱字の修正
   - 説明の追加・改善

3. **テスト・フィードバック**
   - バグ報告
   - 使用感のフィードバック

## 🎉 成功事例

### 実際の運用例

1. **個人ブログでの活用**
   - 法律関連記事の自動収集
   - コンテンツ作成の効率化

2. **企業での活用**
   - 法務部門での情報収集
   - コンプライアンス情報の監視

3. **研究での活用**
   - 法学研究での情報収集
   - トレンド分析

## 📈 将来の展望

### 予定されている改善

1. **パフォーマンス向上**
   - 処理速度の最適化
   - メモリ使用量の削減

2. **機能追加**
   - 新しいニュースサイト対応
   - 高度なフィルタリング機能

3. **UI/UX改善**
   - モバイル対応の強化
   - アクセシビリティの向上

このガイドに従って設定することで、完全無料で永続的に運用可能な法律ニュースRSSサービスを構築できます。

