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

def get_targets_from_config():
    """
    config.jsonファイルからターゲットリストを取得する関数
    
    Returns:
        list: ターゲット情報のリスト
    """
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        
        if "targets" not in config or not config["targets"]:
            logger.warning("config.jsonにターゲット情報がありません。デフォルト設定を使用します。")
            return [{"name": "一般ユーザー", "keywords": []}]
        
        logger.info(f"ターゲット数: {len(config['targets'])}")
        return config["targets"]
    except Exception as e:
        logger.error(f"config.jsonの読み込みエラー: {e}")
        return [{"name": "一般ユーザー", "keywords": []}]

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
    
    logger.info(f"ターゲット '{target_name}' の処理を開始します")
    
    # .envファイルからログイン情報を取得
    username = os.getenv("THREADS_USERNAME")
    password = os.getenv("THREADS_PASSWORD")
    
    if not username or not password:
        logger.error("環境変数にThreadsのログイン情報が設定されていません")
        return None
    
    # スクレイピング実行
    csv_file = None
    scraper = ThreadsScraper(headless=False)
    
    try:
        # ログイン処理を実行
        if not scraper.login(username, password):
            logger.error("Threadsへのログインに失敗しました。処理を中止します。")
            return None
        
        posts = []
        
        if keywords:
            # キーワードがある場合は検索ベースでスクレイピング
            for keyword in keywords:
                logger.info(f"キーワード '{keyword}' でスクレイピングを実行します")
                keyword_posts = scraper.extract_posts_from_search(
                    keyword=keyword,
                    max_posts=10,
                    exclude_image_posts=True,
                    min_likes=0,
                    target=target_name
                )
                posts.extend(keyword_posts)
            
            # 収集した投稿がある場合
            if posts:
                # 日付ディレクトリを作成
                now = datetime.datetime.now()
                date_str = now.strftime('%Y-%m-%d')
                raw_data_dir = f"data/raw/{target_name}/{date_str}"
                os.makedirs(raw_data_dir, exist_ok=True)
                
                # 時刻を含むファイル名で保存
                time_str = now.strftime('%H%M%S')
                csv_file = f"{raw_data_dir}/{target_name}_{time_str}.csv"
            
        else:
            # キーワードがない場合は一般的なスクレイピング
            posts = scraper.extract_posts(
                max_posts=30,
                exclude_image_posts=True
            )
            # CSVファイル名を設定
            csv_file = f"data/{target_name}.csv"
        
        # 投稿を保存
        if posts:
            df = pd.DataFrame(posts, columns=["username", "post_text", "likes", "target"])
            df.to_csv(csv_file, index=False, encoding='utf-8-sig')
            logger.info(f"{len(posts)} 件の投稿を {csv_file} に保存しました")
    
    except Exception as e:
        logger.error(f"スクレイピング中にエラーが発生しました: {e}")
        return None
        
    finally:
        # スクレイパーを必ず閉じる
        scraper.close()
    
    # 以降のデータ処理と投稿生成
    if not csv_file or not os.path.exists(csv_file):
        logger.error(f"ターゲット '{target_name}' の投稿収集に失敗しました")
        return None
    
    posts = read_posts_from_csv(csv_file)
    if not posts:
        logger.error(f"ターゲット '{target_name}' の投稿データがありません")
        return None
    
    # 投稿処理と最終出力
    logger.info(f"ターゲット '{target_name}' の投稿処理フェーズを開始します")
    final_posts = process_posts(posts, [target_name])
    
    # 出力フェーズ
    logger.info(f"ターゲット '{target_name}' の出力フェーズを開始します")
    result_file = save_final_posts_to_csv(final_posts, target_name)
    
    # 出力後にシンボリックリンクとファイル数制限を適用
    if result_file:
        create_latest_symlink(result_file, target_name)
        limit_csv_files_per_target(target_name, max_files=10)
    
    return result_file

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
    final_posts = process_posts(posts, target_names)
    
    # 全ターゲットをまとめて保存
    result_file = save_final_posts_to_csv(final_posts, "all_targets")
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
    
    results = []
    
    # コマンドライン引数からCSVファイルを読み込むかどうかを判断
    if len(sys.argv) > 1 and sys.argv[1].endswith('.csv'):
        result_file = process_csv_file(sys.argv[1], targets)
        if result_file:
            results.append(result_file)
    else:
        # ターゲットごとに処理を実行
        for target in targets:
            result_file = process_target(target)
            if result_file:
                results.append(result_file)
    
    # 最終結果の報告
    if results:
        logger.info(f"全ての処理が完了しました。結果は以下のファイルに保存されています：")
        for file in results:
            logger.info(f"- {file}")
    else:
        logger.error("処理は完了しましたが、結果の保存に失敗しました。")

if __name__ == "__main__":
    main() 