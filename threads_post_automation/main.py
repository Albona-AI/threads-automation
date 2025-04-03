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

def ensure_directories():
    """
    必要なディレクトリ構造を作成する関数
    """
    directories = ["data", "data/output-post", "data/raw"]
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"ディレクトリを作成しました: {directory}")
    return True

def get_targets_from_config(config_file="config.json"):
    """
    設定ファイルからターゲット情報を読み込む関数
    
    Args:
        config_file (str): 設定ファイルのパス
    
    Returns:
        list: ターゲット情報のリスト
    """
    try:
        if not os.path.exists(config_file):
            logger.error(f"設定ファイル {config_file} が見つかりません")
            return []
        
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        targets = config.get("targets", [])
        
        if not targets:
            logger.warning("設定ファイルにターゲット情報がありません")
        else:
            logger.info(f"{len(targets)} 件のターゲットを読み込みました")
        
        return targets
    
    except Exception as e:
        logger.error(f"設定ファイル読み込みエラー: {e}")
        return []

def read_posts_from_csv(csv_file):
    """
    CSVファイルから投稿を読み込む関数
    
    Args:
        csv_file (str): CSVファイルのパス
        
    Returns:
        list: (username, post_text, likes) のタプルのリスト
    """
    try:
        df = pd.read_csv(csv_file, encoding='utf-8-sig')
        
        # 必要なカラムが存在するか確認
        required_columns = ["username", "post_text"]
        for col in required_columns:
            if col not in df.columns:
                logger.error(f"必要なカラム '{col}' がCSVファイルに存在しません")
                return []
        
        # likesカラムが存在しない場合は0を設定
        if "likes" not in df.columns:
            df["likes"] = 0
        
        # タプルのリストに変換
        posts = list(zip(df["username"], df["post_text"], df["likes"]))
        logger.info(f"{len(posts)} 件の投稿を読み込みました")
        return posts
    
    except Exception as e:
        logger.error(f"CSVファイルの読み込みエラー: {e}")
        return []

def save_final_posts_to_csv(final_posts, target_name):
    """
    最終投稿をCSVに保存する関数
    
    Args:
        final_posts (list): (参考投稿名, ターゲット名, 完成した投稿本文) のタプルのリスト
        target_name (str): ターゲット名
        
    Returns:
        str: 保存したCSVファイルのパス
    """
    if not final_posts:
        logger.warning("保存する最終投稿がありません")
        return None
    
    # 日付ベースのフォルダ構造を作成
    now = datetime.datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    output_base_dir = "data/output-post"
    
    # ターゲット名と日付でフォルダを作成
    target_date_dir = f"{output_base_dir}/{target_name}/{date_str}"
    os.makedirs(target_date_dir, exist_ok=True)
    
    # 時間のみのタイムスタンプでファイル名を生成（より短く）
    time_str = now.strftime('%H%M%S')
    csv_filename = f"{target_date_dir}/final_posts_{time_str}.csv"
    
    try:
        df = pd.DataFrame(final_posts, columns=["reference_post", "target", "final_post"])
        df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
        logger.info(f"{len(final_posts)} 件の最終投稿を {csv_filename} に保存しました")
        return csv_filename
    
    except Exception as e:
        logger.error(f"最終投稿のCSV保存エラー: {e}")
        return None

def create_latest_symlink(csv_filename, target_name):
    """
    最新のCSVファイルへのシンボリックリンクを作成する
    """
    output_dir = "data/output-post"
    latest_link = f"{output_dir}/latest_{target_name}.csv"
    
    # 既存のシンボリックリンクまたはファイルがあれば削除
    if os.path.exists(latest_link) or os.path.islink(latest_link):
        try:
            if os.path.islink(latest_link):
                os.unlink(latest_link)
            else:
                os.remove(latest_link)
        except Exception as e:
            logger.warning(f"既存のリンク/ファイルの削除に失敗しました: {e}")
    
    # 絶対パスを取得
    abs_csv_filename = os.path.abspath(csv_filename)
    
    # シンボリックリンク作成を試み、失敗したらコピーを作成
    try:
        os.symlink(abs_csv_filename, latest_link)
        logger.info(f"最新ファイルへのシンボリックリンクを作成しました: {latest_link}")
    except Exception as e:
        logger.warning(f"シンボリックリンク作成に失敗しました。ファイルをコピーします: {e}")
        os.makedirs(os.path.dirname(latest_link), exist_ok=True)
        try:
            shutil.copy2(csv_filename, latest_link)
            logger.info(f"最新ファイルのコピーを作成しました: {latest_link}")
        except Exception as e:
            logger.error(f"ファイルコピーにも失敗しました: {e}")

def limit_csv_files_per_target(target_name, max_files=10):
    """
    ターゲットごとに保持するCSVファイルの数を制限する
    """
    target_dir = f"data/output-post/{target_name}"
    if not os.path.exists(target_dir):
        return
    
    # 日付ごとのフォルダをリストアップし、古い順にソート
    date_dirs = sorted([d for d in os.listdir(target_dir) 
                       if os.path.isdir(os.path.join(target_dir, d))])
    
    # 日付ディレクトリが多すぎる場合、古い日付から削除
    if len(date_dirs) <= max_files:
        return
        
    # 削除が必要な数を計算して、その数だけ古いディレクトリを削除
    dirs_to_remove = date_dirs[:len(date_dirs) - max_files]
    for old_dir in dirs_to_remove:
        old_path = os.path.join(target_dir, old_dir)
        shutil.rmtree(old_path)
        logger.info(f"古いデータディレクトリを削除しました: {old_path}")

def process_target(target):
    """
    特定のターゲットに対する処理を実行する関数
    """
    target_name = target["name"]
    keywords = target.get("keywords", [])
    min_likes = target.get("min_likes", 300)  # 設定ファイルからいいね数閾値を取得（デフォルト300）
    
    # 投稿数の設定を取得
    max_posts_per_keyword = target.get("max_posts_per_keyword", 30)  # デフォルト30件
    max_posts_total = target.get("max_posts_total", 100)  # デフォルト合計100件

    logger.info(f"ターゲット '{target_name}' の処理を開始します (最小いいね数: {min_likes}, キーワードあたり最大: {max_posts_per_keyword}件, 合計最大: {max_posts_total}件)")
    
    # .envファイルからログイン情報を取得
    username = os.getenv("THREADS_USERNAME")
    password = os.getenv("THREADS_PASSWORD")
    
    if not username or not password:
        logger.error("環境変数にThreadsのログイン情報が設定されていません")
        return None
    
    # ヘッドレスモードかどうかを環境変数から取得
    headless = os.getenv("HEADLESS_BROWSER", "True").lower() == "true"
    logger.info(f"{'ヘッドレス' if headless else '表示'} モードでスクレイピングを実行します")
    
    # 通常モードでスクレイピングを実行
    scraper = ThreadsScraper(headless=headless)
    
    try:
        # ログイン処理を実行
        if not scraper.login(username, password):
            logger.error("Threadsへのログインに失敗しました。処理を中止します。")
            return None
        
        # 日付ディレクトリを作成
        now = datetime.datetime.now()
        date_str = now.strftime('%Y-%m-%d')
        raw_data_dir = f"data/raw/{target_name}/{date_str}"
        os.makedirs(raw_data_dir, exist_ok=True)
        
        # 時刻を含むファイル名を設定
        time_str = now.strftime('%H%M%S')
        csv_file = f"{raw_data_dir}/{target_name}_{time_str}.csv"
        
        posts = []
        
        # キーワードがある場合はキーワード検索を実行
        if keywords:
            logger.info(f"キーワードリスト {keywords} のスクレイピングを実行します")
            
            for keyword in keywords:
                logger.info(f"キーワード '{keyword}' の投稿を取得します")
                keyword_posts = scraper.extract_posts_from_search(
                    keyword=keyword,
                    max_posts=max_posts_per_keyword,  # 設定ファイルの値を使用
                    exclude_image_posts=True,
                    min_likes=min_likes,
                    target=target_name
                )
                
                if keyword_posts:
                    logger.info(f"キーワード '{keyword}' から {len(keyword_posts)} 件の投稿を取得しました")
                    posts.extend(keyword_posts)
                else:
                    logger.warning(f"キーワード '{keyword}' からは投稿を取得できませんでした")
                
                # 連続アクセスを避けるため少し待機
                time.sleep(random.uniform(2.0, 5.0))
        else:
            # 通常のスクレイピング
            posts = scraper.extract_posts(
                max_posts=max_posts_total,  # 設定ファイルの値を使用
                exclude_image_posts=True,
                min_likes=min_likes
            )
        
        # 重複排除処理
        unique_posts = []
        seen_posts = set()
        
        for post in posts:
            # ユーザー名と投稿先頭部分で一意性を判断
            post_id = f"{post[0]}:{post[1][:50]}"
            if post_id not in seen_posts:
                unique_posts.append(post)
                seen_posts.add(post_id)
        
        # 最大件数を制限
        if len(unique_posts) > max_posts_total:
            logger.info(f"投稿数が上限を超えているため、{max_posts_total}件に制限します ({len(unique_posts)}件 → {max_posts_total}件)")
            unique_posts = unique_posts[:max_posts_total]
        
        logger.info(f"重複排除後: {len(unique_posts)}/{len(posts)} 件の投稿を取得しました")
        
        # 取得した投稿をCSVに保存
        if unique_posts:
            csv_file = scraper.save_to_csv(
                posts=unique_posts,
                filename=csv_file,
                min_likes=min_likes
            )
            
            if csv_file:
                logger.info(f"ターゲット '{target_name}' 向けの {len(unique_posts)} 件の投稿を {csv_file} に保存しました")
                return csv_file
            else:
                logger.error(f"投稿のCSV保存に失敗しました")
                return None
        else:
            logger.warning(f"投稿が取得できませんでした")
            return None
    
    except Exception as e:
        logger.error(f"スクレイピング中にエラーが発生しました: {e}")
        logger.error(traceback.format_exc())
        return None
    
    finally:
        # スクレイパーを閉じる
        scraper.close()

def process_csv_file(csv_file, targets):
    """
    CSVファイルから投稿を読み込み処理する関数
    """
    logger.info(f"指定されたCSVファイル {csv_file} から投稿を読み込みます")
    posts = read_posts_from_csv(csv_file)
    
    if not posts:
        logger.error("処理対象の投稿がありません")
        return None
    
    # すべてのターゲット向けに処理
    target_names = [target["name"] for target in targets]
    logger.info(f"投稿処理フェーズを開始します（ターゲット: {', '.join(target_names)}）")
    
    # ChatGPT処理を実行
    final_posts = process_posts(posts, target_names)
    
    if not final_posts:
        logger.error("ChatGPTによる投稿処理が失敗しました")
        return None
    
    # 全ターゲットをまとめて保存
    result_file = save_final_posts_to_csv(final_posts, "all_targets")
    
    # 最新ファイルへのシンボリックリンクを作成
    if result_file:
        create_latest_symlink(result_file, "all_targets")
        
        # 古いファイルのクリーンアップ
        limit_csv_files_per_target("all_targets")
    
    return result_file if result_file else None

def main():
    """
    メイン処理フロー
    """
    # .envファイルから環境変数をロード
    load_dotenv()
    
    # 必要なディレクトリ構造を確保
    ensure_directories()
    
    # ターゲットリストを取得
    targets = get_targets_from_config()
    if not targets:
        logger.error("処理対象のターゲットがありません。設定ファイルを確認してください。")
        return
    
    results = []
    
    # コマンドライン引数からCSVファイルを読み込むかどうかを判断
    if len(sys.argv) > 1 and sys.argv[1].endswith('.csv'):
        logger.info(f"コマンドライン引数から指定されたCSVファイル {sys.argv[1]} を処理します")
        result_file = process_csv_file(sys.argv[1], targets)
        if result_file:
            results.append(result_file)
    else:
        # ターゲットごとに処理を実行
        for target in targets:
            result_file = process_target(target)
            if result_file:
                logger.info(f"スクレイピング結果をChatGPTで処理します: {result_file}")
                processed_file = process_csv_file(result_file, [target])
                if processed_file:
                    results.append(processed_file)
                    # 最新ファイルへのシンボリックリンクを作成
                    create_latest_symlink(processed_file, target["name"])
                    # 古いファイルのクリーンアップ
                    limit_csv_files_per_target(target["name"])
    
    # 最終結果の報告
    if results:
        logger.info(f"全ての処理が完了しました。結果は以下のファイルに保存されています：")
        for file in results:
            logger.info(f"- {file}")
    else:
        logger.error("処理は完了しましたが、結果の保存に失敗しました。")

if __name__ == "__main__":
    main() 