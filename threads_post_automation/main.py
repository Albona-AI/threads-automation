"""
Threads投稿収集から最終投稿生成までのパイプラインを管理するメインスクリプト
"""

import os
import sys
import json
import logging
import datetime
import pandas as pd
from dotenv import load_dotenv
from scraper import ThreadsScraper
from chatgpt_integration import process_posts
import shutil
import random
import time
import traceback

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 設定ファイルの読み込み
def load_config(config_path="config.json"):
    """設定ファイルを読み込む関数"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except Exception as e:
        logger.error(f"設定ファイルの読み込みに失敗しました: {e}")
        return None

def read_posts_from_csv(csv_file):
    """CSVファイルから投稿を読み込む関数"""
    try:
        df = pd.read_csv(csv_file, encoding='utf-8-sig')
        posts = []
        for _, row in df.iterrows():
            if 'username' in row and 'post_text' in row and 'likes' in row:
                posts.append((row['username'], row['post_text'], row.get('likes', 0)))
        logger.info(f"{len(posts)} 件の投稿を読み込みました")
        return posts
    except Exception as e:
        logger.error(f"CSVファイルの読み込みに失敗しました: {e}")
        logger.error(traceback.format_exc())
        return []

def save_final_posts_by_account(generated_posts, accounts, targets_dict):
    """
    アカウントごとに投稿を振り分けて保存する関数
    
    Args:
        generated_posts (dict): {ターゲット名: [(参考投稿名, ターゲット名, 完成した投稿本文), ...]} の辞書
        accounts (list): アカウント設定のリスト
        targets_dict (dict): ターゲット設定の辞書
        
    Returns:
        list: 保存したCSVファイルのパスのリスト
    """
    if not generated_posts:
        logger.warning("保存する最終投稿がありません")
        return []
    
    # 出力ディレクトリを作成
    output_base_dir = "data/output-post"
    os.makedirs(output_base_dir, exist_ok=True)
    
    # 日付と時刻を含むプレフィックスを生成
    now = datetime.datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H%M%S')
    
    saved_files = []
    
    # ターゲットごとのアカウントリストを作成
    accounts_by_target = {}
    for account in accounts:
        target = account.get('target')
        if target not in accounts_by_target:
            accounts_by_target[target] = []
        accounts_by_target[target].append(account)
    
    # ターゲットごとに投稿を処理
    for target_name, target_posts in generated_posts.items():
        if not target_posts:
            logger.warning(f"ターゲット '{target_name}' には保存する投稿がありません")
            continue
        
        # このターゲットのアカウントを取得
        target_accounts = accounts_by_target.get(target_name, [])
        if not target_accounts:
            logger.warning(f"ターゲット '{target_name}' に対応するアカウントがありません")
            continue
        
        # このターゲットの設定を取得
        target_config = targets_dict.get(target_name)
        if not target_config:
            logger.warning(f"ターゲット '{target_name}' の設定情報が見つかりません")
            continue
        
        # 各アカウントへの投稿割り当て数を計算
        max_posts_per_keyword = target_config.get('max_posts_per_keyword', 5)
        
        # 投稿をアカウントに分配
        posts_for_accounts = {}
        total_posts = len(target_posts)
        
        # 各アカウントに振り分ける投稿数 (均等に割り振る)
        posts_per_account = total_posts // len(target_accounts)
        if posts_per_account == 0 and total_posts > 0:
            posts_per_account = 1  # 最低1投稿は割り当てる
        
        # 投稿をシャッフルして、アカウント間で偏りが出ないようにする
        shuffled_posts = random.sample(target_posts, len(target_posts))
        
        # 各アカウントに投稿を均等に割り振る
        for i, account in enumerate(target_accounts):
            username = account.get('username')
            start_idx = i * posts_per_account
            end_idx = min(start_idx + posts_per_account, total_posts)
            
            if start_idx < total_posts:
                posts_for_accounts[username] = shuffled_posts[start_idx:end_idx]
            else:
                posts_for_accounts[username] = []
        
        # 残りの投稿をランダムに割り当て
        remaining_posts = shuffled_posts[len(target_accounts) * posts_per_account:]
        account_usernames = [account.get('username') for account in target_accounts]
        
        for post in remaining_posts:
            random_username = random.choice(account_usernames)
            posts_for_accounts[random_username].append(post)
        
        # 各アカウントに投稿を保存
        for account in target_accounts:
            username = account.get('username')
            account_posts = posts_for_accounts.get(username, [])
            
            if not account_posts:
                logger.warning(f"アカウント '{username}' には割り当てる投稿がありません")
                continue
            
            # ユーザー名を使用したファイル名を生成
            username_filename = f"{output_base_dir}/threads_posts_{username}_{date_str}_{time_str}.csv"
            
            try:
                # 新しいフォーマットのデータを準備
                new_data = []
                
                # 現在時刻を基準に15分刻みの投稿時間を作成
                base_time = now
                hour_counter = 0
                
                # このアカウントのすべての投稿を処理
                for ref, tgt, post_content in account_posts:
                    # 投稿時間を計算（15分刻み）
                    scheduled_time = base_time + datetime.timedelta(minutes=hour_counter * 15)
                    scheduled_time_str = scheduled_time.strftime('%Y-%m-%dT%H:%M:%S')
                    hour_counter += 1
                    
                    # 各行のデータを作成
                    row_data = {
                        'username': username,
                        'content': post_content,
                        'image': '',  # 空白
                        'replyContent': account.get('replyContent', ''),
                        'replyImage': account.get('replyImage', ''),
                        'scheduledTime': scheduled_time_str
                    }
                    
                    new_data.append(row_data)
                
                # DataFrameに変換してCSV保存
                df = pd.DataFrame(new_data)
                df.to_csv(username_filename, index=False, encoding='utf-8-sig')
                logger.info(f"アカウント '{username}' の {len(account_posts)} 件の投稿を {username_filename} に保存しました")
                saved_files.append(username_filename)
                
            except Exception as e:
                logger.error(f"アカウント '{username}' の投稿保存中にエラーが発生しました: {e}")
                logger.error(traceback.format_exc())
    
    if not saved_files:
        logger.warning("どのアカウントの投稿も保存されませんでした")
    else:
        logger.info(f"{len(saved_files)} 個のアカウント用CSVファイルを保存しました")
    
    return saved_files

def process_csv_file(csv_file, config):
    """
    CSVファイルから投稿を読み込み処理する関数
    
    Args:
        csv_file (str): CSVファイルのパス
        config (dict): 設定情報
        
    Returns:
        list: 保存したCSVファイルのパスのリスト
    """
    try:
        logger.info(f"CSVファイル {csv_file} からの投稿処理を開始します")
        posts = read_posts_from_csv(csv_file)
        
        if not posts:
            logger.error("処理対象の投稿がありません")
            return []
        
        # ターゲットとアカウントの情報を取得
        targets = config.get('targets', [])
        accounts = config.get('accounts', [])
        
        # ターゲット名のリストを準備
        target_names = [target["target"] for target in targets]
        target_dict = {target["target"]: target for target in targets}
        
        logger.info(f"投稿処理フェーズを開始します（ターゲット: {', '.join(target_names)}）")
        
        # ChatGPT処理を実行
        final_posts = process_posts(posts, target_names)
        
        if not final_posts:
            logger.error("ChatGPTによる投稿処理が失敗しました")
            return []
        
        # ターゲットごとに分類するための辞書を作成
        final_posts_by_target = {}
        for ref, tgt, post in final_posts:
            if tgt not in final_posts_by_target:
                final_posts_by_target[tgt] = []
            final_posts_by_target[tgt].append((ref, tgt, post))
        
        # ターゲットごとに個別のファイルに保存
        result_files = save_final_posts_by_account(final_posts_by_target, accounts, target_dict)
        
        return result_files
    
    except Exception as e:
        logger.error(f"CSV処理中にエラーが発生しました: {e}")
        logger.error(traceback.format_exc())
        return []

def run_threads_scraper(config):
    """
    スクレイピングを実行する関数
    
    Args:
        config (dict): 設定情報の辞書
        
    Returns:
        str: 保存したCSVファイルのパス、または失敗時はNone
    """
    try:
        # ターゲットとアカウント設定を取得
        targets = config.get('targets', [])
        accounts = config.get('accounts', [])
        
        # ターゲットごとのアカウント数をカウント
        accounts_per_target = {}
        for account in accounts:
            target = account.get('target')
            if target not in accounts_per_target:
                accounts_per_target[target] = 0
            accounts_per_target[target] += 1
        
        # ターゲットごとに処理
        all_scraped_posts = []
        
        # スクレイパーの初期化
        scraper = ThreadsScraper(headless=False)
        
        # 環境変数からログイン情報を取得
        username = os.getenv("THREADS_USERNAME")
        password = os.getenv("THREADS_PASSWORD")
        
        if not username or not password:
            logger.error("環境変数にログイン情報が設定されていません。")
            return None
        
        # ログイン処理を明示的に呼び出す - ユーザー名とパスワードを渡す
        login_success = scraper.login(username, password)
        if not login_success:
            logger.error("Threadsへのログインに失敗しました。")
            return None
            
        output_dir = "data/scraped"
        os.makedirs(output_dir, exist_ok=True)
        
        for target in targets:
            target_name = target.get('target')
            keywords = target.get('keywords', [])
            min_likes = target.get('min_likes', 500)
            max_posts_per_keyword = target.get('max_posts_per_keyword', 5)
            
            # このターゲットのアカウント数
            num_accounts = accounts_per_target.get(target_name, 0)
            if num_accounts == 0:
                logger.warning(f"ターゲット '{target_name}' に対応するアカウントがありません。スキップします。")
                continue
            
            # 希望する処理: キーワードごとに「アカウント数 × max_posts_per_keyword」の投稿を取得
            posts_per_keyword = num_accounts * max_posts_per_keyword
            
            logger.info(f"ターゲット '{target_name}' のスクレイピングを開始します。必要投稿数: {posts_per_keyword * len(keywords)}")
            
            # キーワードごとにスクレイピング
            for keyword in keywords:
                logger.info(f"キーワード '{keyword}' のスクレイピングを開始します (1キーワードあたり {posts_per_keyword} 件)")
                
                # キーワード検索結果を取得
                posts = scraper.search_keyword(keyword, max_posts=posts_per_keyword, min_likes=min_likes)
                
                # 結果を追加
                for post in posts:
                    # (username, post_text, likes)の形式でall_scraped_postsに追加
                    all_scraped_posts.append((post[0], post[1], post[2]))
                
                logger.info(f"キーワード '{keyword}' で {len(posts)} 件の投稿を取得しました")
                
                # ランダムな休憩時間
                time.sleep(random.uniform(3, 7))
        
        # クッキー保存
        scraper.save_cookies()
        
        # 結果をCSVに保存
        if all_scraped_posts:
            temp_csv = f"{output_dir}/all_scraped_posts.csv"
            df = pd.DataFrame(all_scraped_posts, columns=["username", "post_text", "likes"])
            df.to_csv(temp_csv, index=False, encoding='utf-8-sig')
            logger.info(f"合計 {len(all_scraped_posts)} 件の投稿を {temp_csv} に保存しました")
            
            # 結果を返す
            return temp_csv
        else:
            logger.warning("スクレイピングの結果、投稿が見つかりませんでした")
            return None
    
    except Exception as e:
        logger.error(f"スクレイピング中にエラーが発生しました: {e}")
        logger.error(traceback.format_exc())
        return None
    
    finally:
        # スクレイパーを終了
        scraper.close()

def main():
    """メイン実行関数"""
    try:
        # 環境変数の読み込み
        load_dotenv()
        
        # 設定ファイルの読み込み
        config = load_config()
        if not config:
            logger.error("設定ファイルの読み込みに失敗しました。処理を中止します。")
            sys.exit(1)
        
        # ターゲットとアカウントの情報を取得
        targets = config.get('targets', [])
        accounts = config.get('accounts', [])
        
        if not targets:
            logger.error("ターゲットの設定がありません。処理を中止します。")
            sys.exit(1)
        
        if not accounts:
            logger.error("アカウントの設定がありません。処理を中止します。")
            sys.exit(1)
        
        logger.info(f"{len(targets)} 個のターゲットと {len(accounts)} 個のアカウントが読み込まれました")
        
        # スクレイピング実行
        csv_file = run_threads_scraper(config)
        
        # 投稿生成と保存
        if csv_file:
            result_files = process_csv_file(csv_file, config)
            
            # 最終結果の報告
            if result_files:
                logger.info(f"全ての処理が完了しました。結果は以下のファイルに保存されています：")
                for file in result_files:
                    logger.info(f"- {file}")
            else:
                logger.error("処理は完了しましたが、結果の保存に失敗しました。")
        else:
            logger.error("スクレイピングに失敗したため、投稿生成を行いませんでした。")
    
    except Exception as e:
        logger.error(f"実行中にエラーが発生しました: {e}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main() 