"""
Threads投稿収集から最終投稿生成までのパイプラインを管理するメインスクリプト
"""

import os
import sys
import logging
import datetime
import pandas as pd
from dotenv import load_dotenv
from scraper import scrape_threads_posts
from chatgpt_integration import process_posts

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_targets_from_env():
    """
    .envファイルからターゲットリストを取得する関数
    
    Returns:
        list: ターゲット名のリスト
    """
    targets_str = os.getenv("TARGETS", "")
    if not targets_str:
        logger.warning("環境変数 TARGETS が設定されていません。デフォルトターゲットを使用します。")
        return ["一般ユーザー"]
    
    targets = [target.strip() for target in targets_str.split(",")]
    logger.info(f"ターゲットリスト: {targets}")
    return targets

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

def save_final_posts_to_csv(final_posts):
    """
    最終投稿をCSVに保存する関数
    
    Args:
        final_posts (list): (参考投稿名, ターゲット名, 完成した投稿本文) のタプルのリスト
        
    Returns:
        str: 保存したCSVファイルのパス
    """
    if not final_posts:
        logger.warning("保存する最終投稿がありません")
        return None
    
    # タイムスタンプ付きのCSVファイル名を生成
    now = datetime.datetime.now()
    csv_filename = f"final_posts_{now.strftime('%Y%m%d_%H%M%S')}.csv"
    
    try:
        # データフレームを作成して保存
        df = pd.DataFrame(final_posts, columns=["reference_post", "target", "final_post"])
        df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
        logger.info(f"{len(final_posts)} 件の最終投稿を {csv_filename} に保存しました")
        return csv_filename
    
    except Exception as e:
        logger.error(f"最終投稿のCSV保存エラー: {e}")
        return None

def main():
    """
    メイン処理関数
    """
    # .envファイルから環境変数をロード
    load_dotenv()
    
    # ターゲットリストを取得
    targets = get_targets_from_env()
    
    # コマンドライン引数からCSVファイルを読み込むかどうかを判断
    if len(sys.argv) > 1 and sys.argv[1].endswith('.csv'):
        csv_file = sys.argv[1]
        logger.info(f"指定されたCSVファイル {csv_file} から投稿を読み込みます")
        posts = read_posts_from_csv(csv_file)
    else:
        # 投稿収集フェーズ
        logger.info("Threadsから投稿を収集します")
        csv_file = scrape_threads_posts(max_posts=30, headless=False, exclude_image_posts=True)
        
        if not csv_file:
            logger.error("投稿収集に失敗しました")
            return
        
        posts = read_posts_from_csv(csv_file)
    
    if not posts:
        logger.error("処理対象の投稿がありません")
        return
    
    # 投稿処理フェーズ（分析・テンプレート化・最終投稿生成）
    logger.info("投稿処理フェーズを開始します")
    final_posts = process_posts(posts, targets)
    
    # 出力フェーズ
    logger.info("出力フェーズを開始します")
    result_file = save_final_posts_to_csv(final_posts)
    
    if result_file:
        logger.info(f"処理が完了しました。結果は {result_file} に保存されています。")
    else:
        logger.error("処理は完了しましたが、結果の保存に失敗しました。")

if __name__ == "__main__":
    main() 