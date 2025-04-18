"""
OpenAI APIを使用して投稿の分析とテンプレート化を行うモジュール
"""

import os
import logging
import openai
from dotenv import load_dotenv
from tqdm import tqdm
from prompt_templates import ANALYTICS_PROMPT, TEMPLATE_PROMPT, FINAL_POST_PROMPT
import concurrent.futures
from functools import partial

# .envファイルから環境変数をロード
load_dotenv()
        
# APIキー設定
openai.api_key = os.getenv("OPENAI_API_KEY")
model = os.getenv("OPENAI_MODEL", "o1")

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 並行処理の設定
MAX_WORKERS = int(os.getenv("MAX_API_WORKERS", "5"))  # デフォルトは5つの並行ワーカー

def call_openai_api(messages, custom_model=None):
    """
    OpenAI APIを呼び出す関数
    """
    try:
        response = openai.ChatCompletion.create(
            model=custom_model if custom_model else model,
            messages=messages,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return None

def analyze_post(post_text, username=""):
    """
    投稿の分析を行う関数
    
    Args:
        post_text (str): 投稿本文
        username (str): 投稿者名（ログ用）
    
    Returns:
        str: 分析結果、または失敗した場合はNone
    """
    try:
        logger.info(f"Analyzing post from {username}")
        
        # プロンプトを作成 - refersパラメータを使用
        prompt = ANALYTICS_PROMPT.format(refers=post_text, analysis="")
        
        # APIを呼び出す
        messages = [{"role": "user", "content": prompt}]
        analysis = call_openai_api(messages)
        
        return analysis
    except Exception as e:
        logger.error(f"Post analysis error: {e}")
        return None

def create_template(analysis, username=""):
    """
    分析結果からテンプレートを作成する関数
    
    Args:
        analysis (str): 分析結果
        username (str): 元の投稿者名（ログ用）
    
    Returns:
        str: 作成されたテンプレート、または失敗した場合はNone
    """
    try:
        logger.info(f"Creating template based on analysis of {username}'s post")
        
        # プロンプトを作成 - refersパラメータも渡す
        prompt = TEMPLATE_PROMPT.format(analysis=analysis, refers="", target="")
        
        # APIを呼び出す
        messages = [{"role": "user", "content": prompt}]
        template = call_openai_api(messages)
        
        return template
    except Exception as e:
        logger.error(f"Template creation error: {e}")
        return None

def create_final_post(template, target, username=""):
    """
    テンプレートから最終投稿を作成する関数
    
    Args:
        template (str): テンプレート
        target (str): ターゲット名
        username (str): 元の投稿者名（ログ用）
    
    Returns:
        str: 作成された最終投稿、または失敗した場合はNone
    """
    try:
        logger.info(f"Creating final post based on template from {username}'s post for target {target}")
        
        # プロンプトを作成 - すべての必要なパラメータを渡す
        prompt = FINAL_POST_PROMPT.format(target=target, template=template, refers="")
        
        # APIを呼び出す
        messages = [{"role": "user", "content": prompt}]
        final_post = call_openai_api(messages)
        
        return final_post
    except Exception as e:
        logger.error(f"Final post creation error: {e}")
        return None

def _process_post(post, targets):
    """
    一つの投稿に対し、全ターゲットの最終投稿を生成する
    
    Args:
        post: (username, post_text, likes) のタプル
        targets: ターゲット名のリスト
    
    Returns:
        list: [(元投稿者名, ターゲット名, 最終投稿), ...] のリスト
    """
    username, post_text, _ = post
    results = []
    
    # 元のポストを分析
    analysis = analyze_post(post_text, username)
    if not analysis:
        logger.warning(f"Failed to analyze post from {username}")
        return results
    
    # テンプレートを作成
    template = create_template(analysis, username)
    if not template:
        logger.warning(f"Failed to create template for {username}'s post")
        return results
    
    # 各ターゲットに対して最終投稿を生成
    for target in targets:
        final_post = create_final_post(template, target, username)
        if final_post:
            results.append((username, target, final_post))
        else:
            logger.warning(f"Failed to generate final post for target {target} from {username}'s post")
    
    return results

def process_posts(posts, targets):
    """
    収集した投稿を処理し、各ターゲット向けの最終投稿を生成する関数
    
    Args:
        posts (list): (username, post_text, likes) のタプルのリスト
        targets (list): ターゲット名のリスト
        
    Returns:
        list: (参考投稿名, ターゲット名, 完成した投稿本文) のタプルのリスト
    """
    final_posts = []
    
    logger.info(f"Processing {len(posts)} posts for {len(targets)} targets")
    
    # 投稿ごとに並行して処理
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 部分関数を作成してターゲットリストを固定
        process_single_post = partial(_process_post, targets=targets)
        
        # 進捗バーを表示しながら処理
        results_iter = executor.map(process_single_post, posts)
        for post_results in tqdm(results_iter, total=len(posts), desc="Processing posts"):
            final_posts.extend(post_results)
    
    logger.info(f"Generated a total of {len(final_posts)} final posts")
    return final_posts